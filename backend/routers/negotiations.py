"""
Post-auction negotiation portal (BaT April 2025 flow).
Extracted from server.py — the routes own their Pydantic models via models.py
and share the same Motor db client via deps.py.

Dependencies that live in server.py (get_current_user, _auction_status,
_buyer_fee, email_won) are injected at app wire-up via `configure()`.
"""
import logging
import uuid
from datetime import datetime, timezone, timedelta
from typing import Optional

from fastapi import APIRouter, HTTPException, Depends

from deps import db
from models import (
    NegotiationOpening, NegotiationResponse, NegotiationFinal, NegotiationMessage,
)

router = APIRouter()
logger = logging.getLogger(__name__)

NEG_WINDOW = timedelta(hours=24)
NEG_OPEN_STATES = {"awaiting_seller_opening", "awaiting_buyer_response", "awaiting_seller_final"}

# --- Injected dependencies (wired by server.py via configure()) ---
_get_current_user = None
_auction_status = None
_buyer_fee = None
_email_won = None


def configure(*, get_current_user, auction_status, buyer_fee, email_won):
    """Called once at app startup by server.py."""
    global _get_current_user, _auction_status, _buyer_fee, _email_won
    _get_current_user = get_current_user
    _auction_status = auction_status
    _buyer_fee = buyer_fee
    _email_won = email_won


async def _user_dep():
    # Thin wrapper so Depends() can resolve lazily after configure()
    return await _get_current_user()


def _neg_public(n: dict, viewer_id: Optional[str] = None) -> dict:
    d = {k: v for k, v in n.items() if k != "_id"}
    if d.get("deadline_at"):
        try:
            dl = datetime.fromisoformat(d["deadline_at"])
            d["seconds_left"] = max(0, int((dl - datetime.now(timezone.utc)).total_seconds()))
        except Exception:
            d["seconds_left"] = 0
    return d


async def _ensure_negotiation(auction_id: str) -> Optional[dict]:
    """Auto-create a negotiation when the auction is reserve_not_met and none exists.
    Also auto-expires if a 24h deadline has elapsed without action.
    """
    a = await db.auctions.find_one({"id": auction_id}, {"_id": 0})
    if not a:
        return None
    if _auction_status(a) != "reserve_not_met" or not a.get("high_bidder_id"):
        return await db.negotiations.find_one({"auction_id": auction_id}, {"_id": 0})

    n = await db.negotiations.find_one({"auction_id": auction_id}, {"_id": 0})
    now = datetime.now(timezone.utc)
    if not n:
        doc = {
            "id": str(uuid.uuid4()),
            "auction_id": auction_id,
            "seller_id": a["seller_id"],
            "seller_name": a.get("seller_name"),
            "buyer_id": a["high_bidder_id"],
            "buyer_name": a.get("high_bidder_name"),
            "status": "awaiting_seller_opening",
            "final_price_eur": None,
            "seller_offer_eur": None,
            "buyer_counter_eur": None,
            "deadline_at": (now + NEG_WINDOW).isoformat(),
            "created_at": now.isoformat(),
            "updated_at": now.isoformat(),
            "messages": [],
        }
        await db.negotiations.insert_one(doc)
        return {k: v for k, v in doc.items() if k != "_id"}

    if n.get("status") in NEG_OPEN_STATES and n.get("deadline_at"):
        try:
            dl = datetime.fromisoformat(n["deadline_at"])
            if now >= dl:
                await db.negotiations.update_one(
                    {"id": n["id"]},
                    {"$set": {"status": "expired", "updated_at": now.isoformat()}},
                )
                n["status"] = "expired"
        except Exception:
            pass
    return n


def _neg_require_party(n: dict, user: dict, party: str):
    uid = user["id"]
    if user.get("role") == "admin":
        return
    if party == "seller" and n.get("seller_id") != uid:
        raise HTTPException(status_code=403, detail="Само продавачът може да извърши това")
    if party == "buyer" and n.get("buyer_id") != uid:
        raise HTTPException(status_code=403, detail="Само купувачът може да извърши това")
    if party == "any" and uid not in (n.get("seller_id"), n.get("buyer_id")):
        raise HTTPException(status_code=403, detail="Нямате достъп")


