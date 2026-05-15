"""
WebAuthn / FIDO2 passkey authentication.

This router implements the four standard WebAuthn endpoints (register/auth
× begin/finish) plus management endpoints (list, rename, remove). Passkeys
are an OPT-IN secondary login method — email/password and TOTP 2FA keep
working unchanged.

Architecture decisions:
  • RP ID = `autoandbid.bg` (canonical). The two regional TLDs
    (`autoandbid.com`, `autoandbid.ro`) participate via the
    Related Origin Requests manifest at `/.well-known/webauthn`,
    so a single passkey works on all three domains in modern browsers.
  • Challenges live in MongoDB with a TTL index → automatic single-use
    expiration after 600 seconds, no Redis needed.
  • `sign_count` is enforced strictly increasing → cloning detection.
  • Recent-auth gating instead of per-action password prompts: once the
    user verifies their password (login OR explicit `/reauth`), the
    session's `recent_auth_at` is bumped and add/remove operations are
    allowed for the next REAUTH_WINDOW_SECONDS. A stale 30-day session
    that no human typed a password into cannot enrol attacker keys.
  • Audit events captured for: created / removed / authenticated /
    failed_auth / clone_detection.

Library: `webauthn` (Duo Labs, modern fork of py_webauthn).
"""

from __future__ import annotations

import base64
import logging
import os
import secrets
import uuid as _uuid
from datetime import datetime, timedelta, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel
from webauthn import (
    generate_authentication_options,
    generate_registration_options,
    options_to_json,
    verify_authentication_response,
    verify_registration_response,
)
from webauthn.helpers.cose import COSEAlgorithmIdentifier
from webauthn.helpers.structs import (
    AttestationConveyancePreference,
    AuthenticatorAttachment,
    AuthenticatorSelectionCriteria,
    PublicKeyCredentialDescriptor,
    ResidentKeyRequirement,
    UserVerificationRequirement,
)

log = logging.getLogger(__name__)

# ---- Configuration ---------------------------------------------------------
# Canonical RP ID is `autoandbid.bg` (BG market is the primary one). The
# other two brand TLDs (.com, .ro) participate via the
# `/.well-known/webauthn` Related Origin Requests manifest, so a single
# passkey works on all three domains in modern browsers (Chromium 128+,
# Safari 18+).
RP_ID = os.environ.get("WEBAUTHN_RP_ID", "autoandbid.bg")
RP_NAME = os.environ.get("WEBAUTHN_RP_NAME", "Auto&Bid")
ALLOWED_ORIGINS = [
    "https://autoandbid.com",
    "https://autoandbid.bg",
    "https://autoandbid.ro",
    "https://www.autoandbid.com",
    "https://www.autoandbid.bg",
    "https://www.autoandbid.ro",
]
# In dev/preview the React app runs on a *.preview.emergentagent.com host.
# Allow it via env var so tests pass without leaking it into production.
_extra = os.environ.get("WEBAUTHN_EXTRA_ORIGINS", "").strip()
if _extra:
    ALLOWED_ORIGINS.extend(o.strip() for o in _extra.split(",") if o.strip())

# Re-auth window: how long a freshly-verified password remains "fresh"
# for sensitive operations (add / remove passkey). 10 minutes balances
# UX (no per-click password prompt) with security (a stolen long-lived
# session token cannot enrol attacker keys silently).
REAUTH_WINDOW_SECONDS = 10 * 60


def _auto_device_name(request: Request) -> str:
    """Generate a friendly device name from the User-Agent header.

    Used when the client doesn't supply an explicit name (the new
    default — UX request to skip the device-name prompt). Falls back
    to a stable label so the user can always tell devices apart in the
    list and rename later via `/rename/{id}`.
    """
    ua_raw = (request.headers.get("user-agent") or "").lower()
    try:
        from user_agents import parse as _ua_parse
        ua = _ua_parse(ua_raw or "Unknown")
        browser = (ua.browser.family or "Browser").strip()
        os_name = (ua.os.family or "Device").strip()
        if ua.is_mobile:
            return f"{browser} on {os_name}"[:80]
        return f"{browser} on {os_name}"[:80]
    except Exception:
        # Best-effort string matching when the user_agents pkg is missing.
        if "iphone" in ua_raw or "ipad" in ua_raw:
            return "iPhone/iPad"
        if "macintosh" in ua_raw or "mac os" in ua_raw:
            return "Mac"
        if "windows" in ua_raw:
            return "Windows"
        if "android" in ua_raw:
            return "Android"
        if "linux" in ua_raw:
            return "Linux"
        return "New device"


