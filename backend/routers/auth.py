"""
Auth routes — register, login (with 2FA challenge), me, forgot/reset password, TOTP 2FA.
Uses configure() dependency injection to avoid circular imports.
"""
import logging
import os
import secrets
import base64
import io
import uuid as _uuid
import hashlib
import bcrypt
from datetime import datetime, timezone, timedelta
from fastapi import APIRouter, HTTPException, Depends, Request, Response
import pyotp
import qrcode
from user_agents import parse as _parse_ua

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

# --- Cookie auth (C3): JWT в httpOnly cookie + CSRF (double-submit) ----------
COOKIE_TTL_DAYS = 7  # стандартен TTL за обикновен login
REMEMBER_TTL_DAYS = 90  # cap за "Запомни ме" (3 месеца)
COOKIE_TTL_SEC = COOKIE_TTL_DAYS * 24 * 60 * 60
REMEMBER_TTL_SEC = REMEMBER_TTL_DAYS * 24 * 60 * 60
ACCESS_COOKIE = "access_token"
CSRF_COOKIE = "csrf_token"
# Secure cookies на production (HTTPS).  Може да се изключи за локален dev.
COOKIE_SECURE = os.environ.get("COOKIE_SECURE", "1") not in ("0", "false", "False")
COOKIE_SAMESITE = os.environ.get("COOKIE_SAMESITE", "lax")

# Постоянна стойност за константно-времево сравнение при login (M1):
# Когато потребителят не съществува, изпълняваме bcrypt срещу този dummy hash,
# за да предотвратим timing-side-channel за откриване на регистрирани имейли.
_DUMMY_BCRYPT_HASH = bcrypt.hashpw(b"dummy-not-a-real-password", bcrypt.gensalt()).decode("utf-8")


def _set_auth_cookies(response: Response, token: str, max_age_sec: int = COOKIE_TTL_SEC) -> str:
    """Записва access_token (httpOnly) и csrf_token (readable от JS) cookies.

    `max_age_sec` контролира продължителността — стандарт 7 дни, 90 дни при
    "Запомни ме".  Връща CSRF токена.
    """
    csrf = secrets.token_urlsafe(32)
    response.set_cookie(
        key=ACCESS_COOKIE,
        value=token,
        max_age=max_age_sec,
        httponly=True,
        secure=COOKIE_SECURE,
        samesite=COOKIE_SAMESITE,
        path="/",
    )
    response.set_cookie(
        key=CSRF_COOKIE,
        value=csrf,
        max_age=max_age_sec,
        httponly=False,
        secure=COOKIE_SECURE,
        samesite=COOKIE_SAMESITE,
        path="/",
    )
    return csrf


def _clear_auth_cookies(response: Response) -> None:
    response.delete_cookie(
        ACCESS_COOKIE, path="/", secure=COOKIE_SECURE, samesite=COOKIE_SAMESITE, httponly=True,
    )
    response.delete_cookie(
        CSRF_COOKIE, path="/", secure=COOKIE_SECURE, samesite=COOKIE_SAMESITE, httponly=False,
    )


