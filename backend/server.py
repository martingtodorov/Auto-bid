from dotenv import load_dotenv
from pathlib import Path

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

import os
import uuid
import logging
import bcrypt
import jwt
from datetime import datetime, timezone, timedelta
from typing import List, Optional
from fastapi import FastAPI, APIRouter, HTTPException, Depends, Request, Query, WebSocket, WebSocketDisconnect
from starlette.middleware.cors import CORSMiddleware
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
app = FastAPI(title="AutoBid.bg API")
api = APIRouter(prefix="/api")

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


# ---- Models ----
class UserRegister(BaseModel):
    email: EmailStr
    password: str = Field(min_length=6)
    name: str = Field(min_length=1)

class UserLogin(BaseModel):
    email: EmailStr
    password: str

class UserOut(BaseModel):
    id: str
    email: str
    name: str
    role: str = "user"
    created_at: str

class AuctionCreate(BaseModel):
    title: str
    make: str
    model: str
    year: int
    mileage_km: int
    fuel: str
    transmission: str
    body_type: str
    power_hp: int
    engine_cc: int
    color: str
    region: str
    city: str
    description: str
    images: List[str] = []
    images_exterior: List[str] = []
    images_wheels: List[str] = []
    images_bumper: List[str] = []
    images_interior: List[str] = []
    starting_bid_eur: float
    reserve_eur: Optional[float] = None
    duration_days: int = 7
    contact_email: EmailStr
    contact_phone: str = Field(min_length=5, max_length=32)

class BidCreate(BaseModel):
    amount_eur: float
    payment_method_id: Optional[str] = None  # mock Stripe payment method token

class AdminDecision(BaseModel):
    reason: Optional[str] = None

class CommentCreate(BaseModel):
    text: str = Field(min_length=1, max_length=1200)

class AuctionUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    starting_bid_eur: Optional[float] = None
    reserve_eur: Optional[float] = None
    images: Optional[List[str]] = None
    images_exterior: Optional[List[str]] = None
    images_wheels: Optional[List[str]] = None
    images_bumper: Optional[List[str]] = None
    images_interior: Optional[List[str]] = None
    color: Optional[str] = None
    region: Optional[str] = None
    city: Optional[str] = None
    vin: Optional[str] = None


class AdminAuctionUpdate(BaseModel):
    """Full admin edit — allows changing every field on an auction."""
    title: Optional[str] = None
    description: Optional[str] = None
    make: Optional[str] = None
    model: Optional[str] = None
    year: Optional[int] = None
    mileage_km: Optional[int] = None
    fuel: Optional[str] = None
    transmission: Optional[str] = None
    body_type: Optional[str] = None
    power_hp: Optional[int] = None
    engine_cc: Optional[int] = None
    color: Optional[str] = None
    region: Optional[str] = None
    city: Optional[str] = None
    vin: Optional[str] = None
    images: Optional[List[str]] = None
    images_exterior: Optional[List[str]] = None
    images_wheels: Optional[List[str]] = None
    images_bumper: Optional[List[str]] = None
    images_interior: Optional[List[str]] = None
    starting_bid_eur: Optional[float] = None
    reserve_eur: Optional[float] = None
    current_bid_eur: Optional[float] = None
    ends_at: Optional[str] = None
    status: Optional[str] = None
    featured: Optional[bool] = None
    seller_name: Optional[str] = None
    contact_email: Optional[str] = None
    contact_phone: Optional[str] = None

class CounterOfferCreate(BaseModel):
    price_eur: float

class NegotiationRespond(BaseModel):
    accept: bool

class ProfileUpdate(BaseModel):
    phone: Optional[str] = None
    sms_opt_in: Optional[bool] = None

class AdminUserUpdate(BaseModel):
    name: Optional[str] = None
    email: Optional[EmailStr] = None
    phone: Optional[str] = None
    is_verified_dealer: Optional[bool] = None
    role: Optional[str] = None  # "user" or "admin"

class SavedSearchCreate(BaseModel):
    name: str
    filters: dict


# ---- Auth routes ----
@api.post("/auth/register")
async def register(payload: UserRegister):
    email = payload.email.lower().strip()
    if await db.users.find_one({"email": email}):
        raise HTTPException(status_code=400, detail="Имейлът вече е регистриран")
    user_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    doc = {
        "id": user_id,
        "email": email,
        "name": payload.name.strip(),
        "password_hash": hash_password(payload.password),
        "role": "user",
        "created_at": now,
    }
    await db.users.insert_one(doc)
    token = create_token(user_id, email)
    return {
        "token": token,
        "user": {"id": user_id, "email": email, "name": doc["name"], "role": "user", "created_at": now},
    }

