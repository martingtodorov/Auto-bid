from dotenv import load_dotenv
from pathlib import Path

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

import os
import asyncio
import uuid
import logging
import bcrypt
import jwt
from datetime import datetime, timezone, timedelta
from typing import List, Optional
from fastapi import FastAPI, APIRouter, HTTPException, Depends, Request, Query, WebSocket, WebSocketDisconnect, Response
from fastapi.responses import PlainTextResponse
from starlette.middleware.cors import CORSMiddleware
import re
from motor.motor_asyncio import AsyncIOMotorClient
from pydantic import BaseModel, Field, EmailStr, ConfigDict

from emails import email_outbid, email_won, email_approved, email_rejected, email_seller_new_bid, email_seller_new_comment, email_vin_delivery
from ws import hub
from sms import send_sms

# ---- MongoDB ----
mongo_url = os.environ['MONGO_URL']
client = AsyncIOMotorClient(mongo_url)
db = client[os.environ['DB_NAME']]

# ---- App ----
app = FastAPI(title="autobids.bg API")
api = APIRouter(prefix="/api")

# ---- Rate limiter (slowapi) ----
from slowapi import Limiter
from slowapi.util import get_remote_address


def _real_client_ip(request: Request) -> str:
    """Resolve the real client IP behind the Kubernetes ingress / load balancer.
    Falls back to the direct remote address if no trusted proxy header is present.
    """
    # X-Forwarded-For may contain a comma-separated list — the FIRST entry is the client.
    xff = request.headers.get("x-forwarded-for") or request.headers.get("X-Forwarded-For")
    if xff:
        return xff.split(",")[0].strip()
    real = request.headers.get("x-real-ip") or request.headers.get("X-Real-Ip")
    if real:
        return real.strip()
    return get_remote_address(request)


limiter = Limiter(key_func=_real_client_ip, default_limits=[])

JWT_ALGORITHM = "HS256"
JWT_SECRET = os.environ['JWT_SECRET']

# ---- Helpers ----
def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")

def verify_password(plain: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))
    except Exception:
        return False

def create_token(user_id: str, email: str, days: int = 7) -> str:
    payload = {
        "sub": user_id,
        "email": email,
        "exp": datetime.now(timezone.utc) + timedelta(days=days),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)

async def get_current_user(request: Request) -> dict:
    auth = request.headers.get("Authorization", "")
    token = None
    if auth.startswith("Bearer "):
        token = auth[7:]
    if not token:
        token = request.cookies.get("access_token")
    if not token:
        raise HTTPException(status_code=401, detail="Не сте автентикиран")
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        user = await db.users.find_one({"id": payload["sub"]}, {"_id": 0, "password_hash": 0})
        if not user:
            raise HTTPException(status_code=401, detail="Потребителят не е намерен")
        if user.get("banned"):
            raise HTTPException(status_code=403, detail="Акаунтът е блокиран. За въпроси: contact@autobids.bg")
        return user
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Сесията е изтекла")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Невалиден токен")

async def get_optional_user(request: Request):
    try:
        return await get_current_user(request)
    except HTTPException:
        return None


# ---- Models (imported from models.py) ----
from models import (
    UserRegister, UserLogin, UserOut,
    AuctionCreate, BidCreate, BiddingCreditCreate, AdminDecision, CommentCreate,
    AuctionUpdate, AdminAuctionUpdate,
    CounterOfferCreate, NegotiationRespond,
    NegotiationOpening, NegotiationResponse, NegotiationFinal, NegotiationMessage,
    ProfileUpdate, AdminUserUpdate, SavedSearchCreate, SiteSettingsUpdate,
)


# ---- Auth routes moved to routers/auth.py ----


# ---- Auction helpers ----
# Global settings cache (loaded at startup, refreshed on admin update).
SETTINGS_DEFAULTS = {
    "buyer_fee_pct": 2.0,
    "buyer_fee_min_eur": 150.0,
    "buyer_fee_max_eur": 4000.0,
    "seo_title": "Auto&Bid.bg — Автомобилни търгове",
    "seo_description": "Auto&Bid.bg е платформа за онлайн търгове на автомобили в България. Всеки автомобил е внимателно подбран, документиран и представен от нашия екип.",
    "seo_title_bg": "",
    "seo_title_ro": "",
    "seo_title_en": "",
    "seo_description_bg": "",
    "seo_description_ro": "",
    "seo_description_en": "",
    "google_site_verification": "",
    "bing_site_verification": "",
    "google_analytics_id": "",
    "faq_content": "",
    "terms_content": "",
    "contacts_content": "",
    "fees_content": "",
    "how_it_works_content": "",
    # --- Stripe CMS ---
    "stripe_mode": "test",
    "stripe_enabled": False,
    "stripe_publishable_key_test": "",
    "stripe_publishable_key_live": "",
    "stripe_secret_key_test": "",
    "stripe_secret_key_live": "",
    "stripe_webhook_secret_test": "",
    "stripe_webhook_secret_live": "",
    # --- Phase 5 ---
    "og_image_url": "",
    "maintenance_mode": False,
    "maintenance_message": "AutoBids.bg се обновява. Моля, върнете се след малко.",
    # --- Phase 6: Multi-language hero CMS ---
    "hero_headline_bg": "",
    "hero_subtitle_bg": "",
    "hero_headline_ro": "",
    "hero_subtitle_ro": "",
    "hero_headline_en": "",
    "hero_subtitle_en": "",
}
_settings_cache: dict = dict(SETTINGS_DEFAULTS)


async def _load_settings_cache() -> None:
    global _settings_cache
    doc = await db.site_settings.find_one({"id": "global"}, {"_id": 0})
    merged = dict(SETTINGS_DEFAULTS)
    if doc:
        for k in SETTINGS_DEFAULTS:
            if k in doc and doc[k] is not None:
                merged[k] = doc[k]
    _settings_cache = merged


def _settings() -> dict:
    return _settings_cache


def _bid_step(current_price: float) -> float:
    from helpers import bid_step as _bs
    return _bs(current_price)


def _buyer_fee(amount_eur: float) -> float:
    """Buyer's premium — configurable by admin. Defaults: 2%, min €150, max €4 000."""
    s = _settings()
    from helpers import buyer_fee as _bf
    return _bf(
        amount_eur,
        s.get("buyer_fee_pct", 2.0),
        s.get("buyer_fee_min_eur", 150.0),
        s.get("buyer_fee_max_eur", 4000.0),
    )


def _auction_status(a: dict) -> str:
    from helpers import auction_status as _as
    return _as(a)

def _mask_vin(vin: str) -> str:
    if not vin:
        return vin
    v = vin.strip().upper()
    if len(v) <= 7:
        return "*" * len(v)
    return v[:-7] + ("*" * 7)


async def _enrich_dealer_status(items: list) -> list:
    """Bulk-fetches sellers and adds seller_is_verified_dealer to each auction dict."""
    if not items:
        return items
    seller_ids = {a.get("seller_id") for a in items if a.get("seller_id") and a.get("seller_id") != "platform"}
    verified_ids = set()
    if seller_ids:
        async for u in db.users.find({"id": {"$in": list(seller_ids)}, "is_verified_dealer": True}, {"_id": 0, "id": 1}):
            verified_ids.add(u["id"])
    for a in items:
        sid = a.get("seller_id")
        if sid == "platform":
            a["seller_is_verified_dealer"] = True
        else:
            a["seller_is_verified_dealer"] = sid in verified_ids
    return items


def _public_auction(a: dict, viewer: Optional[dict] = None) -> dict:
    a = {k: v for k, v in a.items() if k != "_id"}
    a["status"] = _auction_status(a)
    reserve = a.get("reserve_eur")
    is_owner_or_admin = viewer and (viewer.get("id") == a.get("seller_id") or viewer.get("role") == "admin")
    no_reserve = bool(a.get("no_reserve"))
    # Reserve outcome is only revealed to the public once the auction has ended.
    ended_states = ("sold", "ended", "reserve_not_met")
    show_reserve_outcome = a["status"] in ended_states
    if no_reserve:
        a["has_reserve"] = False
        a["no_reserve"] = True
        a["reserve_met"] = None
        a.pop("reserve_eur", None)
    elif reserve is not None and reserve > 0:
        a["has_reserve"] = True
        if show_reserve_outcome or is_owner_or_admin:
            a["reserve_met"] = float(a.get("current_bid_eur", 0)) >= float(reserve)
        else:
            a["reserve_met"] = None
        if not is_owner_or_admin:
            a.pop("reserve_eur", None)
    else:
        a["has_reserve"] = False
        a["reserve_met"] = None
        a.pop("reserve_eur", None)
    if a.get("vin"):
        a["vin_masked"] = True
        a["vin"] = _mask_vin(a["vin"])
    return a


# ---- Auctions ----
@api.get("/auctions")
async def list_auctions(
    request: Request,
    make: Optional[str] = None,
    fuel: Optional[str] = None,
    transmission: Optional[str] = None,
    region: Optional[str] = None,
    body_type: Optional[str] = None,
    min_price: Optional[float] = None,
    max_price: Optional[float] = None,
    year_min: Optional[int] = None,
    year_max: Optional[int] = None,
    q: Optional[str] = Query(None, description="Пълнотекстово търсене"),
    status: Optional[str] = Query(None, description="live|ended|sold"),
    sort: Optional[str] = Query("ending_soon"),
    limit: int = 60,
):
    viewer = await get_optional_user(request)
    query = {}
    if make: query["make"] = make
    if fuel: query["fuel"] = fuel
    if transmission: query["transmission"] = transmission
    if region: query["region"] = region
    if body_type: query["body_type"] = body_type
    if year_min or year_max:
        query["year"] = {}
        if year_min: query["year"]["$gte"] = year_min
        if year_max: query["year"]["$lte"] = year_max
    if min_price or max_price:
        query["current_bid_eur"] = {}
        if min_price: query["current_bid_eur"]["$gte"] = min_price
        if max_price: query["current_bid_eur"]["$lte"] = max_price
    if q:
        import re
        rx = {"$regex": re.escape(q.strip()), "$options": "i"}
        query["$or"] = [{"title": rx}, {"description": rx}, {"make": rx}, {"model": rx}, {"color": rx}]

    cursor = db.auctions.find(query, {"_id": 0}).limit(limit)
    items = await cursor.to_list(limit)
    items = [_public_auction(a, viewer) for a in items]

    # Hide non-public statuses from public listings (pending/rejected/withdrawn/removed/cancelled/paused)
    viewer_is_admin = viewer and viewer.get("role") in ("admin", "moderator")
    if not viewer_is_admin:
        items = [a for a in items if a["status"] in ("live", "ended", "sold", "reserve_not_met") and not a.get("is_archived")]

    if status:
        items = [a for a in items if a["status"] == status]

    if sort == "ending_soon":
        items.sort(key=lambda a: a["ends_at"])
    elif sort == "newest":
        items.sort(key=lambda a: a["created_at"], reverse=True)
    elif sort == "price_asc":
        items.sort(key=lambda a: a["current_bid_eur"])
    elif sort == "price_desc":
        items.sort(key=lambda a: a["current_bid_eur"], reverse=True)
    elif sort == "most_bids":
        items.sort(key=lambda a: a.get("bid_count", 0), reverse=True)

    await _enrich_dealer_status(items)
    return items

@api.get("/auctions/featured")
async def featured(request: Request):
    viewer = await get_optional_user(request)
    # Fetch more than needed then filter in Python for computed "live" status
    raw = await db.auctions.find({"featured": True}, {"_id": 0}).limit(30).to_list(30)
    items = [_public_auction(a, viewer) for a in raw]
    live = [a for a in items if a["status"] == "live"]
    live = live[:6]
    await _enrich_dealer_status(live)
    return live

@api.get("/auctions/sold")
async def sold(
    request: Request,
    make: Optional[str] = None,
    body_type: Optional[str] = None,
    fuel: Optional[str] = None,
    year_min: Optional[int] = None,
    year_max: Optional[int] = None,
    price_min: Optional[float] = None,
    price_max: Optional[float] = None,
    q: Optional[str] = None,
    sort: Optional[str] = Query("recent"),
    limit: int = 48,
    offset: int = 0,
):
    viewer = await get_optional_user(request)
    query: dict = {"status": "sold"}
    if make: query["make"] = make
    if body_type: query["body_type"] = body_type
    if fuel: query["fuel"] = fuel
    if year_min or year_max:
        query["year"] = {}
        if year_min: query["year"]["$gte"] = year_min
        if year_max: query["year"]["$lte"] = year_max
    if price_min or price_max:
        query["current_bid_eur"] = {}
        if price_min: query["current_bid_eur"]["$gte"] = price_min
        if price_max: query["current_bid_eur"]["$lte"] = price_max
    if q:
        import re
        rx = {"$regex": re.escape(q.strip()), "$options": "i"}
        query["$or"] = [{"title": rx}, {"make": rx}, {"model": rx}, {"description": rx}]

    sort_field, sort_dir = "finalized_at", -1
    if sort == "price_desc": sort_field, sort_dir = "current_bid_eur", -1
    elif sort == "price_asc": sort_field, sort_dir = "current_bid_eur", 1
    elif sort == "oldest": sort_field, sort_dir = "finalized_at", 1

    limit = max(1, min(100, int(limit)))
    offset = max(0, int(offset))

    total = await db.auctions.count_documents(query)
    cursor = db.auctions.find(query, {"_id": 0}).sort(sort_field, sort_dir).skip(offset).limit(limit)
    raw = await cursor.to_list(limit)
    items = [_public_auction(a, viewer) for a in raw]
    await _enrich_dealer_status(items)
    # Backwards-compat: return plain list when no pagination requested (offset=0 & small query)
    if offset == 0 and not any([make, body_type, fuel, year_min, year_max, price_min, price_max, q]) and sort == "recent" and limit == 48:
        return items
    return {"items": items, "total": total, "offset": offset, "limit": limit}


