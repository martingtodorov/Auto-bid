"""In-app notifications (inbox) — durable per-user message log.

Persists to Mongo collection `user_notifications`. Each notification carries:
  - id (uuid)
  - user_id (recipient)
  - type (free-form bucket: "outbid", "won", "lost", "listing_approved", ...)
  - title, body
  - auction_id (optional — if set, frontend deep-links here)
  - link (optional explicit URL override)
  - read (bool), read_at (iso)
  - created_at (iso)
"""
from __future__ import annotations
from datetime import datetime, timezone
from typing import Optional, List
import uuid
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel


def build_inbox_router(db, get_current_user):
    router = APIRouter(prefix="/api", tags=["inbox"])

    class MarkReadBody(BaseModel):
        ids: Optional[List[str]] = None

    @router.get("/inbox")
    async def list_inbox(limit: int = 50, offset: int = 0, user: dict = Depends(get_current_user)):
        limit = max(1, min(200, int(limit)))
        offset = max(0, int(offset))
        q = {"user_id": user["id"]}
        total = await db.user_notifications.count_documents(q)
        unread = await db.user_notifications.count_documents({**q, "read": False})
        items = (
            await db.user_notifications.find(q, {"_id": 0})
            .sort("created_at", -1)
            .skip(offset)
            .limit(limit)
            .to_list(limit)
        )
        return {"items": items, "total": total, "unread": unread, "offset": offset, "limit": limit}

    @router.get("/inbox/unread-count")
    async def unread_count(user: dict = Depends(get_current_user)):
        n = await db.user_notifications.count_documents({"user_id": user["id"], "read": False})
        return {"unread": int(n)}

    @router.post("/inbox/mark-read")
    async def mark_read(payload: MarkReadBody, user: dict = Depends(get_current_user)):
        ids = payload.ids or []
        if not ids:
            raise HTTPException(status_code=400, detail="ids[] is required")
        now = datetime.now(timezone.utc).isoformat()
        result = await db.user_notifications.update_many(
            {"user_id": user["id"], "id": {"$in": ids}, "read": False},
            {"$set": {"read": True, "read_at": now}},
        )
        return {"ok": True, "updated": result.modified_count}

    @router.post("/inbox/mark-all-read")
    async def mark_all_read(user: dict = Depends(get_current_user)):
        now = datetime.now(timezone.utc).isoformat()
        result = await db.user_notifications.update_many(
            {"user_id": user["id"], "read": False},
            {"$set": {"read": True, "read_at": now}},
        )
        return {"ok": True, "updated": result.modified_count}

    return router


async def notify_user(db, *, user_id: str, type: str, title: str = "", body: str = "",
                      data: Optional[dict] = None,
                      auction_id: Optional[str] = None, link: Optional[str] = None,
                      push_template_id: Optional[str] = None,
                      push_fmt: Optional[dict] = None,
                      push_kind: Optional[str] = None) -> str:
    """Emit a single in-app notification. Returns the notification id.
    `data` carries placeholder args (e.g. {"car": "BMW", "amount": 23000}) that
    the frontend interpolates into a translated `notifications.types.{type}.{title|body}` key.

    If `push_template_id` is given, ALSO dispatch a Web Push notification
    using that template. Respects the user's `notification_prefs.push.<push_kind>`
    flag (defaults to enabled). Admins/moderators always receive the push —
    operational alerts cannot be muted.
    """
    nid = str(uuid.uuid4())
    doc = {
        "id": nid,
        "user_id": user_id,
        "type": type,
        "title": title[:200],
        "body": body[:1000],
        "data": data or {},
        "auction_id": auction_id,
        "link": link or (f"/auctions/{auction_id}" if auction_id else None),
        "read": False,
        "read_at": None,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.user_notifications.insert_one(doc)

    # Optional Web Push dispatch. Wrapped so a push failure never breaks the
    # in-app notification write above.
    if push_template_id:
        try:
            user = await db.users.find_one({"id": user_id}, {"_id": 0, "role": 1, "notification_prefs": 1})
            role = (user or {}).get("role", "user")
            # Admins/mods always receive; user opt-out only applies to the
            # `user` role and only if a `push_kind` is supplied.
            allowed = True
            if role == "user" and push_kind:
                prefs = (user or {}).get("notification_prefs") or {}
                push_prefs = prefs.get("push") or {}
                # Default: enabled. Only explicit `false` disables.
                if push_prefs.get(push_kind) is False:
                    allowed = False
            if allowed:
                from services import push_templates as _pt
                await _pt.send_template(
                    user_id,
                    push_template_id,
                    fmt_args=push_fmt or {},
                    url=doc.get("link") or "/",
                    tag=f"{type}:{auction_id or nid}",
                )
        except Exception:
            pass
    return nid


async def notify_admins(db, *, type: str, title: str = "", body: str = "",
                        data: Optional[dict] = None,
                        auction_id: Optional[str] = None, link: Optional[str] = None,
                        push_template_id: Optional[str] = None,
                        push_fmt: Optional[dict] = None) -> int:
    """Fan out one notification to every admin & moderator. Returns count fanned out.

    If `push_template_id` is supplied, each admin ALSO receives a localized
    Web Push — admins have no opt-out for operational alerts.
    """
    cursor = db.users.find({"role": {"$in": ["admin", "moderator"]}}, {"_id": 0, "id": 1})
    count = 0
    async for u in cursor:
        try:
            await notify_user(db, user_id=u["id"], type=type, title=title, body=body, data=data,
                              auction_id=auction_id, link=link,
                              push_template_id=push_template_id, push_fmt=push_fmt)
            count += 1
        except Exception:
            pass
    return count
