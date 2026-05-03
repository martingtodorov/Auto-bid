"""
Seller-initiated requests:
  • POST   /auctions/{id}/request-promotion          — ask moderators to feature this auction
  • POST   /auctions/{id}/request-text-change        — ask moderators to edit title/description
  • PATCH  /auctions/{id}/reorder-images             — seller reorders photos (no approval needed)
  • GET    /me/seller-requests                       — my pending/decided requests
  • GET    /admin/seller-requests                    — moderator queue (filter by status/type)
  • POST   /admin/seller-requests/{id}/approve       — apply change + mark done
  • POST   /admin/seller-requests/{id}/reject        — reject with reason

Collection: `seller_requests`
  { id, auction_id, auction_title, seller_id, seller_name, type,
    payload: {title?, description?, note?},
    status: "pending" | "approved" | "rejected",
    created_at, decided_at?, decided_by?, decision_reason? }
"""
import logging
import uuid as _uuid
from datetime import datetime, timezone
from typing import Optional, List

from fastapi import APIRouter, Depends, HTTPException, Request, Query

from deps import db
from models import PromotionRequestCreate, TextChangeRequestCreate, ReorderImagesRequest, ModerationDecision
from helpers import audit_log

router = APIRouter()
logger = logging.getLogger(__name__)

# Dependency injection
_get_current_user = None
_require_admin_or_moderator = None


def configure(*, get_current_user, require_admin_or_moderator):
    global _get_current_user, _require_admin_or_moderator
    _get_current_user = get_current_user
    _require_admin_or_moderator = require_admin_or_moderator


async def _load_auction_for_seller(auction_id: str, user: dict) -> dict:
    a = await db.auctions.find_one({"id": auction_id}, {"_id": 0})
    if not a:
        raise HTTPException(status_code=404, detail="Обявата не е намерена")
    if a.get("seller_id") != user["id"] and user.get("role") not in ("admin", "moderator"):
        raise HTTPException(status_code=403, detail="Нямате достъп до тази обява")
    return a