@api.get("/stats/sold")
async def stats_sold(days: Optional[int] = None):
    """Public aggregate statistics for sold auctions. Optional `days` window."""
    match: dict = {"status": "sold"}
    if days and days > 0:
        cutoff = (datetime.now(timezone.utc) - timedelta(days=int(days))).isoformat()
        match["finalized_at"] = {"$gte": cutoff}

    pipe = [
        {"$match": match},
        {"$group": {
            "_id": None,
            "count": {"$sum": 1},
            "total_eur": {"$sum": "$current_bid_eur"},
            "avg_eur": {"$avg": "$current_bid_eur"},
            "max_eur": {"$max": "$current_bid_eur"},
            "min_eur": {"$min": "$current_bid_eur"},
            "avg_mileage": {"$avg": "$mileage_km"},
        }},
    ]
    totals_cur = db.auctions.aggregate(pipe)
    totals_doc = await totals_cur.to_list(1)
    totals = totals_doc[0] if totals_doc else {}
    totals.pop("_id", None)

    # Median (fetch prices, compute in Python — small dataset)
    prices_cur = db.auctions.find(match, {"_id": 0, "current_bid_eur": 1}).sort("current_bid_eur", 1)
    prices = [float(p["current_bid_eur"]) async for p in prices_cur]
    median_eur = 0.0
    if prices:
        n = len(prices)
        median_eur = prices[n // 2] if n % 2 else (prices[n // 2 - 1] + prices[n // 2]) / 2

    # By make (top 10)
    by_make_cur = db.auctions.aggregate([
        {"$match": match},
        {"$group": {"_id": "$make", "count": {"$sum": 1}, "avg_eur": {"$avg": "$current_bid_eur"}, "total_eur": {"$sum": "$current_bid_eur"}}},
        {"$sort": {"count": -1}},
        {"$limit": 10},
    ])
    by_make = [
        {"make": d["_id"] or "—", "count": d["count"], "avg_eur": round(d["avg_eur"] or 0, 2), "total_eur": round(d["total_eur"] or 0, 2)}
        async for d in by_make_cur
    ]

    # By body type
    by_body_cur = db.auctions.aggregate([
        {"$match": match},
        {"$group": {"_id": "$body_type", "count": {"$sum": 1}, "avg_eur": {"$avg": "$current_bid_eur"}}},
        {"$sort": {"count": -1}},
    ])
    by_body = [
        {"body_type": d["_id"] or "—", "count": d["count"], "avg_eur": round(d["avg_eur"] or 0, 2)}
        async for d in by_body_cur
    ]

    # Monthly trend (last 12 months)
    month_cur = db.auctions.aggregate([
        {"$match": {**match, "finalized_at": match.get("finalized_at", {"$exists": True})}},
        {"$addFields": {"fin_month": {"$substr": ["$finalized_at", 0, 7]}}},
        {"$group": {"_id": "$fin_month", "count": {"$sum": 1}, "avg_eur": {"$avg": "$current_bid_eur"}, "total_eur": {"$sum": "$current_bid_eur"}}},
        {"$sort": {"_id": -1}},
        {"$limit": 12},
    ])
    by_month = [
        {"month": d["_id"] or "—", "count": d["count"], "avg_eur": round(d["avg_eur"] or 0, 2), "total_eur": round(d["total_eur"] or 0, 2)}
        async for d in month_cur
    ]
    by_month.reverse()  # chronological

    # Highest sale (single)
    highest_doc = await db.auctions.find_one(match, {"_id": 0, "id": 1, "title": 1, "current_bid_eur": 1, "images": 1, "year": 1, "make": 1, "model": 1, "finalized_at": 1}, sort=[("current_bid_eur", -1)])

    return {
        "window_days": days,
        "total_count": int(totals.get("count", 0) or 0),
        "total_volume_eur": round(totals.get("total_eur", 0) or 0, 2),
        "avg_price_eur": round(totals.get("avg_eur", 0) or 0, 2),
        "median_price_eur": round(median_eur, 2),
        "min_price_eur": round(totals.get("min_eur", 0) or 0, 2),
        "max_price_eur": round(totals.get("max_eur", 0) or 0, 2),
        "avg_mileage_km": round(totals.get("avg_mileage", 0) or 0, 0),
        "by_make": by_make,
        "by_body_type": by_body,
        "by_month": by_month,
        "highest_sale": highest_doc,
    }

@api.get("/auctions/facets")
async def facets():
    makes = await db.auctions.distinct("make")
    fuels = await db.auctions.distinct("fuel")
    transmissions = await db.auctions.distinct("transmission")
    regions = await db.auctions.distinct("region")
    body_types = await db.auctions.distinct("body_type")
    return {
        "makes": sorted(makes),
        "fuels": sorted(fuels),
        "transmissions": sorted(transmissions),
        "regions": sorted(regions),
        "body_types": sorted(body_types),
    }

@api.get("/auctions/{auction_id}")
async def get_auction(auction_id: str, request: Request):
    viewer = await get_optional_user(request)
    a = await db.auctions.find_one({"id": auction_id}, {"_id": 0})
    if not a:
        raise HTTPException(status_code=404, detail="Търгът не е намерен")
    # Phase 4: views counter (increment once per request; bots included is ok for MVP)
    try:
        await db.auctions.update_one({"id": auction_id}, {"$inc": {"views_count": 1}})
    except Exception:
        pass
    public = _public_auction(a, viewer)
    public["views_count"] = int(a.get("views_count") or 0) + 1
    # Enrich with seller verified status (platform listings are considered verified)
    seller_id = a.get("seller_id")
    if seller_id == "platform":
        public["seller_is_verified_dealer"] = True
    else:
        seller = await db.users.find_one({"id": seller_id}, {"_id": 0, "is_verified_dealer": 1}) if seller_id else None
        public["seller_is_verified_dealer"] = bool(seller and seller.get("is_verified_dealer"))
    # Reveal full VIN to: seller, admin (always), or bidders (only while auction is live).
    # On ended/sold/cancelled auctions the VIN stays masked for bidders — privacy of the sold vehicle.
    if a.get("vin") and viewer:
        is_privileged = viewer.get("role") == "admin" or viewer.get("id") == a.get("seller_id")
        if not is_privileged and _auction_status(a) == "live":
            from services import bidding as bidding_svc
            is_privileged = await bidding_svc.has_user_bid(auction_id, viewer["id"])
        if is_privileged:
            public["vin"] = a["vin"].strip().upper()
            public["vin_masked"] = False
    # Expose cached translations (if any) so the frontend can avoid extra calls
    public["description_ro"] = a.get("description_ro") or ""
    public["description_en"] = a.get("description_en") or ""
    return public


@api.get("/healthz")
async def healthz():
    """Simple liveness probe for container orchestrators. Does not touch Mongo
    to avoid cascade failures — use `/readyz` for readiness with DB ping."""
    return {"status": "ok"}


@api.get("/readyz")
async def readyz():
    """Readiness probe: verifies MongoDB connectivity."""
    try:
        await db.command("ping")
        return {"status": "ready"}
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"db unavailable: {e}")


@api.get("/auctions/{auction_id}/translate-description")
@limiter.limit("20/minute")
async def translate_auction_description(
    auction_id: str, request: Request, lang: str = Query(..., regex="^(ro|en|bg)$"),
):
    """Auto-translate auction description into target language, cache result, return it.

    Subsequent calls return the cached value for the same (auction, lang) tuple
    unless the seller updates the description (which clears cached translations).
    """
    a = await db.auctions.find_one({"id": auction_id}, {"_id": 0})
    if not a:
        raise HTTPException(status_code=404, detail="Обявата не е намерена")
    if lang == "bg":
        # Canonical text is already Bulgarian — nothing to do.
        return {"lang": "bg", "text": a.get("description") or "", "cached": True}
    cache_key = f"description_{lang}"
    cached = a.get(cache_key)
    if cached:
        return {"lang": lang, "text": cached, "cached": True}
    source = (a.get("description") or "").strip()
    if not source:
        return {"lang": lang, "text": "", "cached": False}
    from translate import translate_text  # local import to avoid cycles at boot
    translated = await translate_text(source, lang)
    if not translated:
        raise HTTPException(status_code=503, detail="Translation service unavailable")
    await db.auctions.update_one({"id": auction_id}, {"$set": {cache_key: translated}})
    return {"lang": lang, "text": translated, "cached": False}

@api.post("/auctions")
@limiter.limit("10/minute")
async def create_auction(request: Request, payload: AuctionCreate, user: dict = Depends(get_current_user)):
    # --- Size limits (DoS protection against huge base64 images) ---
    # Each image is a base64 data URL or https URL. Cap per-image + total payload.
    MAX_PER_IMG = 5 * 1024 * 1024        # 5 MB per image (base64 overhead considered)
    MAX_TOTAL_IMGS = 120
    MAX_TOTAL_PAYLOAD = 120 * 1024 * 1024  # 120 MB aggregate

    total_bytes = 0
    total_count = 0
    for bucket in (payload.images, payload.images_exterior, payload.images_wheels,
                   payload.images_bumper, payload.images_interior):
        if not bucket:
            continue
        for item in bucket:
            if not isinstance(item, str):
                continue
            size = len(item)
            if size > MAX_PER_IMG:
                raise HTTPException(status_code=413, detail="Една от снимките е твърде голяма (макс. 5 MB всяка)")
            total_bytes += size
            total_count += 1
    if total_count > MAX_TOTAL_IMGS:
        raise HTTPException(status_code=413, detail=f"Твърде много снимки (макс. {MAX_TOTAL_IMGS})")
    if total_bytes > MAX_TOTAL_PAYLOAD:
        raise HTTPException(status_code=413, detail="Общият размер на снимките надвишава 120 MB")

    # Validate per-category image minimums (when using categorized uploader)
    exterior = payload.images_exterior or []
    wheels = payload.images_wheels or []
    bumper = payload.images_bumper or []
    interior = payload.images_interior or []
    has_categorized = bool(exterior or wheels or bumper or interior)
    if has_categorized:
        errors = []
        if len(exterior) < 8: errors.append(f"минимум 8 екстериорни снимки (имате {len(exterior)})")
        if len(wheels) < 4: errors.append(f"минимум 4 снимки на джанти (имате {len(wheels)})")
        if len(bumper) < 1: errors.append(f"минимум 1 снимка на предната броня (имате {len(bumper)})")
        if len(interior) < 4: errors.append(f"минимум 4 интериорни снимки (имате {len(interior)})")
        if errors:
            raise HTTPException(status_code=400, detail="Снимките са непълни: " + "; ".join(errors))

    # Build merged images list in natural viewing order: exterior first, then bumper, wheels, interior
    merged = []
    if has_categorized:
        merged = [*exterior, *bumper, *wheels, *interior]
    else:
        merged = list(payload.images or [])

    auction_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc)
    ends_at = now + timedelta(days=payload.duration_days)
    doc = payload.model_dump()
    # Offload images to configured storage backend (inline|s3). Runs in a
    # worker thread so a slow S3 upload doesn't stall the event loop.
    from storage import store_images
    merged = await asyncio.to_thread(store_images, merged)
    doc["images"] = merged

    # ---- VAT validation ----
    vat = (doc.get("vat_status") or "").strip() or None
    if vat and vat not in ("exempt", "vat_inclusive"):
        raise HTTPException(status_code=400, detail="vat_status трябва да е 'exempt' или 'vat_inclusive'")
    if vat == "vat_inclusive":
        if not doc.get("price_net_eur") or not doc.get("price_gross_eur"):
            raise HTTPException(status_code=400, detail="За 'неосвободена от ДДС' са задължителни нетна и брутна цена")
        if float(doc["price_gross_eur"]) <= float(doc["price_net_eur"]):
            raise HTTPException(status_code=400, detail="Брутната цена трябва да е по-голяма от нетната")
    else:
        doc["price_net_eur"] = None
        doc["price_gross_eur"] = None

    # ---- No-reserve flag ----
    if doc.get("no_reserve"):
        doc["reserve_eur"] = None

    # ---- Validate make is in the known catalog (if any makes seeded) ----
    known_make = await db.makes.find_one({"name": doc.get("make", "")}, {"_id": 0, "name": 1})
    total_makes = await db.makes.count_documents({})
    if total_makes > 0 and not known_make:
        raise HTTPException(status_code=400, detail=f"Неизвестна марка '{doc.get('make','')}'. Изберете от списъка или помолете админ да я добави.")

    doc.update({
        "id": auction_id,
        "seller_id": user["id"],
        "seller_name": user["name"],
        "current_bid_eur": payload.starting_bid_eur,
        "bid_count": 0,
        "created_at": now.isoformat(),
        "ends_at": ends_at.isoformat(),
        "status": "pending",  # awaiting approval
        "featured": False,
        "is_archived": False,
    })
    await db.auctions.insert_one(doc)
    return {"id": auction_id, "status": "pending"}


# ---- Public makes catalog ----
@api.get("/makes")
async def list_makes():
    """Public list of approved car makes (alphabetical)."""
    items = await db.makes.find({}, {"_id": 0, "id": 1, "name": 1}).sort("name", 1).to_list(1000)
    return items


@api.post("/auctions/{auction_id}/duplicate")
async def duplicate_auction(auction_id: str, user: dict = Depends(get_current_user)):
    """Seller duplicates their own (or admin any) auction as a new pending draft."""
    src = await db.auctions.find_one({"id": auction_id}, {"_id": 0})
    if not src:
        raise HTTPException(status_code=404, detail="Обявата не е намерена")
    if src.get("seller_id") != user["id"] and user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Нямате права да дублирате тази обява")

    new_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc)
    clone = {k: v for k, v in src.items() if k not in ("id", "_id", "current_bid_eur", "bid_count",
                                                        "high_bidder_id", "high_bidder_name", "status",
                                                        "created_at", "ends_at", "finalized_at",
                                                        "featured", "is_archived", "reactivated_at",
                                                        "paused", "paused_at", "premium_captured")}
    clone.update({
        "id": new_id,
        "seller_id": user["id"],
        "seller_name": user["name"],
        "title": f"{src.get('title','Обява')} (копие)",
        "current_bid_eur": src.get("starting_bid_eur", 0),
        "bid_count": 0,
        "status": "pending",
        "featured": False,
        "is_archived": False,
        "created_at": now.isoformat(),
        "ends_at": (now + timedelta(days=10)).isoformat(),
        "duplicated_from": auction_id,
    })
    await db.auctions.insert_one(clone)
    return {"id": new_id, "status": "pending"}


# ---- Mobile.bg import ----
class MobileBgImport(BaseModel):
    url: Optional[str] = None
    html: Optional[str] = None  # alternate: raw pasted HTML/text from the page


_MOBILEBG_FUEL_MAP = {
    "бензинов": "Бензин", "бензин": "Бензин",
    "дизелов": "Дизел", "дизел": "Дизел",
    "хибриден": "Хибриден", "хибрид": "Хибриден",
    "електрически": "Електрически", "електро": "Електрически",
    "газ/бензин": "Газ/Бензин", "lpg": "Газ/Бензин", "метан": "Газ/Бензин",
}
_MOBILEBG_TRANS_MAP = {
    "автоматична": "Автоматична", "автоматичнa": "Автоматична", "автоматик": "Автоматична",
    "ръчна": "Ръчна", "ръчни": "Ръчна", "механична": "Ръчна",
}
_MOBILEBG_BODY_MAP = {
    "седан": "Седан", "хечбек": "Хечбек", "комби": "Комби",
    "джип": "Джип", "suv": "Джип", "кросоувър": "Джип",
    "купе": "Купе", "кабрио": "Кабрио", "кабриолет": "Кабрио",
    "ван": "Ван", "миниван": "Ван", "пикап": "Пикап",
}


def _normalize(val: str, mapping: dict, default: str = "") -> str:
    if not val:
        return default
    low = val.strip().lower()
    for k, v in mapping.items():
        if k in low:
            return v
    return default