def _b64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode().rstrip("=")


def _b64url_decode(data: str) -> bytes:
    pad = (-len(data)) % 4
    return base64.urlsafe_b64decode(data + ("=" * pad))


# ---- Pydantic payload models ----------------------------------------------
class ReauthPayload(BaseModel):
    password: str


class RegisterBeginPayload(BaseModel):
    # Both optional — flows where the session is "recently authenticated"
    # skip the inline password and let the client auto-name the device.
    device_name: Optional[str] = None
    password: Optional[str] = None


class RegisterFinishPayload(BaseModel):
    credential: dict
    device_name: Optional[str] = None


class AuthBeginPayload(BaseModel):
    email: Optional[str] = None


class AuthFinishPayload(BaseModel):
    credential: dict


class TwoFactorBeginPayload(BaseModel):
    challenge_token: str


class RenamePayload(BaseModel):
    name: str


class RemovePayload(BaseModel):
    # Optional — recent-auth window replaces it in normal use.
    password: Optional[str] = None


# ---- Audit helper ---------------------------------------------------------
async def _audit(db, user_id: str, action: str, request: Request, **extra):
    try:
        await db.passkey_audit_log.insert_one({
            "id": str(_uuid.uuid4()),
            "user_id": user_id,
            "action": action,
            "ip": request.client.host if request.client else None,
            "user_agent": (request.headers.get("user-agent") or "")[:512],
            "origin": request.headers.get("origin"),
            "at": datetime.now(timezone.utc).isoformat(),
            **extra,
        })
    except Exception as e:  # noqa: BLE001
        log.warning("passkey audit insert failed: %s", e)


def _verify_origin(request: Request) -> str:
    origin = request.headers.get("origin") or ""
    if origin not in ALLOWED_ORIGINS:
        raise HTTPException(
            status_code=403,
            detail=f"Origin {origin or '(missing)'} not authorised for WebAuthn.",
        )
    return origin


