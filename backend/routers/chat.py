"""Two-way chat between admins/moderators and end users.

Each "thread" is keyed by the end user's id (`thread_user_id`). Admins
share a single thread per user — any admin can read and reply, and the
user sees all admin replies as one conversation with "Поддръжка".

Mongo collection `chat_messages`:
  - id (uuid)
  - thread_user_id (str, user.id of the customer)
  - sender_id (str)
  - sender_role ("admin" | "user")
  - sender_name (str)
  - body (str, ≤ 4000 chars)
  - created_at (iso str)
  - read_by_user (bool)   — for messages where sender_role == "admin"
  - read_by_admin (bool)  — for messages where sender_role == "user"

Side effects on send:
  - admin → user: notify_user inbox + web push to the customer
  - user  → admin: notify_admins inbox (admins can refresh chat panel)

Rate limiting: chat endpoints are rate-limited to prevent spam (a malicious
user could otherwise hammer admins; admins themselves are trusted but the
limit also stops a stuck UI from saturating Mongo).
"""
from __future__ import annotations
from datetime import datetime, timezone
from typing import Optional, List
import uuid

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class SendMessageBody(BaseModel):
    body: str = Field(..., min_length=1, max_length=4000)


def build_chat_router(db, get_current_user, require_admin_or_moderator, limiter=None):
    router = APIRouter(prefix="/api", tags=["chat"])

    # Use the central app limiter when supplied; fall back to a no-op so the
    # decorators stay valid in unit tests / standalone usage.
    if limiter is None:
        from slowapi import Limiter
        from slowapi.util import get_remote_address
        limiter = Limiter(key_func=get_remote_address)
    _chat_limiter = limiter

    # ---------- USER side ----------

    @router.get("/me/chat/messages")
    async def my_chat_messages(limit: int = 200, user: dict = Depends(get_current_user)):
        limit = max(1, min(500, int(limit)))
        items = (
            await db.chat_messages.find(
                {"thread_user_id": user["id"]}, {"_id": 0}
            )
            .sort("created_at", 1)
            .to_list(limit)
        )
        unread = await db.chat_messages.count_documents(
            {"thread_user_id": user["id"], "sender_role": "admin", "read_by_user": False}
        )
        return {"items": items, "unread": int(unread)}

    @router.get("/me/chat/unread-count")
    async def my_chat_unread(user: dict = Depends(get_current_user)):
        n = await db.chat_messages.count_documents(
            {"thread_user_id": user["id"], "sender_role": "admin", "read_by_user": False}
        )
        return {"unread": int(n)}

    @router.post("/me/chat/messages")
    @_chat_limiter.limit("20/minute")
    async def my_chat_send(request: Request, payload: SendMessageBody, user: dict = Depends(get_current_user)):
        body_clean = payload.body.strip()
        if not body_clean:
            raise HTTPException(status_code=400, detail="Празно съобщение")
        msg = {
            "id": str(uuid.uuid4()),
            "thread_user_id": user["id"],
            "sender_id": user["id"],
            "sender_role": "user",
            "sender_name": user.get("name") or user.get("email", "Потребител"),
            "body": body_clean[:4000],
            "created_at": _now_iso(),
            "read_by_user": True,
            "read_by_admin": False,
        }
        await db.chat_messages.insert_one(msg)

        # Fan out an inbox notification to every admin/moderator so they can
        # see in their bell that a customer has replied.
        try:
            from routers.inbox import notify_admins
            await notify_admins(
                db,
                type="chat_user_message",
                title="Ново съобщение от потребител",
                body=f"{msg['sender_name']}: {body_clean[:120]}",
                data={"thread_user_id": user["id"], "preview": body_clean[:120]},
                link="/admin?tab=chat",
            )
        except Exception:
            pass

        msg.pop("_id", None)
        return msg

    @router.post("/me/chat/read")
    async def my_chat_mark_read(user: dict = Depends(get_current_user)):
        result = await db.chat_messages.update_many(
            {
                "thread_user_id": user["id"],
                "sender_role": "admin",
                "read_by_user": False,
            },
            {"$set": {"read_by_user": True}},
        )
        return {"ok": True, "updated": result.modified_count}

    # ---------- ADMIN side ----------

    @router.get("/admin/chat/threads")
    async def admin_list_threads(_admin: dict = Depends(require_admin_or_moderator)):
        # Group by thread_user_id, get last message + unread counts.
        pipeline = [
            {"$sort": {"created_at": -1}},
            {
                "$group": {
                    "_id": "$thread_user_id",
                    "last_message": {"$first": "$body"},
                    "last_at": {"$first": "$created_at"},
                    "last_role": {"$first": "$sender_role"},
                    "unread_for_admin": {
                        "$sum": {
                            "$cond": [
                                {"$and": [
                                    {"$eq": ["$sender_role", "user"]},
                                    {"$eq": ["$read_by_admin", False]},
                                ]},
                                1, 0,
                            ]
                        }
                    },
                    "total": {"$sum": 1},
                }
            },
            {"$sort": {"last_at": -1}},
            {"$limit": 500},
        ]
        threads = await db.chat_messages.aggregate(pipeline).to_list(500)

        # Hydrate with user info.
        user_ids = [t["_id"] for t in threads]
        users_map = {}
        if user_ids:
            async for u in db.users.find(
                {"id": {"$in": user_ids}},
                {"_id": 0, "id": 1, "name": 1, "email": 1, "role": 1},
            ):
                users_map[u["id"]] = u

        out = []
        for t in threads:
            uid = t["_id"]
            u = users_map.get(uid, {})
            out.append({
                "thread_user_id": uid,
                "user_name": u.get("name") or u.get("email", "?"),
                "user_email": u.get("email"),
                "user_role": u.get("role"),
                "last_message": t.get("last_message", "")[:200],
                "last_at": t.get("last_at"),
                "last_role": t.get("last_role"),
                "unread_for_admin": int(t.get("unread_for_admin", 0)),
                "total": int(t.get("total", 0)),
            })
        return {"items": out}

    @router.get("/admin/chat/unread-count")
    async def admin_chat_unread(_admin: dict = Depends(require_admin_or_moderator)):
        n = await db.chat_messages.count_documents(
            {"sender_role": "user", "read_by_admin": False}
        )
        return {"unread": int(n)}

    @router.get("/admin/chat/threads/{user_id}/messages")
    async def admin_thread_messages(user_id: str, limit: int = 500,
                                    _admin: dict = Depends(require_admin_or_moderator)):
        limit = max(1, min(1000, int(limit)))
        items = (
            await db.chat_messages.find(
                {"thread_user_id": user_id}, {"_id": 0}
            )
            .sort("created_at", 1)
            .to_list(limit)
        )
        # Find user info for header.
        u = await db.users.find_one(
            {"id": user_id},
            {"_id": 0, "id": 1, "name": 1, "email": 1, "role": 1},
        ) or {}
        return {"items": items, "user": u}

    @router.post("/admin/chat/threads/{user_id}/messages")
    @_chat_limiter.limit("60/minute")
    async def admin_thread_send(request: Request, user_id: str, payload: SendMessageBody,
                                admin: dict = Depends(require_admin_or_moderator)):
        # Verify the recipient exists.
        recipient = await db.users.find_one({"id": user_id}, {"_id": 0, "id": 1, "name": 1, "email": 1})
        if not recipient:
            raise HTTPException(status_code=404, detail="Потребителят не е намерен")

        body_clean = payload.body.strip()
        if not body_clean:
            raise HTTPException(status_code=400, detail="Празно съобщение")

        msg = {
            "id": str(uuid.uuid4()),
            "thread_user_id": user_id,
            "sender_id": admin["id"],
            "sender_role": "admin",
            "sender_name": admin.get("name") or "Поддръжка",
            "body": body_clean[:4000],
            "created_at": _now_iso(),
            "read_by_user": False,
            "read_by_admin": True,
        }
        await db.chat_messages.insert_one(msg)

        # Inbox + push to customer.
        try:
            from routers.inbox import notify_user
            await notify_user(
                db,
                user_id=user_id,
                type="chat_admin_message",
                title="Ново съобщение от поддръжка",
                body=body_clean[:200],
                data={"preview": body_clean[:200]},
                link="/inbox",
            )
        except Exception:
            pass
        try:
            from services import push_templates
            await push_templates.send_template(
                user_id,
                "chat_admin_message",
                fmt_args={"preview": body_clean[:140]},
                url="/inbox",
                tag="chat",
            )
        except Exception:
            pass

        msg.pop("_id", None)
        return msg

    @router.post("/admin/chat/threads/{user_id}/read")
    async def admin_thread_mark_read(user_id: str,
                                     _admin: dict = Depends(require_admin_or_moderator)):
        result = await db.chat_messages.update_many(
            {
                "thread_user_id": user_id,
                "sender_role": "user",
                "read_by_admin": False,
            },
            {"$set": {"read_by_admin": True}},
        )
        return {"ok": True, "updated": result.modified_count}

    return router