@api.post("/auctions/import-mobile-bg")
@limiter.limit("10/minute")
async def import_from_mobile_bg(request: Request, payload: MobileBgImport, user: dict = Depends(get_current_user)):
    """Scrapes a mobile.bg listing URL and returns a dict of pre-filled auction fields.
    Does NOT include price (user must set it themselves)."""
    from bs4 import BeautifulSoup
    import re as _re

    url = (payload.url or "").strip()
    pasted_html = (payload.html or "").strip()

    # SSRF protection: accept only known mobile.bg hostnames (scheme must be http/https).
    if url:
        from urllib.parse import urlparse
        p = urlparse(url)
        if p.scheme not in ("http", "https"):
            raise HTTPException(status_code=400, detail="Невалиден URL (разрешени са само http/https)")
        host = (p.hostname or "").lower()
        if not (host == "mobile.bg" or host.endswith(".mobile.bg")):
            raise HTTPException(status_code=400, detail="Разрешени са само URL-и от mobile.bg")

    html = None
    if pasted_html:
        html = pasted_html
    else:
        if not url:
            raise HTTPException(status_code=400, detail="Поставете линк към обявата в mobile.bg или копирайте съдържанието на страницата")
        if not url.startswith("http"):
            url = "https://" + url
        if "mobile.bg" not in url:
            raise HTTPException(status_code=400, detail="Поддържат се само линкове от mobile.bg")

        try:
            from curl_cffi import requests as curl_requests
            import asyncio as _asyncio

            impersonations = ["chrome131", "chrome124", "safari17_0"]
            resp = None
            last_status = None
            for imp in impersonations:
                def _fetch(_imp=imp):
                    return curl_requests.get(
                        url,
                        impersonate=_imp,
                        timeout=20,
                        headers={
                            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
                            "Accept-Language": "bg-BG,bg;q=0.9,en-US;q=0.8,en;q=0.7",
                            "Upgrade-Insecure-Requests": "1",
                            "Referer": "https://www.google.com/",
                        },
                        allow_redirects=True,
                    )

                loop = _asyncio.get_event_loop()
                r = await loop.run_in_executor(None, _fetch)
                last_status = r.status_code
                if r.status_code < 400 and len(r.text) > 3000 and "затруднения" not in r.text:
                    resp = r
                    break

            # Fallback: public CORS/scrape proxies — mobile.bg blocks datacenter IPs
            if resp is None:
                import urllib.parse as _urlparse
                enc = _urlparse.quote(url, safe="")
                proxy_urls = [
                    f"https://api.codetabs.com/v1/proxy/?quest={url}",
                    f"https://corsproxy.io/?url={enc}",
                    f"https://api.allorigins.win/raw?url={enc}",
                    f"https://thingproxy.freeboard.io/fetch/{url}",
                ]

                for proxy_url in proxy_urls:
                    def _fetch_proxy(_p=proxy_url):
                        return curl_requests.get(_p, timeout=25, impersonate="chrome124", allow_redirects=True)
                    try:
                        r = await loop.run_in_executor(None, _fetch_proxy)
                        if r.status_code < 400 and len(r.content) > 10000:
                            # Check that body contains actual cyrillic text (not CF block)
                            try:
                                decoded_test = r.content.decode("windows-1251", errors="ignore")
                                if "Бензин" in decoded_test or "Дизел" in decoded_test or "куб" in decoded_test or "Двигател" in decoded_test:
                                    resp = r
                                    break
                            except Exception:
                                pass
                    except Exception:
                        continue

            if resp is None:
                raise HTTPException(
                    status_code=502,
                    detail="Не успяхме да заредим обявата. Моля проверете линка.",
                )

            try:
                # mobile.bg често сервира страниците в windows-1251
                raw = resp.content
                if b"windows-1251" in raw[:1024].lower():
                    html = raw.decode("windows-1251", errors="ignore")
                else:
                    html = resp.text
            except Exception:
                html = resp.text
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=502, detail=f"Неуспешна връзка с mobile.bg: {e}")

    # Decode windows-1251 if needed
    if "<meta" in html and "windows-1251" in html.lower() and "Ã" in html:
        try:
            html = resp.content.decode("windows-1251", errors="ignore")
        except Exception:
            pass

    soup = BeautifulSoup(html, "lxml")
    full_text = soup.get_text(" ", strip=True)

    # Title: try h1 first
    title = ""
    h1 = soup.find("h1")
    if h1:
        title = h1.get_text(" ", strip=True)
    if not title:
        title_tag = soup.find("title")
        if title_tag:
            title = title_tag.get_text(" ", strip=True).split("|")[0].strip()

    # Strip any "Обява: <id>" / "ID: <id>" suffix or prefix (mobile.bg shows listing id in h1)
    def _strip_listing_id(s: str) -> str:
        if not s:
            return s
        s = _re.sub(r"\s*(?:Обява|ID|No\.?)[:\s]*\d+\s*", " ", s, flags=_re.IGNORECASE)
        s = _re.sub(r"\s{2,}", " ", s).strip(" -—|")
        return s

    title = _strip_listing_id(title)

    # Extract make + model from title: "BMW X5 3.0d — ..." -> make=BMW, model="X5 ..."
    make = ""
    model = ""
    if title:
        clean_title = title
        parts = clean_title.split()
        if len(parts) >= 2:
            make = parts[0]
            # Take everything up to year or dash (up to first 5 words max)
            model_parts = []
            for w in parts[1:6]:
                if _re.match(r"^(19[5-9]\d|20[0-2]\d)[.,г]*$", w):
                    break
                if w in ("-", "—", "–"):
                    break
                model_parts.append(w)
            model = " ".join(model_parts).strip()

    # Year: first 4-digit number between 1950-2030
    year_match = _re.search(r"\b(19[5-9]\d|20[0-2]\d|20[3-5]\d)\s*г\.?", full_text) or _re.search(r"\b(19[5-9]\d|20[0-2]\d|20[3-5]\d)\b", full_text)
    year = int(year_match.group(1)) if year_match else 0

    # Mileage: look for " 123 456 км" or "123456 км"
    mileage = 0
    mi = _re.search(r"([\d\s]{3,10})\s*км", full_text)
    if mi:
        try: mileage = int(mi.group(1).replace(" ", "").replace(",", ""))
        except Exception: pass

    # Power hp
    power = 0
    pm = _re.search(r"(\d{2,4})\s*(к\.с\.|кс|hp)", full_text, _re.IGNORECASE)
    if pm:
        try: power = int(pm.group(1))
        except Exception: pass

    # Engine cc — try multiple patterns in order:
    # 1) Modern mobile.bg "item" block: <div class="item"><div>Кубатура [куб.см]</div><div>3000 см<sup>3</sup></div></div>
    # 2) Legacy mpLabel/mpInfo structure
    # 3) Explicit "XXXX куб.см" / "XXXX cc" anywhere in text
    # 4) Liter notation "2.0L", "3.0i", "2.0 TDI/TFSI/CDI/TSI" in title/description
    engine_cc = 0

    # (1) Modern "item" spec row — find div.item whose first inner div mentions Кубатура/Обем,
    #     then grab the first digit-group from the sibling value div.
    for item in soup.select("div.item"):
        kids = item.find_all("div", recursive=False)
        if len(kids) >= 2:
            label_txt = kids[0].get_text(" ", strip=True)
            if _re.search(r"\b(Кубатура|Обем)\b", label_txt, _re.IGNORECASE):
                val_txt = kids[1].get_text(" ", strip=True)
                m = _re.search(r"(\d{3,5})", val_txt)
                if m:
                    try:
                        engine_cc = int(m.group(1))
                        break
                    except Exception:
                        pass

    # (2) Legacy structured field
    if not engine_cc:
        for label_m in _re.finditer(r'mpLabel[^>]*>\s*(Обем|Кубатура)\s*[\[\(]?[^<]*?[<][\w\s="/]*?mpInfo[^>]*>\s*(\d+)', html):
            try:
                engine_cc = int(label_m.group(2))
                break
            except Exception:
                pass

    # (3) plain text patterns
    if not engine_cc:
        m = _re.search(r"(\d{3,4})\s*куб\.?\s*см", full_text, _re.IGNORECASE) or _re.search(r"(\d{3,4})\s*cc\b", full_text, _re.IGNORECASE) or _re.search(r"(?:Обем|Кубатура)[^0-9]{0,40}(\d{3,5})", full_text)
        if m:
            try: engine_cc = int(m.group(1))
            except Exception: pass

    # (4) liter notation, e.g. "2.0 TDI", "3.0L", "1.8 TSI", "3.0i"
    if not engine_cc:
        search_src = f"{title}\n{model}\n{full_text[:800]}"
        m = _re.search(r"\b([1-6])[\.,]([0-9])\s*(?:[LlЛл]|TDI|TFSI|TSI|CDI|CRDI|HDI|dCi|THP|MultiAir|Ecoboost|Turbo|[ivtdбa-я]{1,4})?\b", search_src)
        if m:
            try:
                engine_cc = int(m.group(1) + m.group(2) + "00")
            except Exception:
                pass

    # Validate range
    if engine_cc and (engine_cc < 500 or engine_cc > 8500):
        engine_cc = 0

    # Fuel / Transmission / Body - find in text
    fuel = _normalize(full_text, _MOBILEBG_FUEL_MAP, "Бензин")
    transmission = _normalize(full_text, _MOBILEBG_TRANS_MAP, "Ръчна")
    # Body type: check ordered list so "Купе"/"Кабрио" match before "джип"/"suv"
    body_type = "Седан"
    body_order = ["кабриолет", "кабрио", "купе", "комби", "хечбек", "джип", "suv", "кросоувър", "ван", "пикап", "седан"]
    lowered = full_text.lower()
    # Look specifically for "Категория" keyword for precise match
    cat = _re.search(r"Категория[:\s]+([А-Яа-я\-]+)", full_text)
    if cat:
        body_type = _normalize(cat.group(1), _MOBILEBG_BODY_MAP, body_type)
    else:
        for key in body_order:
            if key in lowered:
                body_type = _MOBILEBG_BODY_MAP.get(key, body_type)
                break

    # Spec-row lookup: mobile.bg renders "<div class='item'><div>Label</div><div>Value</div></div>"
    # Build a dict of {label: value} for all spec items in one pass.
    spec_items: dict = {}
    for item in soup.select("div.item"):
        kids = item.find_all("div", recursive=False)
        if len(kids) >= 2:
            label = kids[0].get_text(" ", strip=True).strip(":")
            # Strip unit suffixes in brackets: "Кубатура [куб.см]" → "Кубатура"
            label_clean = _re.sub(r"\s*\[[^\]]*\]\s*$", "", label).strip()
            value = kids[1].get_text(" ", strip=True)
            if label_clean and value:
                spec_items[label_clean] = value
                # Also keep original key (with brackets) for diagnostics
                spec_items[label] = value

    # Color: prefer structured spec row, fall back to regex on full text.
    color = spec_items.get("Цвят", "").strip()
    if not color:
        cm = _re.search(r"Цвят[:\s]+([А-Яа-я\s\-]{3,30}?)(?=\s+(?:Регион|Град|Населено|Гориво|Двигател|Пробег|Скорост|Мощност|[А-Я][а-я]{5,}:)|[,\.;|\n])", full_text)
        if cm:
            color = cm.group(1).strip(".,; ")

    # Location: structured "Регион" / "Населено място" / "Град" first.
    city = (
        spec_items.get("Населено място")
        or spec_items.get("Град")
        or spec_items.get("Регион")
        or ""
    ).strip()
    if not city:
        # mobile.bg also places the city in <div class="grad"><span>София</span></div>
        grad = soup.select_one("div.grad span")
        if grad:
            city = grad.get_text(" ", strip=True)
    if not city:
        # "Намира се в гр. София" → "София"
        loc_m = _re.search(r"(?:Намира се в|Град|гр\.)\s*([А-Я][А-Яа-я\s\-]{2,40}?)(?=[,\.\|<\n]|$)", full_text)
        if loc_m:
            city = loc_m.group(1).strip(" .,")
    if not city:
        lm = _re.search(r"(?:Регион|Населено място|Град)[:\s]+([А-Яа-я\s]+?)(?=\s{2,}|[,\.\|]|\n)", full_text)
        if lm:
            city = lm.group(1).strip()

    # Description: typically in div.moreInfo > div.text on mobile.bg.
    # Skip the "Допълнителна информация" header block (it's just a section title).
    description = ""
    # Prefer the inner text div which contains the seller's actual description
    inner = soup.select_one("div.moreInfo div.text") or soup.select_one("div.moreInfo > .text")
    if inner:
        description = inner.get_text("\n", strip=True)
    else:
        for sel in ["div.moreInfo", "div.car-details", "div.description", "[id*=More]", "[id*=Comments]"]:
            el = soup.select_one(sel)
            if el:
                description = el.get_text("\n", strip=True)
                break
    # Strip any leading "Допълнителна информация" heading that leaked in
    if description:
        description = _re.sub(r"^\s*Допълнителна\s+информация\s*\n?", "", description, flags=_re.IGNORECASE)
        description = description.strip()
    if not description and h1:
        # fallback: try next sibling paragraphs
        paragraphs = [p.get_text(" ", strip=True) for p in soup.find_all("p") if len(p.get_text(strip=True)) > 40]
        description = "\n\n".join(paragraphs[:3])

    # Images: find all img tags with large photos
    images = []
    for img in soup.find_all("img"):
        src = img.get("src") or img.get("data-src") or ""
        if not src:
            continue
        if src.startswith("//"):
            src = "https:" + src
        elif src.startswith("/"):
            src = "https://www.mobile.bg" + src
        if ("mobile.bg" in src or src.startswith("http")) and any(x in src.lower() for x in ["photo", "pic", "big", "jpg", "jpeg", "png", "webp"]):
            low = src.lower()
            if src not in images and not any(bad in low for bad in ["logo", "icon", "nophoto", "placeholder", "sprite", "avatar"]):
                images.append(src)
        if len(images) >= 24:
            break

    return {
        "title": title[:120] if title else "",
        "make": make,
        "model": model.strip(),
        "year": year,
        "mileage_km": mileage,
        "fuel": fuel,
        "transmission": transmission,
        "body_type": body_type,
        "power_hp": power,
        "engine_cc": engine_cc,
        "color": color,
        "city": city,
        "description": description[:3500] if description else "",
        "images": images,
        "source_url": url or "",
    }



# ---- Bids ----
@api.get("/auctions/{auction_id}/bids")
async def list_bids(auction_id: str):
    from services import bidding as bidding_svc
    return await bidding_svc.list_bids(auction_id, limit=50)


# ---- Bidding Credit (pre-authorization for multiple bids) ----
@api.get("/auctions/{auction_id}/bidding-credit")
async def get_my_credit(auction_id: str, user: dict = Depends(get_current_user)):
    credit = await db.bidding_credits.find_one(
        {"auction_id": auction_id, "user_id": user["id"], "status": "authorized"},
        {"_id": 0},
    )
    return credit or None


@api.post("/auctions/{auction_id}/bidding-credit")
async def create_or_increase_credit(auction_id: str, payload: BiddingCreditCreate, user: dict = Depends(get_current_user)):
    a = await db.auctions.find_one({"id": auction_id}, {"_id": 0})
    if not a:
        raise HTTPException(status_code=404, detail="Търгът не е намерен")
    if _auction_status(a) != "live":
        raise HTTPException(status_code=400, detail="Търгът не е активен")
    if a.get("seller_id") == user["id"]:
        raise HTTPException(status_code=400, detail="Не можете да създавате credit за собствен търг")
    min_credit = float(a["current_bid_eur"]) + 100
    if payload.max_amount_eur < min_credit:
        raise HTTPException(status_code=400, detail=f"Максималната сума трябва да е поне €{int(min_credit)} (следваща наддавка)")

    now = datetime.now(timezone.utc)
    now_iso = now.isoformat()
    preauth_amount = round(float(payload.max_amount_eur) * 0.02, 2)

    existing = await db.bidding_credits.find_one(
        {"auction_id": auction_id, "user_id": user["id"], "status": "authorized"},
        {"_id": 0},
    )
    if existing:
        # Can only INCREASE, never decrease while active
        if payload.max_amount_eur <= float(existing.get("max_amount_eur", 0)):
            raise HTTPException(
                status_code=400,
                detail=f"Активният ви кредит е €{int(existing['max_amount_eur']):,}. Можете само да го увеличите.",
            )
        # Mock Stripe incremental authorization — keep same preauth_id, bump amount
        await db.bidding_credits.update_one(
            {"id": existing["id"]},
            {"$set": {
                "max_amount_eur": float(payload.max_amount_eur),
                "preauth_amount_eur": preauth_amount,
                "updated_at": now_iso,
            }},
        )
        fresh = await db.bidding_credits.find_one({"id": existing["id"]}, {"_id": 0})
        return {"ok": True, "credit": fresh, "action": "increased"}

    # Create new credit
    credit_id = str(uuid.uuid4())
    doc = {
        "id": credit_id,
        "auction_id": auction_id,
        "user_id": user["id"],
        "user_name": user["name"],
        "max_amount_eur": float(payload.max_amount_eur),
        "preauth_id": f"mock_pi_credit_{uuid.uuid4().hex[:16]}",
        "preauth_amount_eur": preauth_amount,
        "status": "authorized",
        "card_last4": payload.payment_method_id[-4:] if payload.payment_method_id else None,
        "created_at": now_iso,
    }
    await db.bidding_credits.insert_one(doc)
    fresh = {k: v for k, v in doc.items() if k != "_id"}
    return {"ok": True, "credit": fresh, "action": "created"}


