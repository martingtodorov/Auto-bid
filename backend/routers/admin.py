"""
Admin router — CMS / users / stats / reseed.

Scope of this module (extracted from server.py):
  • /admin/settings     GET | PUT    (site-wide CMS / buyer fee tiers)
  • /admin/comments/{id} DELETE       (soft-delete comment + WS broadcast)
  • /admin/stats         GET          (platform KPIs)
  • /admin/users         GET
  • /admin/users/{id}    GET | PUT | DELETE
  • /admin/users/{id}/ban | /unban

Auction lifecycle routes (approve/reject/finalize/capture-premium/remove/restore/extend)
stay in server.py for now because they're tightly coupled with bidding logic.
"""
import logging
import re
from datetime import datetime, timezone, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from deps import db
from models import SiteSettingsUpdate, AdminUserUpdate, StripeSettingsUpdate
from helpers import audit_log, mask_secret, stripe_public_config, stripe_runtime_config

router = APIRouter()
logger = logging.getLogger(__name__)

# --- Injected at startup by server.py.configure() ---
_require_admin = None
_require_admin_or_moderator = None
_settings_fn = None
_load_settings_cache = None
_public_comment = None
_hub = None


def configure(*, require_admin, require_admin_or_moderator, settings_fn, load_settings_cache, public_comment, hub):
    global _require_admin, _require_admin_or_moderator, _settings_fn, _load_settings_cache, _public_comment, _hub
    _require_admin = require_admin
    _require_admin_or_moderator = require_admin_or_moderator
    _settings_fn = settings_fn
    _load_settings_cache = load_settings_cache
    _public_comment = public_comment
    _hub = hub