@api.post("/auth/login")
async def login(payload: UserLogin):
    email = payload.email.lower().strip()
    user = await db.users.find_one({"email": email})
    if not user or not verify_password(payload.password, user["password_hash"]):
        raise HTTPException(status_code=401, detail="Грешен имейл или парола")
    token = create_token(user["id"], email)
    return {
        "token": token,
        "user": {
            "id": user["id"],
            "email": user["email"],
            "name": user["name"],
            "role": user.get("role", "user"),
            "created_at": user["created_at"],
        },
    }

@api.get("/auth/me")
async def me(user: dict = Depends(get_current_user)):
    return user


# ---- Auction helpers ----
def _auction_status(a: dict) -> str:
    stored = a.get("status")
    if stored in ("sold", "rejected", "pending", "withdrawn", "reserve_not_met", "ended", "removed"):
        if stored == "ended":
            return "ended"
        return stored
    end = datetime.fromisoformat(a["ends_at"])
    if datetime.now(timezone.utc) >= end:
        reserve = a.get("reserve_eur")
        if reserve and float(a.get("current_bid_eur", 0)) < float(reserve):
            return "reserve_not_met"
        return "ended"
    return "live"

def _mask_vin(vin: str) -> str:
    if not vin:
        return vin
    v = vin.strip().upper()
    if len(v) <= 7:
        return "*" * len(v)
    return v[:-7] + ("*" * 7)


def _public_auction(a: dict, viewer: Optional[dict] = None) -> dict:
    a = {k: v for k, v in a.items() if k != "_id"}
    a["status"] = _auction_status(a)
    reserve = a.get("reserve_eur")
    is_owner_or_admin = viewer and (viewer.get("id") == a.get("seller_id") or viewer.get("role") == "admin")
    if reserve is not None and reserve > 0:
        a["has_reserve"] = True
        a["reserve_met"] = float(a.get("current_bid_eur", 0)) >= float(reserve)
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

    # Hide non-public statuses from public listings (pending/rejected/withdrawn/removed)
    viewer_is_admin = viewer and viewer.get("role") == "admin"
    if not viewer_is_admin:
        items = [a for a in items if a["status"] in ("live", "ended", "sold", "reserve_not_met")]

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

    return items

@api.get("/auctions/featured")
async def featured(request: Request):
    viewer = await get_optional_user(request)
    # Fetch more than needed then filter in Python for computed "live" status
    raw = await db.auctions.find({"featured": True}, {"_id": 0}).limit(30).to_list(30)
    items = [_public_auction(a, viewer) for a in raw]
    live = [a for a in items if a["status"] == "live"]
    return live[:6]

@api.get("/auctions/sold")
async def sold(request: Request):
    viewer = await get_optional_user(request)
    items = await db.auctions.find({"status": "sold"}, {"_id": 0}).limit(12).to_list(12)
    return [_public_auction(a, viewer) for a in items]

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
    public = _public_auction(a, viewer)
    # Enrich with seller verified status (platform listings are considered verified)
    seller_id = a.get("seller_id")
    if seller_id == "platform":
        public["seller_is_verified_dealer"] = True
    else:
        seller = await db.users.find_one({"id": seller_id}, {"_id": 0, "is_verified_dealer": 1}) if seller_id else None
        public["seller_is_verified_dealer"] = bool(seller and seller.get("is_verified_dealer"))
    # Reveal full VIN to: seller, admin, or anyone who placed a bid on this auction
    if a.get("vin") and viewer:
        is_privileged = viewer.get("role") == "admin" or viewer.get("id") == a.get("seller_id")
        if not is_privileged:
            has_bid = await db.bids.find_one({"auction_id": auction_id, "user_id": viewer["id"]}, {"_id": 0, "id": 1})
            is_privileged = bool(has_bid)
        if is_privileged:
            public["vin"] = a["vin"].strip().upper()
            public["vin_masked"] = False
    return public

@api.post("/auctions")
async def create_auction(payload: AuctionCreate, user: dict = Depends(get_current_user)):
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
    doc["images"] = merged
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
    })
    await db.auctions.insert_one(doc)
    return {"id": auction_id, "status": "pending"}


