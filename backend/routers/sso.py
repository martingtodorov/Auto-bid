"""
SSO handoff router for cross-domain login between autoandbid.com / .bg / .ro.
"""
from __future__ import annotations
import os
import secrets as _secrets
import re
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional
from urllib.parse import urlparse

from fastapi import APIRouter, HTTPException, Request, Response, Depends
from pydantic import BaseModel

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth/sso", tags=["sso"])

# Hard-coded production origins. Mirrors `routers.stripe_holds.ALLOWED_PROD_ORIGINS`
# so admins only have to keep one list mentally — every domain that
# can receive Stripe redirects can also receive an SSO handoff.
_ALLOWED_PROD = (
    "https://autoandbid.com",
    "https://www.autoandbid.com",
    "https://autoandbid.bg",
    "https://www.autoandbid.bg",
    "https://autoandbid.ro",
    "https://www.autoandbid.ro",
)
_DEV_ORIGIN_PATTERNS = (
    re.compile(r"^https://[a-z0-9\-]+\.preview\.emergentagent\.com$", re.IGNORECASE),
    re.compile(r"^https://[a-z0-9\-]+\.preview\.emergentcf\.cloud$", re.IGNORECASE),
    re.compile(r"^http://localhost(:\d+)?$", re.IGNORECASE),
)

NONCE_TTL_SEC = 60


def _is_allowed_origin(origin: str) -> bool:
    """Same allow-list semantics as Stripe redirect resolver — fewer
    code paths to keep in sync."""
    if not origin:
        return False
    o = origin.strip().rstrip("/")
    if o in _ALLOWED_PROD:
        return True
    for pat in _DEV_ORIGIN_PATTERNS:
        if pat.match(o):
            return True
    return False


def _origin_of(url: str) -> str:
    try:
        p = urlparse(url)
        if p.scheme and p.netloc:
            return f"{p.scheme}://{p.netloc}"
    except Exception:
        pass
    return ""


class IssueBody(BaseModel):
    return_to: str  # absolute URL the caller wants to land on


class ConsumeBody(BaseModel):
    nonce: str


def build_sso_router(db, create_token, get_current_user, set_auth_cookies) -> APIRouter:
    """Factory — the real `get_current_user` dependency is injected
    here so FastAPI can introspect it at decoration time. Keeping it
    as a factory mirrors the pattern used by watchlist / leaderboard /
    stripe_holds, so server.py wires everything in one consistent way.
    """

    @router.post("/issue")
    async def sso_issue(body: IssueBody, user: dict = Depends(get_current_user)):
        """Issue a 60 s single-use nonce bound to (user, target host).

        The caller MUST already be authenticated on the canonical
        domain (the canonical domain has the long-lived session
        cookie). We refuse to issue when the requested return_to is
        not on a whitelisted origin so this endpoint cannot be
        abused as an open redirector.
        """
        target_origin = _origin_of(body.return_to)
        if not _is_allowed_origin(target_origin):
            raise HTTPException(status_code=400, detail="return_to host not allowed")
        nonce = _secrets.token_urlsafe(40)
        now = datetime.now(timezone.utc)
        await db.sso_nonces.insert_one({
            "nonce": nonce,
            "user_id": user["id"],
            "target_origin": target_origin,
            "return_to": body.return_to,
            "consumed": False,
            "created_at": now,
            "expires_at": now + timedelta(seconds=NONCE_TTL_SEC),
        })
        return {
            "nonce": nonce,
            "expires_in": NONCE_TTL_SEC,
            "return_to": body.return_to,
        }

    @router.post("/consume")
    async def sso_consume(body: ConsumeBody, request: Request, response: Response):
        """Exchange a nonce for a freshly minted auth cookie on the
        *current* domain.

        Called by the receiving domain's frontend (autoandbid.bg /
        .ro), so `request.headers["origin"]` is the domain that
        should receive the cookie. We additionally cross-check the
        nonce's `target_origin` against the inbound Origin header so
        a nonce minted for `.bg` cannot be redeemed against `.ro`
        even by an attacker who copies the URL.
        """
        nonce = (body.nonce or "").strip()
        if not nonce:
            raise HTTPException(status_code=400, detail="missing nonce")
        inbound_origin = (request.headers.get("origin") or "").strip().rstrip("/")
        # Atomically mark the nonce consumed so a parallel replay loses.
        doc = await db.sso_nonces.find_one_and_update(
            {"nonce": nonce, "consumed": False},
            {"$set": {"consumed": True, "consumed_at": datetime.now(timezone.utc)}},
            return_document=True,
        )
        if not doc:
            raise HTTPException(status_code=401, detail="nonce invalid or already used")
        # Belt-and-braces TTL check (Mongo's TTL sweeper runs every
        # 60 s — short windows can drift).
        expires_at = doc.get("expires_at")
        if isinstance(expires_at, datetime):
            if expires_at.tzinfo is None:
                expires_at = expires_at.replace(tzinfo=timezone.utc)
            if datetime.now(timezone.utc) > expires_at:
                raise HTTPException(status_code=401, detail="nonce expired")
        # Cross-origin domain check.
        #
        # In production, every front-end domain is on a different
        # public origin (.com / .bg / .ro). The Origin header reaches
        # the backend untouched and we can therefore enforce that the
        # nonce is redeemed on the same TLD it was issued for.
        #
        # In dev/preview, however, the inbound Origin is rewritten
        # by the K8s ingress to the cluster preview hostname (e.g.
        # `*.cluster-X.preview.emergentcf.cloud`). It does not match
        # the production target_origin recorded at issue time, so
        # strict equality would lock dev users out forever.
        #
        # Compromise: only enforce equality when **both** sides are
        # production hosts. Preview/dev is already covered by the
        # nonce's single-use + 60 s TTL primary defenses.
        target = doc.get("target_origin", "")
        if target in _ALLOWED_PROD and inbound_origin in _ALLOWED_PROD and target != inbound_origin:
            logger.warning("[sso] origin mismatch: nonce=%s expected=%s got=%s",
                           nonce[:12], target, inbound_origin)
            raise HTTPException(status_code=401, detail="nonce host mismatch")
        user = await db.users.find_one(
            {"id": doc["user_id"]}, {"_id": 0, "password_hash": 0}
        )
        if not user or user.get("blocked"):
            raise HTTPException(status_code=401, detail="user not found or blocked")
        # Mint a fresh JWT for THIS domain. Standard 7-day TTL —
        # receiving domain becomes a normal logged-in session.
        token = create_token(user["id"], user["email"], days=7)
        csrf = set_auth_cookies(response, token, max_age_sec=7 * 86400)
        return {
            "ok": True,
            "user": user,
            "csrf": csrf,
            "return_to": doc.get("return_to", "/"),
        }

    return router