# --- Sessions: устройства и активни сесии ------------------------------------
def _device_info_from_request(request: Request) -> dict:
    """Парсва User-Agent + IP заглавията и връща читаемо описание на устройството."""
    ua_string = (request.headers.get("user-agent") or "")[:500]
    ip = (request.client.host if request.client else "") or ""
    # Уважаваме X-Forwarded-For при reverse proxy (вземаме първия публичен hop).
    fwd = request.headers.get("x-forwarded-for") or ""
    if fwd:
        ip = fwd.split(",")[0].strip() or ip
    info = {"user_agent": ua_string, "ip": ip,
            "browser": "Unknown", "os": "Unknown", "device_label": "Непознато устройство",
            "device_type": "desktop"}
    if not ua_string:
        return info
    try:
        ua = _parse_ua(ua_string)
        b_ver = (ua.browser.version_string or "").strip()
        o_ver = (ua.os.version_string or "").strip()
        info["browser"] = (f"{ua.browser.family} {b_ver}".strip()) or "Unknown"
        info["os"] = (f"{ua.os.family} {o_ver}".strip()) or "Unknown"
        if ua.is_mobile or ua.is_tablet:
            info["device_type"] = "tablet" if ua.is_tablet else "mobile"
            brand = (ua.device.brand or "").strip()
            model = (ua.device.model or "").strip()
            family = (ua.device.family or "").strip()
            # Apple/iOS не разкрива конкретен модел — използваме "iPhone"/"iPad" + версия
            if family.lower() == "iphone":
                info["device_label"] = f"iPhone · iOS {o_ver}".strip(" ·")
            elif family.lower() == "ipad":
                info["device_label"] = f"iPad · iPadOS {o_ver}".strip(" ·")
            elif brand and model:
                info["device_label"] = f"{brand} {model}".strip()
            elif family and family != "Other":
                info["device_label"] = family
            else:
                info["device_label"] = "Мобилно устройство"
        elif ua.is_pc:
            info["device_type"] = "desktop"
            os_family = (ua.os.family or "").strip()
            if os_family.lower().startswith("mac"):
                info["device_label"] = f"Mac · macOS {o_ver}".strip(" ·")
            elif os_family.lower().startswith("windows"):
                info["device_label"] = f"Windows {o_ver} компютър".strip()
            elif os_family.lower().startswith("linux") or "ubuntu" in os_family.lower():
                info["device_label"] = f"{os_family} компютър".strip()
            else:
                info["device_label"] = f"{os_family or 'Desktop'} компютър".strip()
        elif ua.is_bot:
            info["device_type"] = "bot"
            info["device_label"] = f"Bot ({ua.browser.family})".strip()
    except Exception:
        pass
    return info


async def _create_session(user_id: str, request: Request, *, remember: bool, ttl_days: int) -> dict:
    """Създава нов session документ и връща го (със `id` за JWT `sid` claim)."""
    now = datetime.now(timezone.utc)
    info = _device_info_from_request(request)
    sid = str(_uuid.uuid4())
    doc = {
        "id": sid,
        "user_id": user_id,
        "remember": bool(remember),
        "created_at": now.isoformat(),
        "last_seen_at": now.isoformat(),
        "expires_at": (now + timedelta(days=ttl_days)).isoformat(),
        "user_agent": info["user_agent"],
        "ip": info["ip"],
        "browser": info["browser"],
        "os": info["os"],
        "device_label": info["device_label"],
        "device_type": info["device_type"],
    }
    await db.sessions.insert_one(doc)
    return doc


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


# ─── Email verification (48h TTL, HMAC-hashed tokens) ────────────────────────
EMAIL_VERIFY_TTL_HOURS = 48
EMAIL_VERIFY_TTL_SEC = EMAIL_VERIFY_TTL_HOURS * 3600
EMAIL_VERIFY_RESEND_COOLDOWN_SEC = 60   # min seconds between manual resends per email


def _hmac_token(token: str) -> str:
    """HMAC-SHA256 hash with the JWT secret. Only the hash is stored in DB."""
    import hmac
    secret = (os.environ.get("JWT_SECRET", "") or "dev-secret").encode("utf-8")
    return hmac.new(secret, token.encode("utf-8"), hashlib.sha256).hexdigest()


async def _ensure_email_verifications_index():
    """Idempotent TTL index — created on first call."""
    try:
        await db.email_verifications.create_index(
            "created_at", expireAfterSeconds=EMAIL_VERIFY_TTL_SEC
        )
    except Exception as e:
        logger.warning("email_verifications TTL index creation failed: %s", e)