# ---- Router builder -------------------------------------------------------
def build_passkey_router(
    *,
    db,
    get_current_user,
    verify_password,            # callable(user_doc, password_str) -> bool
    create_token,               # callable(uid, email, days, sid=None) -> str
    create_session,             # async callable(user_id, request, remember, ttl_days) -> session dict
    set_auth_cookies,           # callable(response, token, max_age_sec) -> csrf
    remember_ttl_days: int,
    cookie_ttl_days: int,
    sanitize_user,              # callable(user) -> dict (strips secrets)
) -> APIRouter:
    """Inject DB + auth helpers from server.py so we don't fork those flows."""
    router = APIRouter(prefix="/auth/passkey", tags=["auth", "passkey"])

    # ── Recent-auth gate ─────────────────────────────────────────────────
    async def _session_recent_auth(request: Request) -> tuple[bool, Optional[dict]]:
        """Return (is_recent, session_doc). `is_recent` means the user
        verified their password within `REAUTH_WINDOW_SECONDS`.

        We read the JWT-bound session id from `request.state.sid` (set by
        `get_current_user`) and look at the session's `recent_auth_at`
        field. Older sessions that pre-date this field — e.g. existing
        users with cookies from before the migration — are treated as
        non-recent so they're prompted for the password once.
        """
        sid = getattr(request.state, "sid", None)
        if not sid:
            return False, None
        sess = await db.sessions.find_one({"id": sid}, {"_id": 0})
        if not sess:
            return False, None
        raw = sess.get("recent_auth_at")
        if not raw:
            return False, sess
        try:
            ts = datetime.fromisoformat(raw)
        except (ValueError, TypeError):
            return False, sess
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        age = (datetime.now(timezone.utc) - ts).total_seconds()
        return age < REAUTH_WINDOW_SECONDS, sess

    async def _bump_recent_auth(request: Request) -> None:
        """Mark the current session as freshly password-verified."""
        sid = getattr(request.state, "sid", None)
        if not sid:
            return
        await db.sessions.update_one(
            {"id": sid},
            {"$set": {"recent_auth_at": datetime.now(timezone.utc).isoformat()}},
        )

    @router.get("/reauth-status")
    async def reauth_status(request: Request, user: dict = Depends(get_current_user)):
        """Tell the client whether sensitive passkey operations can be
        performed without an additional password prompt.

        Returns `{recent: true, fresh_for_sec: <seconds left>}` when the
        session is inside the re-auth window. Otherwise the client should
        render the password gate before invoking add/remove.
        """
        recent, sess = await _session_recent_auth(request)
        out: dict = {"recent": recent, "window_seconds": REAUTH_WINDOW_SECONDS}
        if recent and sess and sess.get("recent_auth_at"):
            try:
                ts = datetime.fromisoformat(sess["recent_auth_at"])
                if ts.tzinfo is None:
                    ts = ts.replace(tzinfo=timezone.utc)
                age = (datetime.now(timezone.utc) - ts).total_seconds()
                out["fresh_for_sec"] = max(0, int(REAUTH_WINDOW_SECONDS - age))
            except Exception:
                pass
        return out

    @router.post("/reauth")
    async def reauth(
        request: Request,
        payload: ReauthPayload,
        user: dict = Depends(get_current_user),
    ):
        """Verify the user's password and bump `recent_auth_at` on the
        current session so subsequent add/remove calls within
        `REAUTH_WINDOW_SECONDS` skip the password prompt.
        """
        if not await verify_password(user, payload.password):
            await _audit(db, user["id"], "reauth_failed", request)
            raise HTTPException(status_code=401, detail="Грешна парола.")
        await _bump_recent_auth(request)
        await _audit(db, user["id"], "reauth_ok", request)
        return {"ok": True, "fresh_for_sec": REAUTH_WINDOW_SECONDS}

    # ── REGISTRATION ─────────────────────────────────────────────────────
    @router.post("/register-begin")
    async def register_begin(
        request: Request,
        payload: RegisterBeginPayload,
        user: dict = Depends(get_current_user),
    ):
        """Step 1 of registration. Issue publicKeyCredentialCreationOptions.

        Authentication policy: the operation is allowed when either
        (a) the session is inside the re-auth window — set on login or
        explicit `/reauth` — OR (b) the client supplies a fresh password
        in the payload. Falling back to (b) lets legacy clients keep
        working until they pick up the new `/reauth` flow.
        """
        _verify_origin(request)
        recent, _ = await _session_recent_auth(request)
        if not recent:
            if not payload.password or not await verify_password(user, payload.password):
                raise HTTPException(
                    status_code=401,
                    detail="Необходимо е скорошно потвърждаване с парола.",
                    headers={"X-Reauth-Required": "1"},
                )
            # Honour the implicit password verification as a recent-auth event.
            await _bump_recent_auth(request)

        # Exclude already-registered creds so the same authenticator
        # cannot be enrolled twice (browser will show "already registered").
        existing = await db.passkey_credentials.find(
            {"user_id": user["id"]}, {"_id": 0, "credential_id": 1, "transports": 1}
        ).to_list(50)
        exclude_credentials = [
            PublicKeyCredentialDescriptor(id=_b64url_decode(c["credential_id"]))
            for c in existing
        ]

        opts = generate_registration_options(
            rp_id=RP_ID,
            rp_name=RP_NAME,
            user_id=user["id"].encode(),
            user_name=user["email"],
            user_display_name=user.get("name") or user["email"],
            attestation=AttestationConveyancePreference.NONE,
            authenticator_selection=AuthenticatorSelectionCriteria(
                # Don't pin to platform — let users register security keys too.
                resident_key=ResidentKeyRequirement.PREFERRED,
                user_verification=UserVerificationRequirement.PREFERRED,
            ),
            supported_pub_key_algs=[
                COSEAlgorithmIdentifier.ECDSA_SHA_256,
                COSEAlgorithmIdentifier.RSASSA_PKCS1_v1_5_SHA_256,
            ],
            exclude_credentials=exclude_credentials,
        )

        # Auto-name when the client didn't supply one — UX request to
        # remove the device-name prompt. The user can rename later via
        # `/auth/passkey/rename/{id}`.
        device_name = (payload.device_name or "").strip() or _auto_device_name(request)

        # Persist the challenge for ~10 min so register-finish can verify it.
        # TTL index on `expires_at` will auto-expire abandoned challenges.
        challenge_b64 = _b64url_encode(opts.challenge)
        await db.passkey_challenges.insert_one({
            "id": str(_uuid.uuid4()),
            "challenge": challenge_b64,
            "user_id": user["id"],
            "operation": "register",
            "device_name": device_name[:80],
            "expires_at": datetime.now(timezone.utc) + timedelta(minutes=10),
        })
        return {"options": options_to_json(opts), "device_name": device_name}

    @router.post("/register-finish")
    async def register_finish(
        request: Request,
        payload: RegisterFinishPayload,
        user: dict = Depends(get_current_user),
    ):
        origin = _verify_origin(request)
        # Pop the challenge so it's single-use (replay prevention).
        challenge_doc = await db.passkey_challenges.find_one_and_delete({
            "user_id": user["id"], "operation": "register",
        })
        if not challenge_doc:
            raise HTTPException(status_code=400, detail="No active passkey challenge — restart registration.")

        try:
            verification = verify_registration_response(
                credential=payload.credential,
                expected_challenge=_b64url_decode(challenge_doc["challenge"]),
                expected_origin=ALLOWED_ORIGINS,  # any of the three brand TLDs
                expected_rp_id=RP_ID,
                require_user_verification=False,
            )
        except Exception as e:  # noqa: BLE001
            log.warning("passkey register verify failed for user=%s: %s", user["id"], e)
            await _audit(db, user["id"], "register_failed", request, error=str(e)[:200])
            raise HTTPException(status_code=400, detail="Регистрацията на ключа неуспешна.")

        cred_id_b64 = _b64url_encode(verification.credential_id)
        # Reject duplicates (defense in depth — exclude_credentials should
        # already prevent this client-side).
        if await db.passkey_credentials.find_one({"credential_id": cred_id_b64}):
            raise HTTPException(status_code=409, detail="Този passkey вече е регистриран.")

        transports = []
        try:
            transports = list(payload.credential.get("response", {}).get("transports") or [])
        except Exception:
            transports = []

        # Name resolution order:
        #   1. Client-supplied (legacy clients still send this).
        #   2. Name we generated at register-begin from User-Agent.
        #   3. Generic fallback.
        name = (payload.device_name or "").strip() \
            or (challenge_doc.get("device_name") or "").strip() \
            or "Passkey"
        await db.passkey_credentials.insert_one({
            "id": str(_uuid.uuid4()),
            "user_id": user["id"],
            "credential_id": cred_id_b64,
            "public_key": _b64url_encode(verification.credential_public_key),
            "sign_count": verification.sign_count,
            "transports": transports,
            "device_name": name[:80],
            "created_at": datetime.now(timezone.utc).isoformat(),
            "last_used_at": None,
            "rp_id_when_created": RP_ID,
            "origin_when_created": origin,
        })
        await _audit(db, user["id"], "passkey_created", request, credential_id=cred_id_b64)
        return {"ok": True, "credential_id": cred_id_b64, "device_name": name[:80]}

    # ── PRIMARY AUTHENTICATION (login page) ─────────────────────────────
    @router.get("/has-passkey")
    async def has_passkey(email: str):
        """Email-blur hint: does this account have any passkey enrolled?

        Returns `{has: bool}`. We intentionally don't reveal whether the
        email exists at all (always `false` for non-users to avoid
        enumeration).
        """
        u = await db.users.find_one({"email": (email or "").strip().lower()}, {"_id": 0, "id": 1})
        if not u:
            return {"has": False}
        n = await db.passkey_credentials.count_documents({"user_id": u["id"]})
        return {"has": n > 0}

    @router.post("/authenticate-begin")
    async def authenticate_begin(request: Request, payload: AuthBeginPayload):
        """Step 1 of login. If `email` is supplied, restrict allowed creds
        to that user (good UX — browser only prompts for matching keys).
        Otherwise emit an empty `allowCredentials` list so resident-key
        authenticators can self-discover (passkey autofill on iOS/Android)."""
        _verify_origin(request)
        allow: list[PublicKeyCredentialDescriptor] = []
        target_uid: Optional[str] = None
        if payload.email:
            u = await db.users.find_one(
                {"email": payload.email.strip().lower()},
                {"_id": 0, "id": 1},
            )
            if u:
                target_uid = u["id"]
                creds = await db.passkey_credentials.find(
                    {"user_id": u["id"]}, {"_id": 0, "credential_id": 1, "transports": 1}
                ).to_list(50)
                allow = [
                    PublicKeyCredentialDescriptor(id=_b64url_decode(c["credential_id"]))
                    for c in creds
                ]

        opts = generate_authentication_options(
            rp_id=RP_ID,
            allow_credentials=allow if allow else None,
            user_verification=UserVerificationRequirement.PREFERRED,
        )
        challenge_b64 = _b64url_encode(opts.challenge)
        await db.passkey_challenges.insert_one({
            "id": str(_uuid.uuid4()),
            "challenge": challenge_b64,
            "user_id": target_uid,
            "operation": "authenticate",
            "expires_at": datetime.now(timezone.utc) + timedelta(minutes=10),
        })
        return {"options": options_to_json(opts)}

    async def _verify_assertion_and_login(
        request: Request,
        response: Response,
        credential: dict,
        operation: str,
        remember: bool = False,
    ):
        """Shared verification path used by both primary login and
        2FA-as-passkey flow. Returns the user dict on success and sets
        the auth cookies on `response`."""
        _verify_origin(request)
        cred_id = credential.get("id") or credential.get("rawId")
        if not cred_id:
            raise HTTPException(status_code=400, detail="Missing credential id.")
        stored = await db.passkey_credentials.find_one({"credential_id": cred_id}, {"_id": 0})
        if not stored:
            raise HTTPException(status_code=401, detail="Този passkey не е разпознат.")
        # Single-use challenge: the most recent challenge for this user
        # (or for `target_uid=None` discoverable flow — match any).
        chq = await db.passkey_challenges.find_one_and_delete(
            {"operation": operation, "$or": [{"user_id": stored["user_id"]}, {"user_id": None}]},
            sort=[("expires_at", -1)],
        )
        if not chq:
            raise HTTPException(status_code=400, detail="No active challenge — start over.")

        try:
            verification = verify_authentication_response(
                credential=credential,
                expected_challenge=_b64url_decode(chq["challenge"]),
                expected_rp_id=RP_ID,
                expected_origin=ALLOWED_ORIGINS,
                credential_public_key=_b64url_decode(stored["public_key"]),
                credential_current_sign_count=stored["sign_count"],
                require_user_verification=False,
            )
        except Exception as e:  # noqa: BLE001
            log.warning("passkey auth verify failed cred=%s: %s", cred_id[:12], e)
            await _audit(db, stored["user_id"], "auth_failed", request, error=str(e)[:200])
            raise HTTPException(status_code=401, detail="Passkey удостоверяване неуспешно.")

        # Sign-count cloning detection: must strictly increase except for
        # the (legitimate) case where the authenticator never increments.
        new_count = verification.new_sign_count
        if new_count and new_count <= stored["sign_count"]:
            await _audit(
                db, stored["user_id"], "clone_suspected", request,
                stored=stored["sign_count"], received=new_count,
            )
            raise HTTPException(status_code=401, detail="Passkey не премина проверка за клониране.")

        await db.passkey_credentials.update_one(
            {"credential_id": cred_id},
            {"$set": {
                "sign_count": new_count,
                "last_used_at": datetime.now(timezone.utc).isoformat(),
            }},
        )
        user = await db.users.find_one({"id": stored["user_id"]})
        if not user:
            raise HTTPException(status_code=401, detail="Потребителят не съществува.")

        ttl_days = remember_ttl_days if remember else cookie_ttl_days
        ttl_sec = ttl_days * 24 * 60 * 60
        sess = await create_session(user["id"], request, remember=remember, ttl_days=ttl_days)
        token = create_token(user["id"], user["email"], days=ttl_days, sid=sess["id"])
        csrf = set_auth_cookies(response, token, max_age_sec=ttl_sec)
        await _audit(db, user["id"], "passkey_authenticated", request, credential_id=cred_id)
        return {"token": token, "csrf_token": csrf, "user": sanitize_user(user)}

    @router.post("/authenticate-finish")
    async def authenticate_finish(request: Request, response: Response, payload: AuthFinishPayload):
        return await _verify_assertion_and_login(
            request, response, payload.credential, operation="authenticate"
        )

    # ── 2FA ALTERNATIVE ─────────────────────────────────────────────────
    # When TOTP step is required (login returned `requires_2fa: true`),
    # the user can choose to use a passkey instead.
    @router.post("/2fa-begin")
    async def two_factor_begin(request: Request, payload: TwoFactorBeginPayload):
        """Issue a passkey challenge bound to an active 2FA challenge_token."""
        _verify_origin(request)
        # Reuse the existing 2FA challenge_doc to look up the user.
        from hashlib import sha256
        ch_hash = sha256(payload.challenge_token.encode()).hexdigest()
        ch = await db.auth_challenges.find_one({"challenge": ch_hash}, {"_id": 0})
        if not ch:
            raise HTTPException(status_code=401, detail="Невалиден challenge.")
        if datetime.fromisoformat(ch["expires_at"]) < datetime.now(timezone.utc):
            raise HTTPException(status_code=401, detail="Challenge изтече.")

        creds = await db.passkey_credentials.find(
            {"user_id": ch["user_id"]}, {"_id": 0, "credential_id": 1}
        ).to_list(50)
        if not creds:
            raise HTTPException(status_code=400, detail="Няма регистрирани passkeys за акаунта.")
        allow = [PublicKeyCredentialDescriptor(id=_b64url_decode(c["credential_id"])) for c in creds]
        opts = generate_authentication_options(
            rp_id=RP_ID,
            allow_credentials=allow,
            user_verification=UserVerificationRequirement.PREFERRED,
        )
        challenge_b64 = _b64url_encode(opts.challenge)
        await db.passkey_challenges.insert_one({
            "id": str(_uuid.uuid4()),
            "challenge": challenge_b64,
            "user_id": ch["user_id"],
            "operation": "2fa",
            "auth_challenge_hash": ch_hash,
            "expires_at": datetime.now(timezone.utc) + timedelta(minutes=10),
        })
        return {"options": options_to_json(opts)}

    @router.post("/2fa-finish")
    async def two_factor_finish(
        request: Request,
        response: Response,
        payload: AuthFinishPayload,
        challenge_token: str,
    ):
        """Verify the passkey assertion and issue the JWT cookie that
        normal `/auth/2fa/verify` would have issued."""
        from hashlib import sha256
        ch_hash = sha256(challenge_token.encode()).hexdigest()
        ch = await db.auth_challenges.find_one({"challenge": ch_hash}, {"_id": 0})
        if not ch:
            raise HTTPException(status_code=401, detail="Невалиден challenge.")
        result = await _verify_assertion_and_login(
            request, response, payload.credential, operation="2fa", remember=bool(ch.get("remember")),
        )
        # Consume the 2FA challenge so it can't be reused via TOTP after.
        await db.auth_challenges.delete_one({"challenge": ch_hash})
        return result

    # ── MANAGEMENT ──────────────────────────────────────────────────────
    @router.get("/list")
    async def list_passkeys(user: dict = Depends(get_current_user)):
        items = await db.passkey_credentials.find(
            {"user_id": user["id"]},
            {"_id": 0, "credential_id": 1, "device_name": 1, "created_at": 1,
             "last_used_at": 1, "transports": 1},
        ).sort("created_at", -1).to_list(50)
        return {"items": items}

    @router.post("/remove/{credential_id}")
    async def remove_passkey(
        credential_id: str,
        request: Request,
        payload: RemovePayload,
        user: dict = Depends(get_current_user),
    ):
        """Delete a registered passkey.

        Same auth gate as `register-begin`: recent-auth window OR
        explicit password in the payload. Clients in the new flow won't
        send the password; the recent-auth check covers them.
        """
        recent, _ = await _session_recent_auth(request)
        if not recent:
            if not payload.password or not await verify_password(user, payload.password):
                raise HTTPException(
                    status_code=401,
                    detail="Необходимо е скорошно потвърждаване с парола.",
                    headers={"X-Reauth-Required": "1"},
                )
            await _bump_recent_auth(request)
        res = await db.passkey_credentials.delete_one({
            "credential_id": credential_id,
            "user_id": user["id"],
        })
        if not res.deleted_count:
            raise HTTPException(status_code=404, detail="Passkey не е намерен.")
        await _audit(db, user["id"], "passkey_removed", request, credential_id=credential_id)
        return {"ok": True}

    @router.post("/rename/{credential_id}")
    async def rename_passkey(
        credential_id: str,
        request: Request,
        payload: RenamePayload,
        user: dict = Depends(get_current_user),
    ):
        """Rename a registered passkey. No re-auth required — this is
        cosmetic metadata, not a privilege escalation. Names are clamped
        to 80 characters and stripped of leading/trailing whitespace.
        """
        new_name = (payload.name or "").strip()[:80]
        if not new_name:
            raise HTTPException(status_code=400, detail="Името не може да е празно.")
        res = await db.passkey_credentials.update_one(
            {"credential_id": credential_id, "user_id": user["id"]},
            {"$set": {"device_name": new_name}},
        )
        if not res.matched_count:
            raise HTTPException(status_code=404, detail="Passkey не е намерен.")
        await _audit(db, user["id"], "passkey_renamed", request, credential_id=credential_id)
        return {"ok": True, "device_name": new_name}

    return router