# ---- Bids ----
@api.get("/auctions/{auction_id}/bids")
async def list_bids(auction_id: str):
    items = await db.bids.find({"auction_id": auction_id}, {"_id": 0}).sort("amount_eur", -1).limit(50).to_list(50)
    return items

@api.post("/auctions/{auction_id}/bids")
async def place_bid(auction_id: str, payload: BidCreate, user: dict = Depends(get_current_user)):
    a = await db.auctions.find_one({"id": auction_id})
    if not a:
        raise HTTPException(status_code=404, detail="Търгът не е намерен")
    if _auction_status(a) != "live":
        raise HTTPException(status_code=400, detail="Търгът не е активен")
    if a.get("seller_id") == user["id"]:
        raise HTTPException(status_code=400, detail="Не можете да наддавате за собствен автомобил")
    min_next = float(a["current_bid_eur"]) + 100
    if payload.amount_eur < min_next:
        raise HTTPException(status_code=400, detail=f"Минималната следваща наддавка е €{int(min_next)}")
    if not payload.payment_method_id:
        raise HTTPException(status_code=402, detail="Необходима е валидна карта за наддаване")

    now = datetime.now(timezone.utc)
    bid_id = str(uuid.uuid4())
    preauth_amount = round(float(payload.amount_eur) * 0.02, 2)

    # Release current user's previous active preauth(s) on this auction
    await db.bids.update_many(
        {"auction_id": auction_id, "user_id": user["id"], "preauth_status": "authorized"},
        {"$set": {"preauth_status": "released", "preauth_released_at": now.isoformat()}},
    )

    # Release previous high bidder (different user) preauth + email
    prev_high_bidder_id = a.get("high_bidder_id")
    if prev_high_bidder_id and prev_high_bidder_id != user["id"]:
        await db.bids.update_many(
            {"auction_id": auction_id, "user_id": prev_high_bidder_id, "preauth_status": "authorized"},
            {"$set": {"preauth_status": "released", "preauth_released_at": now.isoformat()}},
        )
        prev_user = await db.users.find_one({"id": prev_high_bidder_id}, {"_id": 0})
        if prev_user:
            try:
                await email_outbid(prev_user["email"], prev_user["name"], a["title"], auction_id, float(payload.amount_eur))
            except Exception as e:
                logger.error("email_outbid failed: %s", e)

    bid_doc = {
        "id": bid_id,
        "auction_id": auction_id,
        "user_id": user["id"],
        "user_name": user["name"],
        "amount_eur": float(payload.amount_eur),
        "created_at": now.isoformat(),
        "preauth_id": f"mock_pi_{uuid.uuid4().hex[:16]}",
        "preauth_status": "authorized",
        "preauth_amount_eur": preauth_amount,
        "card_last4": payload.payment_method_id[-4:] if payload.payment_method_id else None,
    }
    await db.bids.insert_one(bid_doc)

    ends_at = datetime.fromisoformat(a["ends_at"])
    update = {
        "current_bid_eur": float(payload.amount_eur),
        "bid_count": int(a.get("bid_count", 0)) + 1,
        "high_bidder_id": user["id"],
        "high_bidder_name": user["name"],
    }
    if (ends_at - now).total_seconds() < 120:
        update["ends_at"] = (now + timedelta(minutes=2)).isoformat()
    await db.auctions.update_one({"id": auction_id}, {"$set": update})

    public_bid = {k: v for k, v in bid_doc.items() if k != "_id"}
    await hub.broadcast(auction_id, {
        "type": "bid",
        "auction_id": auction_id,
        "current_bid_eur": float(payload.amount_eur),
        "high_bidder_name": user["name"],
        "bid_count": update["bid_count"],
        "ends_at": update.get("ends_at", a["ends_at"]),
        "bid": {k: public_bid.get(k) for k in ("id", "user_name", "amount_eur", "created_at")},
    })

    # Notify seller (if real seller, not platform, and not self-bid already blocked)
    seller_id = a.get("seller_id")
    if seller_id and seller_id != "platform":
        seller = await db.users.find_one({"id": seller_id}, {"_id": 0})
        if seller and seller.get("email"):
            try:
                await email_seller_new_bid(seller["email"], seller.get("name", ""), a["title"], auction_id, user["name"], float(payload.amount_eur), update["bid_count"])
            except Exception as e:
                logger.error("email_seller_new_bid failed: %s", e)

    # FOMO SMS blast when auction enters final 5 minutes
    new_ends_at = datetime.fromisoformat(update.get("ends_at", a["ends_at"]))
    seconds_left = (new_ends_at - now).total_seconds()
    if seconds_left <= 300:
        # Recipients: unique previous bidders (except current) + watchers, who opted in
        recipient_ids: set = set()
        async for b in db.bids.find({"auction_id": auction_id}, {"_id": 0, "user_id": 1}).limit(500):
            if b["user_id"] != user["id"]:
                recipient_ids.add(b["user_id"])
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
            body = f"AutoBid.bg: Нова наддавка €{int(payload.amount_eur):,} за {a['title'][:50]}. Остават {mins}м. {app_url}/auctions/{auction_id}"
            for r in recipients:
                if r.get("phone"):
                    try:
                        await send_sms(r["phone"], body)
                    except Exception as e:
                        logger.error("send_sms failed: %s", e)

    return {"ok": True, "bid": public_bid, "preauth_amount_eur": preauth_amount}