def register_routes():
    assert _require_admin is not None, "admin router not configured"

    # ---- CMS: settings ----
    @router.get("/admin/settings")
    async def admin_get_settings(_admin: dict = Depends(_require_admin_or_moderator)):
        return _settings_fn()

    @router.put("/admin/settings")
    async def admin_update_settings(request: Request, payload: SiteSettingsUpdate, admin: dict = Depends(_require_admin)):
        update = {k: v for k, v in payload.model_dump().items() if v is not None}
        if not update:
            return _settings_fn()
        if "buyer_fee_pct" in update:
            pct = float(update["buyer_fee_pct"])
            if pct < 0 or pct > 25:
                raise HTTPException(status_code=400, detail="Таксата трябва да е между 0% и 25%")
        if "buyer_fee_min_eur" in update and float(update["buyer_fee_min_eur"]) < 0:
            raise HTTPException(status_code=400, detail="Минималната такса не може да е отрицателна")
        if "buyer_fee_max_eur" in update and float(update["buyer_fee_max_eur"]) < 0:
            raise HTTPException(status_code=400, detail="Максималната такса не може да е отрицателна")

        update["updated_at"] = datetime.now(timezone.utc).isoformat()
        await db.site_settings.update_one(
            {"id": "global"},
            {"$set": update, "$setOnInsert": {"id": "global"}},
            upsert=True,
        )
        await _load_settings_cache()
        await audit_log(db, actor_id=admin["id"], actor_email=admin.get("email", ""), actor_role=admin.get("role", ""),
                        action="settings.update", target_type="site_settings", target_id="global",
                        details={"fields": list(update.keys())}, ip=request.client.host if request.client else "")
        return _settings_fn()

    # ---- Stripe CMS (super-admin only; secret keys masked on GET) ----
    @router.get("/admin/stripe")
    async def admin_get_stripe(_admin: dict = Depends(_require_admin)):
        s = _settings_fn()
        return {
            "mode": s.get("stripe_mode") or "test",
            "stripe_enabled": bool(s.get("stripe_enabled")),
            "stripe_publishable_key_test": s.get("stripe_publishable_key_test") or "",
            "stripe_publishable_key_live": s.get("stripe_publishable_key_live") or "",
            # secrets are masked — never sent in cleartext after save
            "stripe_secret_key_test_masked": mask_secret(s.get("stripe_secret_key_test", "")),
            "stripe_secret_key_live_masked": mask_secret(s.get("stripe_secret_key_live", "")),
            "stripe_webhook_secret_test_masked": mask_secret(s.get("stripe_webhook_secret_test", "")),
            "stripe_webhook_secret_live_masked": mask_secret(s.get("stripe_webhook_secret_live", "")),
            "has_secret_test": bool(s.get("stripe_secret_key_test")),
            "has_secret_live": bool(s.get("stripe_secret_key_live")),
            "has_webhook_test": bool(s.get("stripe_webhook_secret_test")),
            "has_webhook_live": bool(s.get("stripe_webhook_secret_live")),
        }

    @router.put("/admin/stripe")
    async def admin_update_stripe(request: Request, payload: StripeSettingsUpdate, admin: dict = Depends(_require_admin)):
        raw = payload.model_dump()
        # translate frontend keys → storage keys
        update: dict = {}
        if raw.get("mode") is not None:
            if raw["mode"] not in ("test", "live"):
                raise HTTPException(status_code=400, detail="mode трябва да е 'test' или 'live'")
            update["stripe_mode"] = raw["mode"]
        if raw.get("stripe_enabled") is not None:
            update["stripe_enabled"] = bool(raw["stripe_enabled"])
        for k in ("stripe_publishable_key_test", "stripe_publishable_key_live",
                  "stripe_secret_key_test", "stripe_secret_key_live",
                  "stripe_webhook_secret_test", "stripe_webhook_secret_live"):
            v = raw.get(k)
            if v is not None and v.strip():
                update[k] = v.strip()
        if not update:
            raise HTTPException(status_code=400, detail="Няма промени за запазване.")

        # Light format validation
        if "stripe_secret_key_test" in update and not update["stripe_secret_key_test"].startswith("sk_test_"):
            raise HTTPException(status_code=400, detail="Test secret key трябва да започва с sk_test_")
        if "stripe_secret_key_live" in update and not update["stripe_secret_key_live"].startswith("sk_live_"):
            raise HTTPException(status_code=400, detail="Live secret key трябва да започва с sk_live_")
        if "stripe_publishable_key_test" in update and not update["stripe_publishable_key_test"].startswith("pk_test_"):
            raise HTTPException(status_code=400, detail="Test publishable key трябва да започва с pk_test_")
        if "stripe_publishable_key_live" in update and not update["stripe_publishable_key_live"].startswith("pk_live_"):
            raise HTTPException(status_code=400, detail="Live publishable key трябва да започва с pk_live_")

        update["updated_at"] = datetime.now(timezone.utc).isoformat()
        await db.site_settings.update_one({"id": "global"}, {"$set": update, "$setOnInsert": {"id": "global"}}, upsert=True)
        await _load_settings_cache()
        # Audit only field names — NEVER log key values
        await audit_log(db, actor_id=admin["id"], actor_email=admin.get("email", ""), actor_role=admin.get("role", ""),
                        action="stripe.update", target_type="site_settings", target_id="global",
                        details={"fields": list(update.keys())}, ip=request.client.host if request.client else "")
        return {"ok": True, "updated_fields": list(update.keys())}

    # ---- Audit log (admin + moderator read-only) ----
    @router.get("/admin/audit-log")
    async def admin_audit_log(
        limit: int = 100, offset: int = 0,
        action: Optional[str] = None, actor_id: Optional[str] = None, target_id: Optional[str] = None,
        _admin: dict = Depends(_require_admin_or_moderator),
    ):
        limit = max(1, min(500, int(limit)))
        offset = max(0, int(offset))
        query: dict = {}
        if action:
            query["action"] = action
        if actor_id:
            query["actor_id"] = actor_id
        if target_id:
            query["target_id"] = target_id
        total = await db.audit_log.count_documents(query)
        items = await db.audit_log.find(query, {"_id": 0}).sort("at", -1).skip(offset).limit(limit).to_list(limit)
        return {"items": items, "total": total, "offset": offset, "limit": limit}

    # ---- Re-activate a sold / ended / reserve_not_met auction back to live ----
    @router.post("/admin/auctions/{auction_id}/reactivate")
    async def admin_reactivate(auction_id: str, request: Request,
                               days: int = Query(default=7, ge=1, le=60),
                               admin: dict = Depends(_require_admin)):
        """Re-open a closed auction (sold / ended / reserve_not_met / withdrawn / removed) as live.
        Clears sale-completion fields; preserves bid history for reference.
        """
        a = await db.auctions.find_one({"id": auction_id}, {"_id": 0})
        if not a:
            raise HTTPException(status_code=404, detail="Обявата не е намерена")
        if a.get("status") not in ("sold", "ended", "reserve_not_met", "withdrawn", "removed"):
            raise HTTPException(status_code=400, detail=f"Не може да се реактивира обява със статус '{a.get('status')}'")
        now = datetime.now(timezone.utc)
        new_ends = now + timedelta(days=int(days))
        await db.auctions.update_one(
            {"id": auction_id},
            {
                "$set": {"status": "live", "ends_at": new_ends.isoformat(), "reactivated_at": now.isoformat()},
                "$unset": {"finalized_at": "", "premium_captured": "", "removed_at": ""},
            },
        )
        await audit_log(db, actor_id=admin["id"], actor_email=admin.get("email", ""), actor_role=admin.get("role", ""),
                        action="auction.reactivate", target_type="auction", target_id=auction_id,
                        details={"previous_status": a.get("status"), "new_ends_at": new_ends.isoformat(), "days": days},
                        ip=request.client.host if request.client else "")
        return {"ok": True, "status": "live", "ends_at": new_ends.isoformat()}

    # ---- Comments moderation ----
    @router.delete("/admin/comments/{comment_id}")
    async def admin_delete_comment(comment_id: str, request: Request, admin: dict = Depends(_require_admin_or_moderator)):
        c = await db.comments.find_one({"id": comment_id}, {"_id": 0})
        if not c:
            raise HTTPException(status_code=404, detail="Коментарът не е намерен")
        now = datetime.now(timezone.utc).isoformat()
        await db.comments.update_one(
            {"id": comment_id},
            {"$set": {"deleted": True, "deleted_at": now, "deleted_by": admin["id"]}},
        )
        a = await db.auctions.find_one({"id": c["auction_id"]}, {"_id": 0, "seller_id": 1})
        if a:
            updated = {**c, "deleted": True, "deleted_at": now, "deleted_by": admin["id"]}
            public = _public_comment(updated, a)
            await _hub.broadcast(c["auction_id"], {"type": "comment_deleted", "comment": public})
        await audit_log(db, actor_id=admin["id"], actor_email=admin.get("email", ""), actor_role=admin.get("role", ""),
                        action="comment.delete", target_type="comment", target_id=comment_id,
                        details={"auction_id": c["auction_id"]}, ip=request.client.host if request.client else "")
        return {"ok": True}

    # ---- Platform KPIs ----
    @router.get("/admin/stats")
    async def admin_stats(_admin: dict = Depends(_require_admin_or_moderator)):
        now = datetime.now(timezone.utc)
        week_ago = (now - timedelta(days=7)).isoformat()
        month_ago = (now - timedelta(days=30)).isoformat()

        total_auctions = await db.auctions.count_documents({})
        pending = await db.auctions.count_documents({"status": "pending"})
        live_stored = await db.auctions.count_documents({"status": {"$in": ["live", None]}})
        sold_count_s = await db.auctions.count_documents({"status": "sold"})
        removed = await db.auctions.count_documents({"status": {"$in": ["removed", "rejected", "withdrawn"]}})
        reserve_not_met = await db.auctions.count_documents({"status": "reserve_not_met"})

        total_users = await db.users.count_documents({})
        admins = await db.users.count_documents({"role": "admin"})
        verified_dealers = await db.users.count_documents({"is_verified_dealer": True})
        new_users_week = await db.users.count_documents({"created_at": {"$gte": week_ago}})

        total_bids = await db.bids.count_documents({})
        bids_this_week = await db.bids.count_documents({"created_at": {"$gte": week_ago}})

        gmv_cursor = db.auctions.aggregate([
            {"$match": {"status": "sold"}},
            {"$group": {"_id": None, "gmv": {"$sum": "$current_bid_eur"}, "commission": {"$sum": "$premium_amount_eur"}, "count": {"$sum": 1}}},
        ])
        gmv_docs = await gmv_cursor.to_list(1)
        gmv = float(gmv_docs[0]["gmv"]) if gmv_docs else 0.0
        commission = float(gmv_docs[0]["commission"]) if gmv_docs else 0.0
        sold_count = int(gmv_docs[0]["count"]) if gmv_docs else 0

        gmv_month_cursor = db.auctions.aggregate([
            {"$match": {"status": "sold", "finalized_at": {"$gte": month_ago}}},
            {"$group": {"_id": None, "gmv": {"$sum": "$current_bid_eur"}, "commission": {"$sum": "$premium_amount_eur"}}},
        ])
        gmv_month_docs = await gmv_month_cursor.to_list(1)
        gmv_month = float(gmv_month_docs[0]["gmv"]) if gmv_month_docs else 0.0
        commission_month = float(gmv_month_docs[0]["commission"]) if gmv_month_docs else 0.0

        return {
            "auctions": {"total": total_auctions, "pending": pending, "live": live_stored, "sold": sold_count_s, "removed": removed, "reserve_not_met": reserve_not_met},
            "users": {"total": total_users, "admins": admins, "verified_dealers": verified_dealers, "new_this_week": new_users_week},
            "bids": {"total": total_bids, "this_week": bids_this_week},
            "revenue": {"gmv_all_time": gmv, "commission_all_time": commission, "gmv_last_30d": gmv_month, "commission_last_30d": commission_month, "sold_count": sold_count},
        }

    # ---- Users management ----
    @router.get("/admin/users")
    async def admin_list_users(q: Optional[str] = None, _admin: dict = Depends(_require_admin_or_moderator)):
        query: dict = {}
        if q:
            rx = {"$regex": re.escape(q.strip()), "$options": "i"}
            query["$or"] = [{"name": rx}, {"email": rx}, {"phone": rx}]
        items = await db.users.find(query, {"_id": 0, "password_hash": 0}).sort("created_at", -1).limit(500).to_list(500)
        return items

    @router.get("/admin/users/{user_id}")
    async def admin_get_user(user_id: str, _admin: dict = Depends(_require_admin_or_moderator)):
        u = await db.users.find_one({"id": user_id}, {"_id": 0, "password_hash": 0})
        if not u:
            raise HTTPException(status_code=404, detail="Потребителят не е намерен")
        return u

    @router.put("/admin/users/{user_id}")
    async def admin_update_user(user_id: str, payload: AdminUserUpdate, admin_user: dict = Depends(_require_admin)):
        u = await db.users.find_one({"id": user_id}, {"_id": 0})
        if not u:
            raise HTTPException(status_code=404, detail="Потребителят не е намерен")
        update: dict = {}
        if payload.name is not None:
            update["name"] = payload.name.strip()
        if payload.email is not None:
            new_email = payload.email.lower().strip()
            if new_email != u["email"]:
                existing = await db.users.find_one({"email": new_email, "id": {"$ne": user_id}})
                if existing:
                    raise HTTPException(status_code=400, detail="Имейлът вече се използва от друг потребител")
                update["email"] = new_email
        if payload.phone is not None:
            phone = payload.phone.strip()
            if phone and not phone.startswith("+"):
                raise HTTPException(status_code=400, detail="Телефонът трябва да е в международен формат (+359...)")
            update["phone"] = phone
        if payload.is_verified_dealer is not None:
            update["is_verified_dealer"] = bool(payload.is_verified_dealer)
        if payload.role is not None:
            if payload.role not in ("user", "admin", "moderator"):
                raise HTTPException(status_code=400, detail="Невалидна роля")
            if user_id == admin_user["id"] and payload.role != "admin":
                raise HTTPException(status_code=400, detail="Не можете да смените собствената си роля")
            update["role"] = payload.role

        if update:
            await db.users.update_one({"id": user_id}, {"$set": update})
            if "name" in update:
                await db.auctions.update_many({"seller_id": user_id}, {"$set": {"seller_name": update["name"]}})

        fresh = await db.users.find_one({"id": user_id}, {"_id": 0, "password_hash": 0})
        return {"ok": True, "user": fresh}

    @router.post("/admin/users/{user_id}/ban")
    async def admin_ban_user(user_id: str, admin_user: dict = Depends(_require_admin)):
        if user_id == admin_user["id"]:
            raise HTTPException(status_code=400, detail="Не можете да блокирате собствения си акаунт")
        u = await db.users.find_one({"id": user_id}, {"_id": 0})
        if not u:
            raise HTTPException(status_code=404, detail="Потребителят не е намерен")
        if u.get("role") in ("admin", "moderator"):
            raise HTTPException(status_code=400, detail="Не можете да блокирате друг служител на платформата")
        now = datetime.now(timezone.utc).isoformat()
        await db.users.update_one({"id": user_id}, {"$set": {"banned": True, "banned_at": now, "banned_by": admin_user["id"]}})
        await audit_log(db, actor_id=admin_user["id"], actor_email=admin_user.get("email", ""), actor_role=admin_user.get("role", ""),
                        action="user.ban", target_type="user", target_id=user_id, details={})
        return {"ok": True, "banned": True}

    @router.post("/admin/users/{user_id}/unban")
    async def admin_unban_user(user_id: str, _admin: dict = Depends(_require_admin)):
        u = await db.users.find_one({"id": user_id}, {"_id": 0})
        if not u:
            raise HTTPException(status_code=404, detail="Потребителят не е намерен")
        await db.users.update_one({"id": user_id}, {"$set": {"banned": False}, "$unset": {"banned_at": "", "banned_by": ""}})
        return {"ok": True, "banned": False}

    @router.delete("/admin/users/{user_id}")
    async def admin_delete_user(user_id: str, admin_user: dict = Depends(_require_admin)):
        if user_id == admin_user["id"]:
            raise HTTPException(status_code=400, detail="Не можете да изтриете собствения си акаунт")
        u = await db.users.find_one({"id": user_id}, {"_id": 0})
        if not u:
            raise HTTPException(status_code=404, detail="Потребителят не е намерен")
        if u.get("role") in ("admin", "moderator"):
            raise HTTPException(status_code=400, detail="Не можете да изтриете друг служител на платформата")

        bids = await db.bids.delete_many({"user_id": user_id})
        comments = await db.comments.delete_many({"user_id": user_id})
        watches = await db.watches.delete_many({"user_id": user_id})
        saved = await db.saved_searches.delete_many({"user_id": user_id})
        credits = await db.bidding_credits.delete_many({"user_id": user_id})
        anon = await db.auctions.update_many(
            {"seller_id": user_id},
            {"$set": {"seller_name": "Изтрит потребител", "seller_id": "deleted"}},
        )
        hb = await db.auctions.update_many(
            {"high_bidder_id": user_id},
            {"$set": {"high_bidder_id": None, "high_bidder_name": None}},
        )
        await db.users.delete_one({"id": user_id})
        return {
            "ok": True,
            "deleted": {
                "user": 1,
                "bids": bids.deleted_count,
                "comments": comments.deleted_count,
                "watches": watches.deleted_count,
                "saved_searches": saved.deleted_count,
                "bidding_credits": credits.deleted_count,
                "auctions_anonymized": anon.modified_count,
                "bidder_references_cleared": hb.modified_count,
            },
        }