async def _complete_negotiation(auction_id: str, negotiation_id: str, price: float, now: datetime):
    buyer_fee = _buyer_fee(price)
    await db.negotiations.update_one(
        {"id": negotiation_id},
        {"$set": {
            "status": "accepted",
            "final_price_eur": float(price),
            "buyer_fee_eur": buyer_fee,
            "completed_at": now.isoformat(),
            "updated_at": now.isoformat(),
        }},
    )
    await db.auctions.update_one(
        {"id": auction_id},
        {"$set": {
            "status": "sold",
            "current_bid_eur": float(price),
            "finalized_at": now.isoformat(),
            "premium_amount_eur": buyer_fee,
        }},
    )
    a = await db.auctions.find_one({"id": auction_id}, {"_id": 0})
    if a and a.get("high_bidder_id"):
        winner = await db.users.find_one({"id": a["high_bidder_id"]}, {"_id": 0})
        if winner and winner.get("email"):
            try:
                await _email_won(winner["email"], winner["name"], a["title"], auction_id, float(price))
            except Exception as e:
                logger.error("email_won (negotiation) failed: %s", e)
    # Admin push — sale concluded after reserve-not-met negotiation.
    # Uses the same VAT-aware helper as the live-sold flow so the admin
    # sees gross price + 2 % commission when VAT applies.
    try:
        from routers.inbox import notify_admins as _notify_admins
        from server import _admin_notif_vat_fields
        vat = _admin_notif_vat_fields(float(price), a or {})
        await _notify_admins(
            db,
            type="auction_sold_negotiated",
            data={
                "title": (a or {}).get("title", ""),
                "price": float(price),
                "price_gross": vat["gross"],
                "commission": vat["commission"],
            },
            auction_id=auction_id,
            push_template_id="admin_auction_sold_negotiated",
            push_fmt={
                "title": ((a or {}).get("title") or "")[:80],
                # GROSS price (what the buyer actually pays). Keeps admin's
                # eyeballed commission figure aligned with Stripe statement.
                "price": vat["gross"],
                "vat_suffix": vat["vat_suffix"],
                "commission": vat["commission"],
            },
        )
    except Exception:
        pass


@router.get("/auctions/{auction_id}/negotiation")
async def _neg_get_placeholder(auction_id: str):
    # Placeholder — actual handler is (re)registered via `register_routes()` below.
    # This is overwritten cleanly by FastAPI when the real route is added.
    raise HTTPException(status_code=503, detail="Negotiation router not yet configured")