async def _issue_verification_email(user: dict, ip_addr: str = "", ua: str = "") -> None:
    """Generate a fresh token, persist its hash, and send the email via Resend.

    Old un-consumed tokens for the same user are invalidated (replaced by the
    new one) so reissuing doesn't pile up entries in the collection.
    """
    await _ensure_email_verifications_index()
    token = secrets.token_urlsafe(32)  # 256 bits of entropy
    token_hash = _hmac_token(token)
    now = datetime.now(timezone.utc)
    # Invalidate previous active tokens for this user
    await db.email_verifications.delete_many(
        {"user_id": user["id"], "consumed": {"$ne": True}}
    )
    await db.email_verifications.insert_one({
        "id": str(_uuid.uuid4()),
        "user_id": user["id"],
        "email": user["email"],
        "token_hash": token_hash,
        "ip": ip_addr,
        "user_agent": ua,
        "created_at": now,                     # BSON datetime — TTL index expects this
        "created_at_iso": now.isoformat(),     # human-readable copy
        "consumed": False,
    })
    # Build the link → frontend page consumes the token via POST /api/auth/verify-email
    from emails import APP_URL
    link = f"{APP_URL.rstrip('/')}/verify-email?token={token}"
    lang = (user.get("lang") or "bg").lower()
    if lang.startswith("ro"):
        subject = "Confirmă-ți adresa de email"
        body = f"""
          <p>Bună, {user.get('name','')},</p>
          <p>Mulțumim că te-ai înregistrat pe autoandbid.com. Te rugăm să-ți confirmi adresa de email apăsând butonul de mai jos:</p>
          <p><a href="{link}" style="background:#1B4D3E;color:#ffffff;padding:12px 22px;border-radius:10px;text-decoration:none;font-weight:600;display:inline-block;">Confirmă email</a></p>
          <p style="color:#6b7280;font-size:13px;">Linkul este valabil 48 de ore. Dacă nu ai inițiat această cerere, poți ignora acest mesaj.</p>
        """
    elif lang.startswith("en"):
        subject = "Verify your email address"
        body = f"""
          <p>Hi {user.get('name','')},</p>
          <p>Thanks for signing up on autoandbid.com. Please confirm your email address by clicking the button below:</p>
          <p><a href="{link}" style="background:#1B4D3E;color:#ffffff;padding:12px 22px;border-radius:10px;text-decoration:none;font-weight:600;display:inline-block;">Verify email</a></p>
          <p style="color:#6b7280;font-size:13px;">This link is valid for 48 hours. If you did not request this, you can safely ignore this email.</p>
        """
    else:
        subject = "Потвърдете имейл адреса си"
        body = f"""
          <p>Здравейте, {user.get('name','')},</p>
          <p>Благодарим, че се регистрирахте в autoandbid.com. Моля, потвърдете имейл адреса си, като натиснете бутона по-долу:</p>
          <p><a href="{link}" style="background:#1B4D3E;color:#ffffff;padding:12px 22px;border-radius:10px;text-decoration:none;font-weight:600;display:inline-block;">Потвърди имейл</a></p>
          <p style="color:#6b7280;font-size:13px;">Линкът е валиден 48 часа. Ако не сте инициирали това действие, можете да игнорирате имейла.</p>
        """
    await send_email(user["email"], subject, _shell(subject, body))