def register_routes():
    assert _get_current_user is not None, "seller_requests router not configured"

    # ------------------------------------------------------------------
    # 1) Seller reorders photos on own auction — no approval required
    # ------------------------------------------------------------------
    @router.patch("/auctions/{auction_id}/reorder-images")
    async def reorder_images(auction_id: str, payload: ReorderImagesRequest, request: Request,
                             user: dict = Depends(_get_current_user)):
        a = await _load_auction_for_seller(auction_id, user)
        existing = list(a.get("images") or [])
        new_order = [s for s in (payload.images or []) if isinstance(s, str)]
        if not new_order:
            raise HTTPException(status_code=400, detail="Списъкът със снимки не може да е празен")
        # Security: every new image must be one of the existing images — no add/remove via reorder
        if sorted(new_order) != sorted(existing):
            raise HTTPException(
                status_code=400,
                detail="Само пренареждане е разрешено. Използвайте редактиране за добавяне/премахване на снимки.",
            )
        await db.auctions.update_one({"id": auction_id}, {"$set": {
            "images": new_order,
            "images_reordered_at": datetime.now(timezone.utc).isoformat(),
        }})
        await audit_log(
            db, actor_id=user["id"], actor_email=user.get("email", ""), actor_role=user.get("role", "user"),
            action="auction.images_reorder", target_type="auction", target_id=auction_id,
            details={"count": len(new_order)}, ip=request.client.host if request.client else "",
            user_agent=request.headers.get("user-agent", ""),
        )
        return {"ok": True, "images": new_order}

    # ------------------------------------------------------------------
    # 2) Seller requests promotion — REMOVED.
    # Promotion is now self-serve via `/api/auctions/{id}/promote/checkout`
    # (Stripe €30) and `/promote/finalize`. See server.py.
    # ------------------------------------------------------------------

    # ------------------------------------------------------------------
    # 3) Seller requests text change on live/pending auction
    # ------------------------------------------------------------------
    @router.post("/auctions/{auction_id}/request-text-change")
    async def request_text_change(auction_id: str, payload: TextChangeRequestCreate, request: Request,
                                  user: dict = Depends(_get_current_user)):
        a = await _load_auction_for_seller(auction_id, user)
        if a.get("status") not in ("pending", "live", "paused"):
            raise HTTPException(status_code=400, detail="Заявки за промяна са позволени само за активни/очакващи обяви.")
        if not (payload.title or payload.description):
            raise HTTPException(status_code=400, detail="Въведете ново заглавие или описание.")
        existing = await db.seller_requests.find_one(
            {"auction_id": auction_id, "type": "text_change", "status": "pending"}, {"_id": 0, "id": 1},
        )
        if existing:
            raise HTTPException(status_code=409, detail="Имате чакаща заявка за промяна. Изчакайте модератор или я оттеглете.")
        doc = {
            "id": _uuid.uuid4().hex,
            "auction_id": auction_id,
            "auction_title": a.get("title", ""),
            "seller_id": user["id"],
            "seller_name": user.get("name", ""),
            "type": "text_change",
            "payload": {
                "title": (payload.title or "").strip()[:200] if payload.title else None,
                "description": (payload.description or "").strip()[:8000] if payload.description else None,
                "note": (payload.note or "").strip()[:600],
                "current_title": a.get("title", ""),
                "current_description": a.get("description", ""),
            },
            "status": "pending",
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        await db.seller_requests.insert_one(doc)
        doc.pop("_id", None)
        try:
            from routers.inbox import notify_admins as _notify_admins
            await _notify_admins(
                db, type="text_change_request",
                data={"seller": user.get("name", ""), "title": a.get("title", "")},
                auction_id=auction_id,
                link="/admin?tab=requests",
                push_template_id="admin_text_change_request",
                push_fmt={"seller": (user.get("name") or "Продавач")[:60], "title": (a.get("title") or "")[:80]},
            )
        except Exception:
            pass
        await audit_log(
            db, actor_id=user["id"], actor_email=user.get("email", ""), actor_role=user.get("role", "user"),
            action="seller_request.create", target_type="auction", target_id=auction_id,
            details={"type": "text_change"}, ip=request.client.host if request.client else "",
            user_agent=request.headers.get("user-agent", ""),
        )
        return doc

    # ------------------------------------------------------------------
    # 4) Seller — my requests
    # ------------------------------------------------------------------
    @router.get("/me/seller-requests")
    async def my_requests(status: Optional[str] = None, user: dict = Depends(_get_current_user)):
        q: dict = {"seller_id": user["id"]}
        if status:
            q["status"] = status
        items = await db.seller_requests.find(q, {"_id": 0}).sort("created_at", -1).limit(100).to_list(100)
        return items

    @router.delete("/me/seller-requests/{req_id}")
    async def cancel_request(req_id: str, user: dict = Depends(_get_current_user)):
        r = await db.seller_requests.find_one({"id": req_id}, {"_id": 0})
        if not r:
            raise HTTPException(status_code=404, detail="Заявката не е намерена")
        if r["seller_id"] != user["id"] and user.get("role") not in ("admin", "moderator"):
            raise HTTPException(status_code=403, detail="Нямате достъп до тази заявка")
        if r["status"] != "pending":
            raise HTTPException(status_code=400, detail="Само чакащи заявки могат да бъдат оттеглени")
        await db.seller_requests.update_one({"id": req_id}, {"$set": {
            "status": "cancelled", "decided_at": datetime.now(timezone.utc).isoformat(),
        }})
        return {"ok": True}

    # ------------------------------------------------------------------
    # 5) Admin/Moderator — list + approve + reject
    # ------------------------------------------------------------------
    @router.get("/admin/seller-requests")
    async def admin_list_requests(
        status: Optional[str] = None, type: Optional[str] = None,
        limit: int = Query(default=100, ge=1, le=500),
        _admin: dict = Depends(_require_admin_or_moderator),
    ):
        q: dict = {}
        if status:
            q["status"] = status
        if type:
            q["type"] = type
        items = await db.seller_requests.find(q, {"_id": 0}).sort("created_at", -1).limit(limit).to_list(limit)
        return items

    @router.post("/admin/seller-requests/{req_id}/approve")
    async def admin_approve_request(req_id: str, payload: ModerationDecision, request: Request,
                                    admin: dict = Depends(_require_admin_or_moderator)):
        r = await db.seller_requests.find_one({"id": req_id}, {"_id": 0})
        if not r:
            raise HTTPException(status_code=404, detail="Заявката не е намерена")
        if r["status"] != "pending":
            raise HTTPException(status_code=400, detail="Заявката вече е обработена")

        auction_id = r["auction_id"]
        a = await db.auctions.find_one({"id": auction_id}, {"_id": 0, "id": 1, "status": 1})
        if not a:
            raise HTTPException(status_code=404, detail="Обявата вече не съществува")

        now = datetime.now(timezone.utc).isoformat()
        applied: dict = {}

        if r["type"] == "promotion":
            await db.auctions.update_one({"id": auction_id}, {"$set": {"featured": True, "featured_at": now}})
            applied["featured"] = True
        elif r["type"] == "text_change":
            update: dict = {}
            p = r.get("payload") or {}
            if p.get("title"):
                update["title"] = p["title"]
            if p.get("description"):
                update["description"] = p["description"]
                # Invalidate cached translations when source description changes
                update["description_ro"] = ""
                update["description_en"] = ""
            # Допуска admin да приложи манУални преводи едновременно с
            # одобрението (override на любой auto-translate).  ModerationDecision
            # вече има `description_ro` / `description_en` опционални полета.
            if payload and payload.description_ro is not None:
                update["description_ro"] = (payload.description_ro or "").strip()
            if payload and payload.description_en is not None:
                update["description_en"] = (payload.description_en or "").strip()
            if update:
                await db.auctions.update_one({"id": auction_id}, {"$set": update})
            applied = update
        else:
            raise HTTPException(status_code=400, detail=f"Непознат тип заявка: {r['type']}")

        await db.seller_requests.update_one({"id": req_id}, {"$set": {
            "status": "approved", "decided_at": now, "decided_by": admin["id"],
            "decision_reason": (payload.reason or "").strip()[:500] if payload else "",
            "applied": applied,
        }})
        await audit_log(
            db, actor_id=admin["id"], actor_email=admin.get("email", ""), actor_role=admin.get("role", ""),
            action=f"seller_request.approve.{r['type']}", target_type="auction", target_id=auction_id,
            details={"request_id": req_id, "applied": list(applied.keys()) if isinstance(applied, dict) else []},
            ip=request.client.host if request.client else "",
            user_agent=request.headers.get("user-agent", ""),
        )
        return {"ok": True, "status": "approved", "applied": applied}

    @router.post("/admin/seller-requests/{req_id}/reject")
    async def admin_reject_request(req_id: str, payload: ModerationDecision, request: Request,
                                   admin: dict = Depends(_require_admin_or_moderator)):
        r = await db.seller_requests.find_one({"id": req_id}, {"_id": 0})
        if not r:
            raise HTTPException(status_code=404, detail="Заявката не е намерена")
        if r["status"] != "pending":
            raise HTTPException(status_code=400, detail="Заявката вече е обработена")
        if not (payload.reason and payload.reason.strip()):
            raise HTTPException(status_code=400, detail="Въведете причина за отказ (мин. 3 символа).")
        now = datetime.now(timezone.utc).isoformat()
        await db.seller_requests.update_one({"id": req_id}, {"$set": {
            "status": "rejected", "decided_at": now, "decided_by": admin["id"],
            "decision_reason": payload.reason.strip()[:500],
        }})
        await audit_log(
            db, actor_id=admin["id"], actor_email=admin.get("email", ""), actor_role=admin.get("role", ""),
            action=f"seller_request.reject.{r['type']}", target_type="auction", target_id=r["auction_id"],
            details={"request_id": req_id, "reason": payload.reason.strip()[:200]},
            ip=request.client.host if request.client else "",
            user_agent=request.headers.get("user-agent", ""),
        )
        return {"ok": True, "status": "rejected"}
