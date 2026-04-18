"""
Auth routes — register, login, me (GET/PUT).
Extracted from server.py. Uses configure() dependency injection to avoid
circular imports.
"""
import logging
from datetime import datetime, timezone
from fastapi import APIRouter, HTTPException, Depends, Request

from deps import db
from models import UserRegister, UserLogin

router = APIRouter(prefix="/auth")
logger = logging.getLogger(__name__)

# Injected dependencies (wired from server.py at startup via configure())
_hash_password = None
_verify_password = None
_create_token = None
_get_current_user = None
_limiter = None


def configure(*, hash_password, verify_password, create_token, get_current_user, limiter):
    global _hash_password, _verify_password, _create_token, _get_current_user, _limiter
    _hash_password = hash_password
    _verify_password = verify_password
    _create_token = create_token
    _get_current_user = get_current_user
    _limiter = limiter


def register_routes():
    """Called by server.py after configure() to wire HTTP routes with proper deps."""

    @router.post("/register")
    @_limiter.limit("5/minute")
    async def register(request: Request, payload: UserRegister):
        import uuid as _uuid
        existing = await db.users.find_one({"email": payload.email.lower()})
        if existing:
            raise HTTPException(status_code=409, detail="Имейлът вече е регистриран")
        user_id = str(_uuid.uuid4())
        doc = {
            "id": user_id,
            "email": payload.email.lower(),
            "name": payload.name.strip(),
            "password_hash": _hash_password(payload.password),
            "role": "user",
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        await db.users.insert_one(doc)
        token = _create_token(user_id, doc["email"])
        return {
            "token": token,
            "user": {k: v for k, v in doc.items() if k not in ("_id", "password_hash")},
        }

    @router.post("/login")
    @_limiter.limit("10/minute")
    async def login(request: Request, payload: UserLogin):
        email = payload.email.lower()
        user = await db.users.find_one({"email": email})
        if not user or not _verify_password(payload.password, user["password_hash"]):
            raise HTTPException(status_code=401, detail="Грешен имейл или парола")
        if user.get("banned"):
            raise HTTPException(status_code=403, detail="Акаунтът е блокиран. За въпроси: contact@autobid.bg")
        token = _create_token(user["id"], email)
        return {
            "token": token,
            "user": {k: v for k, v in user.items() if k not in ("_id", "password_hash")},
        }

    @router.get("/me")
    async def me(user: dict = Depends(_get_current_user)):
        return user