@api.delete("/auctions/{auction_id}/bidding-credit")
async def release_my_credit(auction_id: str, user: dict = Depends(get_current_user)):
    a = await db.auctions.find_one({"id": auction_id}, {"_id": 0})
    if not a:
        raise HTTPException(status_code=404, detail="Търгът не е намерен")
    if a.get("high_bidder_id") == user["id"] and _auction_status(a) == "live":
        raise HTTPException(status_code=400, detail="Не можете да освободите кредита докато сте водещ наддавач")
    now_iso = datetime.now(timezone.utc).isoformat()
    res = await db.bidding_credits.update_many(
        {"auction_id": auction_id, "user_id": user["id"], "status": "authorized"},
        {"$set": {"status": "released", "released_at": now_iso}},
    )
    return {"ok": True, "released": res.modified_count}

@api.post("/auctions/{auction_id}/bids")
@limiter.limit("30/minute")
async def place_bid(request: Request, auction_id: str, payload: BidCreate, user: dict = Depends(get_current_user)):
    """
    Direct bidding (BaT-style) — ACID-correct via PostgreSQL.

      • amount_eur is the visible bid; minimum = current + variable step (_bid_step)
      • Concurrent bidders for the same auction are serialised via SELECT FOR UPDATE
        on the bid_state row, so two near-simultaneous bids cannot both win.
      • Hard anti-sniping: any bid in final 2 min resets timer to 2 min.
      • Card hold = buyer fee (5% of bid, min €150, max €4,000).
    """
    from services import bidding as bidding_svc

    a = await db.auctions.find_one({"id": auction_id})
    if not a:
        raise HTTPException(status_code=404, detail="Търгът не е намерен")
    if _auction_status(a) != "live":
        raise HTTPException(status_code=400, detail="Търгът не е активен")
    if a.get("seller_id") == user["id"]:
        raise HTTPException(status_code=400, detail="Не можете да наддавате за собствен автомобил")

    # Phase 3: platform suspension or per-auction bid block?
    if user.get("suspended"):
        raise HTTPException(status_code=403, detail="Акаунтът е временно спрян от наддаване. Свържете се с поддръжка.")
    blk = await db.bid_blocks.find_one({"auction_id": auction_id, "user_id": user["id"]}, {"_id": 0, "id": 1})
    if blk:
        raise HTTPException(status_code=403, detail="Не можете да наддавате за тази обява — достъпът е ограничен.")

    amount = float(payload.amount_eur)
    now = datetime.now(timezone.utc)

    # Bidding credit or fresh preauth?
    credit = await db.bidding_credits.find_one(
        {"auction_id": auction_id, "user_id": user["id"], "status": "authorized"},
        {"_id": 0},
    )
    credit_covers = bool(credit and float(credit.get("max_amount_eur", 0)) >= amount)
    if not credit_covers and not payload.payment_method_id:
        raise HTTPException(status_code=402, detail="Необходима е валидна карта за наддаване")

    bid_id = str(uuid.uuid4())
    fee_amount = _buyer_fee(amount)

    # Release this user's previous active preauths on this auction (only if not credit-backed)
    if not credit_covers:
        await bidding_svc.release_user_active_preauths(auction_id, user["id"])

    if credit_covers:
        preauth_id = credit["preauth_id"]
        preauth_status_val = "credit_backed"
        card_last4 = credit.get("card_last4")
        credit_id_val = credit["id"]
    else:
        preauth_id = f"mock_pi_{uuid.uuid4().hex[:16]}"
        preauth_status_val = "authorized"
        card_last4 = payload.payment_method_id[-4:] if payload.payment_method_id else None
        credit_id_val = None

    # ACID-correct placement (locks bid_state, validates, inserts, updates)
    try:
        result = await bidding_svc.place_bid(
            auction_id=auction_id,
            user_id=user["id"],
            user_name=user["name"],
            amount_eur=amount,
            bid_id=bid_id,
            preauth_id=preauth_id,
            preauth_status=preauth_status_val,
            preauth_amount_eur=fee_amount,
            card_last4=card_last4,
            credit_id=credit_id_val,
            fallback_starting_bid_eur=float(a.get("current_bid_eur", 0)),
            fallback_ends_at=datetime.fromisoformat(a["ends_at"]),
            bid_step_fn=_bid_step,
            extension_minutes=2,
        )
    except ValueError as ve:
        # min_bid:<value>
        if str(ve).startswith("min_bid:"):
            min_next = float(str(ve).split(":", 1)[1])
            raise HTTPException(status_code=400, detail=f"Минималната следваща наддавка е €{int(min_next)}")
        raise

    triggered_extension = result["triggered_extension"]
    new_ends_at_iso = result["ends_at"]

    # Release previous leader's preauth/credit + email them (Postgres + Mongo)
    prev_high = a.get("high_bidder_id")
    if prev_high and prev_high != user["id"]:
        await bidding_svc.release_user_active_preauths(auction_id, prev_high)
        await db.bidding_credits.update_many(
            {"auction_id": auction_id, "user_id": prev_high, "status": "authorized"},
            {"$set": {"status": "released", "released_at": now.isoformat()}},
        )
        prev_user = await db.users.find_one({"id": prev_high}, {"_id": 0})
        if prev_user and prev_user.get("email"):
            try:
                await email_outbid(prev_user["email"], prev_user["name"], a["title"], auction_id, amount)
            except Exception as e:
                logger.error("email_outbid failed: %s", e)
            # Web Push — outbid notification
            try:
                from services import push as push_svc
                await push_svc.send_to_user(
                    prev_high,
                    title=f"Надминати сте · {a['title'][:60]}",
                    body=f"Ново наддаване €{int(amount):,}. Все още можете да отговорите.",
                    url=f"/auctions/{auction_id}",
                    tag=f"outbid-{auction_id}",
                )
            except Exception as e:
                logger.error("push outbid failed: %s", e)

    # Mirror denormalised fields onto the Mongo auction so the rest of the app
    # (filters, listings, sorting, sitemap) keeps working without a join.
    update = {
        "current_bid_eur": amount,
        "bid_count": result["bid_count"],
        "high_bidder_id": user["id"],
        "high_bidder_name": user["name"],
    }
    if triggered_extension:
        update["ends_at"] = new_ends_at_iso
    await db.auctions.update_one({"id": auction_id}, {"$set": update})

    public_bid = result["bid"]
    await hub.broadcast(auction_id, {
        "type": "bid",
        "auction_id": auction_id,
        "current_bid_eur": amount,
        "high_bidder_name": user["name"],
        "bid_count": result["bid_count"],
        "ends_at": new_ends_at_iso,
        "bid": {k: public_bid.get(k) for k in ("id", "user_id", "user_name", "amount_eur", "created_at")},
    })

    # Notify seller on new bid
    seller_id = a.get("seller_id")
    if seller_id and seller_id != "platform":
        seller = await db.users.find_one({"id": seller_id}, {"_id": 0})
        if seller and seller.get("email"):
            try:
                await email_seller_new_bid(seller["email"], seller.get("name", ""), a["title"], auction_id, user["name"], amount, result["bid_count"])
            except Exception as e:
                logger.error("email_seller_new_bid failed: %s", e)
        # Web Push — your car got a bid
        if seller_id:
            try:
                from services import push as push_svc
                await push_svc.send_to_user(
                    seller_id,
                    title=f"Нова наддавка · {a['title'][:60]}",
                    body=f"{user['name']} наддаде €{int(amount):,}. Общо {result['bid_count']} наддавания.",
                    url=f"/auctions/{auction_id}",
                    tag=f"seller-bid-{auction_id}",
                )
            except Exception as e:
                logger.error("push seller_new_bid failed: %s", e)

    # FOMO SMS blast in final 5 minutes
    new_ends_at = datetime.fromisoformat(new_ends_at_iso.replace("Z", "+00:00"))
    seconds_left = (new_ends_at - now).total_seconds()
    if seconds_left <= 300:
        recipient_ids = set(await bidding_svc.collect_bidder_ids(auction_id, exclude_user_id=user["id"], limit=500))
        async for w in db.watches.find({"auction_id": auction_id}, {"_id": 0, "user_id": 1}).limit(500):
            if w["user_id"] != user["id"]:
                recipient_ids.add(w["user_id"])
        if recipient_ids:
            recipients = await db.users.find(
                {"id": {"$in": list(recipient_ids)}, "sms_opt_in": True, "phone": {"$ne": None, "$ne": ""}},
                {"_id": 0, "phone": 1, "name": 1},
            ).to_list(500)
            mins = max(1, int(seconds_left // 60))
            app_url = os.environ.get("APP_URL", "")
            body = f"autobids.bg: Нова наддавка €{int(amount):,} за {a['title'][:50]}. Остават {mins}м. {app_url}/auctions/{auction_id}"
            for r in recipients:
                if r.get("phone"):
                    try:
                        await send_sms(r["phone"], body)
                    except Exception as e:
                        logger.error("send_sms failed: %s", e)

    return {"ok": True, "bid": public_bid, "preauth_amount_eur": fee_amount, "buyer_fee_eur": fee_amount}


@api.get("/auctions/{auction_id}/next-bid")
async def next_bid_info(auction_id: str):
    """Returns the minimum next valid bid amount and the estimated buyer fee for it."""
    a = await db.auctions.find_one({"id": auction_id}, {"_id": 0, "current_bid_eur": 1, "ends_at": 1, "status": 1})
    if not a:
        raise HTTPException(status_code=404, detail="Търгът не е намерен")
    current = float(a.get("current_bid_eur", 0))
    step = _bid_step(current)
    min_next = current + step
    return {
        "current_bid_eur": current,
        "step_eur": step,
        "min_next_eur": min_next,
        "buyer_fee_eur": _buyer_fee(min_next),
    }





# ---- Comments ----
DELETED_COMMENT_TEXT = "Коментарът е премахнат поради неконструктивно съдържание."


def _public_comment(c: dict, auction: dict) -> dict:
    """Mark owner badge + replace text on deleted comments."""
    d = {k: v for k, v in c.items() if k != "_id"}
    d["is_owner"] = bool(auction.get("seller_id") and d.get("user_id") == auction.get("seller_id"))
    if d.get("deleted"):
        d["text"] = DELETED_COMMENT_TEXT
    return d


@api.get("/comments/{comment_id}/translate")
@limiter.limit("30/minute")
async def translate_comment(comment_id: str, request: Request, lang: str = Query(..., regex="^(ro|en|bg)$")):
    """Auto-translate a single comment into target language and cache result on the comment doc."""
    c = await db.comments.find_one({"id": comment_id}, {"_id": 0})
    if not c:
        raise HTTPException(status_code=404, detail="Comment not found")
    cache_key = f"text_{lang}"
    cached = c.get(cache_key)
    if cached:
        return {"lang": lang, "text": cached, "cached": True}
    source = (c.get("text") or "").strip()
    if not source:
        return {"lang": lang, "text": "", "cached": False}
    from translate import translate_text
    translated = await translate_text(source, lang)
    if not translated:
        raise HTTPException(status_code=503, detail="Translation service unavailable")
    await db.comments.update_one({"id": comment_id}, {"$set": {cache_key: translated}})
    return {"lang": lang, "text": translated, "cached": False}


@api.get("/auctions/{auction_id}/comments")
async def list_comments(auction_id: str):
    a = await db.auctions.find_one({"id": auction_id}, {"_id": 0, "seller_id": 1})
    if not a:
        raise HTTPException(status_code=404, detail="Търгът не е намерен")
    items = await db.comments.find({"auction_id": auction_id}, {"_id": 0}).sort("created_at", -1).limit(200).to_list(200)
    return [_public_comment(c, a) for c in items]

@api.post("/auctions/{auction_id}/comments")
async def add_comment(auction_id: str, payload: CommentCreate, user: dict = Depends(get_current_user)):
    a = await db.auctions.find_one({"id": auction_id}, {"_id": 0})
    if not a:
        raise HTTPException(status_code=404, detail="Търгът не е намерен")
    doc = {
        "id": str(uuid.uuid4()),
        "auction_id": auction_id,
        "user_id": user["id"],
        "user_name": user["name"],
        "text": payload.text.strip(),
        "deleted": False,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.comments.insert_one(doc)
    public = _public_comment(doc, a)
    await hub.broadcast(auction_id, {"type": "comment", "comment": public})

    # Notify seller (unless seller is commenting on own auction or is platform)
    seller_id = a.get("seller_id")
    if seller_id and seller_id != "platform" and seller_id != user["id"]:
        seller = await db.users.find_one({"id": seller_id}, {"_id": 0})
        if seller and seller.get("email"):
            try:
                snippet = (payload.text.strip()[:200] + "…") if len(payload.text.strip()) > 200 else payload.text.strip()
                await email_seller_new_comment(seller["email"], seller.get("name", ""), a["title"], auction_id, user["name"], snippet)
            except Exception as e:
                logger.error("email_seller_new_comment failed: %s", e)

    return public


# ---- Admin ----
async def require_admin(user: dict = Depends(get_current_user)):
    if user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Само администратори")
    return user


async def require_admin_or_moderator(user: dict = Depends(get_current_user)):
    """Moderators have read-only access to settings/CMS, can moderate comments/users.
    Super-admin has all privileges including Stripe CMS + settings writes.
    """
    if user.get("role") not in ("admin", "moderator"):
        raise HTTPException(status_code=403, detail="Нужни са админ или модератор права")
    return user


# ---- Site Settings (CMS) ----
@api.get("/settings")
async def get_public_settings():
    """Public subset of site settings (fee %, SEO, verification tags, page contents)."""
    s = _settings()
    return {
        "buyer_fee_pct": s.get("buyer_fee_pct"),
        "buyer_fee_min_eur": s.get("buyer_fee_min_eur"),
        "buyer_fee_max_eur": s.get("buyer_fee_max_eur"),
        "seo_title": s.get("seo_title"),
        "seo_description": s.get("seo_description"),
        "seo_title_bg": s.get("seo_title_bg") or s.get("seo_title") or "",
        "seo_title_ro": s.get("seo_title_ro") or "",
        "seo_title_en": s.get("seo_title_en") or "",
        "seo_description_bg": s.get("seo_description_bg") or s.get("seo_description") or "",
        "seo_description_ro": s.get("seo_description_ro") or "",
        "seo_description_en": s.get("seo_description_en") or "",
        "google_site_verification": s.get("google_site_verification"),
        "bing_site_verification": s.get("bing_site_verification"),
        "google_analytics_id": s.get("google_analytics_id"),
        "faq_content": s.get("faq_content"),
        "terms_content": s.get("terms_content"),
        "contacts_content": s.get("contacts_content"),
        "fees_content": s.get("fees_content"),
        "how_it_works_content": s.get("how_it_works_content"),
        # Multi-language CMS (falls back to non-suffixed BG version when empty)
        "faq_content_bg": s.get("faq_content_bg") or s.get("faq_content") or "",
        "faq_content_ro": s.get("faq_content_ro") or "",
        "faq_content_en": s.get("faq_content_en") or "",
        "terms_content_bg": s.get("terms_content_bg") or s.get("terms_content") or "",
        "terms_content_ro": s.get("terms_content_ro") or "",
        "terms_content_en": s.get("terms_content_en") or "",
        "contacts_content_bg": s.get("contacts_content_bg") or s.get("contacts_content") or "",
        "contacts_content_ro": s.get("contacts_content_ro") or "",
        "contacts_content_en": s.get("contacts_content_en") or "",
        "fees_content_bg": s.get("fees_content_bg") or s.get("fees_content") or "",
        "fees_content_ro": s.get("fees_content_ro") or "",
        "fees_content_en": s.get("fees_content_en") or "",
        "how_it_works_content_bg": s.get("how_it_works_content_bg") or s.get("how_it_works_content") or "",
        "how_it_works_content_ro": s.get("how_it_works_content_ro") or "",
        "how_it_works_content_en": s.get("how_it_works_content_en") or "",
        "og_image_url": s.get("og_image_url") or "",
        "maintenance_mode": bool(s.get("maintenance_mode")),
        "maintenance_message": s.get("maintenance_message") or "",
        "hero_headline_bg": s.get("hero_headline_bg") or "",
        "hero_subtitle_bg": s.get("hero_subtitle_bg") or "",
        "hero_headline_ro": s.get("hero_headline_ro") or "",
        "hero_subtitle_ro": s.get("hero_subtitle_ro") or "",
        "hero_headline_en": s.get("hero_headline_en") or "",
        "hero_subtitle_en": s.get("hero_subtitle_en") or "",
    }


# moved → routers/admin.py (admin_get_settings, admin_update_settings)


# moved → routers/admin.py (admin_delete_comment)


# ---- Stripe: public config (safe for frontend) + webhook ----
from helpers import stripe_public_config as _stripe_public_config  # noqa: E402
from helpers import stripe_runtime_config as _stripe_runtime_config  # noqa: E402


@api.get("/stripe/public-config")
async def stripe_public_config_endpoint():
    """Used by frontend to init Stripe.js. Secret keys are never exposed."""
    return _stripe_public_config(_settings())


@api.post("/webhooks/stripe")
async def stripe_webhook(request: Request):
    """Stripe webhook receiver. Uses dynamic webhook_secret from admin settings.
    Accepts raw bytes, verifies signature, and logs events. Parsing of specific
    event types (payment_intent.succeeded etc.) will be wired when real Stripe
    PaymentIntents replace the current mock.
    """
    cfg = _stripe_runtime_config(_settings())
    sig_header = request.headers.get("stripe-signature", "")
    body = await request.body()
    if not cfg.get("webhook_secret"):
        logger.warning("[stripe_webhook] received but no webhook_secret configured (mode=%s)", cfg.get("mode"))
        return {"ok": False, "reason": "webhook_secret_not_configured"}

    # Minimal HMAC verification (Stripe-compatible v1 signature)
    # header format: t=TIMESTAMP,v1=SIGNATURE,v0=...
    try:
        import hmac, hashlib
        parts = dict(p.split("=", 1) for p in sig_header.split(",") if "=" in p)
        t = parts.get("t", ""); v1 = parts.get("v1", "")
        signed_payload = f"{t}.{body.decode('utf-8')}".encode("utf-8")
        expected = hmac.new(cfg["webhook_secret"].encode("utf-8"), signed_payload, hashlib.sha256).hexdigest()
        if not hmac.compare_digest(expected, v1):
            raise HTTPException(status_code=400, detail="Invalid signature")
    except HTTPException:
        raise
    except Exception as e:
        logger.error("[stripe_webhook] sig verify failed: %s", e)
        raise HTTPException(status_code=400, detail="Invalid signature format")

    # Persist event for audit / replay
    try:
        import json as _json
        payload = _json.loads(body.decode("utf-8"))
        await db.stripe_events.insert_one({
            "id": payload.get("id"),
            "type": payload.get("type"),
            "mode": cfg.get("mode"),
            "received_at": datetime.now(timezone.utc).isoformat(),
            "data": payload.get("data", {}),
        })
    except Exception as e:
        logger.error("[stripe_webhook] persist failed: %s", e)
    return {"ok": True, "received": True}


@api.get("/admin/pending")
async def admin_pending(_admin: dict = Depends(require_admin_or_moderator)):
    items = await db.auctions.find({"status": "pending"}, {"_id": 0}).sort("created_at", -1).to_list(200)
    return items

@api.post("/admin/auctions/{auction_id}/approve")
async def admin_approve(auction_id: str, _admin: dict = Depends(require_admin)):
    a = await db.auctions.find_one({"id": auction_id}, {"_id": 0})
    if not a:
        raise HTTPException(status_code=404, detail="Обявата не е намерена")
    now = datetime.now(timezone.utc)
    ends_at = now + timedelta(days=int(a.get("duration_days", 10)))
    await db.auctions.update_one({"id": auction_id}, {"$set": {"status": "live", "ends_at": ends_at.isoformat(), "approved_at": now.isoformat()}})
    seller = await db.users.find_one({"id": a.get("seller_id")}, {"_id": 0})
    if seller and seller.get("email"):
        try:
            await email_approved(seller["email"], seller.get("name", ""), a["title"], auction_id)
        except Exception as e:
            logger.error("email_approved failed: %s", e)
    # Notify users with matching saved searches
    try:
        fresh = await db.auctions.find_one({"id": auction_id}, {"_id": 0})
        if fresh:
            await notify_matching_saved_searches(fresh)
    except Exception as e:
        logger.error("saved search notification failed: %s", e)
    return {"ok": True}

@api.post("/admin/auctions/{auction_id}/reject")
async def admin_reject(auction_id: str, payload: AdminDecision, _admin: dict = Depends(require_admin)):
    a = await db.auctions.find_one({"id": auction_id}, {"_id": 0})
    if not a:
        raise HTTPException(status_code=404, detail="Обявата не е намерена")
    await db.auctions.update_one({"id": auction_id}, {"$set": {"status": "rejected", "rejected_reason": payload.reason or ""}})
    seller = await db.users.find_one({"id": a.get("seller_id")}, {"_id": 0})
    if seller and seller.get("email"):
        try:
            await email_rejected(seller["email"], seller.get("name", ""), a["title"], payload.reason or "")
        except Exception as e:
            logger.error("email_rejected failed: %s", e)
    return {"ok": True}

@api.post("/admin/auctions/{auction_id}/finalize")
async def admin_finalize(auction_id: str, _admin: dict = Depends(require_admin)):
    """Releases ALL preauths (no commission captured) and marks auction as sold."""
    from services import bidding as bidding_svc
    a = await db.auctions.find_one({"id": auction_id}, {"_id": 0})
    if not a:
        raise HTTPException(status_code=404, detail="Обявата не е намерена")
    now_iso = datetime.now(timezone.utc).isoformat()
    await bidding_svc.release_all_active_preauths(auction_id)
    # Release all bidding credits too
    await db.bidding_credits.update_many(
        {"auction_id": auction_id, "status": "authorized"},
        {"$set": {"status": "released", "released_at": now_iso}},
    )
    await db.auctions.update_one({"id": auction_id}, {"$set": {"status": "sold", "premium_captured": False}})
    winner_id = a.get("high_bidder_id")
    if winner_id:
        u = await db.users.find_one({"id": winner_id}, {"_id": 0})
        if u:
            try:
                await email_won(u["email"], u["name"], a["title"], auction_id, float(a["current_bid_eur"]))
            except Exception as e:
                logger.error("email_won failed: %s", e)
    return {"ok": True}


@api.post("/admin/auctions/{auction_id}/capture-premium")
async def admin_capture_premium(auction_id: str, _admin: dict = Depends(require_admin)):
    """Captures winner's 2% pre-authorization as buyer's premium. Releases losing bidders' preauths."""
    from services import bidding as bidding_svc
    a = await db.auctions.find_one({"id": auction_id}, {"_id": 0})
    if not a:
        raise HTTPException(status_code=404, detail="Обявата не е намерена")
    now_iso = datetime.now(timezone.utc).isoformat()
    winner_id = a.get("high_bidder_id")

    # Capture winner's bidding credit (preferred) OR their authorized preauth
    captured_amount = 0.0
    if winner_id:
        winner_credit = await db.bidding_credits.find_one(
            {"auction_id": auction_id, "user_id": winner_id, "status": "authorized"},
            {"_id": 0},
        )
        if winner_credit:
            # Capture 2% of actual winning bid, not max credit
            captured_amount = round(float(a.get("current_bid_eur", 0)) * 0.02, 2)
            await db.bidding_credits.update_one(
                {"id": winner_credit["id"]},
                {"$set": {"status": "captured", "captured_at": now_iso, "captured_amount_eur": captured_amount}},
            )
            # Mark the winning bid linked to this credit (in Postgres)
            winner_bid = await bidding_svc.get_winning_bid(auction_id)
            if winner_bid and winner_bid.get("user_id") == winner_id and winner_bid.get("credit_id") == winner_credit["id"]:
                await bidding_svc.mark_winner_capture(auction_id, winner_bid["id"], captured_amount)
        else:
            winner_bid = await bidding_svc.get_winning_bid(auction_id)
            if winner_bid and winner_bid.get("user_id") == winner_id and winner_bid.get("preauth_status") == "authorized":
                captured_amount = float(winner_bid.get("preauth_amount_eur") or 0.0)
                await bidding_svc.mark_winner_capture(auction_id, winner_bid["id"], captured_amount)

    # Release all OTHER authorized preauths and credits
    await bidding_svc.release_all_active_preauths(auction_id)
    await db.bidding_credits.update_many(
        {"auction_id": auction_id, "status": "authorized"},
        {"$set": {"status": "released", "released_at": now_iso}},
    )

    await db.auctions.update_one(
        {"id": auction_id},
        {"$set": {"status": "sold", "premium_captured": True, "premium_amount_eur": captured_amount, "finalized_at": now_iso}},
    )

    if winner_id:
        u = await db.users.find_one({"id": winner_id}, {"_id": 0})
        if u:
            try:
                await email_won(u["email"], u["name"], a["title"], auction_id, float(a["current_bid_eur"]))
            except Exception as e:
                logger.error("email_won failed: %s", e)

    return {"ok": True, "captured_eur": captured_amount}


@api.get("/admin/sold")
async def admin_sold(_admin: dict = Depends(require_admin_or_moderator)):
    from services import bidding as bidding_svc
    items = await db.auctions.find({"status": "sold"}, {"_id": 0}).sort("finalized_at", -1).to_list(500)
    # Enrich with winner info and current premium state
    enriched = []
    for a in items:
        winner = None
        if a.get("high_bidder_id"):
            winner = await db.users.find_one({"id": a["high_bidder_id"]}, {"_id": 0, "password_hash": 0})
        winning_bid = await bidding_svc.get_winning_bid(a["id"])
        enriched.append({
            **a,
            "winner_email": winner.get("email") if winner else None,
            "winner_name": winner.get("name") if winner else None,
            "winning_bid_preauth_status": winning_bid.get("preauth_status") if winning_bid else None,
            "winning_bid_preauth_amount": winning_bid.get("preauth_amount_eur") if winning_bid else None,
            "commission_eur": round(float(a.get("current_bid_eur", 0)) * 0.02, 2),
        })
    return enriched


# ---- WebSocket ----
@app.websocket("/api/ws/auctions/{auction_id}")
async def ws_auction(websocket: WebSocket, auction_id: str):
    await websocket.accept()
    await hub.join(auction_id, websocket)
    try:
        while True:
            # Keepalive: we don't process client messages, just hold the connection
            await websocket.receive_text()
    except WebSocketDisconnect:
        await hub.leave(auction_id, websocket)
    except Exception:
        await hub.leave(auction_id, websocket)


# ---- Watchlist ----
@api.get("/auctions/{auction_id}/watch-status")
async def watch_status(auction_id: str, user: dict = Depends(get_current_user)):
    existing = await db.watches.find_one({"auction_id": auction_id, "user_id": user["id"]})
    return {"watching": bool(existing)}


@api.post("/auctions/{auction_id}/request-vin")
async def request_vin(auction_id: str, user: dict = Depends(get_current_user)):
    a = await db.auctions.find_one({"id": auction_id}, {"_id": 0})
    if not a:
        raise HTTPException(status_code=404, detail="Търгът не е намерен")
    if _auction_status(a) != "live":
        raise HTTPException(status_code=400, detail="VIN може да бъде заявен само при активен търг")
    if not a.get("vin"):
        raise HTTPException(status_code=400, detail="За този автомобил VIN не е наличен")
    if a.get("seller_id") == user["id"] or user.get("role") == "admin":
        raise HTTPException(status_code=400, detail="Вие вече имате достъп до пълния VIN")
    from services import bidding as _bidding_svc
    already_bid_flag = await _bidding_svc.has_user_bid(auction_id, user["id"])
    if already_bid_flag:
        raise HTTPException(status_code=400, detail="Вие вече сте наддавали — пълният VIN е видим в обявата")
    existing = await db.vin_requests.find_one({"auction_id": auction_id, "user_id": user["id"]})
    if existing:
        raise HTTPException(status_code=429, detail="Вече сте заявили пълния VIN за тази обява. Проверете имейла си.")

    await db.vin_requests.insert_one({
        "id": str(uuid.uuid4()),
        "auction_id": auction_id,
        "user_id": user["id"],
        "created_at": datetime.now(timezone.utc).isoformat(),
    })
    try:
        await email_vin_delivery(user["email"], user.get("name", ""), a["title"], auction_id, a["vin"].strip().upper())
    except Exception as e:
        logger.error("email_vin_delivery failed: %s", e)
    return {"ok": True, "message": f"Изпратихме пълния VIN на {user['email']}"}

@api.post("/auctions/{auction_id}/watch")
async def toggle_watch(auction_id: str, user: dict = Depends(get_current_user)):
    existing = await db.watches.find_one({"auction_id": auction_id, "user_id": user["id"]})
    if existing:
        await db.watches.delete_one({"auction_id": auction_id, "user_id": user["id"]})
        return {"watching": False}
    await db.watches.insert_one({
        "id": str(uuid.uuid4()),
        "auction_id": auction_id,
        "user_id": user["id"],
        "created_at": datetime.now(timezone.utc).isoformat(),
    })
    return {"watching": True}

@api.get("/me/watchlist")
async def my_watchlist(user: dict = Depends(get_current_user)):
    watches = await db.watches.find({"user_id": user["id"]}, {"_id": 0}).to_list(200)
    ids = [w["auction_id"] for w in watches]
    if not ids:
        return []
    items = await db.auctions.find({"id": {"$in": ids}}, {"_id": 0}).to_list(200)
    for a in items: a["status"] = _auction_status(a)
    return items

@api.get("/me/bids")
async def my_bids(user: dict = Depends(get_current_user)):
    from services import bidding as bidding_svc
    return await bidding_svc.list_user_bids(user["id"], limit=200)

@api.get("/me/listings")
async def my_listings(user: dict = Depends(get_current_user)):
    items = await db.auctions.find({"seller_id": user["id"]}, {"_id": 0}).sort("created_at", -1).to_list(500)
    return [_public_auction(a, user) for a in items]


# ---- Profile ----
@api.patch("/me/profile")
async def update_my_profile(payload: ProfileUpdate, user: dict = Depends(get_current_user)):
    update = {}
    if payload.phone is not None:
        phone = payload.phone.strip()
        if phone and not phone.startswith("+"):
            raise HTTPException(status_code=400, detail="Телефонът трябва да е в международен формат (+359...)")
        update["phone"] = phone
    if payload.sms_opt_in is not None:
        update["sms_opt_in"] = bool(payload.sms_opt_in)
    if update:
        await db.users.update_one({"id": user["id"]}, {"$set": update})
    u = await db.users.find_one({"id": user["id"]}, {"_id": 0, "password_hash": 0})
    return u


# ---- Saved searches ----
def _matches_saved_search(auction: dict, f: dict) -> bool:
    try:
        if f.get("make") and auction.get("make") != f["make"]: return False
        if f.get("fuel") and auction.get("fuel") != f["fuel"]: return False
        if f.get("transmission") and auction.get("transmission") != f["transmission"]: return False
        if f.get("region") and auction.get("region") != f["region"]: return False
        if f.get("body_type") and auction.get("body_type") != f["body_type"]: return False
        year = int(auction.get("year", 0))
        if f.get("year_min") and year < int(f["year_min"]): return False
        if f.get("year_max") and year > int(f["year_max"]): return False
        price = float(auction.get("current_bid_eur", 0))
        if f.get("min_price") and price < float(f["min_price"]): return False
        if f.get("max_price") and price > float(f["max_price"]): return False
        q = (f.get("q") or "").strip().lower()
        if q:
            hay = " ".join([str(auction.get(k, "")) for k in ("title", "description", "make", "model", "color")]).lower()
            if q not in hay: return False
        return True
    except Exception:
        return False


@api.post("/me/saved-searches")
async def create_saved_search(payload: SavedSearchCreate, user: dict = Depends(get_current_user)):
    doc = {
        "id": str(uuid.uuid4()),
        "user_id": user["id"],
        "name": payload.name.strip() or "Нова записана търсачка",
        "filters": {k: v for k, v in payload.filters.items() if v not in (None, "", [])},
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.saved_searches.insert_one(doc)
    return {k: v for k, v in doc.items() if k != "_id"}


@api.get("/me/saved-searches")
async def list_saved_searches(user: dict = Depends(get_current_user)):
    items = await db.saved_searches.find({"user_id": user["id"]}, {"_id": 0}).sort("created_at", -1).to_list(200)
    return items


@api.delete("/me/saved-searches/{search_id}")
async def delete_saved_search(search_id: str, user: dict = Depends(get_current_user)):
    res = await db.saved_searches.delete_one({"id": search_id, "user_id": user["id"]})
    if res.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Не е намерена")
    return {"ok": True}


async def notify_matching_saved_searches(auction: dict):
    """Called when an auction becomes live (admin approves). Emails users with matching saved searches."""
    try:
        searches = await db.saved_searches.find({}, {"_id": 0}).to_list(2000)
    except Exception:
        return
    for s in searches:
        if _matches_saved_search(auction, s.get("filters", {})):
            u = await db.users.find_one({"id": s["user_id"]}, {"_id": 0})
            if u and u.get("email"):
                try:
                    from emails import send_email, _shell, APP_URL
                    html = _shell("Нова обява по ваш критерий", f"""
                      <p>Здравейте, {u.get("name","")},</p>
                      <p>Нова обява отговаря на вашата търсачка <strong>{s['name']}</strong>:</p>
                      <p style="font-size:18px;margin:16px 0;"><strong>{auction['title']}</strong></p>
                      <p>{auction.get("year","")} г. · {auction.get("city","")} · начална цена €{int(auction.get("starting_bid_eur",0)):,}</p>
                      <p><a href="{APP_URL}/auctions/{auction['id']}" style="display:inline-block;background:#1B4D3E;color:#fff;padding:12px 22px;border-radius:999px;text-decoration:none;font-weight:600;">Виж обявата</a></p>
                    """)
                    await send_email(u["email"], f"Нова обява · {auction['title']}", html)
                except Exception as e:
                    logger.error("saved search email failed: %s", e)
            # Web Push — saved-search match
            if u:
                try:
                    from services import push as push_svc
                    await push_svc.send_to_user(
                        s["user_id"],
                        title=f"Нова обява · {s['name']}",
                        body=f"{auction['title']} · от €{int(auction.get('starting_bid_eur', 0)):,}",
                        url=f"/auctions/{auction['id']}",
                        tag=f"saved-{s['id']}",
                    )
                except Exception as e:
                    logger.error("push saved_search failed: %s", e)


# ---- Seller listing management ----
@api.patch("/auctions/{auction_id}")
async def update_listing(auction_id: str, payload: AuctionUpdate, user: dict = Depends(get_current_user)):
    a = await db.auctions.find_one({"id": auction_id}, {"_id": 0})
    if not a:
        raise HTTPException(status_code=404, detail="Обявата не е намерена")
    is_admin = user.get("role") == "admin"
    if a.get("seller_id") != user["id"] and not is_admin:
        raise HTTPException(status_code=403, detail="Няма права за редактиране")

    status = _auction_status(a)
    if not is_admin:
        if status not in ("pending", "rejected"):
            if not (status == "live" and int(a.get("bid_count", 0)) == 0):
                raise HTTPException(status_code=400, detail="Обявата може да се редактира само преди първата наддавка")

    update = {k: v for k, v in payload.model_dump(exclude_unset=True).items() if v is not None}
    # Non-admins cannot change status/featured/ends_at
    if not is_admin:
        for forbidden in ("status", "featured", "ends_at"):
            update.pop(forbidden, None)

    if update:
        if "starting_bid_eur" in update and status in ("pending", "rejected") and not is_admin:
            update["current_bid_eur"] = float(update["starting_bid_eur"])
        if status == "rejected" and not is_admin and "status" not in update:
            update["status"] = "pending"
            await db.auctions.update_one({"id": auction_id}, {"$unset": {"rejected_reason": ""}})
        await db.auctions.update_one({"id": auction_id}, {"$set": update})
    return {"ok": True}


@api.delete("/auctions/{auction_id}")
async def withdraw_listing(auction_id: str, user: dict = Depends(get_current_user)):
    a = await db.auctions.find_one({"id": auction_id}, {"_id": 0})
    if not a:
        raise HTTPException(status_code=404, detail="Обявата не е намерена")
    is_admin = user.get("role") == "admin"
    if a.get("seller_id") != user["id"] and not is_admin:
        raise HTTPException(status_code=403, detail="Няма права")

    status = _auction_status(a)
    if not is_admin:
        if status in ("sold",):
            raise HTTPException(status_code=400, detail="Продадена обява не може да бъде оттеглена")
        if status == "live" and int(a.get("bid_count", 0)) > 0:
            raise HTTPException(status_code=400, detail="Обявата не може да бъде оттеглена с активни наддавания. Свържете се с екипа.")

    from services import bidding as bidding_svc
    await bidding_svc.release_all_active_preauths(auction_id)
    await db.auctions.update_one({"id": auction_id}, {"$set": {"status": "withdrawn"}})
    return {"ok": True}


@api.get("/admin/auctions")
async def admin_list_all(q: Optional[str] = None, status: Optional[str] = None, _admin: dict = Depends(require_admin_or_moderator)):
    query = {}
    if status:
        query["status"] = status
    if q:
        import re
        rx = {"$regex": re.escape(q.strip()), "$options": "i"}
        query["$or"] = [{"title": rx}, {"make": rx}, {"model": rx}, {"seller_name": rx}, {"id": rx}]
    items = await db.auctions.find(query, {"_id": 0}).sort("created_at", -1).limit(300).to_list(300)
    for a in items:
        a["status"] = _auction_status(a)
    return items


ADMIN_ALLOWED_STATUSES = {"pending", "live", "ended", "sold", "reserve_not_met", "withdrawn", "removed", "rejected"}


@api.get("/admin/auctions/{auction_id}")
async def admin_get_auction(auction_id: str, _admin: dict = Depends(require_admin_or_moderator)):
    a = await db.auctions.find_one({"id": auction_id}, {"_id": 0})
    if not a:
        raise HTTPException(status_code=404, detail="Обявата не е намерена")
    a["status"] = _auction_status(a)
    return a


@api.put("/admin/auctions/{auction_id}")
async def admin_update_auction(auction_id: str, payload: AdminAuctionUpdate, _admin: dict = Depends(require_admin)):
    """Admin full edit — may change any field including status, ends_at, current_bid_eur."""
    a = await db.auctions.find_one({"id": auction_id}, {"_id": 0})
    if not a:
        raise HTTPException(status_code=404, detail="Обявата не е намерена")
    update = {k: v for k, v in payload.model_dump(exclude_unset=True).items() if v is not None}

    # Validate status
    if "status" in update:
        if update["status"] not in ADMIN_ALLOWED_STATUSES:
            raise HTTPException(status_code=400, detail="Невалиден статус")

    # Validate ends_at
    if "ends_at" in update:
        try:
            datetime.fromisoformat(update["ends_at"])
        except Exception:
            raise HTTPException(status_code=400, detail="Невалиден формат на дата (ISO 8601)")

    if "vin" in update and update["vin"]:
        update["vin"] = update["vin"].strip().upper()

    if update:
        await db.auctions.update_one({"id": auction_id}, {"$set": update})

    # Broadcast bid-like change if current_bid_eur or ends_at changed, so open pages refresh
    if "current_bid_eur" in update or "ends_at" in update:
        fresh = await db.auctions.find_one({"id": auction_id}, {"_id": 0})
        if fresh:
            try:
                await hub.broadcast(auction_id, {
                    "type": "admin_update",
                    "auction_id": auction_id,
                    "current_bid_eur": float(fresh.get("current_bid_eur", 0)),
                    "ends_at": fresh.get("ends_at"),
                    "status": _auction_status(fresh),
                })
            except Exception as e:
                logger.error("admin_update broadcast failed: %s", e)

    fresh = await db.auctions.find_one({"id": auction_id}, {"_id": 0})
    if fresh:
        fresh["status"] = _auction_status(fresh)
    return {"ok": True, "auction": fresh}


@api.post("/admin/auctions/{auction_id}/remove")
async def admin_remove_auction(auction_id: str, _admin: dict = Depends(require_admin)):
    """Sets status to 'removed' (soft delete). Releases any active preauths."""
    a = await db.auctions.find_one({"id": auction_id}, {"_id": 0})
    if not a:
        raise HTTPException(status_code=404, detail="Обявата не е намерена")
    now_iso = datetime.now(timezone.utc).isoformat()
    from services import bidding as bidding_svc
    await bidding_svc.release_all_active_preauths(auction_id)
    await db.auctions.update_one(
        {"id": auction_id},
        {"$set": {"status": "removed", "removed_at": now_iso}},
    )
    try:
        await hub.broadcast(auction_id, {"type": "removed", "auction_id": auction_id})
    except Exception:
        pass
    return {"ok": True}


@api.post("/admin/auctions/{auction_id}/restore")
async def admin_restore_auction(auction_id: str, _admin: dict = Depends(require_admin)):
    """Restore a removed/withdrawn auction — sets status to 'live' if end date is in the future, otherwise 'ended'."""
    a = await db.auctions.find_one({"id": auction_id}, {"_id": 0})
    if not a:
        raise HTTPException(status_code=404, detail="Обявата не е намерена")
    try:
        end = datetime.fromisoformat(a["ends_at"])
    except Exception:
        end = datetime.now(timezone.utc) - timedelta(days=1)
    new_status = "live" if end > datetime.now(timezone.utc) else "ended"
    await db.auctions.update_one({"id": auction_id}, {"$set": {"status": new_status}})
    return {"ok": True, "status": new_status}


@api.delete("/admin/auctions/{auction_id}")
async def admin_hard_delete_auction(auction_id: str, _admin: dict = Depends(require_admin)):
    """PERMANENTLY deletes an auction and all associated records (bids, comments, watches, credits, vin requests)."""
    a = await db.auctions.find_one({"id": auction_id}, {"_id": 0})
    if not a:
        raise HTTPException(status_code=404, detail="Обявата не е намерена")
    now_iso = datetime.now(timezone.utc).isoformat()
    from services import bidding as bidding_svc
    # Release active credit/preauth mocks before wiping
    await bidding_svc.release_all_active_preauths(auction_id)
    await db.bidding_credits.update_many(
        {"auction_id": auction_id, "status": "authorized"},
        {"$set": {"status": "released", "released_at": now_iso}},
    )
    # Cascade delete
    res_bids_count = await bidding_svc.delete_bids_for_auction(auction_id)
    res_comments = await db.comments.delete_many({"auction_id": auction_id})
    res_watches = await db.watches.delete_many({"auction_id": auction_id})
    res_credits = await db.bidding_credits.delete_many({"auction_id": auction_id})
    res_vin = await db.vin_requests.delete_many({"auction_id": auction_id})
    await db.auctions.delete_one({"id": auction_id})
    return {
        "ok": True,
        "deleted": {
            "auction": 1,
            "bids": res_bids_count,
            "comments": res_comments.deleted_count,
            "watches": res_watches.deleted_count,
            "bidding_credits": res_credits.deleted_count,
            "vin_requests": res_vin.deleted_count,
        },
    }


# ---- Admin: Dashboard / Stats ----
# moved → routers/admin.py (admin_stats)


# ---- Admin: users ----
# moved → routers/admin.py (admin_list_users, admin_get_user, admin_update_user)


@api.post("/admin/auctions/{auction_id}/extend")
async def admin_extend_auction(
    auction_id: str,
    days: int = Query(default=10, ge=1, le=60),
    _admin: dict = Depends(require_admin),
):
    """Renew an ended/reserve_not_met auction: resets ends_at to now+days and sets status='live'.
    Preserves bids and current_bid. Clears finalized_at.
    """
    a = await db.auctions.find_one({"id": auction_id}, {"_id": 0})
    if not a:
        raise HTTPException(status_code=404, detail="Обявата не е намерена")
    if a.get("status") not in ("ended", "reserve_not_met", "withdrawn"):
        raise HTTPException(
            status_code=400,
            detail="Може да се подновяват само обяви със статус 'ended', 'reserve_not_met' или 'withdrawn'",
        )
    now = datetime.now(timezone.utc)
    new_ends = now + timedelta(days=int(days))
    await db.auctions.update_one(
        {"id": auction_id},
        {
            "$set": {
                "status": "live",
                "ends_at": new_ends.isoformat(),
                "duration_days": int(days),
                "extended_at": now.isoformat(),
            },
            "$unset": {"finalized_at": ""},
        },
    )
    return {"ok": True, "status": "live", "ends_at": new_ends.isoformat()}


# moved → routers/admin.py (admin_ban_user, admin_unban_user, admin_delete_user)




# ---- Post-auction reserve-not-met flow ----
@api.post("/auctions/{auction_id}/accept-high-bid")
async def seller_accept_high_bid(auction_id: str, user: dict = Depends(get_current_user)):
    a = await db.auctions.find_one({"id": auction_id}, {"_id": 0})
    if not a:
        raise HTTPException(status_code=404, detail="Обявата не е намерена")
    if a.get("seller_id") != user["id"] and user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Няма права")
    if _auction_status(a) != "reserve_not_met":
        raise HTTPException(status_code=400, detail="Действието е достъпно само при недостигнат резерв")
    if not a.get("high_bidder_id"):
        raise HTTPException(status_code=400, detail="Няма водещ наддавач")
    await db.auctions.update_one({"id": auction_id}, {"$set": {"status": "sold", "finalized_at": datetime.now(timezone.utc).isoformat()}})
    winner = await db.users.find_one({"id": a["high_bidder_id"]}, {"_id": 0})
    if winner:
        try:
            await email_won(winner["email"], winner["name"], a["title"], auction_id, float(a["current_bid_eur"]))
        except Exception as e:
            logger.error("email_won failed: %s", e)
    return {"ok": True}


@api.post("/auctions/{auction_id}/counter-offer")
async def seller_counter_offer(auction_id: str, payload: CounterOfferCreate, user: dict = Depends(get_current_user)):
    a = await db.auctions.find_one({"id": auction_id}, {"_id": 0})
    if not a:
        raise HTTPException(status_code=404, detail="Обявата не е намерена")
    if a.get("seller_id") != user["id"] and user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Няма права")
    if _auction_status(a) != "reserve_not_met":
        raise HTTPException(status_code=400, detail="Действието е достъпно само при недостигнат резерв")
    if not a.get("high_bidder_id"):
        raise HTTPException(status_code=400, detail="Няма водещ наддавач")
    if payload.price_eur <= 0:
        raise HTTPException(status_code=400, detail="Невалидна цена")

    await db.auctions.update_one({"id": auction_id}, {"$set": {
        "counter_offer_eur": float(payload.price_eur),
        "counter_offer_to": a["high_bidder_id"],
        "counter_status": "pending",
        "counter_offer_at": datetime.now(timezone.utc).isoformat(),
    }})
    return {"ok": True}


@api.post("/auctions/{auction_id}/counter-offer/respond")
async def respond_counter_offer(auction_id: str, payload: NegotiationRespond, user: dict = Depends(get_current_user)):
    a = await db.auctions.find_one({"id": auction_id}, {"_id": 0})
    if not a:
        raise HTTPException(status_code=404, detail="Обявата не е намерена")
    if a.get("counter_offer_to") != user["id"]:
        raise HTTPException(status_code=403, detail="Няма права")
    if a.get("counter_status") != "pending":
        raise HTTPException(status_code=400, detail="Офертата не е активна")

    now_iso = datetime.now(timezone.utc).isoformat()
    if payload.accept:
        new_price = float(a["counter_offer_eur"])
        await db.auctions.update_one({"id": auction_id}, {"$set": {
            "current_bid_eur": new_price,
            "counter_status": "accepted",
            "status": "sold",
            "finalized_at": now_iso,
        }})
        return {"ok": True, "status": "sold"}
    else:
        await db.auctions.update_one({"id": auction_id}, {"$set": {
            "counter_status": "declined",
            "status": "ended",
        }})
        return {"ok": True, "status": "ended"}


# ---- Post-auction negotiation moved to routers/negotiations.py ----



# ---- Public profile ----
@api.get("/users/{user_id}/profile")
async def public_profile(user_id: str):
    u = await db.users.find_one({"id": user_id}, {"_id": 0, "password_hash": 0, "email": 0})
    if not u:
        raise HTTPException(status_code=404, detail="Потребителят не е намерен")
    sold_listings = await db.auctions.find(
        {"seller_id": user_id, "status": "sold"},
        {"_id": 0},
    ).sort("finalized_at", -1).limit(60).to_list(60)
    purchases = await db.auctions.find(
        {"high_bidder_id": user_id, "status": "sold"},
        {"_id": 0},
    ).sort("finalized_at", -1).limit(60).to_list(60)
    active = await db.auctions.find(
        {"seller_id": user_id, "status": "live"},
        {"_id": 0},
    ).limit(12).to_list(12)
    listings_sold = [_public_auction(a) for a in sold_listings]
    bought = [_public_auction(a) for a in purchases]
    active_pub = [_public_auction(a) for a in active]
    total_sales = sum(float(a.get("current_bid_eur", 0)) for a in listings_sold)
    total_bought = sum(float(a.get("current_bid_eur", 0)) for a in bought)

    # Aggregate buyer → seller rating (for AggregateRating JSON-LD on profile page)
    rating_cur = db.reviews.find({"seller_id": user_id}, {"_id": 0, "rating": 1})
    rating_vals = [int(r["rating"]) async for r in rating_cur]
    rating_count = len(rating_vals)
    rating_avg = round(sum(rating_vals) / rating_count, 2) if rating_count else 0.0

    return {
        "user": {"id": u["id"], "name": u["name"], "role": u.get("role", "user"), "member_since": u["created_at"]},
        "stats": {
            "sales_count": len(listings_sold),
            "sales_total_eur": total_sales,
            "purchases_count": len(bought),
            "purchases_total_eur": total_bought,
            "active_count": len(active_pub),
        },
        "rating": {"avg": rating_avg, "count": rating_count},
        "listings_sold": listings_sold,
        "purchases": bought,
        "active_listings": active_pub,
    }


# ---- Seed ----
SEED_AUCTIONS = [
    {
        "title": "Audi A8 4.2 FSI Quattro — пълен сервиз",
        "make": "Audi", "model": "A8", "year": 2011, "mileage_km": 260000,
        "fuel": "Дизел", "transmission": "Автоматична", "body_type": "Седан",
        "power_hp": 232, "engine_cc": 3000, "color": "Тъмно сив",
        "region": "София", "city": "София",
        "images": [
            "https://images.unsplash.com/photo-1698995339730-86b3dd454001?crop=entropy&cs=srgb&fm=jpg&q=85&w=1600",
            "https://images.unsplash.com/photo-1676886417721-2e180ff9adee?crop=entropy&cs=srgb&fm=jpg&q=85&w=1600",
            "https://images.unsplash.com/photo-1754983780904-c9dad94536be?crop=entropy&cs=srgb&fm=jpg&q=85&w=1600",
        ],
        "description": "Пълен сервиз, реални километри. LED матрични фарове, адаптивно въздушно окачване, Bang & Olufsen аудио, CarPlay/Android Auto. Идеален за дълги пътувания.",
        "starting_bid_eur": 9000, "current_bid": 13299, "featured": True, "days_left": 4, "extra_bids": 22,
        "vin": "WAUZZZ4H9CN045678",
    },
    {
        "title": "BMW X5 30d xDrive M Sport — 2025, 37 000 км",
        "make": "BMW", "model": "X5", "year": 2025, "mileage_km": 37000,
        "fuel": "Дизел", "transmission": "Автоматична", "body_type": "Джип",
        "power_hp": 298, "engine_cc": 2999, "color": "Черен",
        "region": "Пловдив", "city": "Пловдив",
        "images": [
            "https://images.unsplash.com/photo-1555215695-3004980ad54e?crop=entropy&cs=srgb&fm=jpg&q=85&w=1600",
            "https://images.unsplash.com/photo-1606664515524-ed2f786a0bd6?crop=entropy&cs=srgb&fm=jpg&q=85&w=1600",
            "https://images.unsplash.com/photo-1617531653332-bd46c24f2068?crop=entropy&cs=srgb&fm=jpg&q=85&w=1600",
        ],
        "description": "Гаранция от БМВ България. M-пакет с 22\" M джанти, Shadow Line, панорамен таван, Harman Kardon, Distronic, Laserlight, безжичен CarPlay.",
        "starting_bid_eur": 55000, "current_bid": 65900, "featured": True, "days_left": 6, "extra_bids": 41,
        "vin": "WBACW81030L123456",
    },
    {
        "title": "Porsche 911 Carrera 4S — колекционерско състояние",
        "make": "Porsche", "model": "911", "year": 2019, "mileage_km": 58000,
        "fuel": "Бензин", "transmission": "Автоматична", "body_type": "Купе",
        "power_hp": 450, "engine_cc": 3000, "color": "GT Silver",
        "region": "София", "city": "София",
        "images": [
            "https://images.unsplash.com/photo-1611821064430-0979d0e51e8b?crop=entropy&cs=srgb&fm=jpg&q=85&w=1600",
            "https://images.unsplash.com/photo-1503376780353-7e6692767b70?crop=entropy&cs=srgb&fm=jpg&q=85&w=1600",
            "https://images.unsplash.com/photo-1614162692292-7ac56d7f7f1e?crop=entropy&cs=srgb&fm=jpg&q=85&w=1600",
        ],
        "description": "992 поколение, Sport Chrono, керамични спирачки, Bose озвучаване. Един собственик, пълна сервизна история в Porsche Център София.",
        "starting_bid_eur": 95000, "reserve_eur": 140000, "current_bid": 128500, "featured": True, "days_left": 2, "extra_bids": 67,
        "vin": "WP0ZZZ99ZKS789012",
    },
    {
        "title": "Alfa Romeo Giulia 2.2D Veloce — 2019, FULL",
        "make": "Alfa Romeo", "model": "Giulia", "year": 2019, "mileage_km": 165000,
        "fuel": "Дизел", "transmission": "Автоматична", "body_type": "Седан",
        "power_hp": 190, "engine_cc": 2200, "color": "Montecarlo Blue",
        "region": "Плевен", "city": "Плевен",
        "images": [
            "https://images.unsplash.com/photo-1542282088-fe8426682b8f?crop=entropy&cs=srgb&fm=jpg&q=85&w=1600",
            "https://images.unsplash.com/photo-1601928894027-24fde6a44a93?crop=entropy&cs=srgb&fm=jpg&q=85&w=1600",
        ],
        "description": "Панорамен покрив, Harman Kardon, Q4 задвижване, ACC, кожен салон червен/черен. Сервизирана изцяло при оторизиран партньор.",
        "starting_bid_eur": 14000, "current_bid": 17777, "featured": False, "days_left": 5, "extra_bids": 14,
    },
    {
        "title": "VW Passat R-Line 2.0 TSI — DSG, Virtual Cockpit",
        "make": "Volkswagen", "model": "Passat", "year": 2019, "mileage_km": 97500,
        "fuel": "Бензин", "transmission": "Автоматична", "body_type": "Комби",
        "power_hp": 190, "engine_cc": 2000, "color": "Deep Black Pearl",
        "region": "София", "city": "София",
        "images": [
            "https://images.unsplash.com/photo-1606611013016-969c19ba27bb?crop=entropy&cs=srgb&fm=jpg&q=85&w=1600",
            "https://images.unsplash.com/photo-1623861397259-2dd3b4a8f7f3?crop=entropy&cs=srgb&fm=jpg&q=85&w=1600",
        ],
        "description": "R-Line пакет 3x, Dynaudio, DCC адаптивно окачване, Distronic, Lane Assist, масаж на шофьорската седалка, Webasto печка.",
        "starting_bid_eur": 16000, "current_bid": 21000, "featured": True, "days_left": 3, "extra_bids": 19,
    },
    {
        "title": "Toyota RAV4 2.5 Hybrid Style — 218 к.с.",
        "make": "Toyota", "model": "RAV4", "year": 2021, "mileage_km": 88000,
        "fuel": "Хибриден", "transmission": "Автоматична", "body_type": "Джип",
        "power_hp": 218, "engine_cc": 2500, "color": "Silver Sky",
        "region": "Пловдив", "city": "Пловдив",
        "images": [
            "https://images.unsplash.com/photo-1617531653332-bd46c24f2068?crop=entropy&cs=srgb&fm=jpg&q=85&w=1600",
            "https://images.unsplash.com/photo-1558981806-ec527fa84c39?crop=entropy&cs=srgb&fm=jpg&q=85&w=1600",
        ],
        "description": "Пълна сервизна история. Adaptive Cruise, Lane Trace, JBL, подгряване, камера 360°, LED Style пакет.",
        "starting_bid_eur": 20000, "current_bid": 28900, "featured": False, "days_left": 7, "extra_bids": 11,
    },
    {
        "title": "Mercedes-Benz E 350 4MATIC — AMG Line",
        "make": "Mercedes-Benz", "model": "E-Class", "year": 2020, "mileage_km": 112000,
        "fuel": "Дизел", "transmission": "Автоматична", "body_type": "Седан",
        "power_hp": 286, "engine_cc": 2925, "color": "Obsidian Black",
        "region": "Варна", "city": "Варна",
        "images": [
            "https://images.unsplash.com/photo-1617788138017-80ad40651399?crop=entropy&cs=srgb&fm=jpg&q=85&w=1600",
            "https://images.unsplash.com/photo-1605559424843-9e4c228bf1c2?crop=entropy&cs=srgb&fm=jpg&q=85&w=1600",
        ],
        "description": "AMG Line Exterior, Burmester, MBUX с двойни екрани, Widescreen Cockpit, Multibeam LED, Airmatic окачване.",
        "starting_bid_eur": 30000, "current_bid": 39200, "featured": False, "days_left": 5, "extra_bids": 27,
    },
    {
        "title": "Citroen C5 X Shine — 5 800 км, като нов",
        "make": "Citroen", "model": "C5 X", "year": 2024, "mileage_km": 5800,
        "fuel": "Бензин", "transmission": "Автоматична", "body_type": "Седан",
        "power_hp": 136, "engine_cc": 1200, "color": "Pearl White",
        "region": "Стара Загора", "city": "Стара Загора",
        "images": [
            "https://images.unsplash.com/photo-1583121274602-3e2820c69888?crop=entropy&cs=srgb&fm=jpg&q=85&w=1600",
            "https://images.unsplash.com/photo-1492144534655-ae79c964c9d7?crop=entropy&cs=srgb&fm=jpg&q=85&w=1600",
        ],
        "description": "Официална гаранция Ситроен. Адаптивен круиз, ленточен асистент, 12\" мултимедия, безжичен CarPlay, подгряване на волан и седалки.",
        "starting_bid_eur": 18000, "current_bid": 22490, "featured": False, "days_left": 6, "extra_bids": 9,
    },
    {
        "title": "BMW M3 Competition — Individual San Marino",
        "make": "BMW", "model": "M3", "year": 2022, "mileage_km": 41000,
        "fuel": "Бензин", "transmission": "Автоматична", "body_type": "Седан",
        "power_hp": 510, "engine_cc": 2993, "color": "San Marino Blue",
        "region": "София", "city": "София",
        "images": [
            "https://images.unsplash.com/photo-1580273916550-e323be2ae537?crop=entropy&cs=srgb&fm=jpg&q=85&w=1600",
            "https://images.unsplash.com/photo-1549399542-7e3f8b79c341?crop=entropy&cs=srgb&fm=jpg&q=85&w=1600",
        ],
        "description": "Individual San Marino Blue, Merino карбонови седалки, M Driver's Package, карбонова керамика, Track Pack. Един собственик.",
        "starting_bid_eur": 80000, "reserve_eur": 100000, "current_bid": 109500, "featured": True, "days_left": 1, "extra_bids": 54,
    },
    {
        "title": "Kia Niro Hybrid — икономичен SUV",
        "make": "Kia", "model": "Niro", "year": 2019, "mileage_km": 239000,
        "fuel": "Хибриден", "transmission": "Автоматична", "body_type": "Джип",
        "power_hp": 105, "engine_cc": 1600, "color": "Snow White Pearl",
        "region": "София", "city": "София",
        "images": [
            "https://images.unsplash.com/photo-1592853625601-dfed1d4e4d44?crop=entropy&cs=srgb&fm=jpg&q=85&w=1600",
        ],
        "description": "Нова хибридна батерия, LED фарове, CarPlay/Android Auto, нови зимни гуми, подарък летни гуми.",
        "starting_bid_eur": 7500, "current_bid": 10699, "featured": False, "days_left": 8, "extra_bids": 6,
    },
    {
        "title": "Alfa Romeo 159 Sportwagon Ti 2.0 JTDM",
        "make": "Alfa Romeo", "model": "159", "year": 2011, "mileage_km": 183264,
        "fuel": "Дизел", "transmission": "Ръчна", "body_type": "Комби",
        "power_hp": 170, "engine_cc": 2000, "color": "Grigio Stromboli",
        "region": "София", "city": "София",
        "images": [
            "https://images.unsplash.com/photo-1503376780353-7e6692767b70?crop=entropy&cs=srgb&fm=jpg&q=85&w=1600",
        ],
        "description": "Ti изпълнение, кожен салон, 18\" джанти, отлично техническо състояние, сервизна история.",
        "starting_bid_eur": 4500, "current_bid": 6650, "featured": False, "days_left": 3, "extra_bids": 8,
    },
    {
        "title": "Lexus LC 500 — V8 Atmospheric",
        "make": "Lexus", "model": "LC 500", "year": 2020, "mileage_km": 29000,
        "fuel": "Бензин", "transmission": "Автоматична", "body_type": "Купе",
        "power_hp": 477, "engine_cc": 4969, "color": "Structural Blue",
        "region": "София", "city": "София",
        "images": [
            "https://images.unsplash.com/photo-1617654112368-307921291f42?crop=entropy&cs=srgb&fm=jpg&q=85&w=1600",
            "https://images.unsplash.com/photo-1549924231-f129b911e442?crop=entropy&cs=srgb&fm=jpg&q=85&w=1600",
        ],
        "description": "Structural Blue — най-рядкото лаково изпълнение. Mark Levinson 13-speaker, карбонов покрив, спортна ауспухова система.",
        "starting_bid_eur": 85000, "current_bid": 98400, "featured": True, "days_left": 4, "extra_bids": 31,
    },
]

SOLD_HISTORY = [
    {
        "title": "Porsche 911 Carrera S (991.2) — Manual",
        "make": "Porsche", "model": "911", "year": 2017, "mileage_km": 48000,
        "fuel": "Бензин", "transmission": "Ръчна", "body_type": "Купе",
        "power_hp": 420, "engine_cc": 3000, "color": "Guards Red",
        "region": "София", "city": "София",
        "images": ["https://images.unsplash.com/photo-1614162883144-1f0d3f59db76?crop=entropy&cs=srgb&fm=jpg&q=85&w=1600"],
        "description": "Продадена миналата седмица след 38 наддавания.",
        "sold_price": 112500,
    },
    {
        "title": "BMW M5 F90 Competition",
        "make": "BMW", "model": "M5", "year": 2021, "mileage_km": 52000,
        "fuel": "Бензин", "transmission": "Автоматична", "body_type": "Седан",
        "power_hp": 625, "engine_cc": 4395, "color": "Marina Bay Blue",
        "region": "Пловдив", "city": "Пловдив",
        "images": ["https://images.unsplash.com/photo-1611821064430-0979d0e51e8b?crop=entropy&cs=srgb&fm=jpg&q=85&w=1600"],
        "description": "49 наддавания, рекорден финал.",
        "sold_price": 96000,
    },
    {
        "title": "Mercedes-Benz G 400 d — AMG Line",
        "make": "Mercedes-Benz", "model": "G-Class", "year": 2022, "mileage_km": 34000,
        "fuel": "Дизел", "transmission": "Автоматична", "body_type": "Джип",
        "power_hp": 330, "engine_cc": 2925, "color": "Designo Platinum Black",
        "region": "Варна", "city": "Варна",
        "images": ["https://images.unsplash.com/photo-1606220588913-b3aacb4d2f46?crop=entropy&cs=srgb&fm=jpg&q=85&w=1600"],
        "description": "Manufaktur интериор, 22\" AMG джанти.",
        "sold_price": 155000,
    },
    {
        "title": "Audi RS6 Avant Performance",
        "make": "Audi", "model": "RS6", "year": 2021, "mileage_km": 61000,
        "fuel": "Бензин", "transmission": "Автоматична", "body_type": "Комби",
        "power_hp": 630, "engine_cc": 3996, "color": "Nardo Grey",
        "region": "София", "city": "София",
        "images": ["https://images.unsplash.com/photo-1606016159991-dfe4f2746ad5?crop=entropy&cs=srgb&fm=jpg&q=85&w=1600"],
        "description": "Dynamic Package, керамика, B&O Advanced.",
        "sold_price": 134000,
    },
]

async def seed():
    count = await db.auctions.count_documents({})
    if count > 0:
        return

    now = datetime.now(timezone.utc)
    for a in SEED_AUCTIONS:
        ends_at = now + timedelta(days=a.pop("days_left", 5))
        bids_n = a.pop("extra_bids", 0)
        current_bid = a.pop("current_bid", a["starting_bid_eur"])
        doc = {
            **a,
            "id": str(uuid.uuid4()),
            "seller_id": "platform",
            "seller_name": "autobids.bg",
            "current_bid_eur": float(current_bid),
            "starting_bid_eur": float(a["starting_bid_eur"]),
            "bid_count": bids_n,
            "high_bidder_name": None,
            "high_bidder_id": None,
            "created_at": now.isoformat(),
            "ends_at": ends_at.isoformat(),
            "status": "live",
        }
        await db.auctions.insert_one(doc)

    past = now - timedelta(days=6)
    for a in SOLD_HISTORY:
        sold_price = a.pop("sold_price")
        doc = {
            **a,
            "id": str(uuid.uuid4()),
            "seller_id": "platform",
            "seller_name": "autobids.bg",
            "starting_bid_eur": float(sold_price) * 0.7,
            "current_bid_eur": float(sold_price),
            "bid_count": 40,
            "featured": False,
            "created_at": (past - timedelta(days=7)).isoformat(),
            "ends_at": past.isoformat(),
            "status": "sold",
        }
        await db.auctions.insert_one(doc)

async def seed_admin():
    email = os.environ.get("ADMIN_EMAIL", "admin@autobids.bg")
    password = os.environ.get("ADMIN_PASSWORD", "admin123")
    existing = await db.users.find_one({"email": email})
    if existing is None:
        await db.users.insert_one({
            "id": str(uuid.uuid4()),
            "email": email,
            "password_hash": hash_password(password),
            "name": "Администратор",
            "role": "admin",
            "created_at": datetime.now(timezone.utc).isoformat(),
        })
    elif not verify_password(password, existing["password_hash"]):
        await db.users.update_one({"email": email}, {"$set": {"password_hash": hash_password(password)}})

@app.on_event("startup")
async def on_startup():
    await db.users.create_index("email", unique=True)
    await db.auctions.create_index("id", unique=True)
    await db.auctions.create_index([("status", 1), ("ends_at", 1)])
    # NOTE: legacy Mongo `bids` index kept for old archive data; new bids live in Postgres.
    await db.bids.create_index("auction_id")
    # Web Push subscriptions (one-doc-per-endpoint)
    await db.push_subscriptions.create_index("endpoint", unique=True)
    await db.push_subscriptions.create_index("user_id")
    await db.comments.create_index("auction_id")
    await db.watches.create_index([("user_id", 1), ("auction_id", 1)])
    await db.bidding_credits.create_index([("auction_id", 1), ("user_id", 1)])
    await db.makes.create_index("name", unique=True)
    await db.audit_log.create_index([("at", -1)])
    # PostgreSQL bidding subsystem (see services/bidding.py)
    from db_pg import init_pg_schema
    await init_pg_schema()
    await _load_settings_cache()
    await seed_admin()
    await seed()
    await _seed_makes()
    # Start background scheduler for auction finalization
    asyncio.create_task(_auction_finalizer_loop())


async def _seed_makes():
    """Seed the makes collection with an initial catalog if empty."""
    count = await db.makes.count_documents({})
    if count > 0:
        return
    initial = [
        "Abarth", "Acura", "Alfa Romeo", "Alpina", "Alpine", "Aston Martin", "Audi",
        "Baic", "Bentley", "BMW", "Bugatti", "Buick", "BYD",
        "Cadillac", "Chevrolet", "Chrysler", "Citroën", "Cupra",
        "Dacia", "Daewoo", "Daihatsu", "Dodge", "DS Automobiles",
        "Ferrari", "Fiat", "Fisker", "Ford",
        "Genesis", "GMC",
        "Honda", "Hongqi", "Hyundai",
        "Ineos", "Infiniti", "Isuzu",
        "Jaguar", "Jeep",
        "Kia", "Koenigsegg",
        "Lada", "Lamborghini", "Lancia", "Land Rover", "Lexus", "Lincoln", "Lotus", "Lucid",
        "Maserati", "Maybach", "Mazda", "McLaren", "Mercedes-Benz", "MG", "MINI", "Mitsubishi", "Morgan",
        "NIO", "Nissan",
        "Opel",
        "Pagani", "Peugeot", "Polestar", "Porsche",
        "Renault", "Rimac", "Rolls-Royce",
        "Saab", "Seat", "Skoda", "Smart", "Ssangyong", "Subaru", "Suzuki",
        "Tesla", "Toyota",
        "Volkswagen", "Volvo",
        "Xpeng",
    ]
    docs = []
    for name in initial:
        docs.append({
            "id": str(uuid.uuid4()),
            "name": name,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "created_by": "system",
        })
    if docs:
        await db.makes.insert_many(docs)
    logger.info("[seed_makes] seeded %d makes", len(docs))


async def _auction_finalizer_loop():
    """Runs every 60 seconds. Transitions live auctions whose ends_at has passed:
      • reserve met or no reserve + bids → 'sold'
      • reserve not met → 'reserve_not_met' (negotiation auto-creates on first GET)
      • no bids at all → 'ended'
    Sends winner email on sold. Releases losing preauths.
    """
    while True:
        try:
            await _finalize_expired_auctions_once()
        except Exception as e:
            logger.error("Auction finalizer loop error: %s", e)
        await asyncio.sleep(60)


async def _finalize_expired_auctions_once():
    now = datetime.now(timezone.utc)
    now_iso = now.isoformat()
    # Find all live auctions past their end time
    cursor = db.auctions.find(
        {"status": "live", "ends_at": {"$lte": now_iso}},
        {"_id": 0},
    )
    expired = await cursor.to_list(500)
    if not expired:
        return

    for a in expired:
        auction_id = a["id"]
        current_bid = float(a.get("current_bid_eur", 0))
        reserve = a.get("reserve_eur")
        has_reserve = reserve is not None and float(reserve) > 0
        has_bids = int(a.get("bid_count", 0)) > 0 and a.get("high_bidder_id")

        if not has_bids:
            # No bidders → ended without sale
            await db.auctions.update_one(
                {"id": auction_id},
                {"$set": {"status": "ended", "finalized_at": now_iso}},
            )
            logger.info("Auto-finalized auction %s → ended (no bids)", auction_id)
            continue

        if has_reserve and current_bid < float(reserve):
            # Reserve not met → open negotiation window (lazy-created on first GET)
            await db.auctions.update_one(
                {"id": auction_id},
                {"$set": {"status": "reserve_not_met", "finalized_at": now_iso}},
            )
            # Email both parties
            try:
                seller = await db.users.find_one({"id": a.get("seller_id")}, {"_id": 0}) if a.get("seller_id") != "platform" else None
                buyer = await db.users.find_one({"id": a.get("high_bidder_id")}, {"_id": 0})
                app_url = os.environ.get("APP_URL", "")
                link = f"{app_url}/auctions/{auction_id}"
                if seller and seller.get("email"):
                    from emails import send_email
                    await send_email(
                        seller["email"],
                        f"Резервът не е достигнат: {a.get('title','')}",
                        f"Резервната цена не е достигната. Имате 24 часа да направите начална оферта на купувача в преговарящата сесия: {link}",
                    )
                if buyer and buyer.get("email"):
                    from emails import send_email
                    await send_email(
                        buyer["email"],
                        f"Резервът не е достигнат: {a.get('title','')}",
                        f"Резервната цена не е достигната, но продавачът има 24 часа да направи начална оферта. Следете преговарящата сесия: {link}",
                    )
            except Exception as e:
                logger.error("reserve_not_met email failed for %s: %s", auction_id, e)
            logger.info("Auto-finalized auction %s → reserve_not_met", auction_id)
            continue

        # Sold (reserve met or no reserve)
        await db.auctions.update_one(
            {"id": auction_id},
            {"$set": {"status": "sold", "finalized_at": now_iso}},
        )
        # Release losing bidders' preauths (keep winner's active for capture)
        from services import bidding as bidding_svc
        await bidding_svc.release_losing_preauths(auction_id, a["high_bidder_id"])
        await db.bidding_credits.update_many(
            {"auction_id": auction_id, "status": "authorized", "user_id": {"$ne": a["high_bidder_id"]}},
            {"$set": {"status": "released", "released_at": now_iso}},
        )
        # Notify winner
        try:
            winner = await db.users.find_one({"id": a["high_bidder_id"]}, {"_id": 0})
            if winner and winner.get("email"):
                await email_won(winner["email"], winner["name"], a["title"], auction_id, current_bid)
        except Exception as e:
            logger.error("email_won auto-finalize failed for %s: %s", auction_id, e)
        logger.info("Auto-finalized auction %s → sold (€%.0f)", auction_id, current_bid)

@api.post("/admin/reseed")
async def reseed():
    from services import bidding as bidding_svc
    await db.auctions.delete_many({})
    await bidding_svc.delete_all_bids()
    await db.comments.delete_many({})
    await db.watches.delete_many({})
    await seed()
    return {"ok": True}


# ---- SEO / Sitemap / Share endpoints moved to routers/seo.py ----



# ---- Mount ----
# Include sub-routers (refactored out of server.py for clarity)
from routers import seo as _seo_router  # noqa: E402
from routers import negotiations as _neg_router  # noqa: E402
from routers import auth as _auth_router  # noqa: E402
from routers import reviews as _reviews_router  # noqa: E402
from routers import admin as _admin_router  # noqa: E402
from routers import seller_requests as _seller_requests_router  # noqa: E402
from routers import push as _push_router  # noqa: E402

# Wire up injected deps for the negotiation router
_neg_router.configure(
    get_current_user=get_current_user,
    auction_status=_auction_status,
    buyer_fee=_buyer_fee,
    email_won=email_won,
)
_neg_router.register_routes(get_current_user)

# Wire up injected deps for the auth router
_auth_router.configure(
    hash_password=hash_password,
    verify_password=verify_password,
    create_token=create_token,
    get_current_user=get_current_user,
    limiter=limiter,
)
_auth_router.register_routes()

# Wire up reviews router
_reviews_router.configure(get_current_user=get_current_user)
_reviews_router.register_routes()

# Wire up admin router (CMS + users + stats; lifecycle routes stay in server.py)
_admin_router.configure(
    require_admin=require_admin,
    require_admin_or_moderator=require_admin_or_moderator,
    settings_fn=_settings,
    load_settings_cache=_load_settings_cache,
    public_comment=_public_comment,
    hub=hub,
)
_admin_router.register_routes()

# Wire up seller requests router (promotion / text-change / image reorder)
_seller_requests_router.configure(
    get_current_user=get_current_user,
    require_admin_or_moderator=require_admin_or_moderator,
)
_seller_requests_router.register_routes()

api.include_router(_seo_router.router)
api.include_router(_neg_router.router)
api.include_router(_auth_router.router)
api.include_router(_reviews_router.router)
api.include_router(_admin_router.router)
api.include_router(_seller_requests_router.router)
api.include_router(_push_router.register_push_routes(get_current_user))

app.include_router(api)

app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=os.environ.get('CORS_ORIGINS', '*').split(','),
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---- WAF lite: block obvious SQLi/XSS patterns in query string ----
_WAF_PATTERNS = re.compile(
    r"(\bunion\s+select\b|\bor\s+1\s*=\s*1\b|';\s*drop\s+table|<script\b|javascript:|onerror\s*=|onload\s*=|%3Cscript)",
    re.IGNORECASE,
)


@app.middleware("http")
async def waf_middleware(request: Request, call_next):
    from urllib.parse import unquote
    qs = request.url.query or ""
    # Decode percent-encoded chars so `%27%20OR%201%3D1` matches patterns
    decoded = unquote(qs)
    if decoded and _WAF_PATTERNS.search(decoded):
        logger.warning("[WAF] blocked request path=%s ip=%s qs=%s", request.url.path, request.client.host if request.client else "?", decoded[:120])
        from fastapi.responses import JSONResponse
        return JSONResponse({"detail": "Заявката е отхвърлена от защитата."}, status_code=400)
    return await call_next(request)


# ---- Maintenance mode middleware ----
@app.middleware("http")
async def maintenance_mode_middleware(request: Request, call_next):
    """If maintenance_mode is on, block all write requests except admin + public reads of essentials."""
    s = _settings()
    if not s.get("maintenance_mode"):
        return await call_next(request)
    method = request.method.upper()
    path = request.url.path or ""
    if method in ("GET", "HEAD", "OPTIONS"):
        return await call_next(request)
    if any(path.startswith(p) for p in ("/api/admin", "/api/auth")):
        return await call_next(request)
    # Block writes
    from fastapi.responses import JSONResponse
    return JSONResponse({"detail": s.get("maintenance_message") or "Поддръжка"}, status_code=503)


# ---- Security headers middleware ----
@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "SAMEORIGIN"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Permissions-Policy"] = "geolocation=(), microphone=(), camera=()"
    # CSP tuned for SPA — allow self + data: images, inline styles (needed by React),
    # and common CDNs we actually use. Add google-analytics/tagmanager later if needed.
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; "
        "script-src 'self' 'unsafe-inline' 'unsafe-eval' https://fonts.googleapis.com; "
        "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
        "img-src 'self' data: blob: https:; "
        "font-src 'self' data: https://fonts.gstatic.com; "
        "connect-src 'self' https: wss:; "
        "frame-ancestors 'self';"
    )
    response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    return response


# ---- Rate limiting (slowapi) ----
try:
    from slowapi import _rate_limit_exceeded_handler
    from slowapi.errors import RateLimitExceeded
    from slowapi.middleware import SlowAPIMiddleware

    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
    app.add_middleware(SlowAPIMiddleware)
except Exception as _rl_err:
    logging.warning("Rate limiting not enabled: %s", _rl_err)


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@app.on_event("shutdown")
async def shutdown_db_client():
    client.close()
