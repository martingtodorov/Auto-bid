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

from emails import email_outbid, email_won, email_approved, email_rejected
from ws import hub

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
    starting_bid_eur: float
    reserve_eur: Optional[float] = None
    duration_days: int = 7

class BidCreate(BaseModel):
    amount_eur: float
    payment_method_id: Optional[str] = None  # mock Stripe payment method token

class AdminDecision(BaseModel):
    reason: Optional[str] = None

class CommentCreate(BaseModel):
    text: str = Field(min_length=1, max_length=1200)


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
    if a.get("status") == "sold":
        return "sold"
    if a.get("status") == "ended":
        return "ended"
    end = datetime.fromisoformat(a["ends_at"])
    if datetime.now(timezone.utc) >= end:
        return "ended"
    return "live"

def _public_auction(a: dict) -> dict:
    a = {k: v for k, v in a.items() if k != "_id"}
    a["status"] = _auction_status(a)
    return a


# ---- Auctions ----
@api.get("/auctions")
async def list_auctions(
    make: Optional[str] = None,
    fuel: Optional[str] = None,
    transmission: Optional[str] = None,
    region: Optional[str] = None,
    body_type: Optional[str] = None,
    min_price: Optional[float] = None,
    max_price: Optional[float] = None,
    year_min: Optional[int] = None,
    year_max: Optional[int] = None,
    status: Optional[str] = Query(None, description="live|ended|sold"),
    sort: Optional[str] = Query("ending_soon"),
    limit: int = 60,
):
    q = {}
    if make: q["make"] = make
    if fuel: q["fuel"] = fuel
    if transmission: q["transmission"] = transmission
    if region: q["region"] = region
    if body_type: q["body_type"] = body_type
    if year_min or year_max:
        q["year"] = {}
        if year_min: q["year"]["$gte"] = year_min
        if year_max: q["year"]["$lte"] = year_max
    if min_price or max_price:
        q["current_bid_eur"] = {}
        if min_price: q["current_bid_eur"]["$gte"] = min_price
        if max_price: q["current_bid_eur"]["$lte"] = max_price

    cursor = db.auctions.find(q, {"_id": 0}).limit(limit)
    items = await cursor.to_list(limit)
    for a in items:
        a["status"] = _auction_status(a)

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
async def featured():
    items = await db.auctions.find({"featured": True}, {"_id": 0}).limit(6).to_list(6)
    for a in items: a["status"] = _auction_status(a)
    return items

@api.get("/auctions/sold")
async def sold():
    items = await db.auctions.find({"status": "sold"}, {"_id": 0}).limit(12).to_list(12)
    return items

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
async def get_auction(auction_id: str):
    a = await db.auctions.find_one({"id": auction_id}, {"_id": 0})
    if not a:
        raise HTTPException(status_code=404, detail="Търгът не е намерен")
    a["status"] = _auction_status(a)
    return a

@api.post("/auctions")
async def create_auction(payload: AuctionCreate, user: dict = Depends(get_current_user)):
    auction_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc)
    ends_at = now + timedelta(days=payload.duration_days)
    doc = payload.model_dump()
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
    preauth_amount = round(float(payload.amount_eur) * 0.03, 2)

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
            "commission_eur": round(float(a.get("current_bid_eur", 0)) * 0.03, 2),
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
        "starting_bid_eur": 95000, "current_bid": 128500, "featured": True, "days_left": 2, "extra_bids": 67,
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
        "starting_bid_eur": 80000, "current_bid": 109500, "featured": True, "days_left": 1, "extra_bids": 54,
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