def register_routes(get_current_user_dep):
    """Re-register all negotiation routes with FastAPI-native dependency injection.
    Called once from server.py after `configure()` has wired in helper functions.
    """
    # Remove the placeholder route so the real one takes effect without shadowing
    router.routes = [r for r in router.routes if getattr(r, "endpoint", None) is not _neg_get_placeholder]

    @router.get("/auctions/{auction_id}/negotiation", name="neg_get")
    async def _get_negotiation(auction_id: str, user: dict = Depends(get_current_user_dep)):
        n = await _ensure_negotiation(auction_id)
        if not n:
            raise HTTPException(status_code=404, detail="Няма активна преговаряща сесия")
        _neg_require_party(n, user, "any")
        return _neg_public(n, user["id"])

    @router.post("/auctions/{auction_id}/negotiation/opening")
    async def _negotiation_opening(auction_id: str, payload: NegotiationOpening, user: dict = Depends(get_current_user_dep)):
        n = await _ensure_negotiation(auction_id)
        if not n:
            raise HTTPException(status_code=404, detail="Няма активна преговаряща сесия")
        _neg_require_party(n, user, "seller")
        if n.get("status") != "awaiting_seller_opening":
            raise HTTPException(status_code=400, detail="Офертата вече е направена")

        now = datetime.now(timezone.utc)
        if payload.decline:
            update = {"status": "declined", "updated_at": now.isoformat(), "closed_by": "seller"}
        else:
            if not payload.price_eur or payload.price_eur <= 0:
                raise HTTPException(status_code=400, detail="Невалидна цена")
            update = {
                "seller_offer_eur": float(payload.price_eur),
                "status": "awaiting_buyer_response",
                "deadline_at": (now + NEG_WINDOW).isoformat(),
                "updated_at": now.isoformat(),
            }
        await db.negotiations.update_one({"id": n["id"]}, {"$set": update})
        refreshed = await db.negotiations.find_one({"id": n["id"]}, {"_id": 0})
        return _neg_public(refreshed)

    @router.post("/auctions/{auction_id}/negotiation/response")
    async def _negotiation_response(auction_id: str, payload: NegotiationResponse, user: dict = Depends(get_current_user_dep)):
        n = await _ensure_negotiation(auction_id)
        if not n:
            raise HTTPException(status_code=404, detail="Няма активна преговаряща сесия")
        _neg_require_party(n, user, "buyer")
        if n.get("status") != "awaiting_buyer_response":
            raise HTTPException(status_code=400, detail="Не се очаква ваш отговор в момента")

        now = datetime.now(timezone.utc)
        action = payload.action
        if action == "accept":
            price = float(n["seller_offer_eur"])
            await _complete_negotiation(n["auction_id"], n["id"], price, now)
        elif action == "counter":
            if not payload.price_eur or payload.price_eur <= 0:
                raise HTTPException(status_code=400, detail="Невалидна цена за контраоферта")
            await db.negotiations.update_one({"id": n["id"]}, {"$set": {
                "buyer_counter_eur": float(payload.price_eur),
                "status": "awaiting_seller_final",
                "deadline_at": (now + NEG_WINDOW).isoformat(),
                "updated_at": now.isoformat(),
            }})
        elif action == "decline":
            await db.negotiations.update_one({"id": n["id"]}, {"$set": {"status": "declined", "updated_at": now.isoformat(), "closed_by": "buyer"}})
        else:
            raise HTTPException(status_code=400, detail="Невалидно действие")
        refreshed = await db.negotiations.find_one({"id": n["id"]}, {"_id": 0})
        return _neg_public(refreshed)

    @router.post("/auctions/{auction_id}/negotiation/final")
    async def _negotiation_final(auction_id: str, payload: NegotiationFinal, user: dict = Depends(get_current_user_dep)):
        n = await _ensure_negotiation(auction_id)
        if not n:
            raise HTTPException(status_code=404, detail="Няма активна преговаряща сесия")
        _neg_require_party(n, user, "seller")
        if n.get("status") != "awaiting_seller_final":
            raise HTTPException(status_code=400, detail="Не е ваш ред да потвърдите")

        now = datetime.now(timezone.utc)
        if payload.action == "accept":
            price = float(n["buyer_counter_eur"])
            await _complete_negotiation(n["auction_id"], n["id"], price, now)
        elif payload.action == "decline":
            await db.negotiations.update_one({"id": n["id"]}, {"$set": {"status": "declined", "updated_at": now.isoformat(), "closed_by": "seller"}})
        else:
            raise HTTPException(status_code=400, detail="Невалидно действие")
        refreshed = await db.negotiations.find_one({"id": n["id"]}, {"_id": 0})
        return _neg_public(refreshed)

    @router.post("/auctions/{auction_id}/negotiation/messages")
    async def _negotiation_send_message(auction_id: str, payload: NegotiationMessage, user: dict = Depends(get_current_user_dep)):
        n = await _ensure_negotiation(auction_id)
        if not n:
            raise HTTPException(status_code=404, detail="Няма активна преговаряща сесия")
        _neg_require_party(n, user, "any")
        msg = {
            "id": str(uuid.uuid4()),
            "user_id": user["id"],
            "user_name": user["name"],
            "role": "seller" if user["id"] == n["seller_id"] else ("buyer" if user["id"] == n["buyer_id"] else "admin"),
            "text": payload.text.strip(),
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        await db.negotiations.update_one(
            {"id": n["id"]},
            {"$push": {"messages": msg}, "$set": {"updated_at": msg["created_at"]}},
        )
        return {"ok": True, "message": msg}