def register_routes():

    @router.post("/register")
    @_limiter.limit("5/minute")
    async def register(request: Request, response: Response, payload: UserRegister):
        if not payload.terms_accepted:
            raise HTTPException(status_code=400, detail="Моля, приемете Общите условия.")
        # Password complexity (8+, uppercase, digit/symbol)
        from services.password_security import validate_complexity, is_password_pwned
        err = validate_complexity(payload.password)
        if err:
            raise HTTPException(status_code=400, detail=err)
        # HaveIBeenPwned check (k-anonymity, no PII transmitted). Network failures
        # never block registration — `is_password_pwned` returns False on error.
        try:
            if await is_password_pwned(payload.password):
                raise HTTPException(
                    status_code=400,
                    detail="Тази парола е била открита в публични пробиви на сигурността. Моля, изберете друга.",
                )
        except HTTPException:
            raise
        except Exception:
            pass
        existing = await db.users.find_one({"email": payload.email.lower()})
        if existing:
            raise HTTPException(status_code=409, detail="Имейлът вече е регистриран")
        user_id = str(_uuid.uuid4())
        # Capture device + network fingerprint at the moment of T&C acceptance
        ip_addr = (request.client.host if request.client else "") or ""
        ua = (request.headers.get("user-agent") or "")[:500]
        lang_hdr = (request.headers.get("accept-language") or "")[:60]
        # Determine initial UI language from Accept-Language so push messages
        # are localized correctly even before the user opens the app.
        lh = (lang_hdr or "").lower()
        initial_lang = "bg"
        for code in ("ro", "en", "bg"):
            if code in lh:
                initial_lang = code
                break
        now_iso = datetime.now(timezone.utc).isoformat()
        # Auto-generate a URL-friendly profile slug from the display name.
        # The helper lives in server.py (single source of truth — same
        # slugifier is used for the one-time backfill at boot). We import
        # lazily here to avoid a circular import at module load.
        from server import _slugify_profile_name, _ensure_unique_profile_slug
        slug_base = _slugify_profile_name(payload.name.strip()) or f"user-{user_id[:6]}"
        profile_slug = await _ensure_unique_profile_slug(slug_base)
        doc = {
            "id": user_id,
            "email": payload.email.lower(),
            "name": payload.name.strip(),
            "profile_slug": profile_slug,
            "password_hash": _hash_password(payload.password),
            "role": "user",
            "lang": initial_lang,
            "created_at": now_iso,
            # Email verification (rolled out 30 Apr 2026). New accounts must
            # verify before bidding/commenting/selling. Older accounts have
            # neither flag set → they pass `require_verified_email`.
            "email_verified": False,
            "verification_required": True,
            # T&C audit trail (required for GDPR / ZZLD proof of consent)
            "terms_accepted": True,
            "terms_accepted_at": now_iso,
            "terms_accepted_ip": ip_addr,
            "terms_accepted_user_agent": ua,
            "terms_accepted_language": lang_hdr,
            "terms_version": (payload.terms_version or "v1")[:20],
        }
        await db.users.insert_one(doc)
        # Issue verification token + email (best-effort; even if email fails,
        # the user can request a resend).
        try:
            await _issue_verification_email(doc, ip_addr, ua)
        except Exception as e:
            logger.error("verification email failed: %s", e)
        # Also log into audit_log as a separate consent record (immutable)
        try:
            await db.audit_log.insert_one({
                "id": str(_uuid.uuid4()),
                "actor_id": user_id,
                "actor_email": doc["email"],
                "actor_role": "user",
                "action": "user.terms_accepted",
                "target_type": "user",
                "target_id": user_id,
                "details": {"terms_version": doc["terms_version"], "language": lang_hdr},
                "ip": ip_addr,
                "user_agent": ua,
                "at": now_iso,
            })
        except Exception as e:
            logger.warning("audit_log insert failed: %s", e)
        # Default 7-day session при регистрация (no "remember" UX тук).
        sess = await _create_session(user_id, request, remember=False, ttl_days=COOKIE_TTL_DAYS)
        token = _create_token(user_id, doc["email"], days=COOKIE_TTL_DAYS, sid=sess["id"])
        csrf = _set_auth_cookies(response, token, max_age_sec=COOKIE_TTL_SEC)
        return {"token": token, "csrf_token": csrf, "user": _sanitize(doc)}

    @router.post("/login")
    @_limiter.limit("10/minute")
    async def login(request: Request, response: Response, payload: UserLogin):
        email = payload.email.lower()
        user = await db.users.find_one({"email": email})
        # Константно-време проверка (M1): дори при липсващ потребител изпълняваме
        # bcrypt срещу dummy hash, за да не може атакуващ да отгатне валидни
        # имейли по разликата във времето на отговора.
        if not user:
            _verify_password(payload.password, _DUMMY_BCRYPT_HASH)
            raise HTTPException(status_code=401, detail="Грешен имейл или парола")

        # Per-account lockout: 10 неуспешни → 15 мин пауза.
        # Защитава срещу distributed brute-force от ботнет (rate limit-ът е per-IP).
        from datetime import datetime as _dt
        locked_until_iso = user.get("login_locked_until")
        if locked_until_iso:
            try:
                lu = _dt.fromisoformat(locked_until_iso.replace("Z", "+00:00"))
                if lu.tzinfo is None:
                    lu = lu.replace(tzinfo=timezone.utc)
                if lu > datetime.now(timezone.utc):
                    mins = max(1, int((lu - datetime.now(timezone.utc)).total_seconds() // 60))
                    raise HTTPException(
                        status_code=429,
                        detail=f"Твърде много неуспешни опити. Опитайте отново след {mins} минути.",
                    )
            except HTTPException:
                raise
            except Exception:
                pass

        if not _verify_password(payload.password, user["password_hash"]):
            # Increment failed-attempts counter; lock out after 10 in a row.
            now = datetime.now(timezone.utc)
            attempts = int(user.get("failed_login_attempts", 0)) + 1
            update: dict = {"$set": {"failed_login_attempts": attempts, "last_failed_login_at": now.isoformat()}}
            if attempts >= 10:
                update["$set"]["login_locked_until"] = (now + timedelta(minutes=15)).isoformat()
                update["$set"]["failed_login_attempts"] = 0  # reset counter when locking
            await db.users.update_one({"id": user["id"]}, update)
            raise HTTPException(status_code=401, detail="Грешен имейл или парола")

        # Successful auth: reset counters, opportunistically rehash to Argon2id
        # if the stored hash is still bcrypt or below the current parameter set.
        clear_doc: dict = {"failed_login_attempts": 0}
        unset_doc: dict = {"login_locked_until": "", "last_failed_login_at": ""}
        try:
            from services.password_security import needs_rehash as _needs_rehash
            if _needs_rehash(user["password_hash"]):
                clear_doc["password_hash"] = _hash_password(payload.password)
        except Exception:
            pass
        await db.users.update_one(
            {"id": user["id"]},
            {"$set": clear_doc, "$unset": unset_doc},
        )
        if user.get("banned"):
            raise HTTPException(status_code=403, detail="Акаунтът е блокиран. За въпроси: contact@autoandbid.com")

        # "Запомни ме" → 90 дни, иначе 7 дни.  Cap-нато на REMEMBER_TTL_DAYS.
        remember = bool(getattr(payload, "remember", False))
        ttl_days = REMEMBER_TTL_DAYS if remember else COOKIE_TTL_DAYS
        ttl_sec = ttl_days * 24 * 60 * 60

        # 2FA challenge flow — issue a short-lived challenge token instead of JWT
        if user.get("totp_enabled"):
            challenge = secrets.token_urlsafe(32)
            await db.auth_challenges.insert_one({
                "id": str(_uuid.uuid4()),
                "challenge": _sha256(challenge),
                "user_id": user["id"],
                "remember": remember,
                "expires_at": (datetime.now(timezone.utc) + timedelta(minutes=CHALLENGE_TTL_MIN)).isoformat(),
            })
            return {"requires_2fa": True, "challenge_token": challenge}

        token = _create_token(user["id"], email, days=ttl_days)
        # Създаваме session документ за този login.
        sess = await _create_session(user["id"], request, remember=remember, ttl_days=ttl_days)
        token = _create_token(user["id"], email, days=ttl_days, sid=sess["id"])
        csrf = _set_auth_cookies(response, token, max_age_sec=ttl_sec)
        return {"token": token, "csrf_token": csrf, "user": _sanitize(user)}

    @router.post("/2fa/verify")
    @_limiter.limit("10/minute")
    async def two_factor_verify(request: Request, response: Response, payload: TwoFactorVerify):
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
        # Възстановяваме "Запомни ме" избора от challenge документа.
        remember = bool(ch.get("remember"))
        ttl_days = REMEMBER_TTL_DAYS if remember else COOKIE_TTL_DAYS
        ttl_sec = ttl_days * 24 * 60 * 60
        sess = await _create_session(user["id"], request, remember=remember, ttl_days=ttl_days)
        token = _create_token(user["id"], user["email"], days=ttl_days, sid=sess["id"])
        csrf = _set_auth_cookies(response, token, max_age_sec=ttl_sec)
        return {"token": token, "csrf_token": csrf, "user": _sanitize(user)}

    @router.post("/2fa/enable")
    async def two_factor_enable(user: dict = Depends(_get_current_user)):
        """Returns a provisioning URI + QR code for the user to scan.
        Does NOT activate 2FA until /2fa/confirm is called with a valid code.
        """
        if user.get("totp_enabled"):
            raise HTTPException(status_code=400, detail="2FA вече е активирано")
        secret = pyotp.random_base32()
        uri = pyotp.totp.TOTP(secret).provisioning_uri(name=user["email"], issuer_name="autoandbid.com")
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
                <p style="margin:0 0 16px 0;">Получихме заявка за нулиране на паролата за вашия autoandbid.com акаунт.</p>
                <p style="margin:0 0 8px 0;">Вашият код за потвърждение (валиден {OTP_TTL_MIN} минути):</p>
                <div style="font-family:'Courier New',monospace;font-size:32px;letter-spacing:8px;background:#f6f7f8;padding:18px;text-align:center;border-radius:10px;border:1px solid #e5e7eb;margin:16px 0;"><strong>{code}</strong></div>
                <p style="color:#6b7280;font-size:13px;margin:24px 0 0 0;">Ако не сте правили такава заявка, можете спокойно да игнорирате това съобщение — паролата ви няма да бъде променена.</p>
                """,
            )
            await send_email(email, "autoandbid.com — Код за нулиране на парола", html)
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

        # Apply same complexity + HIBP rules as on registration
        from services.password_security import validate_complexity, is_password_pwned
        cerr = validate_complexity(payload.new_password)
        if cerr:
            raise HTTPException(status_code=400, detail=cerr)
        try:
            if await is_password_pwned(payload.new_password):
                raise HTTPException(
                    status_code=400,
                    detail="Тази парола е била открита в публични пробиви на сигурността. Моля, изберете друга.",
                )
        except HTTPException:
            raise
        except Exception:
            pass

        await db.users.update_one(
            {"id": user["id"]},
            {
                "$set": {"password_hash": _hash_password(payload.new_password), "failed_login_attempts": 0},
                "$unset": {"login_locked_until": ""},
            },
        )
        await db.password_resets.update_one({"id": rec["id"]}, {"$set": {"used": True, "used_at": datetime.now(timezone.utc).isoformat()}})
        return {"ok": True, "message": "Паролата е сменена. Можете да влезете с новата парола."}

    @router.get("/me")
    async def me(user: dict = Depends(_get_current_user)):
        u = _sanitize(user)
        u["totp_enabled"] = bool(user.get("totp_enabled"))
        u["lang"] = (user.get("lang") or "bg")
        return u

    # ─── Email verification endpoints ────────────────────────────────────────
    from pydantic import BaseModel as _BM

    class _VerifyTokenPayload(_BM):
        token: str

    @router.post("/verify-email")
    @_limiter.limit("20/hour")
    async def verify_email(request: Request, payload: _VerifyTokenPayload):
        """Consume a verification token and mark the user's email as verified.
        Atomic via findOneAndDelete → token cannot be replayed."""
        if not payload.token or len(payload.token) < 20:
            raise HTTPException(status_code=400, detail="Невалиден или изтекъл линк за потвърждение")
        token_hash = _hmac_token(payload.token)
        rec = await db.email_verifications.find_one_and_delete(
            {"token_hash": token_hash, "consumed": {"$ne": True}}
        )
        if not rec:
            raise HTTPException(status_code=400, detail="Невалиден или изтекъл линк за потвърждение")
        # TTL freshness check (defensive — TTL index may have ~1 min lag)
        created = rec.get("created_at")
        if isinstance(created, str):
            try:
                created = datetime.fromisoformat(created)
            except Exception:
                created = None
        if isinstance(created, datetime) and created.tzinfo is None:
            created = created.replace(tzinfo=timezone.utc)
        if created and (datetime.now(timezone.utc) - created).total_seconds() > EMAIL_VERIFY_TTL_SEC:
            raise HTTPException(status_code=400, detail="Невалиден или изтекъл линк за потвърждение")
        await db.users.update_one(
            {"id": rec["user_id"]},
            {"$set": {
                "email_verified": True,
                "verified_at": datetime.now(timezone.utc).isoformat(),
            }},
        )
        return {"ok": True, "message": "Имейлът е потвърден успешно."}

    @router.post("/resend-verification")
    @_limiter.limit("3/hour")
    async def resend_verification(request: Request, user: dict = Depends(_get_current_user)):
        """Re-issue a verification email for the currently authenticated user."""
        if user.get("email_verified"):
            return {"ok": True, "already_verified": True}
        # Per-user 60s cooldown beyond the @_limiter IP-level cap
        latest = await db.email_verifications.find_one(
            {"user_id": user["id"], "consumed": {"$ne": True}},
            sort=[("created_at", -1)],
        )
        if latest:
            created = latest.get("created_at")
            if isinstance(created, str):
                try:
                    created = datetime.fromisoformat(created)
                except Exception:
                    created = None
            if isinstance(created, datetime) and created.tzinfo is None:
                created = created.replace(tzinfo=timezone.utc)
            if created and (datetime.now(timezone.utc) - created).total_seconds() < EMAIL_VERIFY_RESEND_COOLDOWN_SEC:
                raise HTTPException(
                    status_code=429,
                    detail="Моля, изчакайте малко преди да поискате нов линк.",
                )
        ip_addr = (request.client.host if request.client else "") or ""
        ua = (request.headers.get("user-agent") or "")[:500]
        try:
            await _issue_verification_email(user, ip_addr, ua)
        except Exception as e:
            logger.error("resend verification failed: %s", e)
            raise HTTPException(status_code=500, detail="Грешка при изпращане. Опитайте по-късно.")
        return {"ok": True}

    @router.post("/logout")
    async def logout(request: Request, response: Response):
        """Изчиства auth cookies (httpOnly access_token + csrf_token) и
        изтрива текущата сесия от sessions колекцията (ако има)."""
        sid = None
        # Опитваме да разпознаем sid от JWT без верификация (токенът може да
        # е изтекъл, но за маркиране на сесия за изтриване това е достатъчно).
        import jwt as _jwt
        tok = None
        a = request.headers.get("Authorization", "")
        if a.startswith("Bearer "):
            tok = a[7:]
        if not tok:
            tok = request.cookies.get(ACCESS_COOKIE)
        if tok:
            try:
                p = _jwt.decode(tok, options={"verify_signature": False})
                sid = p.get("sid")
            except Exception:
                sid = None
        if sid:
            try:
                await db.sessions.delete_one({"id": sid})
            except Exception:
                pass
        _clear_auth_cookies(response)
        return {"ok": True}

    # ---- Sessions management (изход от устройства) ----
    @router.get("/sessions")
    async def list_sessions(request: Request, user: dict = Depends(_get_current_user)):
        """Списък активни сесии за текущия потребител с маркер за активната."""
        cursor = db.sessions.find({"user_id": user["id"]}, {"_id": 0, "user_agent": 0})
        items = []
        current_sid = getattr(request.state, "sid", None)
        async for s in cursor:
            s["is_current"] = (s.get("id") == current_sid)
            items.append(s)
        # Най-нови първо
        items.sort(key=lambda x: x.get("last_seen_at", ""), reverse=True)
        return {"sessions": items, "current_sid": current_sid}

    @router.delete("/sessions/{sid}")
    async def revoke_session(sid: str, request: Request, user: dict = Depends(_get_current_user)):
        """Прекратява избрана сесия (само ако принадлежи на текущия потребител)."""
        res = await db.sessions.delete_one({"id": sid, "user_id": user["id"]})
        if res.deleted_count == 0:
            raise HTTPException(status_code=404, detail="Сесията не е намерена")
        return {"ok": True, "revoked": sid}

    @router.post("/sessions/revoke-others")
    async def revoke_other_sessions(request: Request, response: Response, user: dict = Depends(_get_current_user)):
        """Изход от всички устройства (без текущото)."""
        current_sid = getattr(request.state, "sid", None)
        q = {"user_id": user["id"]}
        if current_sid:
            q["id"] = {"$ne": current_sid}
        res = await db.sessions.delete_many(q)
        return {"ok": True, "revoked_count": res.deleted_count}

    @router.post("/sessions/revoke-all")
    async def revoke_all_sessions(request: Request, response: Response, user: dict = Depends(_get_current_user)):
        """Изход от всички устройства, включително текущото."""
        res = await db.sessions.delete_many({"user_id": user["id"]})
        _clear_auth_cookies(response)
        return {"ok": True, "revoked_count": res.deleted_count}

    @router.get("/csrf")
    async def get_csrf(request: Request, response: Response):
        """Връща (и обновява, ако липсва) CSRF token cookie за SPA-та.
        Използва се от frontend при стартиране, ако access_token cookie вече
        съществува, но csrf_token cookie е изтрит/липсва.
        """
        existing = request.cookies.get(CSRF_COOKIE)
        if existing:
            return {"csrf_token": existing}
        csrf = secrets.token_urlsafe(32)
        response.set_cookie(
            key=CSRF_COOKIE, value=csrf, max_age=COOKIE_TTL_SEC,
            httponly=False, secure=COOKIE_SECURE, samesite=COOKIE_SAMESITE, path="/",
        )
        return {"csrf_token": csrf}

    @router.post("/me/lang")
    async def set_my_lang(payload: dict, user: dict = Depends(_get_current_user)):
        """Persist the user's UI language so push notifications are localized."""
        lang = (payload.get("lang") or "").strip().lower()[:2]
        if lang not in ("bg", "en", "ro"):
            raise HTTPException(status_code=400, detail="Невалиден език")
        await db.users.update_one({"id": user["id"]}, {"$set": {"lang": lang}})
        return {"ok": True, "lang": lang}

    @router.delete("/me")
    async def delete_me(user: dict = Depends(_get_current_user)):
        """GDPR right-to-erasure — user deletes own account and cascades data.
        Keeps auctions as ledger records (seller anonymized). Clears bids/comments/watches/saved searches/credits/VIN requests/reviews.
        """
        uid = user["id"]
        from services import bidding as bidding_svc
        bids_count = await bidding_svc.delete_bids_for_user(uid)
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
                "bids": bids_count, "comments": comments.deleted_count, "watches": watches.deleted_count,
                "saved_searches": saved.deleted_count, "credits": credits.deleted_count,
                "vin_requests": vins.deleted_count, "reviews": reviews.deleted_count, "notes": notes.deleted_count,
            },
        }
