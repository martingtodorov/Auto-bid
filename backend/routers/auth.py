"""
Auth routes — register, login (with 2FA challenge), me, forgot/reset password, TOTP 2FA.
Uses configure() dependency injection to avoid circular imports.
"""
import logging
import secrets
import base64
import io
import uuid as _uuid
import hashlib
import bcrypt
from datetime import datetime, timezone, timedelta
from fastapi import APIRouter, HTTPException, Depends, Request
import pyotp
import qrcode

from deps import db
from models import (
    UserRegister, UserLogin, ForgotPasswordRequest, ResetPasswordRequest,
    TwoFactorConfirm, TwoFactorVerify,
)
from emails import send_email, _shell

router = APIRouter(prefix="/auth")
logger = logging.getLogger(__name__)

# Injected dependencies
_hash_password = None
_verify_password = None
_create_token = None
_get_current_user = None
_limiter = None

OTP_TTL_MIN = 15
CHALLENGE_TTL_MIN = 5


def configure(*, hash_password, verify_password, create_token, get_current_user, limiter):
    global _hash_password, _verify_password, _create_token, _get_current_user, _limiter
    _hash_password = hash_password
    _verify_password = verify_password
    _create_token = create_token
    _get_current_user = get_current_user
    _limiter = limiter


def _hash_otp(code: str) -> str:
    """Hash an OTP with bcrypt for safe storage."""
    return bcrypt.hashpw(code.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def _verify_otp(code: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(code.encode("utf-8"), hashed.encode("utf-8"))
    except Exception:
        return False


def _sha256(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def _sanitize(user: dict) -> dict:
    return {k: v for k, v in user.items() if k not in ("_id", "password_hash", "totp_secret", "totp_backup_codes")}


def register_routes():

    @router.post("/register")
    @_limiter.limit("5/minute")
    async def register(request: Request, payload: UserRegister):
        if not payload.terms_accepted:
            raise HTTPException(status_code=400, detail="Моля, приемете Общите условия.")
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
            "terms_accepted_at": datetime.now(timezone.utc).isoformat(),
        }
        await db.users.insert_one(doc)
        token = _create_token(user_id, doc["email"])
        return {"token": token, "user": _sanitize(doc)}

    @router.post("/login")
    @_limiter.limit("10/minute")
    async def login(request: Request, payload: UserLogin):
        email = payload.email.lower()
        user = await db.users.find_one({"email": email})
        if not user or not _verify_password(payload.password, user["password_hash"]):
            raise HTTPException(status_code=401, detail="Грешен имейл или парола")
        if user.get("banned"):
            raise HTTPException(status_code=403, detail="Акаунтът е блокиран. За въпроси: contact@autobids.bg")

        # 2FA challenge flow — issue a short-lived challenge token instead of JWT
        if user.get("totp_enabled"):
            challenge = secrets.token_urlsafe(32)
            await db.auth_challenges.insert_one({
                "id": str(_uuid.uuid4()),
                "challenge": _sha256(challenge),
                "user_id": user["id"],
                "expires_at": (datetime.now(timezone.utc) + timedelta(minutes=CHALLENGE_TTL_MIN)).isoformat(),
            })
            return {"requires_2fa": True, "challenge_token": challenge}

        token = _create_token(user["id"], email)
        return {"token": token, "user": _sanitize(user)}

    @router.post("/2fa/verify")
    @_limiter.limit("10/minute")
    async def two_factor_verify(request: Request, payload: TwoFactorVerify):
        ch = await db.auth_challenges.find_one({"challenge": _sha256(payload.challenge_token)}, {"_id": 0})
        if not ch:
            raise HTTPException(status_code=401, detail="Невалиден challenge")
        if datetime.fromisoformat(ch["expires_at"]) < datetime.now(timezone.utc):
            await db.auth_challenges.delete_one({"challenge": _sha256(payload.challenge_token)})
            raise HTTPException(status_code=401, detail="Challenge-ът е изтекъл, моля влезте отново")

        user = await db.users.find_one({"id": ch["user_id"]})
        if not user or not user.get("totp_enabled"):
            raise HTTPException(status_code=400, detail="2FA не е активирано за този акаунт")

        code = payload.code.strip()
        ok = False
        # Try TOTP (6 digits)
        if len(code) == 6 and code.isdigit():
            totp = pyotp.TOTP(user["totp_secret"])
            ok = totp.verify(code, valid_window=1)
        # Backup code fallback (8 chars)
        if not ok and len(code) == 8:
            hashed_codes = user.get("totp_backup_codes", [])
            for hc in list(hashed_codes):
                if _verify_otp(code.upper(), hc):
                    hashed_codes.remove(hc)
                    await db.users.update_one({"id": user["id"]}, {"$set": {"totp_backup_codes": hashed_codes}})
                    ok = True
                    break
        if not ok:
            raise HTTPException(status_code=401, detail="Грешен код")

        # Consume challenge
        await db.auth_challenges.delete_one({"challenge": _sha256(payload.challenge_token)})
        token = _create_token(user["id"], user["email"])
        return {"token": token, "user": _sanitize(user)}

    @router.post("/2fa/enable")
    async def two_factor_enable(user: dict = Depends(_get_current_user)):
        """Returns a provisioning URI + QR code for the user to scan.
        Does NOT activate 2FA until /2fa/confirm is called with a valid code.
        """
        if user.get("totp_enabled"):
            raise HTTPException(status_code=400, detail="2FA вече е активирано")
        secret = pyotp.random_base32()
        uri = pyotp.totp.TOTP(secret).provisioning_uri(name=user["email"], issuer_name="autobids.bg")
        # Save provisional (not enabled) secret
        await db.users.update_one({"id": user["id"]}, {"$set": {"totp_secret": secret, "totp_enabled": False}})
        # Generate QR PNG as data URL
        img = qrcode.make(uri)
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        qr_data_url = f"data:image/png;base64,{base64.b64encode(buf.getvalue()).decode('ascii')}"
        return {"secret": secret, "otpauth_uri": uri, "qr_code_data_url": qr_data_url}

    @router.post("/2fa/confirm")
    async def two_factor_confirm(payload: TwoFactorConfirm, user: dict = Depends(_get_current_user)):
        if user.get("totp_enabled"):
            raise HTTPException(status_code=400, detail="2FA вече е активирано")
        secret = user.get("totp_secret")
        if not secret:
            raise HTTPException(status_code=400, detail="Първо извикайте /2fa/enable")
        if not pyotp.TOTP(secret).verify(payload.code.strip(), valid_window=1):
            raise HTTPException(status_code=400, detail="Грешен код")
        # Generate 8 single-use backup codes (8-char alphanumeric each)
        backup_codes = [secrets.token_hex(4).upper() for _ in range(8)]
        hashed = [_hash_otp(c) for c in backup_codes]
        await db.users.update_one(
            {"id": user["id"]},
            {"$set": {"totp_enabled": True, "totp_backup_codes": hashed, "totp_confirmed_at": datetime.now(timezone.utc).isoformat()}},
        )
        return {"ok": True, "backup_codes": backup_codes, "message": "Запазете резервните кодове на сигурно място — всеки може да се използва еднократно."}

    @router.post("/2fa/disable")
    async def two_factor_disable(payload: TwoFactorConfirm, user: dict = Depends(_get_current_user)):
        if not user.get("totp_enabled"):
            raise HTTPException(status_code=400, detail="2FA не е активирано")
        if not pyotp.TOTP(user["totp_secret"]).verify(payload.code.strip(), valid_window=1):
            raise HTTPException(status_code=400, detail="Грешен код")
        await db.users.update_one(
            {"id": user["id"]},
            {"$set": {"totp_enabled": False}, "$unset": {"totp_secret": "", "totp_backup_codes": "", "totp_confirmed_at": ""}},
        )
        return {"ok": True}

    # ---- Forgot / reset password ----
    @router.post("/forgot-password")
    @_limiter.limit("5/minute")
    async def forgot_password(request: Request, payload: ForgotPasswordRequest):
        email = payload.email.lower()
        user = await db.users.find_one({"email": email}, {"_id": 0, "id": 1, "name": 1})
        # Respond identically whether or not the account exists (avoid enumeration)
        if user:
            code = f"{secrets.randbelow(1_000_000):06d}"
            await db.password_resets.delete_many({"email": email})
            await db.password_resets.insert_one({
                "id": str(_uuid.uuid4()),
                "email": email,
                "code_hash": _hash_otp(code),
                "created_at": datetime.now(timezone.utc).isoformat(),
                "expires_at": (datetime.now(timezone.utc) + timedelta(minutes=OTP_TTL_MIN)).isoformat(),
                "used": False,
                "attempts": 0,
            })
            html = _shell(
                "Нулиране на парола",
                f"""
                <p style="margin:0 0 16px 0;">Здравейте {user.get('name') or ''},</p>
                <p style="margin:0 0 16px 0;">Получихме заявка за нулиране на паролата за вашия autobids.bg акаунт.</p>
                <p style="margin:0 0 8px 0;">Вашият код за потвърждение (валиден {OTP_TTL_MIN} минути):</p>
                <div style="font-family:'Courier New',monospace;font-size:32px;letter-spacing:8px;background:#f6f7f8;padding:18px;text-align:center;border-radius:10px;border:1px solid #e5e7eb;margin:16px 0;"><strong>{code}</strong></div>
                <p style="color:#6b7280;font-size:13px;margin:24px 0 0 0;">Ако не сте правили такава заявка, можете спокойно да игнорирате това съобщение — паролата ви няма да бъде променена.</p>
                """,
            )
            await send_email(email, "autobids.bg — Код за нулиране на парола", html)
        return {"ok": True, "message": f"Ако акаунтът съществува, код е изпратен на {email}. Проверете пощата си."}

    @router.post("/reset-password")
    @_limiter.limit("5/minute")
    async def reset_password(request: Request, payload: ResetPasswordRequest):
        email = payload.email.lower()
        rec = await db.password_resets.find_one({"email": email, "used": False}, {"_id": 0})
        if not rec:
            raise HTTPException(status_code=400, detail="Невалиден или изтекъл код")
        if datetime.fromisoformat(rec["expires_at"]) < datetime.now(timezone.utc):
            raise HTTPException(status_code=400, detail="Кодът е изтекъл — поискайте нов")
        if rec.get("attempts", 0) >= 5:
            raise HTTPException(status_code=429, detail="Твърде много опити — поискайте нов код")
        if not _verify_otp(payload.code.strip(), rec["code_hash"]):
            await db.password_resets.update_one({"id": rec["id"]}, {"$inc": {"attempts": 1}})
            raise HTTPException(status_code=400, detail="Грешен код")

        user = await db.users.find_one({"email": email}, {"_id": 0, "id": 1})
        if not user:
            raise HTTPException(status_code=400, detail="Акаунтът не е намерен")

        await db.users.update_one({"id": user["id"]}, {"$set": {"password_hash": _hash_password(payload.new_password)}})
        await db.password_resets.update_one({"id": rec["id"]}, {"$set": {"used": True, "used_at": datetime.now(timezone.utc).isoformat()}})
        return {"ok": True, "message": "Паролата е сменена. Можете да влезете с новата парола."}

    @router.get("/me")
    async def me(user: dict = Depends(_get_current_user)):
        u = _sanitize(user)
        u["totp_enabled"] = bool(user.get("totp_enabled"))
        return u

    @router.delete("/me")
    async def delete_me(user: dict = Depends(_get_current_user)):
        """GDPR right-to-erasure — user deletes own account and cascades data.
        Keeps auctions as ledger records (seller anonymized). Clears bids/comments/watches/saved searches/credits/VIN requests/reviews.
        """
        uid = user["id"]
        bids = await db.bids.delete_many({"user_id": uid})
        comments = await db.comments.delete_many({"user_id": uid})
        watches = await db.watches.delete_many({"user_id": uid})
        saved = await db.saved_searches.delete_many({"user_id": uid})
        credits = await db.bidding_credits.delete_many({"user_id": uid})
        vins = await db.vin_requests.delete_many({"user_id": uid})
        reviews = await db.reviews.delete_many({"buyer_id": uid})
        notes = await db.user_notes.delete_many({"user_id": uid})
        # Anonymize their auctions (legal/ledger)
        await db.auctions.update_many({"seller_id": uid}, {"$set": {"seller_name": "Изтрит потребител", "seller_id": "deleted"}})
        await db.auctions.update_many({"high_bidder_id": uid}, {"$set": {"high_bidder_id": None, "high_bidder_name": None}})
        await db.users.delete_one({"id": uid})
        return {
            "ok": True,
            "deleted": {
                "bids": bids.deleted_count, "comments": comments.deleted_count, "watches": watches.deleted_count,
                "saved_searches": saved.deleted_count, "credits": credits.deleted_count,
                "vin_requests": vins.deleted_count, "reviews": reviews.deleted_count, "notes": notes.deleted_count,
            },
        }
