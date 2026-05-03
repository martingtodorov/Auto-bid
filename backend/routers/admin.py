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
from services import bidding as bidding_svc
from models import SiteSettingsUpdate, AdminUserUpdate, StripeSettingsUpdate, MakeCreate, CancelReason, InvalidateBidRequest, BlockBidderRequest, InternalNote, BuyerFeeUpdate
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

    @router.get("/admin/audit-log/export")
    async def admin_audit_log_export(
        action: Optional[str] = None, actor_id: Optional[str] = None,
        target_id: Optional[str] = None, since: Optional[str] = None, until: Optional[str] = None,
        admin: dict = Depends(_require_admin_or_moderator),
    ):
        """Export audit-log записите като CSV.  Възприема същите филтри като
        `/admin/audit-log` + опционални `since`/`until` (ISO timestamp)
        за date-range export.  Връща streaming CSV отговор.
        """
        import csv as _csv
        import io as _io
        from fastapi.responses import StreamingResponse
        query: dict = {}
        if action: query["action"] = action
        if actor_id: query["actor_id"] = actor_id
        if target_id: query["target_id"] = target_id
        if since or until:
            at_q = {}
            if since: at_q["$gte"] = since
            if until: at_q["$lte"] = until
            query["at"] = at_q

        # Pull with reasonable cap (50k rows) — много по-голям export трябва
        # да минава през scheduled job или Mongo native export.
        cursor = db.audit_log.find(query, {"_id": 0}).sort("at", -1).limit(50000)
        rows = await cursor.to_list(50000)

        async def _gen():
            buf = _io.StringIO()
            w = _csv.writer(buf, quoting=_csv.QUOTE_ALL)
            w.writerow(["at", "actor_id", "actor_email", "actor_role", "action",
                        "target_id", "target_type", "ip", "user_agent", "details"])
            yield buf.getvalue(); buf.seek(0); buf.truncate(0)
            for r in rows:
                details = r.get("details") or {}
                if isinstance(details, (dict, list)):
                    import json as _json
                    details_str = _json.dumps(details, ensure_ascii=False, default=str)
                else:
                    details_str = str(details)
                w.writerow([
                    r.get("at", ""), r.get("actor_id", ""), r.get("actor_email", ""),
                    r.get("actor_role", ""), r.get("action", ""),
                    r.get("target_id", ""), r.get("target_type", ""),
                    r.get("ip", ""), r.get("user_agent", "")[:300], details_str[:2000],
                ])
                yield buf.getvalue(); buf.seek(0); buf.truncate(0)

        ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        await audit_log(db, actor_id=admin["id"], actor_email=admin.get("email", ""),
                        actor_role=admin.get("role", ""),
                        action="audit_log.export",
                        target_id=None, target_type="audit_log",
                        details={"rows": len(rows), "filters": {k: v for k, v in query.items()}})
        return StreamingResponse(
            _gen(),
            media_type="text/csv; charset=utf-8",
            headers={"Content-Disposition": f'attachment; filename="audit_log_{ts}.csv"'},
        )

    @router.delete("/admin/audit-log")
    async def admin_audit_log_purge(
        before: Optional[str] = None,
        action: Optional[str] = None, actor_id: Optional[str] = None,
        target_id: Optional[str] = None,
        confirm: str = Query(default=""),
        admin: dict = Depends(_require_admin),
    ):
        """Изтрива audit-log записи (само admin, не модератор).

        Параметри:
          - `before` (ISO timestamp) — изтрива записи < тази дата
          - `action`, `actor_id`, `target_id` — допълнителни филтри
          - `confirm` ТРЯБВА да е "DELETE" за да премине

        Изтриването се *самó-логва* като нов audit запис, за да остане
        проследимо кой и кога е почистил историята.
        """
        if confirm != "DELETE":
            raise HTTPException(status_code=400, detail="Очаквам confirm=DELETE за изтриване")
        query: dict = {}
        if before:
            query["at"] = {"$lt": before}
        if action: query["action"] = action
        if actor_id: query["actor_id"] = actor_id
        if target_id: query["target_id"] = target_id
        if not query:
            raise HTTPException(status_code=400, detail="Поне един филтър е задължителен (before/action/actor_id/target_id)")
        # Брой преди изтриване (за audit info)
        will_delete = await db.audit_log.count_documents(query)
        result = await db.audit_log.delete_many(query)
        await audit_log(db, actor_id=admin["id"], actor_email=admin.get("email", ""),
                        actor_role=admin.get("role", ""),
                        action="audit_log.purge",
                        target_id=None, target_type="audit_log",
                        details={"deleted": result.deleted_count, "filters": query, "matched": will_delete})
        return {"ok": True, "deleted": result.deleted_count}

    @router.delete("/admin/audit-log/{entry_id}")
    async def admin_audit_log_delete_one(
        entry_id: str, admin: dict = Depends(_require_admin),
    ):
        """Изтрива един audit запис по `id`."""
        # Audit-log записите използват `id` (UUID) поле
        existing = await db.audit_log.find_one({"id": entry_id}, {"_id": 0, "action": 1})
        if not existing:
            raise HTTPException(status_code=404, detail="Записът не е намерен")
        await db.audit_log.delete_one({"id": entry_id})
        await audit_log(db, actor_id=admin["id"], actor_email=admin.get("email", ""),
                        actor_role=admin.get("role", ""),
                        action="audit_log.delete_one",
                        target_id=entry_id, target_type="audit_log",
                        details={"deleted_action": existing.get("action")})
        return {"ok": True}

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

        total_bids = await bidding_svc.count_bids()
        bids_this_week = await bidding_svc.count_bids(since=datetime.fromisoformat(week_ago) if isinstance(week_ago, str) else week_ago)

        # Commission = sum(`premium_amount_eur`) when admin captured it via
        # /capture-premium, else fall back to 2 % of the winning bid so that
        # auctions finalized via the "release-only" path (admin_finalize)
        # still contribute to the expected-revenue line. Without the
        # fallback, any sale before capture-premium was wired up reads as
        # 0 € commission and the dashboard looks broken.
        gmv_cursor = db.auctions.aggregate([
            {"$match": {"status": "sold"}},
            {"$group": {
                "_id": None,
                "gmv": {"$sum": "$current_bid_eur"},
                "commission": {"$sum": {
                    "$ifNull": [
                        "$premium_amount_eur",
                        {"$multiply": [{"$ifNull": ["$current_bid_eur", 0]}, 0.02]},
                    ],
                }},
                "count": {"$sum": 1},
            }},
        ])
        gmv_docs = await gmv_cursor.to_list(1)
        gmv = float(gmv_docs[0]["gmv"]) if gmv_docs else 0.0
        commission = float(gmv_docs[0]["commission"]) if gmv_docs else 0.0
        sold_count = int(gmv_docs[0]["count"]) if gmv_docs else 0

        # Same fallback for the 30-day window. `finalized_at` may be NULL
        # on legacy rows sold before that column was always written — those
        # are intentionally excluded from the recent bucket (otherwise a
        # missing timestamp would make every sale "recent").
        gmv_month_cursor = db.auctions.aggregate([
            {"$match": {"status": "sold", "finalized_at": {"$gte": month_ago}}},
            {"$group": {
                "_id": None,
                "gmv": {"$sum": "$current_bid_eur"},
                "commission": {"$sum": {
                    "$ifNull": [
                        "$premium_amount_eur",
                        {"$multiply": [{"$ifNull": ["$current_bid_eur", 0]}, 0.02]},
                    ],
                }},
            }},
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
        items = await db.users.find(query, {"_id": 0, "password_hash": 0, "totp_secret": 0, "totp_backup_codes": 0}).sort("created_at", -1).limit(500).to_list(500)
        return items

    @router.get("/admin/users/{user_id}")
    async def admin_get_user(user_id: str, _admin: dict = Depends(_require_admin_or_moderator)):
        u = await db.users.find_one({"id": user_id}, {"_id": 0, "password_hash": 0, "totp_secret": 0, "totp_backup_codes": 0})
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

        bids = await bidding_svc.delete_bids_for_user(user_id)
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
                "bids": bids,
                "comments": comments.deleted_count,
                "watches": watches.deleted_count,
                "saved_searches": saved.deleted_count,
                "bidding_credits": credits.deleted_count,
                "auctions_anonymized": anon.modified_count,
                "bidder_references_cleared": hb.modified_count,
            },
        }

    # ============================================================
    # Phase 2 — Car makes CMS
    # ============================================================
    import uuid as _uuid

    @router.get("/admin/makes")
    async def admin_list_makes(_admin: dict = Depends(_require_admin_or_moderator)):
        items = await db.makes.find({}, {"_id": 0}).sort("name", 1).to_list(1000)
        return items

    @router.post("/admin/makes")
    async def admin_add_make(payload: MakeCreate, request: Request, admin: dict = Depends(_require_admin)):
        name = payload.name.strip()
        if not name:
            raise HTTPException(status_code=400, detail="Името не може да е празно")
        existing = await db.makes.find_one({"name": name}, {"_id": 0, "id": 1})
        if existing:
            raise HTTPException(status_code=409, detail="Тази марка вече съществува")
        doc = {
            "id": str(_uuid.uuid4()),
            "name": name,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "created_by": admin["id"],
        }
        await db.makes.insert_one(doc)
        await audit_log(db, actor_id=admin["id"], actor_email=admin.get("email", ""), actor_role=admin.get("role", ""),
                        action="make.create", target_type="make", target_id=doc["id"],
                        details={"name": name}, ip=request.client.host if request.client else "")
        doc.pop("_id", None)
        return doc

    @router.delete("/admin/makes/{make_id}")
    async def admin_delete_make(make_id: str, request: Request, admin: dict = Depends(_require_admin)):
        make = await db.makes.find_one({"id": make_id}, {"_id": 0})
        if not make:
            raise HTTPException(status_code=404, detail="Марката не е намерена")
        in_use = await db.auctions.count_documents({"make": make["name"]})
        if in_use > 0:
            raise HTTPException(status_code=400, detail=f"Марката се използва в {in_use} обяви и не може да бъде изтрита.")
        await db.makes.delete_one({"id": make_id})
        await audit_log(db, actor_id=admin["id"], actor_email=admin.get("email", ""), actor_role=admin.get("role", ""),
                        action="make.delete", target_type="make", target_id=make_id,
                        details={"name": make["name"]}, ip=request.client.host if request.client else "")
        return {"ok": True}

    # ============================================================
    # Phase 2 — Auction lifecycle (pause / cancel / close-now / archive / featured)
    # ============================================================
    @router.post("/admin/auctions/{auction_id}/pause")
    async def admin_pause(auction_id: str, request: Request, admin: dict = Depends(_require_admin)):
        a = await db.auctions.find_one({"id": auction_id}, {"_id": 0})
        if not a:
            raise HTTPException(status_code=404, detail="Обявата не е намерена")
        if a.get("status") != "live":
            raise HTTPException(status_code=400, detail="Само активни търгове могат да бъдат паузирани")
        if a.get("paused"):
            raise HTTPException(status_code=400, detail="Търгът вече е паузиран")
        now = datetime.now(timezone.utc)
        ends_at = datetime.fromisoformat(a["ends_at"])
        seconds_remaining = max(0, int((ends_at - now).total_seconds()))
        await db.auctions.update_one({"id": auction_id}, {
            "$set": {"paused": True, "paused_at": now.isoformat(), "paused_seconds_remaining": seconds_remaining, "status": "paused"},
        })
        await audit_log(db, actor_id=admin["id"], actor_email=admin.get("email", ""), actor_role=admin.get("role", ""),
                        action="auction.pause", target_type="auction", target_id=auction_id,
                        details={"seconds_remaining": seconds_remaining}, ip=request.client.host if request.client else "")
        return {"ok": True, "status": "paused", "seconds_remaining": seconds_remaining}

    @router.post("/admin/auctions/{auction_id}/unpause")
    async def admin_unpause(auction_id: str, request: Request, admin: dict = Depends(_require_admin)):
        a = await db.auctions.find_one({"id": auction_id}, {"_id": 0})
        if not a:
            raise HTTPException(status_code=404, detail="Обявата не е намерена")
        if not a.get("paused"):
            raise HTTPException(status_code=400, detail="Търгът не е паузиран")
        now = datetime.now(timezone.utc)
        secs = int(a.get("paused_seconds_remaining") or 0)
        new_ends = (now + timedelta(seconds=max(secs, 300))).isoformat()
        await db.auctions.update_one({"id": auction_id}, {
            "$set": {"paused": False, "status": "live", "ends_at": new_ends},
            "$unset": {"paused_at": "", "paused_seconds_remaining": ""},
        })
        await audit_log(db, actor_id=admin["id"], actor_email=admin.get("email", ""), actor_role=admin.get("role", ""),
                        action="auction.unpause", target_type="auction", target_id=auction_id,
                        details={"new_ends_at": new_ends}, ip=request.client.host if request.client else "")
        return {"ok": True, "status": "live", "ends_at": new_ends}

    @router.post("/admin/auctions/{auction_id}/cancel")
    async def admin_cancel(auction_id: str, payload: CancelReason, request: Request, admin: dict = Depends(_require_admin)):
        a = await db.auctions.find_one({"id": auction_id}, {"_id": 0})
        if not a:
            raise HTTPException(status_code=404, detail="Обявата не е намерена")
        if a.get("status") in ("sold", "cancelled", "withdrawn"):
            raise HTTPException(status_code=400, detail=f"Обява със статус '{a.get('status')}' не може да бъде отказана")
        now = datetime.now(timezone.utc).isoformat()
        # Cancel + auto-archive: отказаните обяви също отиват в архив.
        await db.auctions.update_one({"id": auction_id}, {
            "$set": {
                "status": "cancelled",
                "cancelled_at": now,
                "cancel_reason": payload.reason.strip(),
                "cancelled_by": admin["id"],
                "is_archived": True,
                "archived_at": now,
            },
        })
        await audit_log(db, actor_id=admin["id"], actor_email=admin.get("email", ""), actor_role=admin.get("role", ""),
                        action="auction.cancel", target_type="auction", target_id=auction_id,
                        details={"reason": payload.reason.strip()[:200]}, ip=request.client.host if request.client else "")
        return {"ok": True, "status": "cancelled"}

    @router.post("/admin/auctions/{auction_id}/close-now")
    async def admin_close_now(auction_id: str, request: Request, admin: dict = Depends(_require_admin)):
        """Force-end a live auction immediately. Sets ends_at=now; finalizer loop will handle."""
        a = await db.auctions.find_one({"id": auction_id}, {"_id": 0})
        if not a:
            raise HTTPException(status_code=404, detail="Обявата не е намерена")
        if a.get("status") != "live":
            raise HTTPException(status_code=400, detail="Само активни търгове могат да бъдат затваряни ръчно")
        now = datetime.now(timezone.utc).isoformat()
        await db.auctions.update_one({"id": auction_id}, {"$set": {"ends_at": now, "force_closed_at": now, "force_closed_by": admin["id"]}})
        await audit_log(db, actor_id=admin["id"], actor_email=admin.get("email", ""), actor_role=admin.get("role", ""),
                        action="auction.force_close", target_type="auction", target_id=auction_id,
                        details={}, ip=request.client.host if request.client else "")
        return {"ok": True, "ends_at": now, "note": "Финализирането ще се случи до 60 секунди"}

    @router.post("/admin/auctions/{auction_id}/archive")
    async def admin_archive(auction_id: str, request: Request, admin: dict = Depends(_require_admin)):
        a = await db.auctions.find_one({"id": auction_id}, {"_id": 0})
        if not a:
            raise HTTPException(status_code=404, detail="Обявата не е намерена")
        await db.auctions.update_one({"id": auction_id}, {"$set": {"is_archived": True, "archived_at": datetime.now(timezone.utc).isoformat()}})
        await audit_log(db, actor_id=admin["id"], actor_email=admin.get("email", ""), actor_role=admin.get("role", ""),
                        action="auction.archive", target_type="auction", target_id=auction_id,
                        details={"previous_status": a.get("status")}, ip=request.client.host if request.client else "")
        return {"ok": True, "is_archived": True}

    @router.post("/admin/auctions/{auction_id}/unarchive")
    async def admin_unarchive(auction_id: str, request: Request, admin: dict = Depends(_require_admin)):
        await db.auctions.update_one({"id": auction_id}, {"$set": {"is_archived": False}, "$unset": {"archived_at": ""}})
        await audit_log(db, actor_id=admin["id"], actor_email=admin.get("email", ""), actor_role=admin.get("role", ""),
                        action="auction.unarchive", target_type="auction", target_id=auction_id, details={})
        return {"ok": True, "is_archived": False}

    @router.post("/admin/auctions/{auction_id}/featured")
    async def admin_toggle_featured(auction_id: str, request: Request, admin: dict = Depends(_require_admin)):
        a = await db.auctions.find_one({"id": auction_id}, {"_id": 0, "featured": 1})
        if not a:
            raise HTTPException(status_code=404, detail="Обявата не е намерена")
        new_val = not bool(a.get("featured"))
        await db.auctions.update_one({"id": auction_id}, {"$set": {"featured": new_val}})
        await audit_log(db, actor_id=admin["id"], actor_email=admin.get("email", ""), actor_role=admin.get("role", ""),
                        action="auction.featured_toggle", target_type="auction", target_id=auction_id,
                        details={"featured": new_val}, ip=request.client.host if request.client else "")
        return {"ok": True, "featured": new_val}


    # ============================================================
    # Phase 3 — Bid & bidder moderation
    # ============================================================
    @router.get("/admin/auctions/{auction_id}/bids")
    async def admin_bid_history(auction_id: str, _admin: dict = Depends(_require_admin_or_moderator)):
        items = await bidding_svc.list_bids_for_admin(auction_id, limit=500)
        # Enrich blocked status per user
        blocked_ids = set()
        async for b in db.bid_blocks.find({"auction_id": auction_id}, {"_id": 0, "user_id": 1}):
            blocked_ids.add(b["user_id"])
        for it in items:
            it["is_blocked_on_auction"] = it["user_id"] in blocked_ids
        return items

    @router.post("/admin/bids/{bid_id}/invalidate")
    async def admin_invalidate_bid(bid_id: str, payload: InvalidateBidRequest, request: Request, admin: dict = Depends(_require_admin)):
        b = await bidding_svc.get_bid(bid_id)
        if not b:
            raise HTTPException(status_code=404, detail="Бидът не е намерен")
        if b.get("preauth_status") == "released":
            raise HTTPException(status_code=400, detail="Бидът вече е инвалидиран")
        await bidding_svc.invalidate_bid(bid_id)
        # Re-derive auction's high bid from remaining valid bids
        auction_id = b["auction_id"]
        top = await bidding_svc.get_top_active_bid(auction_id)
        a = await db.auctions.find_one({"id": auction_id}, {"_id": 0})
        if top:
            await db.auctions.update_one({"id": auction_id}, {"$set": {
                "current_bid_eur": top["amount_eur"], "high_bidder_id": top["user_id"], "high_bidder_name": top["user_name"],
            }})
        elif a:
            # Fallback to starting bid
            await db.auctions.update_one({"id": auction_id}, {"$set": {
                "current_bid_eur": a.get("starting_bid_eur", 0), "high_bidder_id": None, "high_bidder_name": None,
            }})
        await audit_log(db, actor_id=admin["id"], actor_email=admin.get("email", ""), actor_role=admin.get("role", ""),
                        action="bid.invalidate", target_type="bid", target_id=bid_id,
                        details={"auction_id": auction_id, "reason": payload.reason.strip()[:200]},
                        ip=request.client.host if request.client else "")
        return {"ok": True}

    @router.post("/admin/auctions/{auction_id}/block-bidder")
    async def admin_block_bidder(auction_id: str, payload: BlockBidderRequest, request: Request, admin: dict = Depends(_require_admin)):
        existing = await db.bid_blocks.find_one({"auction_id": auction_id, "user_id": payload.user_id}, {"_id": 0, "id": 1})
        if existing:
            return {"ok": True, "already_blocked": True}
        doc = {
            "id": __import__("uuid").uuid4().hex,
            "auction_id": auction_id,
            "user_id": payload.user_id,
            "reason": (payload.reason or "").strip(),
            "by": admin["id"],
            "at": datetime.now(timezone.utc).isoformat(),
        }
        await db.bid_blocks.insert_one(doc)
        await audit_log(db, actor_id=admin["id"], actor_email=admin.get("email", ""), actor_role=admin.get("role", ""),
                        action="bidder.block", target_type="user", target_id=payload.user_id,
                        details={"auction_id": auction_id, "reason": (payload.reason or "")[:200]},
                        ip=request.client.host if request.client else "")
        return {"ok": True}

    @router.delete("/admin/auctions/{auction_id}/block-bidder/{user_id}")
    async def admin_unblock_bidder(auction_id: str, user_id: str, request: Request, admin: dict = Depends(_require_admin)):
        res = await db.bid_blocks.delete_one({"auction_id": auction_id, "user_id": user_id})
        await audit_log(db, actor_id=admin["id"], actor_email=admin.get("email", ""), actor_role=admin.get("role", ""),
                        action="bidder.unblock", target_type="user", target_id=user_id,
                        details={"auction_id": auction_id}, ip=request.client.host if request.client else "")
        return {"ok": True, "removed": res.deleted_count}

    # ============================================================
    # Phase 3 — User moderation (suspend/verify/notes/vin-log/resend-verify)
    # ============================================================
    @router.post("/admin/users/{user_id}/suspend")
    async def admin_suspend_user(user_id: str, request: Request, admin: dict = Depends(_require_admin)):
        if user_id == admin["id"]:
            raise HTTPException(status_code=400, detail="Не можете да спрете собствения си акаунт")
        u = await db.users.find_one({"id": user_id}, {"_id": 0})
        if not u:
            raise HTTPException(status_code=404, detail="Потребителят не е намерен")
        if u.get("role") in ("admin", "moderator"):
            raise HTTPException(status_code=400, detail="Не можете да спирате друг служител")
        await db.users.update_one({"id": user_id}, {"$set": {"suspended": True, "suspended_at": datetime.now(timezone.utc).isoformat()}})
        await audit_log(db, actor_id=admin["id"], actor_email=admin.get("email", ""), actor_role=admin.get("role", ""),
                        action="user.suspend", target_type="user", target_id=user_id, details={},
                        ip=request.client.host if request.client else "")
        return {"ok": True, "suspended": True}

    @router.post("/admin/users/{user_id}/unsuspend")
    async def admin_unsuspend_user(user_id: str, request: Request, admin: dict = Depends(_require_admin)):
        await db.users.update_one({"id": user_id}, {"$set": {"suspended": False}, "$unset": {"suspended_at": ""}})
        await audit_log(db, actor_id=admin["id"], actor_email=admin.get("email", ""), actor_role=admin.get("role", ""),
                        action="user.unsuspend", target_type="user", target_id=user_id, details={})
        return {"ok": True, "suspended": False}

    @router.post("/admin/users/{user_id}/verify-seller")
    async def admin_verify_seller(user_id: str, request: Request, admin: dict = Depends(_require_admin)):
        await db.users.update_one({"id": user_id}, {"$set": {"is_verified_dealer": True, "verified_at": datetime.now(timezone.utc).isoformat(), "verified_by": admin["id"]}})
        await audit_log(db, actor_id=admin["id"], actor_email=admin.get("email", ""), actor_role=admin.get("role", ""),
                        action="user.verify_seller", target_type="user", target_id=user_id, details={},
                        ip=request.client.host if request.client else "")
        return {"ok": True, "is_verified_dealer": True}

    @router.post("/admin/users/{user_id}/unverify-seller")
    async def admin_unverify_seller(user_id: str, request: Request, admin: dict = Depends(_require_admin)):
        await db.users.update_one({"id": user_id}, {"$set": {"is_verified_dealer": False}})
        await audit_log(db, actor_id=admin["id"], actor_email=admin.get("email", ""), actor_role=admin.get("role", ""),
                        action="user.unverify_seller", target_type="user", target_id=user_id, details={})
        return {"ok": True, "is_verified_dealer": False}

    @router.get("/admin/users/{user_id}/notes")
    async def admin_list_notes(user_id: str, _admin: dict = Depends(_require_admin_or_moderator)):
        items = await db.user_notes.find({"user_id": user_id}, {"_id": 0}).sort("at", -1).limit(200).to_list(200)
        return items

    @router.post("/admin/users/{user_id}/notes")
    async def admin_add_note(user_id: str, payload: InternalNote, admin: dict = Depends(_require_admin_or_moderator)):
        doc = {
            "id": __import__("uuid").uuid4().hex,
            "user_id": user_id,
            "text": payload.text.strip(),
            "author_id": admin["id"],
            "author_name": admin.get("name", ""),
            "author_role": admin.get("role", ""),
            "at": datetime.now(timezone.utc).isoformat(),
        }
        await db.user_notes.insert_one(doc)
        doc.pop("_id", None)
        return doc

    @router.delete("/admin/users/{user_id}/notes/{note_id}")
    async def admin_delete_note(user_id: str, note_id: str, admin: dict = Depends(_require_admin_or_moderator)):
        await db.user_notes.delete_one({"id": note_id, "user_id": user_id})
        return {"ok": True}

    @router.get("/admin/users/{user_id}/vin-requests")
    async def admin_user_vin_requests(user_id: str, _admin: dict = Depends(_require_admin_or_moderator)):
        items = await db.vin_requests.find({"user_id": user_id}, {"_id": 0}).sort("created_at", -1).limit(200).to_list(200)
        return items

    @router.get("/admin/vin-requests")
    async def admin_vin_requests(auction_id: Optional[str] = None, _admin: dict = Depends(_require_admin_or_moderator)):
        q = {}
        if auction_id:
            q["auction_id"] = auction_id
        items = await db.vin_requests.find(q, {"_id": 0}).sort("created_at", -1).limit(500).to_list(500)
        return items

    @router.post("/admin/users/{user_id}/resend-verification")
    async def admin_resend_verification(user_id: str, admin: dict = Depends(_require_admin)):
        """Placeholder hook — sends a fresh Resend email. Real verify-link flow will come when we add email verification."""
        u = await db.users.find_one({"id": user_id}, {"_id": 0})
        if not u:
            raise HTTPException(status_code=404, detail="Потребителят не е намерен")
        try:
            from emails import send_email, _shell
            html = _shell(
                "Потвърдете акаунта си",
                f"<p>Здравейте {u.get('name','')},</p><p>Admin екипът ви подсеща да потвърдите своя акаунт в autoandbid.com. Моля, влезте в профила си и актуализирайте данните за контакт, ако е необходимо.</p>",
            )
            await send_email(u["email"], "autoandbid.com — напомняне за акаунта", html)
            await db.users.update_one({"id": user_id}, {"$set": {"verification_sent_at": datetime.now(timezone.utc).isoformat()}})
        except Exception as e:
            logger.error("resend_verification failed: %s", e)
            raise HTTPException(status_code=500, detail="Неуспешно изпращане")
        await audit_log(db, actor_id=admin["id"], actor_email=admin.get("email", ""), actor_role=admin.get("role", ""),
                        action="user.resend_verification", target_type="user", target_id=user_id, details={})
        return {"ok": True}

    # ============================================================
    # Phase 4 — Buyer fee status + Stripe events
    # ============================================================
    @router.get("/admin/auctions/{auction_id}/buyer-fee")
    async def admin_get_buyer_fee(auction_id: str, _admin: dict = Depends(_require_admin_or_moderator)):
        a = await db.auctions.find_one({"id": auction_id}, {"_id": 0, "id": 1, "title": 1, "current_bid_eur": 1, "status": 1, "high_bidder_id": 1, "high_bidder_name": 1, "buyer_fee_status": 1, "buyer_fee_note": 1, "buyer_fee_updated_at": 1, "premium_amount_eur": 1})
        if not a:
            raise HTTPException(status_code=404, detail="Обявата не е намерена")
        a.setdefault("buyer_fee_status", "unpaid")
        return a

    @router.put("/admin/auctions/{auction_id}/buyer-fee")
    async def admin_update_buyer_fee(auction_id: str, payload: BuyerFeeUpdate, request: Request, admin: dict = Depends(_require_admin)):
        if payload.status not in ("unpaid", "paid", "waived", "refunded"):
            raise HTTPException(status_code=400, detail="Невалиден статус")
        now = datetime.now(timezone.utc).isoformat()
        await db.auctions.update_one({"id": auction_id}, {"$set": {
            "buyer_fee_status": payload.status, "buyer_fee_note": (payload.note or "").strip(),
            "buyer_fee_updated_at": now, "buyer_fee_updated_by": admin["id"],
        }})
        await audit_log(db, actor_id=admin["id"], actor_email=admin.get("email", ""), actor_role=admin.get("role", ""),
                        action="buyer_fee.update", target_type="auction", target_id=auction_id,
                        details={"status": payload.status}, ip=request.client.host if request.client else "")
        return {"ok": True, "status": payload.status}

    @router.get("/admin/stripe/events")
    async def admin_stripe_events(limit: int = 100, _admin: dict = Depends(_require_admin)):
        """Returns recent Stripe webhook events (from stripe_events collection)."""
        limit = max(1, min(500, int(limit)))
        items = await db.stripe_events.find({}, {"_id": 0}).sort("received_at", -1).limit(limit).to_list(limit)
        return {"items": items, "total": await db.stripe_events.count_documents({})}



    # ============================================================
    # Phase 4 — Notification log + CSV export
    # ============================================================
    @router.get("/admin/notifications")
    async def admin_notifications(
        limit: int = 100, offset: int = 0, status: Optional[str] = None,
        _admin: dict = Depends(_require_admin_or_moderator),
    ):
        limit = max(1, min(500, int(limit)))
        offset = max(0, int(offset))
        q: dict = {}
        if status:
            q["status"] = status
        total = await db.notification_log.count_documents(q)
        items = await db.notification_log.find(q, {"_id": 0}).sort("at", -1).skip(offset).limit(limit).to_list(limit)
        return {"items": items, "total": total, "offset": offset, "limit": limit}

    @router.get("/admin/transactions/export.csv")
    async def admin_export_transactions(_admin: dict = Depends(_require_admin)):
        """Export all sold auctions + buyer-fee info as CSV."""
        from fastapi.responses import StreamingResponse
        import io as _io, csv as _csv
        cur = db.auctions.find({"status": "sold"}, {"_id": 0}).sort("finalized_at", -1)
        rows = await cur.to_list(5000)
        buf = _io.StringIO()
        buf.write("\ufeff")
        w = _csv.writer(buf)
        w.writerow(["auction_id", "title", "make", "model", "year", "sold_price_eur", "buyer_fee_status", "premium_amount_eur", "seller_id", "seller_name", "high_bidder_id", "high_bidder_name", "finalized_at"])
        for a in rows:
            w.writerow([
                a.get("id", ""), a.get("title", ""), a.get("make", ""), a.get("model", ""),
                a.get("year", ""), a.get("current_bid_eur", ""),
                a.get("buyer_fee_status", "unpaid"), a.get("premium_amount_eur", ""),
                a.get("seller_id", ""), a.get("seller_name", ""),
                a.get("high_bidder_id", "") or "", a.get("high_bidder_name", "") or "",
                a.get("finalized_at", ""),
            ])
        buf.seek(0)
        return StreamingResponse(
            iter([buf.getvalue().encode("utf-8")]),
            media_type="text/csv",
            headers={"Content-Disposition": f"attachment; filename=transactions_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}.csv"},
        )

    # ============================================================
    # Phase 4 — Canned email templates (stored inside site_settings)
    # ============================================================
    from fastapi import Body

    @router.get("/admin/email-templates")
    async def admin_get_templates(_admin: dict = Depends(_require_admin_or_moderator)):
        s = _settings_fn()
        return s.get("email_templates") or {}

    @router.put("/admin/email-templates")
    async def admin_put_templates(request: Request, payload: dict = Body(...), admin: dict = Depends(_require_admin)):
        if not isinstance(payload, dict):
            raise HTTPException(status_code=400, detail="Очаква се обект с ключ/стойност")
        cleaned: dict = {}
        for k, v in list(payload.items())[:20]:
            if not isinstance(v, dict):
                continue
            subject = str(v.get("subject", ""))[:200]
            body = str(v.get("body", ""))[:20000]
            cleaned[str(k)[:40]] = {"subject": subject, "body": body}
        await db.site_settings.update_one(
            {"id": "global"},
            {"$set": {"email_templates": cleaned, "updated_at": datetime.now(timezone.utc).isoformat()},
             "$setOnInsert": {"id": "global"}},
            upsert=True,
        )
        await _load_settings_cache()
        await audit_log(db, actor_id=admin["id"], actor_email=admin.get("email", ""), actor_role=admin.get("role", ""),
                        action="email_templates.update", target_type="site_settings", target_id="global",
                        details={"count": len(cleaned)}, ip=request.client.host if request.client else "",
                        user_agent=request.headers.get("user-agent", ""))
        return {"ok": True, "templates": cleaned}

    @router.post("/admin/send-email")
    async def admin_send_manual_email(
        request: Request,
        payload: dict = Body(...),
        admin: dict = Depends(_require_admin),
    ):
        to = (payload.get("to") or "").strip().lower()
        subject = (payload.get("subject") or "").strip()[:200]
        body = payload.get("body") or ""
        if "@" not in to or not subject or not body:
            raise HTTPException(status_code=400, detail="Необходими са валиден email, тема и съдържание.")
        from emails import send_email, _shell
        ok = await send_email(to, subject, _shell(subject, f"<div>{body}</div>"))
        await audit_log(db, actor_id=admin["id"], actor_email=admin.get("email", ""), actor_role=admin.get("role", ""),
                        action="email.manual", target_type="email", target_id=to,
                        details={"subject": subject[:120], "ok": ok},
                        ip=request.client.host if request.client else "",
                        user_agent=request.headers.get("user-agent", ""))
        return {"ok": ok}
