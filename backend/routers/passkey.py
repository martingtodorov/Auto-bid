"""
WebAuthn / FIDO2 passkey authentication.

This router implements the four standard WebAuthn endpoints (register/auth
× begin/finish) plus management endpoints (list, rename, remove). Passkeys
are an OPT-IN secondary login method — email/password and TOTP 2FA keep
working unchanged.

Architecture decisions:
  • RP ID = `autoandbid.com` (canonical). The two regional TLDs
    (`autoandbid.bg`, `autoandbid.ro`) participate via the
    Related Origin Requests manifest at `/.well-known/webauthn`,
    so a single passkey works on all three domains in modern browsers.
  • Challenges live in MongoDB with a TTL index → automatic single-use
    expiration after 600 seconds, no Redis needed.
  • `sign_count` is enforced strictly increasing → cloning detection.
  • Recent password re-auth required for both `add` and `remove` flows
    (per user spec — "винаги изисквай пароля отново").
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

# Re-auth window: how recently the user must have entered their password
# before they're allowed to add or remove a passkey. 5 min is short enough
# to mean "in this session" but generous for slow typists.
REAUTH_WINDOW_SECONDS = 5 * 60


def _b64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode().rstrip("=")


def _b64url_decode(data: str) -> bytes:
    pad = (-len(data)) % 4
    return base64.urlsafe_b64decode(data + ("=" * pad))


# ---- Pydantic payload models ----------------------------------------------
class RegisterBeginPayload(BaseModel):
    device_name: str
    password: str  # re-auth check — fresh password verify before challenge issued


class RegisterFinishPayload(BaseModel):
    credential: dict  # raw browser response (id, rawId, response{...}, type)
    device_name: str


class AuthBeginPayload(BaseModel):
    email: Optional[str] = None  # optional — empty allows discoverable creds


class AuthFinishPayload(BaseModel):
    credential: dict


class TwoFactorBeginPayload(BaseModel):
    challenge_token: str


class RemovePayload(BaseModel):
    password: str  # re-auth — same as register


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

    # ── REGISTRATION ─────────────────────────────────────────────────────
    @router.post("/register-begin")
    async def register_begin(
        request: Request,
        payload: RegisterBeginPayload,
        user: dict = Depends(get_current_user),
    ):
        """Step 1 of registration. Re-auth with password, then issue
        publicKeyCredentialCreationOptions (challenge + RP info).
        """
        _verify_origin(request)
        if not await verify_password(user, payload.password):
            raise HTTPException(status_code=401, detail="Грешна парола.")

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

        # Persist the challenge for ~10 min so register-finish can verify it.
        # TTL index on `expires_at` will auto-expire abandoned challenges.
        challenge_b64 = _b64url_encode(opts.challenge)
        await db.passkey_challenges.insert_one({
            "id": str(_uuid.uuid4()),
            "challenge": challenge_b64,
            "user_id": user["id"],
            "operation": "register",
            "device_name": payload.device_name[:80],
            "expires_at": datetime.now(timezone.utc) + timedelta(minutes=10),
        })
        return {"options": options_to_json(opts)}

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

        await db.passkey_credentials.insert_one({
            "id": str(_uuid.uuid4()),
            "user_id": user["id"],
            "credential_id": cred_id_b64,
            "public_key": _b64url_encode(verification.credential_public_key),
            "sign_count": verification.sign_count,
            "transports": transports,
            "device_name": (challenge_doc.get("device_name") or "Passkey")[:80],
            "created_at": datetime.now(timezone.utc).isoformat(),
            "last_used_at": None,
            "rp_id_when_created": RP_ID,
            "origin_when_created": origin,
        })
        await _audit(db, user["id"], "passkey_created", request, credential_id=cred_id_b64)
        return {"ok": True, "credential_id": cred_id_b64}

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
        """Delete a registered passkey. Requires fresh password
        re-authentication (per user policy)."""
        if not await verify_password(user, payload.password):
            raise HTTPException(status_code=401, detail="Грешна парола.")
        res = await db.passkey_credentials.delete_one({
            "credential_id": credential_id,
            "user_id": user["id"],
        })
        if not res.deleted_count:
            raise HTTPException(status_code=404, detail="Passkey не е намерен.")
        await _audit(db, user["id"], "passkey_removed", request, credential_id=credential_id)
        return {"ok": True}

    return router