# ---- Comments ----
@api.get("/auctions/{auction_id}/comments")
async def list_comments(auction_id: str):
    items = await db.comments.find({"auction_id": auction_id}, {"_id": 0}).sort("created_at", -1).limit(100).to_list(100)
    return items

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
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.comments.insert_one(doc)
    public = {k: v for k, v in doc.items() if k != "_id"}
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

@api.get("/admin/pending")
async def admin_pending(_admin: dict = Depends(require_admin)):
    items = await db.auctions.find({"status": "pending"}, {"_id": 0}).sort("created_at", -1).to_list(200)
    return items

@api.post("/admin/auctions/{auction_id}/approve")
async def admin_approve(auction_id: str, _admin: dict = Depends(require_admin)):
    a = await db.auctions.find_one({"id": auction_id}, {"_id": 0})
    if not a:
        raise HTTPException(status_code=404, detail="Обявата не е намерена")
    now = datetime.now(timezone.utc)
    ends_at = now + timedelta(days=int(a.get("duration_days", 7)))
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
    a = await db.auctions.find_one({"id": auction_id}, {"_id": 0})
    if not a:
        raise HTTPException(status_code=404, detail="Обявата не е намерена")
    await db.bids.update_many(
        {"auction_id": auction_id, "preauth_status": "authorized"},
        {"$set": {"preauth_status": "released", "preauth_released_at": datetime.now(timezone.utc).isoformat()}},
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
    """Captures winner's 3% pre-authorization as buyer's premium. Releases losing bidders' preauths."""
    a = await db.auctions.find_one({"id": auction_id}, {"_id": 0})
    if not a:
        raise HTTPException(status_code=404, detail="Обявата не е намерена")
    now_iso = datetime.now(timezone.utc).isoformat()
    winner_id = a.get("high_bidder_id")

    # Capture winner's authorized preauth (if any)
    captured_amount = 0.0
    if winner_id:
        winner_bid = await db.bids.find_one(
            {"auction_id": auction_id, "user_id": winner_id, "preauth_status": "authorized"},
            {"_id": 0},
            sort=[("amount_eur", -1)],
        )
        if winner_bid:
            captured_amount = float(winner_bid.get("preauth_amount_eur", 0.0))
            await db.bids.update_one(
                {"id": winner_bid["id"]},
                {"$set": {"preauth_status": "captured", "preauth_captured_at": now_iso}},
            )

    # Release all other authorized preauths
    q = {"auction_id": auction_id, "preauth_status": "authorized"}
    await db.bids.update_many(q, {"$set": {"preauth_status": "released", "preauth_released_at": now_iso}})

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
async def admin_sold(_admin: dict = Depends(require_admin)):
    items = await db.auctions.find({"status": "sold"}, {"_id": 0}).sort("finalized_at", -1).to_list(500)
    # Enrich with winner info and current premium state
    enriched = []
    for a in items:
        winner = None
        if a.get("high_bidder_id"):
            winner = await db.users.find_one({"id": a["high_bidder_id"]}, {"_id": 0, "password_hash": 0})
        winning_bid = await db.bids.find_one(
            {"auction_id": a["id"], "user_id": a.get("high_bidder_id")},
            {"_id": 0},
            sort=[("amount_eur", -1)],
        )
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
    already_bid = await db.bids.find_one({"auction_id": auction_id, "user_id": user["id"]}, {"_id": 0, "id": 1})
    if already_bid:
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
    bids = await db.bids.find({"user_id": user["id"]}, {"_id": 0}).sort("created_at", -1).limit(200).to_list(200)
    return bids

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

    await db.bids.update_many(
        {"auction_id": auction_id, "preauth_status": "authorized"},
        {"$set": {"preauth_status": "released", "preauth_released_at": datetime.now(timezone.utc).isoformat()}},
    )
    await db.auctions.update_one({"id": auction_id}, {"$set": {"status": "withdrawn"}})
    return {"ok": True}


@api.get("/admin/auctions")
async def admin_list_all(q: Optional[str] = None, status: Optional[str] = None, _admin: dict = Depends(require_admin)):
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
async def admin_get_auction(auction_id: str, _admin: dict = Depends(require_admin)):
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
    await db.bids.update_many(
        {"auction_id": auction_id, "preauth_status": "authorized"},
        {"$set": {"preauth_status": "released", "preauth_released_at": now_iso}},
    )
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


# ---- Admin: users ----
@api.get("/admin/users")
async def admin_list_users(q: Optional[str] = None, _admin: dict = Depends(require_admin)):
    query = {}
    if q:
        import re
        rx = {"$regex": re.escape(q.strip()), "$options": "i"}
        query["$or"] = [{"name": rx}, {"email": rx}, {"phone": rx}]
    items = await db.users.find(query, {"_id": 0, "password_hash": 0}).sort("created_at", -1).limit(500).to_list(500)
    return items


@api.get("/admin/users/{user_id}")
async def admin_get_user(user_id: str, _admin: dict = Depends(require_admin)):
    u = await db.users.find_one({"id": user_id}, {"_id": 0, "password_hash": 0})
    if not u:
        raise HTTPException(status_code=404, detail="Потребителят не е намерен")
    return u


@api.put("/admin/users/{user_id}")
async def admin_update_user(user_id: str, payload: AdminUserUpdate, admin_user: dict = Depends(require_admin)):
    u = await db.users.find_one({"id": user_id}, {"_id": 0})
    if not u:
        raise HTTPException(status_code=404, detail="Потребителят не е намерен")
    update = {}
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
        if payload.role not in ("user", "admin"):
            raise HTTPException(status_code=400, detail="Невалидна роля")
        # Protect: prevent admin from demoting themselves
        if user_id == admin_user["id"] and payload.role != "admin":
            raise HTTPException(status_code=400, detail="Не можете да смените собствената си роля")
        update["role"] = payload.role

    if update:
        await db.users.update_one({"id": user_id}, {"$set": update})
        # Also propagate name to their auctions.seller_name
        if "name" in update:
            await db.auctions.update_many({"seller_id": user_id}, {"$set": {"seller_name": update["name"]}})

    fresh = await db.users.find_one({"id": user_id}, {"_id": 0, "password_hash": 0})
    return {"ok": True, "user": fresh}




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
    return {
        "user": {"id": u["id"], "name": u["name"], "role": u.get("role", "user"), "member_since": u["created_at"]},
        "stats": {
            "sales_count": len(listings_sold),
            "sales_total_eur": total_sales,
            "purchases_count": len(bought),
            "purchases_total_eur": total_bought,
            "active_count": len(active_pub),
        },
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
            "seller_name": "AutoBid.bg",
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
            "seller_name": "AutoBid.bg",
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
    email = os.environ.get("ADMIN_EMAIL", "admin@autobid.bg")
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
    await db.bids.create_index("auction_id")
    await db.comments.create_index("auction_id")
    await db.watches.create_index([("user_id", 1), ("auction_id", 1)])
    await seed_admin()
    await seed()

@api.post("/admin/reseed")
async def reseed():
    await db.auctions.delete_many({})
    await db.bids.delete_many({})
    await db.comments.delete_many({})
    await db.watches.delete_many({})
    await seed()
    return {"ok": True}


# ---- Mount ----
app.include_router(api)

app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=os.environ.get('CORS_ORIGINS', '*').split(','),
    allow_methods=["*"],
    allow_headers=["*"],
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@app.on_event("shutdown")
async def shutdown_db_client():
    client.close()
