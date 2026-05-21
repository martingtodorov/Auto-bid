from dotenv import load_dotenv
from pathlib import Path

ROOT_DIR = Path(__file__).parent
# `override=True` so values in /app/backend/.env always win over the
# parent process's shell env. Without this, the K8s pod's placeholder
# `STRIPE_API_KEY=sk_test_emergent` (set in /etc/environment) would
# shadow the real test key configured in `.env`, silently breaking
# all live Stripe API calls.
load_dotenv(ROOT_DIR / '.env', override=True)

import os
import asyncio
import time
import uuid
import logging
import bcrypt
import jwt
from datetime import datetime, timezone, timedelta
from typing import List, Optional
from fastapi import FastAPI, APIRouter, HTTPException, Depends, Request, Query, WebSocket, WebSocketDisconnect, Response, UploadFile, File
from fastapi.responses import PlainTextResponse
from starlette.middleware.cors import CORSMiddleware
import re
from motor.motor_asyncio import AsyncIOMotorClient
from pymongo import ReturnDocument
from pydantic import BaseModel, Field, EmailStr, ConfigDict

from emails import email_outbid, email_won, email_approved, email_rejected, email_seller_new_bid, email_seller_new_comment, email_vin_delivery, notify_auction_finalized
from ws import hub
from sms import send_sms

# ---- MongoDB ----
mongo_url = os.environ['MONGO_URL']
client = AsyncIOMotorClient(mongo_url)
db = client[os.environ['DB_NAME']]

# ---- App ----
app = FastAPI(title="autoandbid.com API")
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
# Password helpers delegate to services.password_security so that the same
# hashing strategy (Argon2id with bcrypt backwards compat) is used wherever
# password material crosses module boundaries.
from services.password_security import (
    hash_password as _ps_hash,
    verify_password as _ps_verify,
    needs_rehash as _ps_needs_rehash,
)


def hash_password(password: str) -> str:
    return _ps_hash(password)


def verify_password(plain: str, hashed: str) -> bool:
    return _ps_verify(plain, hashed)

def create_token(user_id: str, email: str, days: int = 7, sid: str | None = None) -> str:
    payload = {
        "sub": user_id,
        "email": email,
        "exp": datetime.now(timezone.utc) + timedelta(days=days),
    }
    if sid:
        payload["sid"] = sid
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
        # Session-aware validation: ако токенът има `sid`, проверяваме че
        # сесията не е отзована / изтрита от потребителя.
        sid = payload.get("sid")
        if sid:
            sess = await db.sessions.find_one({"id": sid}, {"_id": 0})
            if not sess:
                raise HTTPException(status_code=401, detail="Сесията е прекратена")
            # rate-limited last_seen update (всяка ~60с)
            try:
                last_seen = sess.get("last_seen_at")
                now = datetime.now(timezone.utc)
                if not last_seen or (now - datetime.fromisoformat(last_seen)).total_seconds() > 60:
                    await db.sessions.update_one(
                        {"id": sid},
                        {"$set": {"last_seen_at": now.isoformat(),
                                  "ip": (request.client.host if request.client else "") or sess.get("ip", "")}},
                    )
            except Exception:
                pass
            request.state.sid = sid
        user = await db.users.find_one({"id": payload["sub"]}, {"_id": 0, "password_hash": 0})
        if not user:
            raise HTTPException(status_code=401, detail="Потребителят не е намерен")
        if user.get("banned"):
            raise HTTPException(status_code=403, detail="Акаунтът е блокиран. За въпроси: contact@autoandbid.com")
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


async def require_verified_email(user: dict = Depends(get_current_user)) -> dict:
    """Dependency: blocks the request unless the user's email is verified.

    Existing accounts created before email-verification was rolled out keep
    their access (they have neither `email_verified=true` nor a `verification_required`
    flag — see `register_with_verification`). Only new accounts are gated.

    Admins and moderators always bypass — the role grant implies trust and
    the admin account itself cannot be gated out of its own control panel.
    """
    if user.get("role") in ("admin", "moderator"):
        return user
    if user.get("verification_required") and not user.get("email_verified"):
        raise HTTPException(
            status_code=403,
            detail="Моля, потвърдете имейл адреса си, преди да извършите това действие.",
        )
    return user


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
    # --- Phase 7: Multi-language CMS content (Markdown) ---
    "faq_content_bg": "", "faq_content_ro": "", "faq_content_en": "",
    "terms_content_bg": "", "terms_content_ro": "", "terms_content_en": "",
    "contacts_content_bg": "", "contacts_content_ro": "", "contacts_content_en": "",
    "fees_content_bg": "", "fees_content_ro": "", "fees_content_en": "",
    "how_it_works_content_bg": "", "how_it_works_content_ro": "", "how_it_works_content_en": "",
    # --- Direct-HTML variants (sanitised rendered) — ако е попълнено,
    # има приоритет пред Markdown варианта.
    "faq_html_bg": "", "faq_html_ro": "", "faq_html_en": "",
    "terms_html_bg": "", "terms_html_ro": "", "terms_html_en": "",
    "contacts_html_bg": "", "contacts_html_ro": "", "contacts_html_en": "",
    "fees_html_bg": "", "fees_html_ro": "", "fees_html_en": "",
    "how_it_works_html_bg": "", "how_it_works_html_ro": "", "how_it_works_html_en": "",
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
    "favicon_url": "",
    "maintenance_mode": False,
    "maintenance_message": "Auto&Bid се обновява. Моля, върнете се след малко.",
    # --- Deindex mode (pre-launch protection) ---
    # Когато е активен:
    #   • /api/robots.txt връща `User-agent: * / Disallow: /`
    #   • `X-Robots-Tag: noindex, nofollow, noarchive, nosnippet` се добавя на
    #     всеки отговор (middleware)
    #   • /api/sitemap.xml и /api/sitemap-images.xml връщат 404
    #   • Frontend инжектира `<meta name="robots" content="noindex,...">`
    # Не блокира логин/API/admin панела — чисто SEO gate.
    "deindex_mode": False,
    # --- Phase 6: Multi-language hero CMS ---
    "hero_headline_bg": "",
    "hero_subtitle_bg": "",
    "hero_headline_ro": "",
    "hero_subtitle_ro": "",
    "hero_headline_en": "",
    "hero_subtitle_en": "",
    # Editable email subject + body per slug. Keys are slugs like
    # `outbid_bg` / `verify_email_en`; values are { subject, body, header,
    # system, lang, description, placeholders }. The schema is enforced
    # in routers/admin.py:admin_put_templates. Without this key in the
    # defaults map, `_load_settings_cache` would silently drop the
    # `email_templates` field on every refresh, making admin edits look
    # like they reverted after a page reload.
    "email_templates": {},
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


def _stripe_meta_get(metadata, key: str):
    """Extract a key from a Stripe metadata object.

    The Stripe Python SDK ≥ 8 returns metadata as a `StripeObject`
    which is **not** a dict subclass — calling `.get()` on it raises
    AttributeError, and `metadata[key]` raises a KeyError that the
    SDK's own `__getitem__` swallows oddly. The safe path is
    `getattr(metadata, key, None)` which works for both StripeObject
    and plain dict (and the empty `{}` fallback we use when metadata
    is missing).
    """
    if metadata is None:
        return None
    # plain dict path
    if isinstance(metadata, dict):
        return metadata.get(key)
    # StripeObject — supports attribute access
    return getattr(metadata, key, None)


def _gross_amount(net_eur: float, auction: dict) -> float:
    """Apply VAT rate to the bid when an auction is sold WITH VAT.
    For VAT-exempt listings the gross equals the net.
    """
    if auction.get("vat_status") != "vat_inclusive":
        return float(net_eur or 0)
    rate = auction.get("vat_rate_pct") or 0
    try:
        return round(float(net_eur or 0) * (1 + float(rate) / 100.0), 2)
    except Exception:
        return float(net_eur or 0)


def _next_step_info(auction: dict, current_net: float) -> dict:
    """Compute min-next-bid and step in BOTH net and gross.

    For VAT-inclusive auctions, the bracket lookup runs on the GROSS
    (VAT-included) price so that buyers see clean BaT-style increments
    like €5000 → €5125 instead of awkward gross numbers like
    €5061 caused by applying VAT to a net-bracket step (€50 * 1.20).
    The net amount stored in our DB then becomes whatever value
    matches that clean gross — usually a small fractional cent that
    rounds cleanly on display.
    """
    vat_inclusive = auction.get("vat_status") == "vat_inclusive"
    rate = float(auction.get("vat_rate_pct") or 0) if vat_inclusive else 0.0
    cur = float(current_net or 0)
    if vat_inclusive and rate > 0:
        mult = 1.0 + rate / 100.0
        cur_gross = round(cur * mult, 2)
        step_gross = _bid_step(cur_gross)
        min_next_gross = round(cur_gross + step_gross, 2)
        min_next_net = round(min_next_gross / mult, 2)
        step_net = round(min_next_net - cur, 2)
        return {
            "step_net": step_net,
            "min_next_net": min_next_net,
            "step_gross": step_gross,
            "min_next_gross": min_next_gross,
        }
    step_net = _bid_step(cur)
    min_next_net = round(cur + step_net, 2)
    return {
        "step_net": step_net,
        "min_next_net": min_next_net,
        "step_gross": step_net,
        "min_next_gross": min_next_net,
    }


def _buyer_fee_on_auction(amount_eur: float, auction: dict) -> float:
    """Buyer's premium charged on the gross (incl. VAT) price."""
    return _buyer_fee(_gross_amount(amount_eur, auction))


def _admin_notif_vat_fields(net_eur: float, auction: dict) -> dict:
    """Build the shared `bid` / `amount` / `price`, `vat_suffix` and
    `commission` fields for admin push notifications. The 2 % commission
    is always computed on the GROSS price (incl. VAT) because that is
    what the buyer is actually charged on top of the net price. For
    VAT-exempt listings `vat_suffix` is an empty string so the
    notification reads naturally (`"… — €5,000."`) — for listings with
    VAT it reads `"… — €6,000 с ДДС."`. Call sites still pass their own
    `title`/`margin` keys; this helper only fills in the VAT-aware
    pricing triad.
    """
    net = round(float(net_eur or 0))
    gross = round(_gross_amount(net_eur, auction))
    has_vat = auction.get("vat_status") == "vat_inclusive" and gross > net
    commission = round(_buyer_fee_on_auction(net_eur, auction))
    return {
        "gross": gross,
        "net": net,
        "vat_suffix": " с ДДС" if has_vat else "",
        "commission": commission,
    }


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


# Threshold above which an active pre-authorization (bidding credit) on ANY
# live auction unlocks full VIN visibility for the user across all listings.
# Set high enough that casual users won't trigger it; low enough that any
# serious cross-shopper qualifies.
HIGH_VALUE_PREAUTH_EUR = 10000


async def _has_high_value_preauth(user_id: Optional[str]) -> bool:
    """True iff the user has at least one active bidding credit / pre-auth
    above HIGH_VALUE_PREAUTH_EUR. Cheap single-document lookup with index
    on (user_id, status, max_amount_eur).
    """
    if not user_id:
        return False
    doc = await db.bidding_credits.find_one(
        {
            "user_id": user_id,
            "status": "authorized",
            "max_amount_eur": {"$gt": HIGH_VALUE_PREAUTH_EUR},
        },
        {"_id": 0, "id": 1},
    )
    return doc is not None


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


# ─── Profile slug helpers ────────────────────────────────────────────────
# Every user gets a URL-friendly `profile_slug` derived from their display
# name (transliterated + sluggified). The slug is unique, admin-unassigned
# and auto-generated at registration time; a one-time backfill at startup
# fills in any pre-existing accounts. `/api/users/{identifier}/profile`
# accepts either the raw UUID or the slug so old bookmarks keep working.

_PROFILE_SLUG_RE = re.compile(r"[^a-z0-9]+")
# Reserved top-level URL segments that the frontend router maps to named
# pages (NOT dealer pages). A slug colliding with any of these would shadow
# the real route once the user is linked from a leaderboard, so we refuse
# them during generation and push the user into `-1` suffix territory.
_RESERVED_SLUGS = {
    "admin", "api", "auctions", "contacts", "dashboard", "dealer", "dealers",
    "faq", "fees", "forgot-password", "how-it-works", "inbox", "leaderboard",
    "login", "logout", "me", "my-listings", "profile", "register",
    "reviews", "sales", "sell", "settings", "static", "terms", "verify-email",
    "watchlist",
}


def _slugify_profile_name(name: str) -> str:
    """Deterministic ASCII slug generator used for both registration and
    backfill. Uses the static Bulgarian→Latin transliteration fallback so
    we don't depend on the LLM at registration time. Returns an empty
    string when the input produces nothing printable — the caller then
    falls back to `user-{short-id}`.
    """
    from translate import _static_transliterate_bg
    s = _static_transliterate_bg(name or "").lower()
    s = _PROFILE_SLUG_RE.sub("-", s).strip("-")
    # Cap at 24 chars so URLs stay short; trailing hyphen trimmed again.
    return s[:24].strip("-")


async def _ensure_unique_profile_slug(base: str, exclude_id: Optional[str] = None) -> str:
    """Return `base` if free, else append `-2`, `-3`, … until unique.
    Reserved top-level names are treated as taken.
    """
    if not base or base in _RESERVED_SLUGS:
        base = f"user-{uuid.uuid4().hex[:6]}"
    slug = base
    n = 2
    while True:
        query = {"profile_slug": slug}
        if exclude_id:
            query["id"] = {"$ne": exclude_id}
        clash = await db.users.find_one(query, {"_id": 1})
        if not clash:
            return slug
        slug = f"{base}-{n}"
        n += 1


async def _resolve_user_by_identifier(identifier: str, projection: Optional[dict] = None) -> Optional[dict]:
    """Look up a user by id *or* profile_slug. Slugs are stored lowercase,
    but URLs are case-insensitive for a nicer UX (e.g. `/profile/Gosho`
    resolves to `gosho`).
    """
    if not identifier:
        return None
    proj = projection if projection is not None else {"_id": 0, "password_hash": 0}
    # First: exact id match (UUIDs contain `-` so they never collide with
    # a pure-ASCII slug).
    u = await db.users.find_one({"id": identifier}, proj)
    if u:
        return u
    return await db.users.find_one({"profile_slug": identifier.lower()}, proj)


async def _hydrate_user_slug(rows: list[dict]) -> None:
    """Mutate `rows` in place to add `user_slug` (the author's profile_slug)
    via a single batched Mongo lookup on `user_id`. Used for comments and
    bids so the UI can link to `/profile/<slug>` without per-row fetches.
    Rows without a `user_id` or without a matching user are skipped —
    the frontend falls back to the UUID in that case.
    """
    if not rows:
        return
    uids = {r.get("user_id") for r in rows if r.get("user_id")}
    if not uids:
        return
    slugs: dict[str, Optional[str]] = {}
    async for u in db.users.find(
        {"id": {"$in": list(uids)}},
        {"_id": 0, "id": 1, "profile_slug": 1},
    ):
        slugs[u["id"]] = u.get("profile_slug")
    for r in rows:
        uid = r.get("user_id")
        if uid and slugs.get(uid):
            r["user_slug"] = slugs[uid]


async def _setup_notifications_ttl() -> None:
    """Configure Mongo to auto-delete READ notifications after 30 days.
    Uses a TTL index on `read_at_ts` (BSON Date) with a partial filter
    on `read: True`. The inbox mark-read handlers write `read_at_ts`
    alongside the ISO `read_at` string — see patch below.

    Idempotent: Mongo treats identical index specs as a no-op. Unread
    notifications are untouched; they expire only after the user marks
    them read or clicks "Clear all".
    """
    try:
        await db.user_notifications.create_index(
            "read_at_ts",
            expireAfterSeconds=30 * 24 * 3600,
            partialFilterExpression={"read": True},
            name="read_at_ts_ttl_30d",
        )
        # One-time backfill: older `read: true` rows have ISO `read_at`
        # but no BSON `read_at_ts`, so Mongo's TTL job skips them. Parse
        # the string into a real datetime and write it back. Limited to
        # 5000 docs per boot to avoid blocking startup on huge inboxes.
        cursor = db.user_notifications.find(
            {"read": True, "read_at_ts": {"$exists": False}, "read_at": {"$type": "string"}},
            {"_id": 0, "id": 1, "read_at": 1},
        ).limit(5000)
        async for doc in cursor:
            try:
                dt = datetime.fromisoformat(doc["read_at"].replace("Z", "+00:00"))
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                await db.user_notifications.update_one(
                    {"id": doc["id"]},
                    {"$set": {"read_at_ts": dt}},
                )
            except Exception:
                pass
    except Exception as e:
        logger.warning("notifications TTL index setup failed: %s", e)



async def _backfill_profile_slugs() -> None:
    """One-time (idempotent) startup task — every user without a
    `profile_slug` gets one generated from their name. Safe to run on
    every boot: users who already have a slug are skipped. Also creates
    the unique sparse index so new accounts can't collide at write time.
    """
    try:
        await db.users.create_index(
            "profile_slug",
            unique=True,
            sparse=True,
            name="profile_slug_unique",
        )
    except Exception as e:
        logger.warning("profile_slug index creation failed: %s", e)
    try:
        await db.users.create_index(
            "username_lc",
            unique=True,
            sparse=True,
            name="username_lc_unique",
        )
    except Exception as e:
        logger.warning("username_lc index creation failed: %s", e)
    cursor = db.users.find(
        {"profile_slug": {"$in": [None, ""]}},
        {"_id": 0, "id": 1, "name": 1},
    )
    async for u in cursor:
        base = _slugify_profile_name(u.get("name") or "") or f"user-{u['id'][:6]}"
        slug = await _ensure_unique_profile_slug(base, exclude_id=u["id"])
        try:
            await db.users.update_one({"id": u["id"]}, {"$set": {"profile_slug": slug}})
        except Exception as e:
            logger.warning("profile_slug backfill failed for %s: %s", u["id"], e)




def _public_auction(a: dict, viewer: Optional[dict] = None, *, unmask_vin: bool = False) -> dict:
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
        # Reveal VIN to admins, the seller, and any caller-flagged privileged
        # viewer (e.g. user with a high-value pre-authorization). Otherwise
        # mask everything but the last 7 characters.
        if is_owner_or_admin or unmask_vin:
            a["vin"] = a["vin"].strip().upper()
            a["vin_masked"] = False
        else:
            a["vin_masked"] = True
            a["vin"] = _mask_vin(a["vin"])
    return a


# Lightweight shape for listing cards (home page + /auctions). Drops
# description blobs, extra image buckets, full spec fields — keeps only
# what `AuctionCard.jsx` actually renders. Cuts typical payloads from
# ~19 KB → ~1.5 KB per auction (92% reduction).
_LIST_KEEP = {
    "id", "slug",
    "title", "make", "model", "year", "mileage_km", "fuel", "transmission",
    "body_type", "color", "region", "city", "country",
    "starting_bid_eur", "current_bid_eur", "buy_now_eur",
    "reserve_met", "has_reserve", "no_reserve",
    "bid_count", "ends_at", "starts_at", "status",
    "featured", "is_archived",
    "seller_is_verified_dealer",
    "vat_status", "vat_rate_pct",
}


# MongoDB projection used when `view=list` is requested — strips the
# heavy fields at the DB driver layer so we never transfer/parse them.
# `images` is kept (cover slice happens in _list_shape), plus everything
# _LIST_KEEP needs + the raw fields required to compute status.
_LIST_MONGO_PROJECTION = {
    "_id": 0,
    "description": 0,
    "description_en": 0,
    "description_bg": 0,
    "description_ro": 0,
    # NB: images_exterior / images_interior / images_bumper / images_wheels
    # ARE included in the list projection (no `0` here) so `_list_shape`
    # below can reorder the preview deck — slides 3-4 must be the first
    # two interior shots (they're also the photos that appear inline
    # within the description on the detail page). Without this, every
    # card silently fell back to "first 4 by upload order" = all
    # exteriors.
    "contact_email": 0,
    "contact_phone": 0,
    "vin": 0,
    "power_hp": 0,
    "engine_cc": 0,
    "price_net_eur": 0,
    "price_gross_eur": 0,
    "duration_days": 0,
    "approved_at": 0,
    "views_count": 0,
    "specs": 0,
    "documents": 0,
    "history": 0,
    "service_history": 0,
    "rejection_reason": 0,
    "translations": 0,
}


def _list_shape(a: dict) -> dict:
    """Project a public auction dict to the minimal subset needed for list
    cards. The AuctionCard mobile-swipe carousel shows 4 photos + a
    "View full auction" CTA at slide 5, in the order:
      slide 1: main (cover)
      slide 2: best exterior
      slide 3-4: first two interior shots
    Interior images are the same photos that get interleaved into the
    description text on the auction detail page (`DescriptionWithInteriorShots`
    splits the body into 3 chunks and injects the first 3 interior
    photos between them) — so slides 3-4 on the card mirror what the
    user sees "inside the listing text" once they tap through.

    Sources, in priority order:
      • If the auction has categorized variants (`images_variants[i].category`),
        build the deck from those.
      • Otherwise fall back to the per-bucket URL arrays
        (`images_exterior`, `images_interior`, ...) which are populated
        for every SellPage submission since iteration 12.
      • Final fallback: the flat `images[]` array (used for very old
        listings that pre-date the bucket UI).
    """
    out = {k: a[k] for k in _LIST_KEEP if k in a}

    # Per-bucket URL arrays — present on every SellPage submission since
    # iteration 12 (the categorized uploader). Used both to derive the
    # `thumbnails`/`images` payload AND as a fallback when the auction
    # has no variant manifests yet.
    ext_urls = list(a.get("images_exterior") or [])
    bump_urls = list(a.get("images_bumper") or [])
    wheel_urls = list(a.get("images_wheels") or [])
    int_urls = list(a.get("images_interior") or [])
    flat = list(a.get("images") or [])
    flat_thumbs = list(a.get("thumbnails") or [])

    # Compose the card preview order: main → exterior → interior × 2,
    # then fillers from the remaining unused exterior/bumper/wheels.
    seen: set[str] = set()
    ordered_urls: list[str] = []
    def _push(u: str | None) -> None:
        if not u or u in seen:
            return
        seen.add(u)
        ordered_urls.append(u)

    if ext_urls or int_urls or bump_urls or wheel_urls:
        # Categorized layout — best signal we have.
        if ext_urls:
            _push(ext_urls[0])  # main / cover
            if len(ext_urls) > 1:
                _push(ext_urls[1])  # 2nd exterior
        # First two interior shots → slides 3 & 4 (also the images
        # interleaved in description text on detail page).
        for u in int_urls[:2]:
            _push(u)
        # Fillers — preserve original ordering.
        for u in (*ext_urls[2:], *bump_urls, *wheel_urls, *int_urls[2:]):
            if len(ordered_urls) >= 4:
                break
            _push(u)
    else:
        # Legacy flat upload — keep whatever order the auction was
        # stored in (mobile.bg imports & very old listings).
        for u in flat[:4]:
            _push(u)

    out["images"] = ordered_urls[:4]
    # Build a parallel thumbnails array by URL match — falls back to
    # the same URL if no thumbnail was generated (storage backend is
    # content-addressed so the URL works as a small image too).
    if flat_thumbs and flat:
        flat_to_thumb = {flat[i]: flat_thumbs[i] for i in range(min(len(flat), len(flat_thumbs)))}
        out["thumbnails"] = [flat_to_thumb.get(u, u) for u in ordered_urls[:4]]
    else:
        out["thumbnails"] = ordered_urls[:4]

    # Category-aware variant projection (mirrors the URL logic above so
    # the frontend `<Picture>` chain picks up AVIF/WebP/JPG fallbacks
    # for the same images we just put in `images[]`).
    variants = a.get("images_variants") or []
    by_cat: dict[str, list[dict]] = {}
    for v in variants:
        by_cat.setdefault((v.get("category") or "other"), []).append(v)
    picked: list[dict] = []
    seen_sha: set[str] = set()
    def _push_var(v: dict | None) -> None:
        if not v:
            return
        sha = v.get("sha")
        if sha in seen_sha:
            return
        seen_sha.add(sha)
        picked.append(v)
    if by_cat:
        if by_cat.get("main"):
            _push_var(by_cat["main"][0])
        elif by_cat.get("exterior"):
            _push_var(by_cat["exterior"][0])
        for v in by_cat.get("exterior", []):
            if len(picked) >= 2:
                break
            _push_var(v)
        for v in by_cat.get("interior", [])[:2]:
            _push_var(v)
        for v in variants:
            if len(picked) >= 4:
                break
            _push_var(v)
    out["images_variants"] = picked[:4]
    return out


# ---- Auctions ----
@api.get("/auctions")
async def list_auctions(
    request: Request,
    response: Response,
    make: Optional[str] = None,
    fuel: Optional[str] = None,
    transmission: Optional[str] = None,
    region: Optional[str] = None,
    country: Optional[str] = None,
    body_type: Optional[str] = None,
    min_price: Optional[float] = None,
    max_price: Optional[float] = None,
    year_min: Optional[int] = None,
    year_max: Optional[int] = None,
    q: Optional[str] = Query(None, description="Пълнотекстово търсене"),
    status: Optional[str] = Query(None, description="live|ended|sold"),
    sort: Optional[str] = Query("ending_soon"),
    limit: int = 24,
    offset: int = 0,
    paginated: int = 0,
    view: Optional[str] = Query("list", description="`list` (default, lightweight) or `full` for the heavy shape"),
):
    # Cap limit so a single request can never blow up the payload.
    limit = max(1, min(limit, 50))
    viewer = await get_optional_user(request)
    viewer_is_admin = viewer and viewer.get("role") in ("admin", "moderator")
    use_list_shape = (view == "list")
    query = {}
    # Hide archived listings at DB level for non-admins (admins see them via the dedicated archive tab).
    if not viewer_is_admin:
        query["is_archived"] = {"$ne": True}
        query["status"] = {"$ne": "archived"}
    if make: query["make"] = make
    if fuel: query["fuel"] = fuel
    if transmission: query["transmission"] = transmission
    if region: query["region"] = region
    if country: query["country"] = country
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

    # NOTE: status & "not archived" filtering is computed Python-side from
    # _public_auction() output (because `status` in DB may be "scheduled"
    # but compute-as-"live"). So we can't trust DB-level skip/limit pagination
    # before the Python filter. We fetch a generous batch (200) per page then
    # paginate after computing public statuses + sorting.
    fetch_cap = 200
    # For `view=list`: use a lean DB projection that strips heavy fields
    # (description, extra image arrays, specs, contacts, VIN, …) BEFORE
    # they leave MongoDB. Cuts Mongo → API network transfer ~80%.
    projection = _LIST_MONGO_PROJECTION if use_list_shape else {"_id": 0}
    cursor = db.auctions.find(query, projection).limit(fetch_cap)
    items = await cursor.to_list(fetch_cap)
    # VIN unmask is irrelevant for `view=list` (VIN is already stripped by
    # the projection) — skip the extra DB lookup entirely. Anonymous
    # viewers also don't need it.
    if viewer and not use_list_shape:
        unmask_for_viewer = await _has_high_value_preauth(viewer["id"])
    else:
        unmask_for_viewer = False
    items = [_public_auction(a, viewer, unmask_vin=unmask_for_viewer) for a in items]

    # Hide non-public statuses from public listings (pending/rejected/withdrawn/removed/cancelled/paused)
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

    total = len(items)
    # Edge-cache anonymous list responses. Cards are identical for every
    # unauthenticated visitor; a 30s shared cache means Cloudflare / nginx
    # proxy cache absorbs virtually all traffic spikes. We still serve
    # fresh data to logged-in users (whose cookies skip the edge cache
    # via `Vary: Cookie`).
    if not viewer:
        response.headers["Cache-Control"] = "public, max-age=15, s-maxage=30, stale-while-revalidate=60"
        response.headers["Vary"] = "Cookie, Accept-Language"
    if paginated:
        offset = max(0, int(offset))
        page_items = items[offset: offset + max(1, min(60, int(limit)))]
        await _enrich_dealer_status(page_items)
        if use_list_shape:
            page_items = [_list_shape(a) for a in page_items]
        return {"items": page_items, "total": total, "offset": offset, "limit": limit}

    # Backwards-compat: legacy callers (featured rails, embedded carousels…)
    # still receive the full unfiltered slice up to `limit`.
    out = items[:limit]
    await _enrich_dealer_status(out)
    if use_list_shape:
        out = [_list_shape(a) for a in out]
    return out

@api.get("/auctions/hero")
async def hero_picks(request: Request, response: Response):
    """Two hero picks for the landing page.

    Selection policy:
      1. Candidates = live, non-archived auctions.
      2. Score each = (featured_flag × 1000) + (bid_count × 10) + comments_count.
         `featured` dominates, activity (bids + comments) is the tie-breaker.
      3. Keep the choice STABLE for 30 minutes so visitors returning mid-
         session don't see the hero shuffle.
      4. Cached picks are invalidated early if any chosen auction has
         ended / been archived / lost its featured flag — we fall through
         to a fresh selection.

    Response: list of up to 2 lightweight (list-shape) auction dicts.
    """
    now = datetime.now(timezone.utc)
    cached = getattr(hero_picks, "_cache", None)
    cache_valid = False
    if cached:
        picked_ids, chosen_at = cached
        if (now - chosen_at).total_seconds() < 1800:  # 30 min
            # Verify both cached picks are still live, not archived and
            # not past their `ends_at`. If any is stale, recompute.
            raws = await db.auctions.find(
                {"id": {"$in": picked_ids}},
                _LIST_MONGO_PROJECTION,
            ).to_list(len(picked_ids))
            fresh = [_public_auction(a, None) for a in raws]
            still_good = (
                len(fresh) == len(picked_ids) and
                all(
                    x.get("status") == "live" and
                    not x.get("is_archived") and
                    x.get("ends_at") and datetime.fromisoformat(x["ends_at"].replace("Z", "+00:00")) > now
                    for x in fresh
                )
            )
            if still_good:
                # Preserve the original cache order (ids)
                ordered = [next((x for x in fresh if x["id"] == pid), None) for pid in picked_ids]
                combined = [x for x in ordered if x]
                cache_valid = True

    if not cache_valid:
        # Pull live candidates (featured first, then the rest as backup)
        raw = await db.auctions.find(
            {"is_archived": {"$ne": True}, "status": "live"},
            _LIST_MONGO_PROJECTION,
        ).limit(60).to_list(60)
        items = [_public_auction(a, None) for a in raw]
        items = [a for a in items if a.get("status") == "live" and not a.get("is_archived")]

        # Activity counts — one aggregation per collection, indexed by auction id
        ids = [a["id"] for a in items]
        comment_counts = {}
        if ids:
            agg = await db.comments.aggregate([
                {"$match": {"auction_id": {"$in": ids}}},
                {"$group": {"_id": "$auction_id", "n": {"$sum": 1}}},
            ]).to_list(1000)
            comment_counts = {x["_id"]: x["n"] for x in agg}

        def _score(a: dict) -> int:
            f = 1000 if a.get("featured") else 0
            bids = int(a.get("bid_count") or 0)
            comments = int(comment_counts.get(a["id"], 0))
            return f + bids * 10 + comments

        items.sort(key=_score, reverse=True)
        combined = items[:2]
        hero_picks._cache = ([a["id"] for a in combined], now)

    await _enrich_dealer_status(combined)
    response.headers["Cache-Control"] = "public, max-age=60, s-maxage=300, stale-while-revalidate=600"
    return [_list_shape(a) for a in combined]


@api.get("/auctions/featured")
async def featured(request: Request, response: Response, view: Optional[str] = None):
    viewer = await get_optional_user(request)
    use_list_shape = (view == "list")
    # Lean projection for list shape — strips description/extra image arrays
    # at the DB layer. Saves Mongo→API transfer time.
    projection = _LIST_MONGO_PROJECTION if use_list_shape else {"_id": 0}
    # Up to 10 items total:
    #   1) all live+featured (may be fewer than 10)
    #   2) top up with live+non-featured (newest first) until 10 or exhausted
    target = 10
    featured_raw = await db.auctions.find(
        {"featured": True, "is_archived": {"$ne": True}, "status": {"$ne": "archived"}},
        projection,
    ).limit(30).to_list(30)
    featured_items = [_public_auction(a, viewer) for a in featured_raw]
    featured_live = [a for a in featured_items if a["status"] == "live" and not a.get("is_archived")]

    combined = featured_live[:target]
    if len(combined) < target:
        needed = target - len(combined)
        have_ids = {a["id"] for a in combined}
        # Pull extra live, non-featured auctions (sorted by ends_at ascending = soonest first)
        extra_raw = await db.auctions.find(
            {
                "featured": {"$ne": True},
                "is_archived": {"$ne": True},
                "status": "live",
            },
            projection,
        ).sort("ends_at", 1).limit(needed * 3).to_list(needed * 3)
        extra_items = [_public_auction(a, viewer) for a in extra_raw]
        for a in extra_items:
            if a["id"] in have_ids:
                continue
            if a["status"] != "live" or a.get("is_archived"):
                continue
            combined.append(a)
            have_ids.add(a["id"])
            if len(combined) >= target:
                break

    await _enrich_dealer_status(combined)
    # Public listing: edge-cache for 60s. Matches frontend landingCache TTL so
    # Cloudflare / browsers don't hit the backend for every homepage view.
    # `s-maxage=60` for shared caches, `stale-while-revalidate=120` lets edge
    # serve stale content while refreshing in background. Zero impact on
    # authenticated viewers — the response has no user-specific fields.
    response.headers["Cache-Control"] = "public, max-age=30, s-maxage=60, stale-while-revalidate=120"
    if use_list_shape:
        combined = [_list_shape(a) for a in combined]
    return combined

@api.get("/auctions/sold")
async def sold(
    request: Request,
    response: Response,
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
    view: Optional[str] = None,
):
    viewer = await get_optional_user(request)
    query: dict = {"status": "sold", "is_archived": {"$ne": True}}
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
    use_list_shape = (view == "list")
    projection = _LIST_MONGO_PROJECTION if use_list_shape else {"_id": 0}
    cursor = db.auctions.find(query, projection).sort(sort_field, sort_dir).skip(offset).limit(limit)
    raw = await cursor.to_list(limit)
    items = [_public_auction(a, viewer) for a in raw]
    await _enrich_dealer_status(items)
    # Public sold listings are long-lived and identical for everybody. Cache
    # aggressively at the edge — 5 minutes shared, 10 minutes stale-while-
    # revalidate. Saves a lot of MongoDB work on the /sales page.
    response.headers["Cache-Control"] = "public, max-age=60, s-maxage=300, stale-while-revalidate=600"
    # Backwards-compat: return plain list when no pagination requested (offset=0 & small query)
    if offset == 0 and not any([make, body_type, fuel, year_min, year_max, price_min, price_max, q]) and sort == "recent" and limit == 48:
        if use_list_shape:
            items = [_list_shape(a) for a in items]
        return items
    if use_list_shape:
        items = [_list_shape(a) for a in items]
    return {"items": items, "total": total, "offset": offset, "limit": limit}


@api.get("/stats/sold")
async def stats_sold(days: Optional[int] = None):
    """Public aggregate statistics for sold auctions. Optional `days` window."""
    match: dict = {"status": "sold", "is_archived": {"$ne": True}}
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
    countries = await db.auctions.distinct("country")
    def _clean(values):
        return sorted(v for v in values if v)
    return {
        "makes": _clean(makes),
        "fuels": _clean(fuels),
        "transmissions": _clean(transmissions),
        "regions": _clean(regions),
        "body_types": _clean(body_types),
        "countries": _clean(countries),
    }

@api.get("/auctions/{auction_id}")
async def get_auction(auction_id: str, request: Request):
    viewer = await get_optional_user(request)
    a = await db.auctions.find_one({"id": auction_id}, {"_id": 0})
    if not a:
        raise HTTPException(status_code=404, detail="Търгът не е намерен")
    # Hide non-public listings from non-admins:
    #   - archived (soft-deleted by admin/seller)
    #   - rejected (refused at moderation — auto-archived)
    #   - cancelled / withdrawn / removed (terminated by admin)
    #   - pending (awaiting moderation — only seller may peek via /me/listings)
    viewer_is_admin = viewer and viewer.get("role") in ("admin", "moderator")
    is_seller = bool(viewer and viewer.get("id") == a.get("seller_id"))
    HIDDEN_STATUSES = {"archived", "rejected", "cancelled", "withdrawn", "removed", "pending"}
    is_archived = bool(a.get("is_archived")) or a.get("status") == "archived"
    if (is_archived or a.get("status") in HIDDEN_STATUSES) and not viewer_is_admin and not is_seller:
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
        seller = (
            await db.users.find_one(
                {"id": seller_id},
                {"_id": 0, "is_verified_dealer": 1, "profile_slug": 1},
            )
            if seller_id
            else None
        )
        public["seller_is_verified_dealer"] = bool(seller and seller.get("is_verified_dealer"))
        if seller and seller.get("profile_slug"):
            public["seller_slug"] = seller["profile_slug"]
    # Reveal full VIN to: seller, admin (always), bidders on live auctions,
    # or any user with a high-value pre-authorization (≥ €10,000) anywhere
    # on the platform. On ended/sold/cancelled auctions the VIN stays masked
    # for plain bidders — but high-value pre-authorized users still see it.
    if a.get("vin") and viewer:
        is_privileged = viewer.get("role") == "admin" or viewer.get("id") == a.get("seller_id")
        if not is_privileged and _auction_status(a) == "live":
            from services import bidding as bidding_svc
            is_privileged = await bidding_svc.has_user_bid(auction_id, viewer["id"])
        if not is_privileged:
            is_privileged = await _has_high_value_preauth(viewer["id"])
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


async def _ensure_seo_translations(auction_id: str, a: dict) -> dict:
    """Eagerly generate `title_<lang>` + `seo_description_<lang>` cache
    fields for both RO and EN. Called once at admin approval time so
    every social share + SERP impression uses locale-correct copy
    instead of falling back to Bulgarian.

    `title_<lang>` carries a localised version of `auction.title` (the
    car make/model line; mostly Latin already, but Gemini handles
    edge cases like "БМВ Х5" → "BMW X5"). `seo_description_<lang>`
    holds a 280-char excerpt that's safe to paste into `<meta name="
    description">` and `og:description` — we keep this separate from
    the full `description_<lang>` so we don't blow the 300-char SERP
    budget when descriptions get long.

    Idempotent: skips any pair already present on the document.
    Returns the patch dict so the caller can merge it into a $set.
    """
    from translate import translate_text
    patch: dict = {}
    title_src = (a.get("title") or "").strip()
    desc_src = (a.get("description") or "").strip()
    for lang in ("en", "ro"):
        # Title — short, idempotent.
        if title_src and not (a.get(f"title_{lang}") or "").strip():
            try:
                translated = await translate_text(title_src, lang)
                if translated:
                    patch[f"title_{lang}"] = translated.strip()
            except Exception as e:  # noqa: BLE001
                logger.info("[seo] title translation %s failed: %s", lang, e)
        # SEO description — derived from translated description (cached
        # in `description_<lang>` if seller / earlier call already ran
        # the full translation). 280 chars matches Google's SERP
        # snippet ceiling.
        if desc_src and not (a.get(f"seo_description_{lang}") or "").strip():
            full = a.get(f"description_{lang}") or ""
            if not full.strip():
                try:
                    full = await translate_text(desc_src, lang) or ""
                    if full.strip():
                        patch[f"description_{lang}"] = full
                except Exception as e:  # noqa: BLE001
                    logger.info("[seo] description translation %s failed: %s", lang, e)
            if full.strip():
                patch[f"seo_description_{lang}"] = full.strip()[:280]
    # Also derive seo_description_bg from the source if missing — keeps
    # the share handler dead-simple (one lookup table, no fallbacks
    # inline).
    if desc_src and not (a.get("seo_description_bg") or "").strip():
        patch["seo_description_bg"] = desc_src[:280]
    if patch:
        await db.auctions.update_one({"id": auction_id}, {"$set": patch})
    return patch

_video_upload_in_flight: set[str] = set()  # user_ids actively uploading

@api.post("/sell/video-upload")
@limiter.limit("5/minute")
async def upload_sell_video(
    request: Request,
    file: UploadFile = File(...),
    user: dict = Depends(require_verified_email),
):
    """Sell-flow video upload with production guardrails.

    Pipeline:
      1. Reject if the user already has an in-flight upload (1 concurrent / user).
      2. Reject if the user has exceeded their hourly / daily quota
         (admins + verified dealers are exempt).
      3. Stream up to 100 MB into a temp file. Anything bigger → 413.
      4. Validate magic bytes (`ftyp` / EBML / RIFF) — cheap content sniff
         so a renamed `.exe` never reaches ffprobe.
      5. Probe duration with ffprobe → reject if > 60 s.
      6. Move to /opt/autobids/uploads/videos/<sha>/source.<ext>.
      7. Extract a poster JPG synchronously (cheap, 1 frame).
      8. Enqueue AV1 transcode on the **single-worker queue**. The
         request returns immediately with the original URL; the URL is
         swapped to the AV1 version once the encoder finishes.
    """
    import tempfile
    from services import video_processing as vp
    from services import video_queue as vq

    is_admin = user.get("role") in ("admin", "moderator")
    is_dealer = bool(user.get("is_verified_dealer"))
    bypass_limits = is_admin or is_dealer
    uid = user["id"]

    # ---- (1) Concurrent-upload guard ---------------------------------------
    if uid in _video_upload_in_flight:
        raise HTTPException(
            status_code=429,
            detail="Имате друго видео в процес на качване. Изчакайте го да приключи.",
        )

    # ---- (2) Hourly / daily quota (Mongo-backed, skipped for admins/dealers)
    if not bypass_limits:
        now = datetime.now(timezone.utc)
        one_hour_ago = (now - timedelta(hours=1)).isoformat()
        one_day_ago = (now - timedelta(hours=24)).isoformat()
        hourly = await db.video_upload_log.count_documents(
            {"user_id": uid, "created_at": {"$gte": one_hour_ago}}
        )
        if hourly >= 3:
            raise HTTPException(
                status_code=429,
                detail="Достигнат е лимитът от 3 видеа на час. Опитайте по-късно.",
            )
        daily = await db.video_upload_log.count_documents(
            {"user_id": uid, "created_at": {"$gte": one_day_ago}}
        )
        if daily >= 10:
            raise HTTPException(
                status_code=429,
                detail="Достигнат е лимитът от 10 видеа на ден. Опитайте утре.",
            )

    if not file or not file.filename:
        raise HTTPException(status_code=400, detail="No file uploaded")

    # ---- (3) Stream to temp file (≤100 MB) ---------------------------------
    _video_upload_in_flight.add(uid)
    tmp = tempfile.NamedTemporaryFile(
        delete=False,
        prefix="vidup_",
        suffix=os.path.splitext(file.filename)[1] or ".bin",
    )
    tmp_path = tmp.name
    total = 0
    try:
        while True:
            chunk = await file.read(1024 * 1024)
            if not chunk:
                break
            total += len(chunk)
            if total > vp.MAX_VIDEO_BYTES:
                raise HTTPException(
                    status_code=413,
                    detail=f"Видеото е по-голямо от {vp.MAX_VIDEO_BYTES // (1024*1024)} MB",
                )
            tmp.write(chunk)
        tmp.close()

        # ---- (4-7) Validate + persist + poster ---------------------------------
        try:
            meta, av1_target = vp.process_uploaded_video(tmp_path, file.filename)
        except ValueError as e:
            logger.warning("video upload rejected for user=%s file=%s: %s", uid, file.filename, e)
            raise HTTPException(status_code=400, detail=str(e))
    except HTTPException:
        # Clean up tmp on validation failure
        if os.path.exists(tmp_path):
            try:
                os.unlink(tmp_path)
            except OSError as e:
                logger.warning("failed to cleanup tmp video %s: %s", tmp_path, e)
        raise
    except Exception:
        if os.path.exists(tmp_path):
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
        logger.exception("video upload crashed for user=%s file=%s", uid, file.filename)
        raise HTTPException(status_code=500, detail="Качването пропадна, опитайте отново.")
    finally:
        _video_upload_in_flight.discard(uid)
        if not tmp.closed:
            tmp.close()

    # ---- (8) Audit log + enqueue AV1 transcode -----------------------------
    try:
        await db.video_upload_log.insert_one({
            "user_id": uid,
            "sha": meta.get("sha"),
            "duration_seconds": meta.get("video_duration_seconds"),
            "size_bytes": total,
            "created_at": datetime.now(timezone.utc).isoformat(),
        })
    except Exception as e:  # noqa: BLE001
        logger.warning("video_upload_log insert failed: %s", e)

    if av1_target and not os.path.exists(av1_target):
        sha = meta.get("sha")
        source_path = os.path.join(
            vp.VIDEOS_DIR, sha[:2], sha[2:4], sha,
            f"source{os.path.splitext(file.filename)[1].lower()}",
        )
        original_url = meta["video_url"]
        av1_url = meta.get("av1_url_when_ready")

        async def _on_av1_done(ok: bool):
            if not ok:
                return
            # Attach AV1 URL as an *additional* field — NEVER overwrite
            # `video_url`. Safari/Firefox still default to H.264, and the
            # `<source>` MIME fallback chain in `<AuctionVideo>` picks
            # AV1 only when the browser advertises support.
            try:
                await db.auctions.update_many(
                    {"video_url": original_url},
                    {"$set": {"video_url_av1": av1_url}},
                )
            except Exception as e:  # noqa: BLE001
                logger.warning("AV1 attach failed for sha=%s: %s", sha, e)

        await vq.enqueue(source_path, av1_target, vp.transcode_to_av1, _on_av1_done)

    return {
        "video_url": meta["video_url"],
        "video_poster_url": meta["video_poster_url"],
        "video_duration_seconds": meta["video_duration_seconds"],
    }


# ---- Image upload (new architecture) --------------------------------------
# Multipart upload endpoint that mirrors the video pipeline:
#   1. Accept raw bytes (5 MB hard cap per file).
#   2. Verify magic bytes — never trust Content-Type or extension.
#   3. Persist the ORIGINAL to disk (content-addressed by sha256).
#   4. Enqueue background AVIF/WebP/JPG variant generation.
#   5. Return the public URL + sha + initial status so the client can show
#      the image immediately while variants encode in the background.
#
# The legacy flow (base64 data URLs + sync `optimize_many`) is preserved
# for /auctions/* endpoints that already accept them; new uploads from
# Sell / ImageUploader go through this new path.

IMAGE_UPLOAD_MAX_BYTES = 5 * 1024 * 1024   # 5 MB per file (originals only)
_IMG_MAGIC = {
    b"\xff\xd8\xff": "jpg",
    b"\x89PNG\r\n\x1a\n": "png",
}


def _sniff_image_ext(head: bytes) -> Optional[str]:
    """Return canonical extension based on the first 12 bytes, or None.

    Supported source formats: JPG, PNG, WebP. HEIC/HEIF are rejected at
    this layer — the frontend converts iPhone uploads to JPEG via the
    libheif WASM bundle before they hit this endpoint, so we never see
    raw HEIC bytes from a well-behaved client. Rejecting them here is a
    defence-in-depth check; if it ever fires, the user gets a clear error
    rather than a confusing background-encode failure 30 s later.
    """
    if not head or len(head) < 12:
        return None
    if head[:3] == b"\xff\xd8\xff":
        return "jpg"
    if head[:8] == b"\x89PNG\r\n\x1a\n":
        return "png"
    if head[:4] == b"RIFF" and head[8:12] == b"WEBP":
        return "webp"
    return None


@api.post("/sell/image-upload")
@limiter.limit("60/minute")
async def upload_sell_image(
    request: Request,
    file: UploadFile = File(...),
    auction_id: Optional[str] = None,
    user: dict = Depends(require_verified_email),
):
    """Upload a single original image and enqueue background optimization.

    Returns:
        {
          "url":        "<public original URL>",
          "sha":        "<sha256>",
          "ext":        "jpg|png|webp",
          "size_bytes": int,
          "status":     "optimizing",  # always — the queue starts immediately
        }

    The returned `url` is usable in `<img src>` straight away. Once the
    background worker finishes (typically 1-5 s) the auction document
    gains an `image_optimization.<sha>.manifest` block with AVIF/WebP
    variants; frontend should refresh from `/auctions/{id}` to pick them
    up, OR poll `/admin/images/status?shas=<sha>` for an unattached
    upload.
    """
    import hashlib
    from services import image_optimization_queue as ioq
    from storage import _get_backend

    if not file:
        raise HTTPException(status_code=400, detail="No file uploaded")

    # Stream the body but cap at the size limit so a malicious client
    # cannot trickle gigabytes through nginx body buffering.
    chunks = bytearray()
    while True:
        chunk = await file.read(64 * 1024)
        if not chunk:
            break
        chunks.extend(chunk)
        if len(chunks) > IMAGE_UPLOAD_MAX_BYTES:
            raise HTTPException(
                status_code=413,
                detail=f"Снимката е по-голяма от {IMAGE_UPLOAD_MAX_BYTES // (1024 * 1024)} MB.",
            )
    if not chunks:
        raise HTTPException(status_code=400, detail="Празен файл.")

    ext = _sniff_image_ext(bytes(chunks[:12]))
    if not ext:
        raise HTTPException(
            status_code=400,
            detail="Файлът не е валидно изображение (JPG / PNG / WebP). "
                   "HEIC/HEIF трябва да се конвертират към JPEG на устройството.",
        )

    sha = hashlib.sha256(bytes(chunks)).hexdigest()

    # Cap originals at ORIGINAL_MAX_EDGE (default 2560 px) on the long edge
    # BEFORE content-addressing them. A 4000×6000 phone shot becomes ~600
    # KB JPEG instead of ~6 MB; every downstream variant generation also
    # gets cheaper. The sha256 is recomputed on the capped bytes so the
    # on-disk filename matches the bytes actually persisted.
    #
    # cap_original_bytes() is idempotent (already-small images pass through
    # untouched), so re-running on a future redeploy is a no-op.
    try:
        from services.image_variants import cap_original_bytes
        capped_bytes, capped_ext = cap_original_bytes(bytes(chunks), ext)
        if capped_bytes is not chunks and len(capped_bytes) != len(chunks):
            # Image was actually downscaled — refresh sha + ext.
            sha = hashlib.sha256(capped_bytes).hexdigest()
            ext = capped_ext
            chunks = bytearray(capped_bytes)
    except Exception as e:  # noqa: BLE001
        # Cap is best-effort — if Pillow chokes on the format we still want
        # the upload to succeed with the raw bytes.
        logger.warning("cap_original_bytes skipped for upload sha=%s: %s",
                       sha[:10], e)

    # Persist the ORIGINAL to disk via the disk storage backend's
    # content-addressed layout. We bypass `store_image()` (which expects
    # a data URL) and write directly so we avoid an unnecessary base64
    # round-trip — uploads of 5 MB photos save ~7 MB of memory each.
    backend = _get_backend()
    root = getattr(backend, "root", None) or os.environ.get("UPLOAD_DIR", "/opt/autobids/uploads")
    rel = f"auctions/{sha[:2]}/{sha}.{ext}"
    abs_path = os.path.join(root, rel)
    if not os.path.exists(abs_path):
        try:
            os.makedirs(os.path.dirname(abs_path), exist_ok=True)
            tmp = abs_path + ".tmp"
            with open(tmp, "wb") as fh:
                fh.write(bytes(chunks))
            os.replace(tmp, abs_path)
        except OSError as e:
            logger.exception("image upload write failed sha=%s: %s", sha[:10], e)
            raise HTTPException(
                status_code=500,
                detail=f"Грешка при запис на диска ({e.strerror}). Опитайте отново.",
            ) from e

    from storage import public_uploads_base
    public_url = f"{public_uploads_base()}/{rel}"

    # Kick off variant generation. The queue worker reads the file from
    # disk, so we don't pass the bytes — saves memory in the queue.
    await ioq.enqueue(
        sha=sha, src_path=abs_path,
        auction_id=auction_id, image_idx=None,
    )

    return {
        "url": public_url,
        "sha": sha,
        "ext": ext,
        "size_bytes": len(chunks),
        "status": "optimizing",
    }


@api.get("/images/status")
async def image_optimization_status(
    shas: str,
    user: dict = Depends(get_current_user),
):
    """Poll endpoint for image optimization status.

    `shas` is a comma-separated list of sha256 ids. Returns a map of
    `{sha: {status, manifest?}}` so the frontend can swap the
    placeholder `<img>` for the AVIF/WebP `<picture>` once ready.

    Up to 60 shas per request (matches the max images-per-listing cap).
    """
    requested = [s.strip() for s in (shas or "").split(",") if s.strip()][:60]
    if not requested:
        return {"items": {}}

    out: dict[str, dict] = {s: {"status": "unknown"} for s in requested}
    # Match any auction that references any of the requested shas.
    or_clauses = [{f"image_optimization.{s}": {"$exists": True}} for s in requested]
    cursor = db.auctions.find(
        {"$or": or_clauses},
        {"_id": 0, "image_optimization": 1},
    )
    async for doc in cursor:
        mp = doc.get("image_optimization") or {}
        for s in requested:
            entry = mp.get(s)
            if entry and out[s]["status"] == "unknown":
                out[s] = {
                    "status": entry.get("status"),
                    "manifest": entry.get("manifest"),
                    "attempts": entry.get("attempts"),
                }
    return {"items": out}


@api.post("/auctions")

@limiter.limit("10/minute")
async def create_auction(request: Request, payload: AuctionCreate, user: dict = Depends(require_verified_email)):
    # --- Image validation, optimization & thumbnail generation ---
    # Per-image hard cap: 10 MB raw (post-decode). Total per listing: 120 MB.
    # Server-side Pillow re-encodes everything to JPEG @ ≤1920px / q=85 and
    # generates 400px thumbnails — strips EXIF, kills SVG-injection vectors.
    from services import image_processing as imgproc

    MAX_PER_IMG_RAW = imgproc.IMAGE_MAX_RAW_BYTES   # 10 MB
    MAX_TOTAL_IMGS = 120
    MAX_TOTAL_PAYLOAD_RAW = 120 * 1024 * 1024       # 120 MB aggregate

    total_raw = 0
    total_count = 0
    for bucket in (payload.images, payload.images_exterior, payload.images_wheels,
                   payload.images_bumper, payload.images_interior):
        if not bucket:
            continue
        for item in bucket:
            if not isinstance(item, str):
                continue
            sz = imgproc.raw_bytes_of(item) if item.startswith("data:image/") else 0
            if sz > MAX_PER_IMG_RAW:
                mb = round(sz / 1024 / 1024, 1)
                raise HTTPException(
                    status_code=413,
                    detail=f"Една от снимките е твърде голяма ({mb} MB). Макс. 10 MB на снимка.",
                )
            total_raw += sz
            total_count += 1
    if total_count > MAX_TOTAL_IMGS:
        raise HTTPException(status_code=413, detail=f"Твърде много снимки (макс. {MAX_TOTAL_IMGS})")
    if total_raw > MAX_TOTAL_PAYLOAD_RAW:
        mb = round(total_raw / 1024 / 1024, 1)
        raise HTTPException(
            status_code=413,
            detail=f"Общият размер на снимките е {mb} MB — надвишава лимита от 120 MB.",
        )

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
    # Tag each entry with its source bucket so the auction card preview
    # picker can order the gallery as: main → exterior → interior → interior.
    merged = []
    image_categories: list[str] = []  # parallel array to `merged`
    if has_categorized:
        # First exterior shot doubles as the "main" cover. Tag it
        # explicitly so the card picker prefers it for slide 1.
        for idx, u in enumerate(exterior):
            merged.append(u)
            image_categories.append("main" if idx == 0 else "exterior")
        for u in bumper:
            merged.append(u); image_categories.append("detail")
        for u in wheels:
            merged.append(u); image_categories.append("detail")
        for u in interior:
            merged.append(u); image_categories.append("interior")
    else:
        merged = list(payload.images or [])
        # Uncategorized upload — tag only the first as main, the rest stay neutral.
        image_categories = ["main" if i == 0 else "other" for i in range(len(merged))]

    # Pre-fetch any external https URLs (e.g. from mobile.bg import) into
    # data URLs so the standard optimize_many → store_image pipeline takes
    # ownership of the bytes. Without this step external CDN URLs would
    # pass through optimize_data_url() untouched and be persisted verbatim,
    # leaving us dependent on focus.bg/mobistatic.bg uptime + leaking the
    # buyer's IP to mobile.bg on every gallery view.
    #
    # `strict=True` returns an empty string in place of any URL that
    # failed to download (404, network error). We drop those entries and
    # the parallel category array so we never persist a broken external
    # URL on a listing.
    #
    # The whole block is wrapped in a try/except because production
    # Hetzner egress to focus.bg/mobistatic.bg can intermittently fail
    # (rate-limiting, transient 502s, blocked DC IP ranges). When it
    # fails we keep the original URLs so the seller can at least submit
    # — the listing will still display via mobile.bg's CDN. Admins can
    # then re-run the migration script once egress is restored.
    try:
        from storage import fetch_remote_images_as_data_urls
        fetched = await fetch_remote_images_as_data_urls(merged, strict=True)
        new_merged: list[str] = []
        new_categories: list[str] = []
        dropped = 0
        for u, c in zip(fetched, image_categories):
            if not u:
                dropped += 1
                continue
            new_merged.append(u)
            new_categories.append(c)
        if dropped:
            logger.warning("[submit] dropped %d unfetchable external image URLs", dropped)
        # Only adopt the filtered list if we ended up with something to
        # store — otherwise fall back to the original payload so the
        # submit doesn't die on a temporary CDN outage.
        if new_merged:
            merged = new_merged
            image_categories = new_categories
    except Exception as _rehost_err:  # noqa: BLE001
        logger.warning("[submit] external rehost pre-fetch failed, keeping original URLs: %s", _rehost_err)
    if not merged:
        raise HTTPException(
            status_code=400,
            detail="Нито една снимка не можа да бъде свалена. Моля, качете снимки директно вместо да импортирате от mobile.bg.",
        )

    # Optimize on a worker thread — Pillow is sync and CPU-bound. Wrap
    # the whole optimize+store step too because focus.bg's https URLs
    # pass through optimize_data_url() as-is, but store_image() will
    # raise `ImageProcessingError` if the local disk isn't writable
    # (UPLOAD_DIR perms / missing mount). On that failure we degrade to
    # persisting the original payload so the seller can still submit.
    try:
        web_urls, thumb_urls, errs = await asyncio.to_thread(imgproc.optimize_many, merged)
        if errs:
            # Surface first 3 errors so user sees actionable feedback.
            msg = "; ".join(errs[:3])
            if len(errs) > 3:
                msg += f"; и още {len(errs) - 3}"
            raise HTTPException(status_code=400, detail=f"Грешка при обработката на снимки: {msg}")
    except HTTPException:
        raise
    except Exception as _opt_err:  # noqa: BLE001
        logger.warning("[submit] optimize_many failed (%s) — saving raw URLs as-is", _opt_err)
        web_urls = list(merged)
        thumb_urls = list(merged)

    auction_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc)
    ends_at = now + timedelta(days=payload.duration_days)
    doc = payload.model_dump()
    # Persist optimized JPEGs (and thumbnails) to the configured storage
    # backend. Runs off the event loop because S3 uploads can be slow.
    # We launch both batches concurrently — they share zero state and
    # the disk/S3 backend handles its own internal serialisation.
    #
    # If disk write fails (most often: `/opt/autobids/uploads` missing
    # or not writable by the backend user), raise a clear 500 instead
    # of swallowing the error — silently keeping data: URLs would bloat
    # the DB document to hundreds of MB and make every gallery request
    # ship base64 bytes back to the browser.
    from storage import store_images
    try:
        web_urls, thumb_urls = await asyncio.gather(
            asyncio.to_thread(store_images, web_urls),
            asyncio.to_thread(store_images, thumb_urls),
        )
    except imgproc.ImageProcessingError as e:
        logging.getLogger("storage").error("Image storage write failed: %s", e)
        raise HTTPException(
            status_code=500,
            detail=f"Съхраняването на снимките не успя: {e}. Свържете се с администратора.",
        )

    # Guard against base64 data: URLs leaking into DB. This can only
    # happen if storage misconfigures *after* the try/except above
    # (e.g. STORAGE_BACKEND=inline), or if a future code path skips
    # the optimize pipeline. Belt-and-suspenders.
    def _strip_data_urls(urls: list[str]) -> list[str]:
        return [u for u in urls if not (isinstance(u, str) and u.startswith("data:"))]
    if any(isinstance(u, str) and u.startswith("data:") for u in web_urls):
        logging.getLogger("storage").error(
            "BUG: data: URLs surfaced past store_images — dropping %d entries",
            sum(1 for u in web_urls if isinstance(u, str) and u.startswith("data:")),
        )
        web_urls = _strip_data_urls(web_urls)
        thumb_urls = _strip_data_urls(thumb_urls)
        if not web_urls:
            raise HTTPException(
                status_code=500,
                detail="Снимките не можаха да бъдат запазени на диска. Свържете се с администратора (STORAGE_BACKEND).",
            )
    doc["images"] = web_urls
    doc["thumbnails"] = thumb_urls

    # ── Variants: deferred to the background queue ─────────────────────
    # Pillow encoding (AVIF + WebP + JPG × 4 sizes = 12 outputs per image)
    # is the single largest CPU cost in this endpoint — historically it
    # added 0.5-1.5 s PER IMAGE × N to the submit latency, so a typical
    # 24-photo listing sat on the submit spinner for 20-40 s.
    #
    # Since 2026-05-16 the new `services.image_optimization_queue`
    # handles this off-band: we persist the optimized JPGs + thumbnails
    # synchronously (so the auction is immediately viewable with a
    # working `<img src>`) and enqueue the AVIF/WebP variant pass for
    # background generation. The frontend `<Picture>` element gracefully
    # falls back to the JPG URL until the manifest lands in
    # `image_optimization.<sha>.manifest`, at which point a periodic
    # auction refresh (or the next page load) picks them up.
    #
    # Net effect: submit latency drops from ~20-40 s → ~3-5 s for a 24-
    # photo listing.
    doc["images_variants"] = []
    # Build a placeholder `image_optimization` map for admin visibility
    # — we don't yet have the file paths (enqueue happens after DB
    # insert below), but `enqueue_for_stored_urls` will overwrite each
    # entry with the real status once it locates the sha + on-disk path.

    # ---- VAT validation ----
    vat = (doc.get("vat_status") or "").strip() or None
    if vat and vat not in ("exempt", "vat_inclusive"):
        raise HTTPException(status_code=400, detail="vat_status трябва да е 'exempt' или 'vat_inclusive'")
    if vat == "vat_inclusive":
        rate = doc.get("vat_rate_pct")
        if rate is None or float(rate) <= 0 or float(rate) > 50:
            raise HTTPException(status_code=400, detail="ДДС % трябва да е между 1 и 50")
        doc["vat_rate_pct"] = float(rate)
        # legacy net/gross fields no longer used
        doc["price_net_eur"] = None
        doc["price_gross_eur"] = None
    else:
        doc["vat_rate_pct"] = None
        doc["price_net_eur"] = None
        doc["price_gross_eur"] = None

    # ---- No-reserve flag ----
    if doc.get("no_reserve"):
        doc["reserve_eur"] = None

    # ---- VIN validation (required for every listing) ----
    vin_raw = (doc.get("vin") or "").strip().upper()
    if not vin_raw:
        raise HTTPException(status_code=400, detail="VIN номерът е задължителен")
    # Allow legacy 11-char Bulgarian frames AND modern 17-char ISO 3779 VINs;
    # reject obvious garbage (must be alphanumeric, no spaces/dashes).
    if not re.match(r"^[A-HJ-NPR-Z0-9]{11,17}$", vin_raw):
        raise HTTPException(status_code=400, detail="VIN може да съдържа само цифри и латински букви (без I, O, Q), 11–17 знака")
    doc["vin"] = vin_raw

    # ---- Buy-now sanity check ----
    if doc.get("buy_now_eur") is not None:
        try:
            bn = float(doc["buy_now_eur"])
        except Exception:
            bn = 0
        if bn <= 0:
            doc["buy_now_eur"] = None
        else:
            if doc.get("reserve_eur") and bn < float(doc["reserve_eur"]):
                raise HTTPException(status_code=400, detail="Цена 'Купи сега' трябва да е поне колкото резерва.")
            if bn < float(doc.get("starting_bid_eur") or 0):
                raise HTTPException(status_code=400, detail="Цена 'Купи сега' трябва да е поне колкото началната цена.")
            doc["buy_now_eur"] = round(bn, 2)

    # ---- Validate make is in the known catalog (if any makes seeded) ----
    known_make = await db.makes.find_one({"name": doc.get("make", "")}, {"_id": 0, "name": 1})
    total_makes = await db.makes.count_documents({})
    if total_makes > 0 and not known_make:
        raise HTTPException(status_code=400, detail=f"Неизвестна марка '{doc.get('make','')}'. Изберете от списъка или помолете админ да я добави.")

    doc.update({
        "id": auction_id,
        "seller_id": user["id"],
        "seller_name": user["name"],
        "seller_avatar_url": user.get("avatar_url"),
        "current_bid_eur": payload.starting_bid_eur,
        "bid_count": 0,
        "created_at": now.isoformat(),
        "ends_at": ends_at.isoformat(),
        "status": "pending",  # awaiting approval
        "featured": False,
        "is_archived": False,
    })
    await db.auctions.insert_one(doc)
    # Schedule background AVIF/WebP variant generation — runs off the
    # critical path so the submit response returns now rather than after
    # ~1 s × N images of Pillow encoding. The queue updates
    # `auctions.image_optimization.<sha>` per image as it progresses,
    # and the frontend `<Picture>` element gracefully falls back to the
    # JPG URLs in `doc["images"]` until variants are ready.
    #
    # IMAGE_VARIANTS_EAGER (default "0" since 2026-05-17):
    #   • "1" — keep the old behaviour, pre-generate all 12 variants in
    #     the background queue right after submission.
    #   • "0" — skip eager generation. Nginx's `try_files $uri @generate`
    #     fallback (see services.image_variants.generate_one_variant)
    #     materialises each variant on first request. This is cheaper at
    #     submit time and lets ops blow away `/variants/` at will.
    if os.environ.get("IMAGE_VARIANTS_EAGER", "0") == "1":
        try:
            from services import image_optimization_queue as _ioq
            await _ioq.enqueue_for_stored_urls(
                web_urls, auction_id=auction_id, categories=image_categories,
            )
        except Exception as e:  # noqa: BLE001
            logger.warning("[submit] failed to enqueue variant generation: %s", e)
    # In-app notification → admins for moderation queue
    try:
        from routers.inbox import notify_admins as _notify_admins
        await _notify_admins(
            db,
            type="listing_pending",
            data={"seller": user.get("name", ""), "title": doc.get("title", "")},
            auction_id=auction_id,
            link="/admin?tab=pending",
            push_template_id="admin_new_pending_listing",
            push_fmt={"seller": user.get("name", "") or "Продавач", "title": doc.get("title", "")[:80]},
        )
    except Exception as e:
        logger.warning("notify_admins (pending) failed: %s", e)
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
async def import_from_mobile_bg(request: Request, payload: MobileBgImport):
    """Scrapes a mobile.bg listing URL and returns a dict of pre-filled auction fields.
    Public helper — no auth needed; the actual auction creation later does require login.
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

    # Images: collect ALL candidate photo URLs (may include thumbnail + big
    # variants of the same picture — mobile.bg embeds both in the gallery
    # markup). We deduplicate below by canonicalizing each URL.
    #
    # IMPORTANT: limit the search to the main ad gallery. mobile.bg
    # appends a "Още обяви в mobile.bg" block with thumbnails of OTHER
    # listings — pulling those in would mix unrelated cars into our
    # imported photo list.
    candidates: list[str] = []
    gallery_roots = []
    for sel in ["#rezon-gallery", ".owl-carousel", ".newAdImages", "section"]:
        el = soup.select_one(sel)
        if el:
            gallery_roots.append(el)
            break  # first matching scope is enough
    search_root = gallery_roots[0] if gallery_roots else soup
    for img in search_root.find_all("img"):
        src = img.get("src") or img.get("data-src") or img.get("data-src-gallery") or ""
        if not src:
            continue
        if src.startswith("//"):
            src = "https:" + src
        elif src.startswith("/"):
            src = "https://www.mobile.bg" + src
        if ("mobile.bg" in src or "focus.bg" in src or src.startswith("http")) and any(x in src.lower() for x in ["photo", "pic", "big", "jpg", "jpeg", "png", "webp"]):
            low = src.lower()
            if not any(bad in low for bad in ["logo", "icon", "nophoto", "placeholder", "sprite", "avatar"]):
                candidates.append(src)

    # ---- Smart thumbnail dedup ----------------------------------------
    # mobile.bg consistently publishes two variants of the same photo in
    # the gallery HTML: one in a "big<N>/" path (e.g. /big1/, /big2/) with
    # the high-res source, and a second in a parallel thumbnail path
    # (the same directory WITHOUT the `/bigN/` segment, serving ~120 px
    # low-res previews for the scroll rail). Users reported ~7 low-res
    # dupes sneaking in because our original regex only matched `/big/`
    # without a trailing digit.
    #
    # Strategy: canonical key = the final filename only (mobile.bg
    # assigns a deterministic `<listingId>_<code>.webp` filename that is
    # IDENTICAL for the big and small variants of the same photo). Then
    # keep the variant with the highest "resolution score" per key and
    # preserve first-seen ordering. Filename-based keying also survives
    # any future CDN path changes on mobile.bg's side.
    def _canon(u: str) -> str:
        lu = u.lower().split("?", 1)[0]
        # Prefer the basename as the canonical key — mobile.bg uses the
        # same filename for thumb + big (only the directory differs).
        tail = lu.rsplit("/", 1)[-1]
        if tail and "." in tail:
            return tail
        # Fallback for URLs without a clear filename — collapse any size
        # folder or suffix so both variants still key the same.
        lu = _re.sub(r"/(big\d*|small|thumb|medium|orig|large|preview|tn)/", "/", lu)
        lu = _re.sub(r"_(big\d*|small|t|thumb|medium|orig|large|preview|tn)(?=\.[a-z0-9]+$)", "", lu)
        lu = _re.sub(r"/(?:\d{1,3})-([^/]+\.(?:jpg|jpeg|png|webp))$", r"/\1", lu)
        return lu

    def _score(u: str) -> int:
        lu = u.lower()
        # Higher = bigger/better. Prefer explicit big/orig/large markers.
        # `big1`, `big2`… are mobile.bg's high-res directories.
        if _re.search(r"/big\d*/", lu) or "_big." in lu or "/orig" in lu or "_orig." in lu:
            return 5
        if "/large/" in lu or "_large." in lu:
            return 4
        if "/medium/" in lu or "_medium." in lu:
            return 2
        if ("/small/" in lu or "_small." in lu or "/thumb/" in lu or
                "_thumb." in lu or "_t." in lu or "/tn/" in lu or "/preview/" in lu):
            return 1
        # No explicit marker → assume standard resolution (neutral)
        return 3

    best_for_key: dict[str, tuple[int, str]] = {}
    key_first_seen: list[str] = []
    for u in candidates:
        k = _canon(u)
        s = _score(u)
        prev = best_for_key.get(k)
        if prev is None:
            key_first_seen.append(k)
            best_for_key[k] = (s, u)
        elif s > prev[0]:
            best_for_key[k] = (s, u)
    images: list[str] = []
    for k in key_first_seen:
        images.append(best_for_key[k][1])
        if len(images) >= 24:
            break

    # ── Rehost imported images to our own storage ─────────────────────
    # Without this step the auction would keep `mobistatic*.focus.bg`
    # URLs forever, which means:
    #   • we can't watermark or re-compress,
    #   • mobile.bg can rotate/delete the source any time and nuke our
    #     gallery,
    #   • the source CDN sees our buyers' IPs on every view.
    #
    # Flow: download each image (parallel, with byte cap and timeout) →
    # data URL → optimize_many (Pillow re-encode, EXIF stripped, JPEG
    # q85, ≤1920 px long edge, plus a 400 px thumbnail) → store_images
    # (sha256-addressed write under /opt/autobids/uploads/auctions/). The
    # final list is short `/api/uploads/...` paths, NOT the gigantic
    # data URLs themselves — keeping the import response small.
    #
    # Pre-fetch + locally-rehost the listing images so they end up under
    # our CDN. Variant generation (AVIF/WebP/JPG × 4 sizes) is DEFERRED
    # to the background queue — the importer used to inline-generate
    # 12 variants per image which added 5-15 s to the importer response
    # on a typical 20-photo listing. Now the importer returns as soon
    # as the optimized JPGs + thumbnails are stored, and the variant
    # pass continues in the background.
    #
    # Any individual fetch failure transparently keeps the original
    # https URL — better to ship the listing with an external image
    # than block the whole import on one flaky CDN slot.
    thumbnails: list[str] = []
    images_variants: list[dict] = []   # always empty here — variants are deferred
    if images:
        try:
            from storage import fetch_remote_images_as_data_urls
            from services.image_processing import optimize_many
            from storage import store_image
            # 1. Download bytes from the source CDN. `strict=True` returns
            #    "" for any URL that 404s / times out so we never persist
            #    a broken external URL on the imported listing.
            data_urls = await fetch_remote_images_as_data_urls(images, strict=True)
            # Realign the source `images` list with the successful fetches
            # so the indices used below for variant generation match.
            images = [src for src, du in zip(images, data_urls) if du]
            data_urls = [du for du in data_urls if du]
            # 2. Re-encode (CPU-bound) on the thread pool so we don't
            #    starve the event loop while Pillow chews on 24 images.
            web_urls, thumb_urls, _errs = await asyncio.to_thread(optimize_many, data_urls)
            # 3. Persist both batches in parallel — independent disk
            #    writes, two threads is roughly 2× faster than serial.
            images, thumbnails = await asyncio.gather(
                asyncio.to_thread(lambda: [store_image(u) for u in web_urls]),
                asyncio.to_thread(lambda: [store_image(u) for u in thumb_urls]),
            )
            # 4. Variants deferred — no inline `variants_from_data_url`.
            #    When the user clicks Submit, `/auctions` will enqueue
            #    a variant generation pass for whatever images make it
            #    into the final listing. We don't enqueue here because
            #    the user might still edit/remove images on the form
            #    before submitting, and we'd be wasting cycles on
            #    photos that never end up in the auction.
        except Exception as _img_e:  # noqa: BLE001
            logger.warning("[mobile.bg import] rehost failed, keeping URLs: %s", _img_e)

    # City: mobile.bg serves everything in Cyrillic. Transliterate to Latin
    # (Gemini → Emergent LLM → deterministic char-map) so the form preset
    # matches the rest of the UI. Country is inferred from the tenant
    # domain (.bg → Bulgaria, .ro → Romania, .com → Bulgaria).
    city_latin = ""
    if city:
        try:
            from translate import transliterate_city_to_latin
            city_latin = await transliterate_city_to_latin(city)
        except Exception:  # defensive — never block an import on this
            from translate import _static_transliterate_bg
            city_latin = _static_transliterate_bg(city)
    from translate import country_from_host
    host_header = (request.headers.get("host") or "").lower()
    country = country_from_host(host_header)

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
        "city": city_latin or city,
        "country": country,
        "description": description[:3500] if description else "",
        "images": images,
        "thumbnails": thumbnails,
        "images_variants": images_variants,
        "source_url": url or "",
    }



# ---- Bids ----
@api.get("/me/preauths")
async def my_preauths(user: dict = Depends(get_current_user)):
    """Return all live auctions where the user has placed a bid — both
    auctions where they are *currently leading* and those where they have
    been *outbid*. Powers the notification bell's "Active bids" pinned
    section.

    For each auction:
      - `is_leading` — True if user is currently the high bidder
      - `user_max_bid_eur` — user's highest bid on the auction
      - `current_bid_eur` — auction's current high bid (== user's bid
        when they are leading; higher when outbid)

    Backwards-compat fields (`max_amount_eur`, `available_eur`,
    `used_eur`) preserved for existing consumers.
    """
    # 1) Pull every live auction the user has at least one bid on (PG).
    from services import bidding as bidding_svc
    bids = await bidding_svc.list_user_bids(user["id"], limit=500)
    if not bids:
        return []

    # Dedupe by auction_id, keeping the highest amount the user bid.
    user_max: dict[str, float] = {}
    for b in bids:
        aid = b.get("auction_id")
        amt = float(b.get("amount_eur") or 0)
        if aid and amt > user_max.get(aid, 0.0):
            user_max[aid] = amt

    # 2) Fetch matching live auctions from Mongo (status, current bid,
    #    title, ends_at, leader).
    cursor = db.auctions.find(
        {
            "id": {"$in": list(user_max.keys())},
            "status": "live",
            "is_archived": {"$ne": True},
        },
        {
            "_id": 0, "id": 1, "title": 1, "slug": 1,
            "current_bid_eur": 1, "high_bidder_id": 1,
            "status": 1, "ends_at": 1, "images": 1,
        },
    )
    out: list[dict] = []
    async for a in cursor:
        aid = a["id"]
        my = float(user_max.get(aid, 0.0))
        cur = float(a.get("current_bid_eur") or 0)
        is_leading = (a.get("high_bidder_id") == user["id"])
        thumb = None
        imgs = a.get("images") or []
        if imgs:
            first = imgs[0]
            thumb = first.get("url") if isinstance(first, dict) else first
        out.append({
            "auction_id": aid,
            "auction_title": a.get("title") or "—",
            "auction_slug": a.get("slug"),
            "auction_status": a.get("status"),
            "auction_thumb": thumb,
            "is_leading": is_leading,
            "user_max_bid_eur": my,
            "current_bid_eur": cur,
            "ends_at": a.get("ends_at"),
            # Backwards-compat fields:
            "max_amount_eur": my,
            "used_eur": my,
            "available_eur": my,
        })
    # Sort: leading first (so "your active leads" sit on top), then
    # outbid. Within each group, soonest-ending first.
    out.sort(key=lambda x: (not x.get("is_leading"), x.get("ends_at") or ""))
    return out


@api.get("/auctions/{auction_id}/bids")
async def list_bids(auction_id: str, request: Request):
    # Hide bid history for archived listings — only admins/moderators can see.
    a = await db.auctions.find_one(
        {"id": auction_id},
        {"_id": 0, "is_archived": 1, "status": 1},
    )
    if not a:
        raise HTTPException(status_code=404, detail="Търгът не е намерен")
    if a.get("is_archived") or a.get("status") == "archived":
        viewer = await get_optional_user(request)
        if not (viewer and viewer.get("role") in ("admin", "moderator")):
            raise HTTPException(status_code=404, detail="Търгът не е намерен")
    from services import bidding as bidding_svc
    bids = await bidding_svc.list_bids(auction_id, limit=50)
    await _hydrate_user_slug(bids)
    return bids


# ---- Bidding Credit (pre-authorization for multiple bids) ----
@api.get("/auctions/{auction_id}/bidding-credit")
async def get_my_credit(auction_id: str, user: dict = Depends(get_current_user)):
    credit = await db.bidding_credits.find_one(
        {"auction_id": auction_id, "user_id": user["id"], "status": "authorized"},
        {"_id": 0},
    )
    return credit or None


@api.post("/auctions/{auction_id}/bidding-credit")
async def create_or_increase_credit(auction_id: str, payload: BiddingCreditCreate, user: dict = Depends(require_verified_email)):
    a = await db.auctions.find_one({"id": auction_id}, {"_id": 0})
    if not a:
        raise HTTPException(status_code=404, detail="Търгът не е намерен")
    if _auction_status(a) != "live":
        raise HTTPException(status_code=400, detail="Търгът не е активен")
    if a.get("seller_id") == user["id"]:
        raise HTTPException(status_code=400, detail="Не можете да създавате credit за собствен търг")
    min_credit = float(a["current_bid_eur"]) + 100
    if payload.max_amount_eur < min_credit:
        raise HTTPException(status_code=400, detail=f"Максималната сума трябва да е поне €{int(min_credit)} (следващо наддаване)")

    now = datetime.now(timezone.utc)
    now_iso = now.isoformat()
    # Buyer's premium (preauth) is computed on the gross — incl. VAT for vat_inclusive auctions
    preauth_amount = _buyer_fee_on_auction(payload.max_amount_eur, a)

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
async def place_bid(request: Request, auction_id: str, payload: BidCreate, user: dict = Depends(require_verified_email)):
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

    # ─── Account-level credit pool check ────────────────────────────
    # Holds are no longer bound to specific auctions — the user tops
    # up an account credit pool, and any leading bid on a live
    # auction commits funds against that pool. Reject the bid if it
    # would push committed > authorized.
    #
    # For admins/moderators we skip the gate (operational test
    # bidding) — same carve-out we use elsewhere.
    bypass_credit = user.get("role") in ("admin", "moderator")
    authorized_total = 0.0
    committed_total = 0.0
    current_high_for_user = 0.0
    if not bypass_credit:
        async for r in db.bid_authorizations.find(
            {"user_id": user["id"],
             "auction_id": None,
             "authorization_status": "active"},
            {"_id": 0, "bidding_limit_eur": 1},
        ):
            authorized_total += float(r.get("bidding_limit_eur") or 0)
        async for ca in db.auctions.find(
            {"high_bidder_id": user["id"], "status": "live"},
            {"_id": 0, "id": 1, "current_bid_eur": 1},
        ):
            cb = float(ca.get("current_bid_eur") or 0)
            committed_total += cb
            if ca["id"] == auction_id:
                current_high_for_user = cb
        # If the user is already leading THIS auction, the new bid
        # *replaces* (not adds to) the previous commitment on this
        # auction. Subtract the existing one so the math reflects the
        # net delta the user is on the hook for.
        new_commit = committed_total - current_high_for_user + amount
        if new_commit > authorized_total + 1e-6:
            shortage = new_commit - authorized_total
            raise HTTPException(
                status_code=402,
                detail=(
                    f"Нямате достатъчен наддавателен кредит. "
                    f"Налични: €{int(authorized_total - committed_total):,}, "
                    f"необходими: €{int(amount - current_high_for_user):,}. "
                    f"Заредете още поне €{int(shortage):,} от профила си."
                ),
            )

    bid_id = str(uuid.uuid4())
    fee_amount = _buyer_fee_on_auction(amount, a)

    # Legacy `bidding_credits` table is no longer written. Bid is
    # backed by the account-level credit pool (validated above).
    preauth_id = f"acct_pool_{uuid.uuid4().hex[:16]}"
    preauth_status_val = "credit_backed"
    card_last4 = None
    credit_id_val = None

    # ACID-correct placement (locks bid_state, validates, inserts, updates)
    # Capture client metadata for the forensic audit trail. We honour the
    # standard reverse-proxy chain (`X-Forwarded-For`) and fall back to
    # `request.client.host` for direct hits. UA is truncated at 512 chars
    # inside the service layer to fit the column.
    _xff = request.headers.get("x-forwarded-for", "")
    # VAT-aware step: when the auction is VAT-inclusive, the bracket
    # lookup runs on the gross price so the buyer-visible min next bid
    # stays a clean BaT increment. Capture the auction's VAT fields in
    # a closure so the locked re-validation inside bidding_svc sees the
    # same rule the client did.
    _vat_inclusive = a.get("vat_status") == "vat_inclusive"
    _vat_rate = float(a.get("vat_rate_pct") or 0) if _vat_inclusive else 0.0
    def _vat_aware_step(current_net: float) -> float:
        if _vat_inclusive and _vat_rate > 0:
            mult = 1.0 + _vat_rate / 100.0
            cur_gross = round(float(current_net) * mult, 2)
            step_gross = _bid_step(cur_gross)
            min_next_gross = round(cur_gross + step_gross, 2)
            min_next_net = round(min_next_gross / mult, 2)
            return round(min_next_net - float(current_net), 2)
        return _bid_step(current_net)

    client_ip = (_xff.split(",")[0].strip() if _xff else (request.client.host if request.client else None))
    client_ua = request.headers.get("user-agent", "")[:512] or None
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
            bid_step_fn=_vat_aware_step,
            extension_minutes=2,
            ip_address=client_ip,
            user_agent=client_ua,
        )
    except ValueError as ve:
        # min_bid:<value>
        if str(ve).startswith("min_bid:"):
            min_next = float(str(ve).split(":", 1)[1])
            raise HTTPException(status_code=400, detail=f"Минималното следващо наддаване е €{int(min_next)}")
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
            from services import notif_prefs as _nprefs
            if _nprefs.is_enabled(prev_user, "email", "outbid"):
                try:
                    await email_outbid(prev_user["email"], prev_user["name"], a["title"], auction_id, amount, lang=prev_user.get("lang") or "bg")
                except Exception as e:
                    logger.error("email_outbid failed: %s", e)
            # Web Push — outbid notification (localized to user's lang)
            if _nprefs.is_enabled(prev_user, "push", "outbid"):
                try:
                    from services import push_templates
                    await push_templates.send_template(
                        prev_high,
                        "outbid",
                        fmt_args={"title": a["title"][:60], "amount": f"{int(amount):,}"},
                        url=f"/auctions/{auction_id}",
                        tag=f"outbid-{auction_id}",
                    )
                except Exception as e:
                    logger.error("push outbid failed: %s", e)

    # Mirror denormalised fields onto the Mongo auction so the rest of the app
    # (filters, listings, sorting, sitemap) keeps working without a join.
    # Best-effort fast path: the outbox event written inside place_bid()'s
    # transaction is the source of truth — if this sync write fails or the
    # process crashes here, the outbox worker (services.outbox_worker) will
    # apply the same change idempotently within ~250ms.
    try:
        update = {
            "current_bid_eur": amount,
            "bid_count": result["bid_count"],
            "high_bidder_id": user["id"],
            "high_bidder_name": user["name"],
        }
        if triggered_extension:
            update["ends_at"] = new_ends_at_iso
        await db.auctions.update_one(
            {"id": auction_id, "$or": [
                {"bid_count": {"$lt": result["bid_count"]}},
                {"bid_count": {"$exists": False}},
            ]},
            {"$set": update},
        )
        # Mark outbox event applied so the worker doesn't redo the same write.
        from services.outbox_worker import pg_session as _pgs
        from sqlalchemy import update as _upd
        from models_pg import BidEvent as _BE
        async with _pgs() as _s:
            await _s.execute(
                _upd(_BE).where(_BE.id == result["event_id"], _BE.applied_at.is_(None)).values(
                    applied_at=datetime.now(timezone.utc),
                    attempt_count=1,
                )
            )
    except Exception as e:
        logger.warning("Sync Mongo mirror failed (outbox will catch up): %s", e)

    public_bid = result["bid"]
    await hub.broadcast(auction_id, {
        "type": "bid",
        "auction_id": auction_id,
        "current_bid_eur": amount,
        "high_bidder_name": user["name"],
        "bid_count": result["bid_count"],
        "ends_at": new_ends_at_iso,
        "bid": {
            **{k: public_bid.get(k) for k in ("id", "user_id", "user_name", "amount_eur", "created_at")},
            "user_slug": user.get("profile_slug"),
        },
    })

    # Refresh the social share card PNG so Facebook/WhatsApp/Telegram
    # see the new price on the next scrape. Fire-and-forget — the
    # `_retry_og_image` helper swallows errors and bumps `og_image_url`
    # with a fresh `?v={updated_at}` cache buster for the crawlers to
    # invalidate their cache on.
    try:
        asyncio.create_task(_retry_og_image(auction_id, delay_sec=0))
    except Exception as e:
        logger.warning("og:bid-refresh schedule failed for %s: %s", auction_id, e)

    # Notify seller on new bid
    seller_id = a.get("seller_id")
    if seller_id and seller_id != "platform":
        seller = await db.users.find_one({"id": seller_id}, {"_id": 0})
        from services import notif_prefs as _nprefs
        if seller and seller.get("email") and _nprefs.is_enabled(seller, "email", "seller_new_bid"):
            try:
                await email_seller_new_bid(seller["email"], seller.get("name", ""), a["title"], auction_id, user["name"], amount, result["bid_count"], lang=seller.get("lang") or "bg")
            except Exception as e:
                logger.error("email_seller_new_bid failed: %s", e)
        # Web Push — your car got a bid (localized for the seller)
        if seller_id and _nprefs.is_enabled(seller, "push", "seller_new_bid"):
            try:
                from services import push_templates
                await push_templates.send_template(
                    seller_id,
                    "seller_new_bid",
                    fmt_args={
                        "title": a["title"][:60],
                        "bidder": user["name"],
                        "amount": f"{int(amount):,}",
                        "count": result["bid_count"],
                    },
                    url=f"/auctions/{auction_id}",
                    tag=f"seller-bid-{auction_id}",
                )
            except Exception as e:
                logger.error("push seller_new_bid failed: %s", e)

        # Reserve-met notification (only fires once per auction)
        reserve = a.get("reserve_eur")
        if (
            seller
            and reserve is not None
            and float(reserve) > 0
            and amount >= float(reserve)
            and not a.get("reserve_met_notified")
        ):
            await db.auctions.update_one(
                {"id": auction_id, "reserve_met_notified": {"$ne": True}},
                {"$set": {"reserve_met_notified": True, "reserve_met_at": now.isoformat()}},
            )
            if seller.get("email") and _nprefs.is_enabled(seller, "email", "reserve_met"):
                try:
                    from emails import email_reserve_met
                    await email_reserve_met(seller["email"], seller.get("name", ""), a["title"], auction_id, amount, float(reserve), lang=seller.get("lang") or "bg")
                except Exception as e:
                    logger.error("email_reserve_met failed: %s", e)
            if _nprefs.is_enabled(seller, "push", "reserve_met"):
                try:
                    from services import push_templates
                    await push_templates.send_template(
                        seller_id,
                        "reserve_met",
                        fmt_args={"title": a["title"][:60], "amount": f"{int(amount):,}"},
                        url=f"/auctions/{auction_id}",
                        tag=f"reserve-met-{auction_id}",
                    )
                except Exception as e:
                    logger.error("push reserve_met failed: %s", e)

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
            body = f"autoandbid.com: Ново наддаване €{int(amount):,} за {a['title'][:50]}. Остават {mins}м. {app_url}/auctions/{auction_id}"
            for r in recipients:
                if r.get("phone"):
                    try:
                        await send_sms(r["phone"], body)
                    except Exception as e:
                        logger.error("send_sms failed: %s", e)

    return {"ok": True, "bid": public_bid, "preauth_amount_eur": fee_amount, "buyer_fee_eur": fee_amount}


# ─── Paid auction promotion ─────────────────────────────────────────────
# Sellers can pay €30 to pin their auction into the featured rotation
# (shown first in the homepage "Active Auctions" grid + hero pool).
# Payment is taken via Stripe Checkout — the `/promote/finalize`
# endpoint verifies the payment and sets `featured=True` on the auction.
# The previous "request-promotion" moderator-review flow is removed;
# promotion is now self-serve and instant on payment.
PROMOTION_PRICE_EUR = 30.0


@api.post("/auctions/{auction_id}/promote/checkout")
async def promote_checkout(auction_id: str, request: Request, body: dict = None,
                           user: dict = Depends(require_verified_email)):
    """Create a €30 Stripe Checkout for auction promotion. Seller-only."""
    a = await db.auctions.find_one({"id": auction_id}, {"_id": 0})
    if not a:
        raise HTTPException(status_code=404, detail="Обявата не е намерена")
    if a.get("seller_id") != user["id"]:
        raise HTTPException(status_code=403, detail="Само продавачът може да промотира обявата си.")
    if a.get("status") not in ("pending", "live"):
        raise HTTPException(status_code=400, detail="Може да се промотират само активни/очакващи обяви.")
    if a.get("featured"):
        raise HTTPException(status_code=400, detail="Тази обява вече е промотирана.")

    import stripe
    api_key = os.environ.get("STRIPE_API_KEY", "")
    if not api_key:
        raise HTTPException(status_code=503, detail="Stripe не е конфигуриран.")
    stripe.api_key = api_key

    # Preserve the seller's current domain (.bg/.com) on the return URL.
    # Shared resolver checks body.origin → Origin header → Referer → env.
    from routers.stripe_holds import resolve_stripe_redirect_origin
    origin = resolve_stripe_redirect_origin(
        (body or {}).get("origin") if isinstance(body, dict) else None,
        request,
    )

    success_url = f"{origin}/my-listings?promote_session={{CHECKOUT_SESSION_ID}}"
    cancel_url = f"{origin}/my-listings?promote_cancelled=1"

    try:
        session = stripe.checkout.Session.create(
            mode="payment",
            line_items=[{
                "price_data": {
                    "currency": "eur",
                    "product_data": {
                        "name": f"Промотиране на обява: {a.get('title','')[:90]}",
                        "description": "Еднократна такса за поставяне в избрана секция на началната страница.",
                    },
                    "unit_amount": int(PROMOTION_PRICE_EUR * 100),
                },
                "quantity": 1,
            }],
            payment_intent_data={
                "capture_method": "automatic",
                "metadata": {
                    "user_id": user["id"],
                    "auction_id": auction_id,
                    "intent": "promote_auction",
                },
            },
            metadata={
                "user_id": user["id"],
                "auction_id": auction_id,
                "intent": "promote_auction",
            },
            customer_email=user.get("email"),
            success_url=success_url,
            cancel_url=cancel_url,
        )
    except stripe.error.StripeError as e:
        logger.exception("promote stripe.checkout.create failed")
        raise HTTPException(status_code=502, detail=f"Stripe error: {getattr(e, 'user_message', str(e))}")

    await db.promotion_payments.insert_one({
        "session_id": session["id"],
        "user_id": user["id"],
        "auction_id": auction_id,
        "amount_eur": PROMOTION_PRICE_EUR,
        "status": "pending",
        "created_at": datetime.now(timezone.utc).isoformat(),
    })
    return {"redirect": True, "id": session["id"], "url": session["url"]}


@api.post("/auctions/{auction_id}/promote/finalize")
async def promote_finalize(auction_id: str, body: dict,
                           user: dict = Depends(require_verified_email)):
    """Activate the `featured` flag after a successful promotion payment.
    Idempotent: a second call on the same session is a no-op."""
    session_id = (body or {}).get("session_id") or ""
    if not session_id:
        raise HTTPException(status_code=400, detail="session_id липсва")

    import stripe
    api_key = os.environ.get("STRIPE_API_KEY", "")
    if not api_key:
        raise HTTPException(status_code=503, detail="Stripe не е конфигуриран.")
    stripe.api_key = api_key

    try:
        session = stripe.checkout.Session.retrieve(session_id)
    except stripe.error.StripeError as e:
        raise HTTPException(status_code=502, detail=f"Stripe retrieve: {e}")

    meta = getattr(session, "metadata", None) or {}
    if _stripe_meta_get(meta, "user_id") != user["id"]:
        raise HTTPException(status_code=403, detail="Сесията не принадлежи на този потребител.")
    if _stripe_meta_get(meta, "auction_id") != auction_id:
        raise HTTPException(status_code=400, detail="Сесията не е за тази обява.")
    if getattr(session, "payment_status", None) != "paid":
        raise HTTPException(status_code=402, detail="Плащането все още не е потвърдено.")

    payment = await db.promotion_payments.find_one({"session_id": session_id}, {"_id": 0})
    if payment and payment.get("status") == "activated":
        return {"ok": True, "already_activated": True}

    now_iso = datetime.now(timezone.utc).isoformat()
    await db.auctions.update_one(
        {"id": auction_id},
        {"$set": {
            "featured": True,
            "featured_at": now_iso,
            "featured_paid": True,
            "featured_session_id": session_id,
        }},
    )
    await db.promotion_payments.update_one(
        {"session_id": session_id},
        {"$set": {"status": "activated", "activated_at": now_iso}},
    )
    return {"ok": True, "auction_id": auction_id}



@api.post("/auctions/{auction_id}/buy-now")
@limiter.limit("10/minute")
async def buy_now(auction_id: str, request: Request, body: dict = None, user: dict = Depends(require_verified_email)):
    """Instant purchase via Stripe Checkout. Creates a Stripe payment
    session for the GROSS (incl. VAT) buy-now price and returns the
    redirect URL. The actual auction claim only happens in
    `/buy-now/finalize` AFTER the payment succeeds — this prevents
    auctions from being "reserved" by users who abandon the checkout.

    Atomic guarantee: `/buy-now/finalize` uses `find_one_and_update`
    to claim the auction exactly once; if two users pay simultaneously,
    the second gets auto-refunded.
    """
    a = await db.auctions.find_one({"id": auction_id}, {"_id": 0})
    if not a:
        raise HTTPException(status_code=404, detail="Търгът не е намерен")
    if _auction_status(a) != "live":
        raise HTTPException(status_code=400, detail="Само активни търгове поддържат 'Купи сега'.")
    if user["id"] == a.get("seller_id"):
        raise HTTPException(status_code=400, detail="Не можете да закупите собствения си автомобил.")
    bn_net = a.get("buy_now_eur")
    if not bn_net or float(bn_net) <= 0:
        raise HTTPException(status_code=400, detail="Тази обява няма зададена цена 'Купи сега'.")
    bn_net = float(bn_net)
    if float(a.get("current_bid_eur") or 0) > bn_net:
        raise HTTPException(status_code=409, detail="Текущата оферта вече надвишава цената 'Купи сега'.")

    bn_gross = _gross_amount(bn_net, a)
    # Stripe charges only the platform's buyer-premium fee (% configured
    # in admin → Settings → buyer_fee_pct, with min/max bounds). The
    # remainder of the car price is settled off-platform between buyer
    # and seller — same model as auction wins. Charging the full price
    # would lock €40k+ on the buyer's card before they even talk to the
    # seller, which is not the product's intent.
    fee_eur = round(_buyer_fee(bn_gross), 2)
    amount_cents = int(round(fee_eur * 100))

    import stripe
    api_key = os.environ.get("STRIPE_API_KEY", "")
    if not api_key:
        raise HTTPException(status_code=503, detail="Stripe не е конфигуриран.")
    stripe.api_key = api_key

    # Preserve the original domain the user came from (.bg vs .com) — the
    # frontend passes `window.location.origin` in the request body, and
    # the Stripe success_url echoes it back so we return to the right
    # place. Falls through Origin → Referer → FRONTEND_URL → base_url so
    # .bg users return to .bg (cookies aren't shared across public-suffix
    # siblings, so the wrong host would log them out after checkout).
    from routers.stripe_holds import resolve_stripe_redirect_origin
    origin = resolve_stripe_redirect_origin(
        (body or {}).get("origin") if isinstance(body, dict) else None,
        request,
    )

    success_url = f"{origin}/auctions/{auction_id}?buy_now_session={{CHECKOUT_SESSION_ID}}"
    cancel_url = f"{origin}/auctions/{auction_id}?buy_now_cancelled=1"

    try:
        session = stripe.checkout.Session.create(
            mode="payment",
            line_items=[{
                "price_data": {
                    "currency": "eur",
                    "product_data": {
                        "name": f"Купи сега — комисионна: {a.get('title','')[:80]}",
                        "description": (
                            f"Платформена комисионна за незабавна покупка на цена "
                            f"€{int(round(bn_gross)):,}".replace(",", " ")
                            + (" (вкл. ДДС)" if a.get("vat_status") == "vat_inclusive" else "")
                        ),
                    },
                    "unit_amount": amount_cents,
                },
                "quantity": 1,
            }],
            # Immediate capture — buy-now is a decisive action, no hold
            # semantics. If atomic claim fails in /finalize, we refund.
            payment_intent_data={
                "capture_method": "automatic",
                "metadata": {
                    "user_id": user["id"],
                    "auction_id": auction_id,
                    "intent": "buy_now",
                    "amount_gross_eur": str(round(bn_gross, 2)),
                    "amount_net_eur": str(round(bn_net, 2)),
                    "platform_fee_eur": str(round(fee_eur, 2)),
                },
            },
            metadata={
                "user_id": user["id"],
                "auction_id": auction_id,
                "intent": "buy_now",
            },
            customer_email=user.get("email"),
            success_url=success_url,
            cancel_url=cancel_url,
        )
    except stripe.error.StripeError as e:
        logger.exception("buy-now stripe.checkout.create failed")
        raise HTTPException(status_code=502, detail=f"Stripe error: {getattr(e, 'user_message', str(e))}")

    # Log the intent so admins can audit abandoned sessions
    await db.buy_now_intents.insert_one({
        "session_id": session["id"],
        "user_id": user["id"],
        "auction_id": auction_id,
        "amount_gross_eur": bn_gross,
        "amount_net_eur": bn_net,
        "platform_fee_eur": fee_eur,
        "status": "pending",
        "created_at": datetime.now(timezone.utc).isoformat(),
    })
    return {
        "redirect": True,
        "id": session["id"],
        "url": session["url"],
        "amount_gross_eur": bn_gross,
        "amount_net_eur": bn_net,
        "platform_fee_eur": fee_eur,
    }


@api.post("/auctions/{auction_id}/buy-now/finalize")
async def buy_now_finalize(auction_id: str, body: dict, user: dict = Depends(require_verified_email)):
    """Claim the auction after a successful buy-now Stripe Checkout.
    Body: `{session_id: "cs_test_..."}`. Idempotent — safe to call
    twice (e.g. if the user refreshes after the redirect). Second
    simultaneous buyer gets an auto-refund.
    """
    session_id = (body or {}).get("session_id") or ""
    if not session_id:
        raise HTTPException(status_code=400, detail="session_id липсва")

    import stripe
    api_key = os.environ.get("STRIPE_API_KEY", "")
    if not api_key:
        raise HTTPException(status_code=503, detail="Stripe не е конфигуриран.")
    stripe.api_key = api_key

    try:
        session = stripe.checkout.Session.retrieve(session_id)
    except stripe.error.StripeError as e:
        raise HTTPException(status_code=502, detail=f"Stripe retrieve: {e}")

    meta = getattr(session, "metadata", None) or {}
    if _stripe_meta_get(meta, "user_id") != user["id"]:
        raise HTTPException(status_code=403, detail="Сесията не принадлежи на този потребител.")
    if _stripe_meta_get(meta, "auction_id") != auction_id:
        raise HTTPException(status_code=400, detail="Сесията не е за тази обява.")
    if getattr(session, "payment_status", None) != "paid":
        raise HTTPException(status_code=402, detail="Плащането все още не е потвърдено от Stripe.")

    a = await db.auctions.find_one({"id": auction_id}, {"_id": 0})
    if not a:
        raise HTTPException(status_code=404, detail="Търгът не е намерен")

    # If already sold via this same session (idempotent replay) just
    # return success. If sold via a different session/user, refund.
    intent_doc = await db.buy_now_intents.find_one({"session_id": session_id}, {"_id": 0})
    if intent_doc and intent_doc.get("status") == "finalized":
        return {"ok": True, "already_finalized": True, "auction_id": auction_id}

    bn_net = float(a.get("buy_now_eur") or 0)
    now = datetime.now(timezone.utc)
    now_iso = now.isoformat()

    # Atomic claim — same safety as before, minus the bid_count increment
    # (buy-now is not a bid, per user request).
    claim = await db.auctions.find_one_and_update(
        {
            "id": auction_id,
            "status": {"$in": ["live", "scheduled"]},
            "is_archived": {"$ne": True},
            "current_bid_eur": {"$lte": bn_net},
        },
        {
            "$set": {
                "status": "sold",
                "current_bid_eur": bn_net,
                "high_bidder_id": user["id"],
                "high_bidder_name": user["name"],
                "ends_at": now_iso,
                "sold_at": now_iso,
                # `finalized_at` makes the auction show up in 30-day GMV
                # metrics and in the buyer's profile Purchases tab. The
                # previous (direct) buy-now path forgot this field, which
                # is part of the reason profile stats weren't updating.
                "finalized_at": now_iso,
                "sold_via_buy_now": True,
                "buy_now_session_id": session_id,
            },
        },
        return_document=ReturnDocument.AFTER,
    )

    if not claim:
        # Someone else won the race → refund this user's payment and
        # return a specific error so the UI can explain.
        pi_id = getattr(session, "payment_intent", None)
        if pi_id:
            try:
                stripe.Refund.create(payment_intent=pi_id, reason="duplicate")
            except Exception as e:
                logger.error("buy-now refund failed for session=%s: %s", session_id, e)
        await db.buy_now_intents.update_one(
            {"session_id": session_id},
            {"$set": {"status": "refunded_lost_race", "updated_at": now_iso}},
        )
        raise HTTPException(status_code=409, detail="Търгът вече е продаден. Плащането ви е възстановено.")

    await db.buy_now_intents.update_one(
        {"session_id": session_id},
        {"$set": {"status": "finalized", "finalized_at": now_iso}},
    )

    await hub.broadcast(auction_id, {
        "type": "buy_now",
        "auction_id": auction_id,
        "buyer_name": user["name"],
        "amount_eur": bn_net,
        "ends_at": now_iso,
    })

    seller_id = a.get("seller_id")
    if seller_id and seller_id != "platform":
        try:
            seller = await db.users.find_one({"id": seller_id}, {"_id": 0, "email": 1, "name": 1, "lang": 1})
            if seller and seller.get("email"):
                await email_seller_new_bid(
                    seller["email"], seller.get("name", ""), a["title"], auction_id,
                    user["name"], bn_net, int(a.get("bid_count") or 0),
                    lang=seller.get("lang") or "bg",
                )
        except Exception as e:
            logger.warning("buy-now seller email failed: %s", e)

    # Admin push with gross+commission (see _admin_notif_vat_fields)
    try:
        from routers.inbox import notify_admins as _notify_admins
        vat = _admin_notif_vat_fields(bn_net, a)
        await _notify_admins(
            db,
            type="auction_buy_now",
            data={
                "title": a.get("title", ""),
                "amount": bn_net,
                "amount_gross": vat["gross"],
                "commission": vat["commission"],
                "buyer": user.get("name", ""),
            },
            auction_id=auction_id,
            push_template_id="admin_auction_buy_now",
            push_fmt={
                "title": (a.get("title") or "")[:80],
                "amount": vat["gross"],
                "vat_suffix": vat["vat_suffix"],
                "commission": vat["commission"],
            },
        )
    except Exception:
        pass
    return {"ok": True, "auction_id": auction_id, "amount_eur": bn_net}


@api.get("/auctions/{auction_id}/next-bid")
async def next_bid_info(auction_id: str):
    """Returns the minimum next valid bid amount and the estimated buyer fee for it."""
    a = await db.auctions.find_one({"id": auction_id}, {"_id": 0, "current_bid_eur": 1, "ends_at": 1, "status": 1, "vat_status": 1, "vat_rate_pct": 1})
    if not a:
        raise HTTPException(status_code=404, detail="Търгът не е намерен")
    current = float(a.get("current_bid_eur", 0))
    info = _next_step_info(a, current)
    min_next = info["min_next_net"]
    return {
        "current_bid_eur": current,
        "step_eur": info["step_net"],
        "min_next_eur": min_next,
        "buyer_fee_eur": _buyer_fee_on_auction(min_next, a),
        "vat_status": a.get("vat_status"),
        "vat_rate_pct": a.get("vat_rate_pct"),
        "min_next_eur_gross": info["min_next_gross"],
        "step_eur_gross": info["step_gross"],
    }





# ---- Comments ----
DELETED_COMMENT_TEXT = "Коментарът е премахнат поради неконструктивно съдържание."


def _public_comment(c: dict, auction: dict, viewer_id: Optional[str] = None) -> dict:
    """Mark owner badge + replace text on deleted comments.

    Adds the vote-score fields so the frontend can render Reddit-style
    up/down arrows without another round-trip. We don't leak the raw
    upvotes/downvotes user_id lists — the viewer_vote flag is enough.
    """
    d = {k: v for k, v in c.items() if k != "_id"}
    d["is_owner"] = bool(auction.get("seller_id") and d.get("user_id") == auction.get("seller_id"))
    if d.get("deleted"):
        d["text"] = DELETED_COMMENT_TEXT
    up = d.pop("upvotes", None) or []
    down = d.pop("downvotes", None) or []
    d["upvote_count"] = len(up)
    d["downvote_count"] = len(down)
    d["score"] = len(up) - len(down)
    d["viewer_vote"] = (
        1 if viewer_id and viewer_id in up
        else -1 if viewer_id and viewer_id in down
        else 0
    )
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
async def list_comments(auction_id: str, request: Request):
    a = await db.auctions.find_one({"id": auction_id}, {"_id": 0, "seller_id": 1, "is_archived": 1, "status": 1})
    if not a:
        raise HTTPException(status_code=404, detail="Търгът не е намерен")
    if a.get("is_archived") or a.get("status") == "archived":
        viewer = await get_optional_user(request)
        if not (viewer and viewer.get("role") in ("admin", "moderator")):
            raise HTTPException(status_code=404, detail="Търгът не е намерен")
    items = await db.comments.find({"auction_id": auction_id}, {"_id": 0}).sort("created_at", -1).limit(200).to_list(200)
    viewer = await get_optional_user(request)
    viewer_id = viewer["id"] if viewer else None
    out = [_public_comment(c, a, viewer_id) for c in items]
    # Hydrate commenter profile_slug so links can be `/profile/<slug>`
    # without an extra round-trip per comment.
    await _hydrate_user_slug(out)
    return out



@api.post("/auctions/{auction_id}/comments")
async def add_comment(auction_id: str, payload: CommentCreate, user: dict = Depends(require_verified_email)):
    a = await db.auctions.find_one({"id": auction_id}, {"_id": 0})
    if not a:
        raise HTTPException(status_code=404, detail="Търгът не е намерен")

    # ---- Photo attachments — owner / admin only --------------------------
    # Sellers can answer buyer questions with photos (e.g. "here's a
    # close-up of the door scratch"). Everyone else gets a hard 403 if
    # they try to attach — we don't want random users dumping images.
    attached_urls: list[str] = []
    if payload.images:
        is_admin = user.get("role") in ("admin", "moderator")
        is_owner = a.get("seller_id") == user["id"]
        if not (is_admin or is_owner):
            raise HTTPException(
                status_code=403,
                detail="Само продавачът може да прикача снимки в коментар.",
            )
        if len(payload.images) > 6:
            raise HTTPException(status_code=400, detail="Максимум 6 снимки на коментар.")
        # Reuse the same image-processing pipeline as auction uploads —
        # resizes to max 1600px on long edge and re-encodes to JPEG at
        # quality 82, so a 6 MB phone shot lands as a ~250 KB data URL
        # in Mongo. For comments this is fine — they're sparse.
        from services.image_processing import optimize_data_url, ImageProcessingError
        for raw in payload.images:
            if not isinstance(raw, str) or not raw:
                continue
            try:
                web_url, _thumb = optimize_data_url(raw)
            except ImageProcessingError as e:
                raise HTTPException(status_code=400, detail=str(e))
            if web_url:
                attached_urls.append(web_url)

    doc = {
        "id": str(uuid.uuid4()),
        "auction_id": auction_id,
        "user_id": user["id"],
        "user_name": user["name"],
        "user_slug": user.get("profile_slug"),
        "user_avatar_url": user.get("avatar_url"),
        "text": payload.text.strip(),
        "images": attached_urls,
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
                await email_seller_new_comment(seller["email"], seller.get("name", ""), a["title"], auction_id, user["name"], snippet, lang=seller.get("lang") or "bg")
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
        # Direct-HTML варианти (имат приоритет над Markdown при render)
        "faq_html_bg": s.get("faq_html_bg") or "",
        "faq_html_ro": s.get("faq_html_ro") or "",
        "faq_html_en": s.get("faq_html_en") or "",
        "terms_html_bg": s.get("terms_html_bg") or "",
        "terms_html_ro": s.get("terms_html_ro") or "",
        "terms_html_en": s.get("terms_html_en") or "",
        "contacts_html_bg": s.get("contacts_html_bg") or "",
        "contacts_html_ro": s.get("contacts_html_ro") or "",
        "contacts_html_en": s.get("contacts_html_en") or "",
        "fees_html_bg": s.get("fees_html_bg") or "",
        "fees_html_ro": s.get("fees_html_ro") or "",
        "fees_html_en": s.get("fees_html_en") or "",
        "how_it_works_html_bg": s.get("how_it_works_html_bg") or "",
        "how_it_works_html_ro": s.get("how_it_works_html_ro") or "",
        "how_it_works_html_en": s.get("how_it_works_html_en") or "",
        "og_image_url": s.get("og_image_url") or "",
        "favicon_url": s.get("favicon_url") or "",
        "maintenance_mode": bool(s.get("maintenance_mode")),
        "maintenance_message": s.get("maintenance_message") or "",
        "deindex_mode": bool(s.get("deindex_mode")),
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
    # Per Stripe security guide, we reject events older than the tolerance
    # window (default 5 min) to make replay attacks against captured webhook
    # bodies materially harder — even if an attacker re-broadcasts a valid
    # signed envelope, the server clock check rejects it.
    WEBHOOK_TOLERANCE_SEC = 300
    try:
        import hmac, hashlib, time as _time
        parts = dict(p.split("=", 1) for p in sig_header.split(",") if "=" in p)
        t = parts.get("t", ""); v1 = parts.get("v1", "")
        # Timestamp tolerance check — protects against replay of old envelopes.
        try:
            ts_int = int(t)
        except (TypeError, ValueError):
            raise HTTPException(status_code=400, detail="Invalid signature timestamp")
        now_s = int(_time.time())
        skew = abs(now_s - ts_int)
        if skew > WEBHOOK_TOLERANCE_SEC:
            logger.warning("[stripe_webhook] timestamp outside tolerance (skew=%ds)", skew)
            raise HTTPException(status_code=400, detail="Webhook timestamp outside tolerance")
        signed_payload = f"{t}.{body.decode('utf-8')}".encode("utf-8")
        expected = hmac.new(cfg["webhook_secret"].encode("utf-8"), signed_payload, hashlib.sha256).hexdigest()
        if not hmac.compare_digest(expected, v1):
            raise HTTPException(status_code=400, detail="Invalid signature")
    except HTTPException:
        raise
    except Exception as e:
        logger.error("[stripe_webhook] sig verify failed: %s", e)
        raise HTTPException(status_code=400, detail="Invalid signature format")

    # Persist event for audit / replay — guarded by a unique index on `id`
    # so duplicate events (Stripe retries, replay attempts within tolerance)
    # collapse to a single row instead of producing N side-effects.
    try:
        import json as _json
        from pymongo.errors import DuplicateKeyError
        payload = _json.loads(body.decode("utf-8"))
        event_id = payload.get("id")
        try:
            await db.stripe_events.insert_one({
                "id": event_id,
                "type": payload.get("type"),
                "mode": cfg.get("mode"),
                "received_at": datetime.now(timezone.utc).isoformat(),
                "data": payload.get("data", {}),
            })
        except DuplicateKeyError:
            # Idempotency win — same Stripe event delivered twice. Acknowledge
            # 200 so Stripe stops retrying, but skip side-effect processing.
            logger.info("[stripe_webhook] duplicate event %s ignored", event_id)
            return {"ok": True, "duplicate": True}
    except HTTPException:
        raise
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
            await email_approved(seller["email"], seller.get("name", ""), a["title"], auction_id, lang=seller.get("lang") or "bg")
        except Exception as e:
            logger.error("email_approved failed: %s", e)
    # In-app + push notification to seller (user can opt-out via notification_prefs.push.listing_approved)
    try:
        if a.get("seller_id") and a["seller_id"] != "platform":
            from routers.inbox import notify_user as _notify_user
            await _notify_user(
                db, user_id=a["seller_id"],
                type="listing_approved",
                data={"title": a.get("title", "")},
                auction_id=auction_id,
                push_template_id="listing_approved",
                push_fmt={"title": (a.get("title") or "")[:80]},
                push_kind="listing_approved",
            )
    except Exception as e:
        logger.warning("notify listing_approved failed: %s", e)
    # Notify users with matching saved searches
    try:
        fresh = await db.auctions.find_one({"id": auction_id}, {"_id": 0})
        if fresh:
            await notify_matching_saved_searches(fresh)
    except Exception as e:
        logger.error("saved search notification failed: %s", e)
    # Notify users who follow the seller — separate from saved-search
    # fan-out so one outage doesn't starve the other.
    try:
        fresh_for_follow = await db.auctions.find_one({"id": auction_id}, {"_id": 0})
        if fresh_for_follow:
            await _notify_followers_new_listing(fresh_for_follow)
    except Exception as e:
        logger.error("follower notification failed: %s", e)
    # Eagerly translate title + SEO description into RO and EN so the
    # very first social share / SERP impression renders with locale-
    # correct copy. Failures are logged but never block approval — the
    # share handler falls back to the BG canonical text if a translation
    # is missing.
    try:
        fresh_for_seo = await db.auctions.find_one({"id": auction_id}, {"_id": 0})
        if fresh_for_seo:
            await _ensure_seo_translations(auction_id, fresh_for_seo)
    except Exception as e:
        logger.warning("SEO i18n translation at approve failed: %s", e)
    # Eager OG image generation — fire before any social crawler can
    # possibly scrape the URL. If the asynchronous generator fails
    # (cover fetch timeout, Pillow decode error, disk full) we retry
    # once in the background; the share route falls back to the static
    # `/og-default.jpg` until the retry succeeds.
    try:
        fresh_for_og = await db.auctions.find_one({"id": auction_id}, {"_id": 0})
        if fresh_for_og:
            from services.og_image import build_and_persist
            og_url = await build_and_persist(fresh_for_og)
            await db.auctions.update_one(
                {"id": auction_id},
                {"$set": {"og_image_url": og_url, "og_image_updated_at": now.isoformat()}},
            )
    except Exception as e:
        logger.warning("og:publish: eager build failed for %s: %s — scheduling retry", auction_id, e)
        asyncio.create_task(_retry_og_image(auction_id, delay_sec=30))
    return {"ok": True}


async def _retry_og_image(auction_id: str, delay_sec: int = 30) -> None:
    """Background retry for OG image generation. Runs once after a delay.

    We intentionally don't loop — the admin panel exposes a manual
    "Regenerate social image" button for the pathological cases where
    both the initial generation and the retry fail (rare; usually means
    the upstream photo CDN is down).
    """
    await asyncio.sleep(delay_sec)
    try:
        a = await db.auctions.find_one({"id": auction_id}, {"_id": 0})
        if not a:
            return
        from services.og_image import build_and_persist
        og_url = await build_and_persist(a)
        await db.auctions.update_one(
            {"id": auction_id},
            {"$set": {
                "og_image_url": og_url,
                "og_image_updated_at": datetime.now(timezone.utc).isoformat(),
            }},
        )
        logger.info("og:retry succeeded for %s → %s", auction_id, og_url)
    except Exception as e:
        logger.warning("og:retry still failing for %s: %s", auction_id, e)


@api.post("/admin/auctions/{auction_id}/regenerate-og-image")
async def admin_regenerate_og(auction_id: str, _admin: dict = Depends(require_admin)):
    """Manually rebuild an auction's OG image — used from the admin
    panel when the eager generation at publish time failed or when the
    editorial team changes the cover photo. Returns the new URL so the
    UI can swap its preview immediately."""
    a = await db.auctions.find_one({"id": auction_id}, {"_id": 0})
    if not a:
        raise HTTPException(status_code=404, detail="Обявата не е намерена")
    from services.og_image import build_and_persist
    og_url = await build_and_persist(a)
    now_iso = datetime.now(timezone.utc).isoformat()
    await db.auctions.update_one(
        {"id": auction_id},
        {"$set": {"og_image_url": og_url, "og_image_updated_at": now_iso}},
    )
    return {"ok": True, "og_image_url": og_url}


# ---- Admin counters (tab badges) ----
@api.get("/admin/image-queue")
async def admin_image_queue(_admin: dict = Depends(require_admin_or_moderator)):
    """Live + persistent stats for the image optimization queue.

    Combines:
      * `stats()`     — in-process queue depth & worker concurrency
      * `db_stats()`  — count of images in each status across the DB
      * `failed_items()` — first ~50 auctions with at least one failed
        image, so the admin can click "Retry" without scrolling through
        the whole catalog.
    """
    from services import image_optimization_queue as ioq
    return {
        "queue": ioq.stats(),
        "db": await ioq.db_stats(),
        "failed": await ioq.failed_items(limit=50),
    }


class _RetryImagePayload(BaseModel):
    sha: str
    auction_id: str


@api.post("/admin/image-queue/retry")
async def admin_image_queue_retry(
    payload: _RetryImagePayload,
    _admin: dict = Depends(require_admin),
):
    """Re-enqueue a failed image. Locates the original on disk by sha
    + auction_id and submits a fresh job from attempt 1.
    """
    from services import image_optimization_queue as ioq

    upload_root = os.environ.get("UPLOAD_DIR", "/opt/autobids/uploads")
    sub = payload.sha[:2]
    d = os.path.join(upload_root, "auctions", sub)
    src = None
    if os.path.isdir(d):
        for name in os.listdir(d):
            if name.startswith(payload.sha + "."):
                src = os.path.join(d, name)
                break
    if not src:
        raise HTTPException(
            status_code=404,
            detail="Оригиналното изображение не е намерено на диска.",
        )
    ok = await ioq.retry_failed(
        sha=payload.sha, src_path=src, auction_id=payload.auction_id,
    )
    return {"ok": ok}


@api.post("/admin/image-queue/backfill")
async def admin_image_queue_backfill(_admin: dict = Depends(require_admin)):
    """Reverse-engineer the `image_optimization` field for every auction.

    Useful after a deploy that introduces the queue logic onto a DB
    that doesn't yet have status tracking for older listings. Idempotent
    — running it twice is safe (the second run will report 0 new work).
    """
    from services import image_optimization_queue as ioq
    return await ioq.backfill_all()


@api.get("/admin/storage-health")
async def admin_storage_health(_admin: dict = Depends(require_admin)):
    """Live diagnostic for the image storage backend.

    Returns the configured backend, root path, on-disk ownership, mode,
    and the result of a write probe. Operators can hit this from a
    browser (admin auth required) without SSH access to the production
    box — invaluable when chasing 'submit returns 500' incidents.
    """
    import os
    import stat as stat_module
    from storage import _get_backend

    info: dict = {}
    try:
        backend = _get_backend()
        info["backend"] = getattr(backend, "name", "?")
        root = getattr(backend, "root", None)
        info["root"] = root
        info["upload_dir_env"] = os.environ.get("UPLOAD_DIR", "(unset)")
        info["storage_backend_env"] = os.environ.get("STORAGE_BACKEND", "(unset)")
        info["service_user_uid"] = os.geteuid()
        info["service_user_gid"] = os.getegid()
        try:
            import pwd, grp  # noqa: E401  (stdlib, unix-only)
            info["service_user"] = pwd.getpwuid(os.geteuid()).pw_name
            info["service_group"] = grp.getgrgid(os.getegid()).gr_name
        except Exception:
            pass

        if root and os.path.exists(root):
            st = os.stat(root)
            try:
                import pwd, grp  # noqa: E401
                info["dir_owner"] = pwd.getpwuid(st.st_uid).pw_name
                info["dir_group"] = grp.getgrgid(st.st_gid).gr_name
            except Exception:
                info["dir_owner_uid"] = st.st_uid
                info["dir_group_gid"] = st.st_gid
            info["dir_mode"] = oct(st.st_mode & 0o777)
            info["dir_writable_for_process"] = os.access(root, os.W_OK)
            try:
                info["children_count"] = len(os.listdir(root))
            except Exception:
                info["children_count"] = "(unreadable)"
        else:
            info["dir_exists"] = False

        # Actual write probe — uses the real backend.store() path so we
        # exercise the same code that fails during submit.
        test_data = (
            "data:image/png;base64,"
            "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNkAAEAAAcAAc+8aFQAAAAASUVORK5CYII="
        )
        try:
            ref = backend.store(test_data)
            info["write_probe"] = "OK"
            info["write_probe_ref"] = ref
        except Exception as e:  # noqa: BLE001 — surface the exact error
            info["write_probe"] = "FAILED"
            info["write_probe_error"] = str(e)
    except Exception as e:  # noqa: BLE001
        info["fatal_error"] = str(e)
    return info


@api.get("/admin/cdn-health")
async def admin_cdn_health(_admin: dict = Depends(require_admin)):
    """Live diagnostic for the public image CDN (`img.autoandbid.bg`).

    The CDN failure mode that has burned us in production is:

        1.  Browser requests https://img.autoandbid.bg/uploads/foo.jpg
        2.  Cloudflare 301-redirects to https://autoandbid.bg/uploads/foo.jpg
        3.  Main vhost serves index.html (`text/html`) — not a real image
        4.  Chrome's Opaque Response Blocking (ORB) blocks the `<img>` load
        5.  All listing photos appear broken until cache TTL expires

    This endpoint helps operators isolate WHERE the 301 originates:

        * `cf_path`        — request through Cloudflare (whatever DNS resolves to)
        * `origin_path`    — request DIRECTLY to the origin server, bypassing CF,
                             by overriding the DNS resolution with the origin IP.

    If `cf_path.status` is 301 but `origin_path.status` is 200 (or 404 with
    image content-type) — the redirect is INJECTED by Cloudflare (Page Rule,
    Bulk Redirect, or Worker). Fix in the Cloudflare dashboard.

    If both return 301 — the origin nginx is misconfigured (re-run the
    Ansible deploy or inspect /etc/nginx/sites-enabled).

    Query params:
        path            — URL path under the CDN to probe (default
                          `/uploads/__probe__.jpg`; 404 is expected and OK)
        origin_ip       — IP to use for the origin probe. Defaults to the
                          `CDN_ORIGIN_IP` env var. Required for the
                          origin probe; the CF probe still runs without it.
    """
    import httpx
    from urllib.parse import urlparse

    cdn_base = (
        os.environ.get("CDN_BASE_URL")
        or os.environ.get("IMAGE_BASE_URL")
        or "https://img.autoandbid.bg"
    ).rstrip("/")
    # Normalise — public_uploads_base() appends /uploads to bare hosts;
    # we want just the host for the probe.
    parsed = urlparse(cdn_base if "://" in cdn_base else f"https://{cdn_base}")
    cdn_host = parsed.netloc or parsed.path
    probe_path = "/uploads/__probe__.jpg"
    full_url = f"https://{cdn_host}{probe_path}"

    origin_ip = os.environ.get("CDN_ORIGIN_IP", "").strip()

    def _summarise(resp: httpx.Response | None, error: Optional[str]) -> dict:
        if resp is None:
            return {"ok": False, "error": error or "no response"}
        loc = resp.headers.get("location") or ""
        ct = (resp.headers.get("content-type") or "").strip()
        # Detect the WRONG redirect: 30x to a different host. The 301
        # http→https redirect on the same host is fine.
        wrong_redirect = False
        if 300 <= resp.status_code < 400 and loc:
            try:
                tgt = urlparse(loc).netloc.lower()
                if tgt and tgt != cdn_host.lower() and not tgt.endswith(f".{cdn_host.lower()}"):
                    wrong_redirect = True
            except Exception:
                pass
        return {
            "ok": (resp.status_code in (200, 404, 416)) and not wrong_redirect,
            "status": resp.status_code,
            "location": loc or None,
            "content_type": ct or None,
            "server": resp.headers.get("server"),
            "cf_ray": resp.headers.get("cf-ray"),
            "wrong_redirect": wrong_redirect,
        }

    out: dict = {
        "cdn_host": cdn_host,
        "cdn_base_env": os.environ.get("CDN_BASE_URL") or os.environ.get("IMAGE_BASE_URL") or "(unset)",
        "origin_ip_env": origin_ip or "(unset)",
        "probe_url": full_url,
    }

    # --- Probe 1: Cloudflare path (normal DNS) ----------------------------
    cf_err: Optional[str] = None
    cf_resp: Optional[httpx.Response] = None
    try:
        async with httpx.AsyncClient(follow_redirects=False, timeout=8.0) as c:
            cf_resp = await c.get(full_url, headers={"User-Agent": "AutoAndBid-CDN-Probe/1"})
    except Exception as e:  # noqa: BLE001
        cf_err = f"{type(e).__name__}: {e}"
    out["cf_path"] = _summarise(cf_resp, cf_err)

    # --- Probe 2: Direct origin (bypass Cloudflare) -----------------------
    if origin_ip:
        origin_err: Optional[str] = None
        origin_resp: Optional[httpx.Response] = None
        try:
            # Pin the connection to the origin IP while keeping SNI + Host
            # set to the public CDN hostname. httpx uses urllib3's resolver
            # via the underlying socket; the cleanest way to override DNS
            # in httpx is `httpx.HTTPTransport` + a custom resolver, but
            # for a one-shot probe we just call the IP directly with the
            # Host header set — this matches what `curl --resolve` does.
            target_url = f"https://{origin_ip}{probe_path}"
            async with httpx.AsyncClient(
                follow_redirects=False,
                timeout=8.0,
                verify=False,  # origin uses CF Origin Cert; verification fails when host=IP
            ) as c:
                origin_resp = await c.get(
                    target_url,
                    headers={"Host": cdn_host, "User-Agent": "AutoAndBid-CDN-Probe/1"},
                )
        except Exception as e:  # noqa: BLE001
            origin_err = f"{type(e).__name__}: {e}"
        out["origin_path"] = _summarise(origin_resp, origin_err)

        # --- Diagnose -----------------------------------------------------
        cf_ok = out["cf_path"]["ok"]
        origin_ok = out["origin_path"]["ok"]
        cf_redirect = out["cf_path"].get("wrong_redirect")
        if cf_ok and origin_ok:
            out["diagnosis"] = "OK — both Cloudflare and origin behave correctly."
        elif cf_redirect and origin_ok:
            out["diagnosis"] = (
                "Cloudflare injects a wrong-domain 301 (origin is fine). "
                "Inspect Page Rules / Bulk Redirects / Workers in the CF "
                "dashboard for any rule matching this hostname."
            )
        elif not origin_ok:
            out["diagnosis"] = (
                "Origin returns a bad response — re-run "
                "`ansible-playbook playbooks/deploy_frontend.yml` and inspect "
                "/etc/nginx/sites-enabled/autoandbid on ab-front1."
            )
        else:
            out["diagnosis"] = "Mixed signals — inspect cf_path and origin_path raw fields."
    else:
        out["origin_path"] = {"ok": False, "error": "Set CDN_ORIGIN_IP env var to enable origin probe."}
        out["diagnosis"] = "Origin probe skipped — set CDN_ORIGIN_IP to compare CF vs origin."

    return out


async def admin_counters(_admin: dict = Depends(require_admin_or_moderator)):
    """Single-shot aggregate counts for every admin panel tab — used by
    the sidebar to show badge numbers without firing one request per tab.

    Individual counts are intentionally bounded (limit-based queries) to
    keep the dashboard snappy even on 100k+ auction datasets.
    """
    # Fire all counts in parallel (asyncio.gather) — ~1 round-trip total.
    pending_q = db.auctions.count_documents({"status": "pending", "is_archived": {"$ne": True}})
    users_q = db.users.count_documents({})
    requests_q = db.seller_requests.count_documents({"status": "pending"})
    sold_q = db.auctions.count_documents({"status": "sold", "is_archived": {"$ne": True}})
    unsold_q = db.auctions.count_documents({
        "status": {"$in": ["ended", "reserve_not_met", "cancelled", "withdrawn"]},
        "is_archived": {"$ne": True},
    })
    archived_q = db.auctions.count_documents({"$or": [{"is_archived": True}, {"status": "archived"}]})
    all_listings_q = db.auctions.count_documents({"is_archived": {"$ne": True}})
    # Chat: number of threads with unread admin-bound messages.
    chat_pipeline = [
        {"$match": {"sender_role": "user", "read_by_admin": False}},
        {"$group": {"_id": "$thread_user_id"}},
        {"$count": "n"},
    ]
    chat_unread_agg = db.chat_messages.aggregate(chat_pipeline)
    # Notifications: unsent / failed email rows in the last 7 days — signal
    # that admin probably wants to investigate.
    week_ago = (datetime.now(timezone.utc) - timedelta(days=7)).isoformat()
    notif_q = db.notification_log.count_documents({
        "channel": "email",
        "status": {"$in": ["error", "mock"]},
        "at": {"$gte": week_ago},
    })

    pending_n, users_n, requests_n, sold_n, unsold_n, archived_n, all_n, notif_n, chat_list = await asyncio.gather(
        pending_q, users_q, requests_q, sold_q, unsold_q, archived_q, all_listings_q, notif_q,
        chat_unread_agg.to_list(1),
    )
    chat_n = int(chat_list[0]["n"]) if chat_list else 0

    return {
        "pending": int(pending_n),
        "all": int(all_n),
        "requests": int(requests_n),
        "users": int(users_n),
        "sold": int(sold_n),
        "unsold": int(unsold_n),
        "archive": int(archived_n),
        "notifications": int(notif_n),
        "chat": int(chat_n),
    }


@api.post("/admin/auctions/{auction_id}/reject")
async def admin_reject(auction_id: str, payload: AdminDecision, _admin: dict = Depends(require_admin)):
    a = await db.auctions.find_one({"id": auction_id}, {"_id": 0})
    if not a:
        raise HTTPException(status_code=404, detail="Обявата не е намерена")
    # Reject + auto-archive: отказаните обяви отиват в архив, не в "Всички обяви".
    now_iso = datetime.now(timezone.utc).isoformat()
    await db.auctions.update_one(
        {"id": auction_id},
        {"$set": {
            "status": "rejected",
            "rejected_reason": payload.reason or "",
            "is_archived": True,
            "archived_at": now_iso,
        }},
    )
    seller = await db.users.find_one({"id": a.get("seller_id")}, {"_id": 0})
    if seller and seller.get("email"):
        try:
            await email_rejected(seller["email"], seller.get("name", ""), a["title"], payload.reason or "", lang=seller.get("lang") or "bg")
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
    await db.auctions.update_one(
        {"id": auction_id},
        {"$set": {"status": "sold", "premium_captured": False, "finalized_at": now_iso}},
    )
    winner_id = a.get("high_bidder_id")
    if winner_id:
        try:
            await notify_auction_finalized(db, a)
        except Exception as e:
            logger.error("notify_auction_finalized failed: %s", e)
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
        try:
            await notify_auction_finalized(db, a)
        except Exception as e:
            logger.error("notify_auction_finalized failed: %s", e)

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
# Watchlist routes (`/watch-status`, `/watch`, `/me/watchlist`) extracted
# to `routers/watchlist.py` on 2026-05-04. Mounted via `build_watchlist_router`
# at the end of this file alongside the other split routers.


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
        await email_vin_delivery(user["email"], user.get("name", ""), a["title"], auction_id, a["vin"].strip().upper(), lang=user.get("lang") or "bg")
    except Exception as e:
        logger.error("email_vin_delivery failed: %s", e)
    return {"ok": True, "message": f"Изпратихме пълния VIN на {user['email']}"}


# ---- One-click unsubscribe (from email footer; token-less) -------------------
@api.get("/unsubscribe")
async def email_unsubscribe(email: str = "", kind: str = ""):
    """Token-less unsubscribe link embedded in every transactional email.

    Behaviour:
      • Without `kind` → disable ALL email channels for the address (marketing
        + transactional notifications). Login / password-reset / verification
        emails are routed via separate flows and unaffected.
      • With `kind` → disable only that specific kind (e.g. `digest_3day`).

    We do not require a token because the worst-case outcome is a malicious
    third party silencing notifications for an email they control or guess;
    no PII is exposed and the user can re-enable from Account → Notifications.
    """
    from services import notif_prefs as _nprefs
    email_lc = (email or "").strip().lower()
    if "@" not in email_lc:
        return Response(
            content="<h2>Invalid request</h2><p>Missing or invalid email address.</p>",
            media_type="text/html",
            status_code=400,
        )
    user = await db.users.find_one({"email": email_lc}, {"_id": 0, "id": 1, "lang": 1})
    if not user:
        # Don't leak whether an address exists — return a generic confirmation.
        return Response(
            content=_unsub_html_response(email_lc, kind=kind, lang="bg"),
            media_type="text/html",
        )
    update: dict = {}
    kind_l = (kind or "").strip().lower()
    if kind_l and kind_l in _nprefs.NOTIF_KINDS:
        update[f"notification_prefs.email.{kind_l}"] = False
    else:
        for k in _nprefs.NOTIF_KINDS:
            update[f"notification_prefs.email.{k}"] = False
        update["email_unsubscribed_at"] = datetime.now(timezone.utc).isoformat()
    if update:
        await db.users.update_one({"id": user["id"]}, {"$set": update})
    return Response(
        content=_unsub_html_response(email_lc, kind=kind_l, lang=(user.get("lang") or "bg")),
        media_type="text/html",
    )


def _unsub_html_response(email: str, kind: str, lang: str) -> str:
    """Confirmation page shown after the user clicks the email Unsubscribe link."""
    from emails import APP_URL as _APP_URL
    lang_norm = (lang or "bg").lower()[:2]
    if lang_norm == "en":
        title = "You've been unsubscribed"
        msg = (
            f"We won't send any more notification emails to <strong>{email}</strong>."
            if not kind
            else f"You won't receive emails of type <strong>{kind}</strong> anymore."
        )
        prefs = "Manage all notification preferences"
    elif lang_norm == "ro":
        title = "Te-am dezabonat"
        msg = (
            f"Nu vom mai trimite emailuri de notificare la <strong>{email}</strong>."
            if not kind
            else f"Nu vei mai primi emailuri de tipul <strong>{kind}</strong>."
        )
        prefs = "Gestionează toate preferințele"
    else:
        title = "Отписани сте"
        msg = (
            f"Няма повече да изпращаме известия на <strong>{email}</strong>."
            if not kind
            else f"Повече няма да получавате имейли от тип <strong>{kind}</strong>."
        )
        prefs = "Управление на всички известия"
    return (
        f"<!doctype html><html><head><meta charset='utf-8'><title>{title}</title>"
        "<style>body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Inter,sans-serif;"
        "background:#f6f7f8;color:#111827;margin:0;padding:0;}"
        ".card{max-width:520px;margin:64px auto;background:#fff;border-radius:18px;"
        "padding:40px 36px;box-shadow:0 1px 2px rgba(0,0,0,.04);}"
        ".brand{font-size:22px;font-weight:700;color:#0b0f1a;margin-bottom:18px;}"
        ".brand .amp{color:#1B4D3E;font-weight:800;}"
        "h1{font-size:26px;margin:0 0 14px 0;color:#0b0f1a;}"
        "p{line-height:1.55;margin:0 0 14px 0;}"
        "a{color:#1B4D3E;text-decoration:underline;}"
        "</style></head><body><div class='card'>"
        "<div class='brand'>Auto<span class='amp'>&amp;</span>Bid</div>"
        f"<h1>{title}</h1><p>{msg}</p>"
        f"<p><a href='{_APP_URL}/account/notifications'>{prefs}</a></p>"
        "</div></body></html>"
    )


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
    # Granular notification toggles (push & email per kind). The client may
    # send a partial update (e.g. only one toggle) — we merge into the
    # existing prefs document by writing dotted-path keys.
    if getattr(payload, "notification_prefs", None) is not None:
        from services import notif_prefs as _nprefs
        clean = _nprefs.normalize_input(payload.notification_prefs or {})
        for ch, kinds in clean.items():
            for kind, val in kinds.items():
                update[f"notification_prefs.{ch}.{kind}"] = bool(val)
    if update:
        await db.users.update_one({"id": user["id"]}, {"$set": update})
    u = await db.users.find_one({"id": user["id"]}, {"_id": 0, "password_hash": 0, "totp_secret": 0, "totp_backup_codes": 0})
    return u


# ---- Profile avatar ----
class AvatarPayload(BaseModel):
    image: str  # data:image/...;base64,...


@api.post("/me/avatar")
async def upload_my_avatar(payload: AvatarPayload, user: dict = Depends(get_current_user)):
    """Accepts a base64 data URL, optimizes to a 256x256 square JPEG and
    persists via the configured storage backend (inline or S3)."""
    from services import image_processing as imgproc
    if not payload.image or not payload.image.startswith("data:image/"):
        raise HTTPException(status_code=400, detail="Невалиден формат на изображението")
    try:
        opt = await asyncio.to_thread(imgproc.optimize_avatar_data_url, payload.image)
    except imgproc.ImageProcessingError as e:
        raise HTTPException(status_code=400, detail=str(e))
    from storage import store_image
    url = await asyncio.to_thread(store_image, opt)
    await db.users.update_one({"id": user["id"]}, {"$set": {"avatar_url": url}})
    # Backfill avatar on this user's auctions and comments so existing rows
    # render the new picture without requiring a re-fetch of /me from each
    # detail page (frontend reads avatar_url straight from auction/comment).
    await db.auctions.update_many({"seller_id": user["id"]}, {"$set": {"seller_avatar_url": url}})
    await db.comments.update_many({"user_id": user["id"]}, {"$set": {"user_avatar_url": url}})
    return {"avatar_url": url}


@api.delete("/me/avatar")
async def delete_my_avatar(user: dict = Depends(get_current_user)):
    await db.users.update_one({"id": user["id"]}, {"$unset": {"avatar_url": ""}})
    await db.auctions.update_many({"seller_id": user["id"]}, {"$unset": {"seller_avatar_url": ""}})
    await db.comments.update_many({"user_id": user["id"]}, {"$unset": {"user_avatar_url": ""}})
    return {"ok": True}


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
            from services import notif_prefs as _nprefs
            if u and u.get("email") and _nprefs.is_enabled(u, "email", "saved_search"):
                try:
                    from emails import send_email, _shell, APP_URL
                    html = _shell("Нова обява по ваш критерий", f"""
                      <p>Здравейте, {u.get("name","")},</p>
                      <p>Нова обява отговаря на вашата търсачка <strong>{s['name']}</strong>:</p>
                      <p style="font-size:18px;margin:16px 0;"><strong>{auction['title']}</strong></p>
                      <p>{auction.get("year","")} г. · {auction.get("city","")} · начална цена €{int(auction.get("starting_bid_eur",0)):,}</p>
                      <p><a href="{APP_URL}/auctions/{auction['id']}" style="display:inline-block;background:#1B4D3E;color:#fff;padding:12px 22px;border-radius:999px;text-decoration:none;font-weight:600;">Виж обявата</a></p>
                    """, to=u["email"], lang=(u.get("lang") or "bg"))
                    await send_email(u["email"], f"Нова обява · {auction['title']}", html)
                except Exception as e:
                    logger.error("saved search email failed: %s", e)
            # Web Push — saved-search match (localized)
            if u and _nprefs.is_enabled(u, "push", "saved_search"):
                try:
                    from services import push_templates
                    await push_templates.send_template(
                        s["user_id"],
                        "saved_search_match",
                        fmt_args={
                            "name": s["name"],
                            "title": auction["title"],
                            "price": f"{int(auction.get('starting_bid_eur', 0)):,}",
                        },
                        url=f"/auctions/{auction['id']}",
                        tag=f"saved-{s['id']}",
                    )
                except Exception as e:
                    logger.error("push saved_search failed: %s", e)


# ---- User follows (reputation/leaderboard prerequisite) ----
# Collection shape: { follower_id, followee_id, created_at }.
# A unique compound index prevents duplicate rows; deletes are straight
# `delete_one` so unfollow is idempotent.

@api.post("/users/{user_id}/follow")
async def follow_user(user_id: str, user: dict = Depends(get_current_user)):
    if user_id == user["id"]:
        raise HTTPException(status_code=400, detail="Не можете да следвате собствения си профил.")
    target = await db.users.find_one({"id": user_id}, {"_id": 0, "id": 1, "name": 1, "email": 1})
    if not target:
        raise HTTPException(status_code=404, detail="Потребителят не е намерен")
    # Idempotent: upsert so double-clicking the button is harmless.
    await db.user_follows.update_one(
        {"follower_id": user["id"], "followee_id": user_id},
        {"$setOnInsert": {
            "follower_id": user["id"],
            "followee_id": user_id,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }},
        upsert=True,
    )
    count = await db.user_follows.count_documents({"followee_id": user_id})
    return {"ok": True, "followers_count": count}


@api.delete("/users/{user_id}/follow")
async def unfollow_user(user_id: str, user: dict = Depends(get_current_user)):
    await db.user_follows.delete_one({"follower_id": user["id"], "followee_id": user_id})
    count = await db.user_follows.count_documents({"followee_id": user_id})
    return {"ok": True, "followers_count": count}


@api.get("/users/{user_id}/follow-status")
async def follow_status(user_id: str, request: Request):
    """Returns followers_count + whether the current viewer is already
    following. Anonymous viewers get `following: false`. Kept cheap so
    it can be called on every profile/dealer render."""
    viewer = await get_optional_user(request)
    following = False
    if viewer and viewer["id"] != user_id:
        following = bool(await db.user_follows.find_one(
            {"follower_id": viewer["id"], "followee_id": user_id},
            {"_id": 1},
        ))
    count = await db.user_follows.count_documents({"followee_id": user_id})
    return {"following": following, "followers_count": count}


@api.get("/users/me/following")
async def list_my_following(user: dict = Depends(get_current_user)):
    rows = await db.user_follows.find(
        {"follower_id": user["id"]},
        {"_id": 0, "followee_id": 1, "created_at": 1},
    ).to_list(500)
    if not rows:
        return []
    ids = [r["followee_id"] for r in rows]
    users = await db.users.find(
        {"id": {"$in": ids}},
        {"_id": 0, "id": 1, "name": 1, "avatar_url": 1, "is_verified_dealer": 1, "dealer_slug": 1},
    ).to_list(500)
    return users


async def _notify_followers_new_listing(auction: dict) -> None:
    """Fan-out notification when a user they follow publishes a new
    listing. Runs after the auction is live so the link is reachable.

    Kept best-effort: email + push are each wrapped so a mail-server
    outage doesn't starve the push broadcast (or vice versa). There's
    no retry queue yet — follow-ups are a nice-to-have, not a
    money-critical path like bids.
    """
    seller_id = auction.get("seller_id")
    if not seller_id or seller_id == "platform":
        return
    follow_rows = await db.user_follows.find(
        {"followee_id": seller_id},
        {"_id": 0, "follower_id": 1},
    ).to_list(2000)
    if not follow_rows:
        return

    seller = await db.users.find_one({"id": seller_id}, {"_id": 0, "name": 1})
    seller_name = (seller or {}).get("name") or "A seller"
    auction_url = f"/auctions/{auction['id']}"

    for row in follow_rows:
        uid = row["follower_id"]
        u = await db.users.find_one(
            {"id": uid},
            {"_id": 0, "id": 1, "email": 1, "name": 1, "notification_prefs": 1},
        )
        if not u:
            continue
        # Email
        if u.get("email"):
            from services import notif_prefs as _nprefs
            if _nprefs.is_enabled(u, "email", "followed_listing"):
                try:
                    from emails import send_email, _shell, APP_URL
                    html = _shell(
                        f"{seller_name} публикува нова обява",
                        f"""
                        <p>Здравейте, {u.get('name', '')},</p>
                        <p><strong>{seller_name}</strong>, когото следвате, пусна нова обява:</p>
                        <p style="font-size:18px;margin:16px 0;">
                          <strong>{auction.get('title', '')}</strong>
                        </p>
                        <p>{auction.get('year', '')} г. · {auction.get('city', '')} · начална цена
                           €{int(auction.get('starting_bid_eur', 0)):,}</p>
                        <p><a href="{APP_URL}{auction_url}"
                              style="display:inline-block;background:#1B4D3E;color:#fff;padding:12px 22px;border-radius:999px;text-decoration:none;font-weight:600;">
                          Виж обявата
                        </a></p>
                        """,
                        to=u["email"], lang=(u.get("lang") or "bg"),
                    )
                    await send_email(u["email"], f"Нова обява от {seller_name}", html)
                except Exception as e:
                    logger.error("follow email failed: %s", e)
        # Web Push
        try:
            from services import notif_prefs as _nprefs
            if _nprefs.is_enabled(u, "push", "followed_listing"):
                from services import push_templates
                await push_templates.send_template(
                    uid,
                    "followed_listing",
                    fmt_args={
                        "seller_name": seller_name,
                        "title": auction.get("title", ""),
                    },
                    url=auction_url,
                    tag=f"follow-{seller_id}-{auction['id']}",
                )
        except Exception as e:
            logger.error("push follow failed: %s", e)


# ---- Comment votes (Reddit-style up/down) ----
class CommentVote(BaseModel):
    vote: int  # 1 | -1 | 0 (clear)


@api.post("/comments/{comment_id}/vote")
async def vote_comment(
    comment_id: str, payload: CommentVote, user: dict = Depends(get_current_user),
):
    if payload.vote not in (-1, 0, 1):
        raise HTTPException(status_code=400, detail="vote must be 1, -1 or 0")
    c = await db.comments.find_one({"id": comment_id}, {"_id": 0})
    if not c:
        raise HTTPException(status_code=404, detail="Comment not found")
    if c.get("deleted"):
        raise HTTPException(status_code=400, detail="Не можете да гласувате на изтрит коментар.")
    # Enforce one vote per user by pulling them off BOTH arrays first,
    # then pushing onto the correct one (if vote != 0). Net effect is
    # idempotent and matches Reddit's voting semantics.
    uid = user["id"]
    await db.comments.update_one(
        {"id": comment_id},
        {"$pull": {"upvotes": uid, "downvotes": uid}},
    )
    if payload.vote == 1:
        await db.comments.update_one({"id": comment_id}, {"$addToSet": {"upvotes": uid}})
    elif payload.vote == -1:
        await db.comments.update_one({"id": comment_id}, {"$addToSet": {"downvotes": uid}})
    fresh = await db.comments.find_one({"id": comment_id}, {"_id": 0, "upvotes": 1, "downvotes": 1})
    up = len(fresh.get("upvotes") or [])
    down = len(fresh.get("downvotes") or [])
    return {"ok": True, "score": up - down, "upvotes": up, "downvotes": down, "viewer_vote": payload.vote}


# ---- Leaderboard ----
# Extracted to `routers/leaderboard.py` on 2026-05-04. The aggregation
# pipelines, in-memory cache and `/api/leaderboard` route now live in
# that module; this stub remains so blame trails point readers to the
# new location.




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
                raise HTTPException(status_code=400, detail="Обявата може да се редактира само преди първото наддаване")

    update = {k: v for k, v in payload.model_dump(exclude_unset=True).items() if v is not None}
    # Non-admins cannot change status/featured/ends_at
    if not is_admin:
        for forbidden in ("status", "featured", "ends_at"):
            update.pop(forbidden, None)

    # If any image bucket is being updated, enforce the same size caps and
    # re-encode through the optimizer + thumbnail pipeline (mirror create flow).
    image_keys = ("images", "images_exterior", "images_wheels", "images_bumper", "images_interior")
    if any(k in update for k in image_keys):
        from services import image_processing as imgproc

        MAX_PER_IMG_RAW = imgproc.IMAGE_MAX_RAW_BYTES
        MAX_TOTAL_PAYLOAD_RAW = 120 * 1024 * 1024
        total_raw = 0
        for k in image_keys:
            for item in (update.get(k) or []):
                if not isinstance(item, str):
                    continue
                sz = imgproc.raw_bytes_of(item) if item.startswith("data:image/") else 0
                if sz > MAX_PER_IMG_RAW:
                    mb = round(sz / 1024 / 1024, 1)
                    raise HTTPException(status_code=413, detail=f"Една от снимките е твърде голяма ({mb} MB). Макс. 10 MB на снимка.")
                total_raw += sz
        if total_raw > MAX_TOTAL_PAYLOAD_RAW:
            mb = round(total_raw / 1024 / 1024, 1)
            raise HTTPException(status_code=413, detail=f"Общият размер на снимките е {mb} MB — надвишава лимита от 120 MB.")

        # Optimize each provided bucket independently — caller wants the
        # bucket structure preserved.
        thumb_buckets: dict[str, list[str]] = {}
        from storage import fetch_remote_images_as_data_urls, store_images
        for k in image_keys:
            urls = update.get(k)
            if not urls:
                continue
            # Pre-fetch external URLs so they're rehosted under our CDN
            # before being persisted (see create_auction for rationale).
            # `strict=True` drops 404/timeout entries so they never leak
            # into DB as external URLs.
            fetched = await fetch_remote_images_as_data_urls(urls, strict=True)
            urls = [u for u in fetched if u]
            if not urls:
                raise HTTPException(status_code=400, detail=f"Нито една снимка в '{k}' не можа да бъде свалена")
            update[k] = urls
            web, thumb, errs = await asyncio.to_thread(imgproc.optimize_many, urls)
            if errs:
                msg = "; ".join(errs[:3])
                raise HTTPException(status_code=400, detail=f"Грешка при обработката на снимки: {msg}")
            web = await asyncio.to_thread(store_images, web)
            thumb = await asyncio.to_thread(store_images, thumb)
            update[k] = web
            thumb_buckets[k] = thumb
        # When the consolidated `images` list was rebuilt, also refresh
        # the `thumbnails` array stored on the doc.
        if "images" in update:
            update["thumbnails"] = thumb_buckets["images"]

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
async def admin_list_all(
    q: Optional[str] = None,
    status: Optional[str] = None,
    include_archived: int = 0,
    limit: int = 25,
    offset: int = 0,
    paginated: int = 0,
    _admin: dict = Depends(require_admin_or_moderator),
):
    """List auctions for admin panel.

    Returns a flat list (legacy clients) by default. When `paginated=1`, returns
    `{items, total, limit, offset}` so the admin UI can show pagination controls.
    """
    query: dict = {}
    # Hide archived listings from the "All listings" tab — they live in their own Archive tab.
    if not include_archived:
        query["is_archived"] = {"$ne": True}
        query["status"] = {"$ne": "archived"}
    if status:
        # Allow explicit override via ?status=archived
        query["status"] = status
        if status == "archived":
            query.pop("is_archived", None)
    if q:
        import re
        rx = {"$regex": re.escape(q.strip()), "$options": "i"}
        query["$or"] = [{"title": rx}, {"make": rx}, {"model": rx}, {"seller_name": rx}, {"id": rx}]
    limit = max(1, min(200, int(limit)))
    offset = max(0, int(offset))
    if paginated:
        total = await db.auctions.count_documents(query)
        items = (
            await db.auctions.find(query, {"_id": 0})
            .sort("created_at", -1)
            .skip(offset)
            .limit(limit)
            .to_list(limit)
        )
        for a in items:
            a["status"] = _auction_status(a)
        return {"items": items, "total": int(total), "limit": limit, "offset": offset}
    items = await db.auctions.find(query, {"_id": 0}).sort("created_at", -1).limit(300).to_list(300)
    for a in items:
        a["status"] = _auction_status(a)
    return items


ADMIN_ALLOWED_STATUSES = {"pending", "live", "ended", "sold", "reserve_not_met", "withdrawn", "removed", "rejected"}


# ---- Admin: archived listings (must be registered BEFORE /{auction_id} routes) ----
@api.get("/admin/auctions/archived")
async def admin_list_archived(_admin: dict = Depends(require_admin_or_moderator)):
    """List every archived (soft-deleted) auction so admin can bulk-restore or hard-delete."""
    items = await db.auctions.find(
        {"$or": [{"is_archived": True}, {"status": "archived"}]},
        {"_id": 0},
    ).sort("archived_at", -1).to_list(500)
    return [_public_auction(a, None) for a in items]


@api.post("/admin/auctions/bulk-restore")
async def admin_bulk_restore(payload: dict, _admin: dict = Depends(require_admin)):
    """Restore multiple archived auctions in one call. Body: {ids: [...]}"""
    ids = payload.get("ids") or []
    if not ids:
        raise HTTPException(status_code=400, detail="ids[] е задължителен")
    restored = []
    skipped = []
    now = datetime.now(timezone.utc)
    for aid in ids:
        a = await db.auctions.find_one({"id": aid}, {"_id": 0})
        if not a:
            skipped.append({"id": aid, "reason": "not_found"})
            continue
        try:
            end = datetime.fromisoformat(a.get("ends_at", ""))
        except Exception:
            end = now - timedelta(days=1)
        new_status = "live" if end > now else "ended"
        await db.auctions.update_one(
            {"id": aid},
            {"$set": {"status": new_status, "is_archived": False}, "$unset": {"archived_at": ""}},
        )
        restored.append({"id": aid, "status": new_status})
    return {"ok": True, "restored": restored, "skipped": skipped}


@api.post("/admin/auctions/bulk-delete")
async def admin_bulk_hard_delete(payload: dict, request: Request, admin: dict = Depends(require_admin)):
    """Permanently delete multiple ARCHIVED auctions. Body: {ids: [...]}.

    Refuses to hard-delete listings that are not currently archived — admin
    must first archive them. This protects against accidental wipes.
    """
    ids = payload.get("ids") or []
    if not ids:
        raise HTTPException(status_code=400, detail="ids[] е задължителен")
    from services import bidding as bidding_svc
    from helpers import audit_log as _audit_log
    deleted = []
    refused = []
    for aid in ids:
        a = await db.auctions.find_one({"id": aid}, {"_id": 0})
        if not a:
            refused.append({"id": aid, "reason": "not_found"})
            continue
        if not (a.get("is_archived") or a.get("status") == "archived"):
            refused.append({"id": aid, "reason": "not_archived"})
            continue
        await bidding_svc.delete_bids_for_auction(aid)
        await db.comments.delete_many({"auction_id": aid})
        await db.watches.delete_many({"auction_id": aid})
        await db.bidding_credits.delete_many({"auction_id": aid})
        await db.vin_requests.delete_many({"auction_id": aid})
        # Also wipe ancillary records that reference the auction.
        try:
            await db.reviews.delete_many({"auction_id": aid})
        except Exception:
            pass
        try:
            await db.bid_authorizations.delete_many({"auction_id": aid})
        except Exception:
            pass
        # Inbox notifications attached to this auction.
        try:
            await db.inbox_notifications.delete_many({"data.auction_id": aid})
        except Exception:
            pass
        await db.auctions.delete_one({"id": aid})
        deleted.append(aid)
        await _audit_log(
            db, actor_id=admin["id"], actor_email=admin.get("email", ""), actor_role=admin.get("role", ""),
            action="auction.hard_delete_bulk", target_type="auction", target_id=aid,
            details={"title": a.get("title")}, ip=request.client.host if request.client else "",
        )
    return {"ok": True, "deleted": deleted, "refused": refused}


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

    # Image limits enforcement (mirror create flow): admin upload also goes
    # through 10MB-per-image / 120MB-total caps + re-encoding pipeline.
    image_keys = ("images", "images_exterior", "images_wheels", "images_bumper", "images_interior")
    if any(k in update for k in image_keys):
        from services import image_processing as imgproc
        from storage import store_images as _store_images
        MAX_PER_IMG_RAW = imgproc.IMAGE_MAX_RAW_BYTES
        MAX_TOTAL_PAYLOAD_RAW = 120 * 1024 * 1024
        total_raw = 0
        for k in image_keys:
            for item in (update.get(k) or []):
                if not isinstance(item, str):
                    continue
                sz = imgproc.raw_bytes_of(item) if item.startswith("data:image/") else 0
                if sz > MAX_PER_IMG_RAW:
                    mb = round(sz / 1024 / 1024, 1)
                    raise HTTPException(status_code=413, detail=f"Една от снимките е твърде голяма ({mb} MB). Макс. 10 MB на снимка.")
                total_raw += sz
        if total_raw > MAX_TOTAL_PAYLOAD_RAW:
            mb = round(total_raw / 1024 / 1024, 1)
            raise HTTPException(status_code=413, detail=f"Общият размер на снимките е {mb} MB — надвишава лимита от 120 MB.")
        thumb_buckets = {}
        from storage import fetch_remote_images_as_data_urls
        for k in image_keys:
            urls = update.get(k)
            if not urls:
                continue
            # Pre-fetch external URLs (e.g. mobile.bg imports) so the
            # standard optimize → store pipeline rehosts them locally.
            # `strict=True` drops failed fetches instead of letting them
            # pass through as external URLs.
            fetched = await fetch_remote_images_as_data_urls(urls, strict=True)
            urls = [u for u in fetched if u]
            if not urls:
                raise HTTPException(status_code=400, detail=f"Нито една снимка в '{k}' не можа да бъде свалена")
            update[k] = urls
            web, thumb, errs = await asyncio.to_thread(imgproc.optimize_many, urls)
            if errs:
                msg = "; ".join(errs[:3])
                raise HTTPException(status_code=400, detail=f"Грешка при обработката на снимки: {msg}")
            web = await asyncio.to_thread(_store_images, web)
            thumb = await asyncio.to_thread(_store_images, thumb)
            update[k] = web
            thumb_buckets[k] = thumb
        if "images" in update:
            update["thumbnails"] = thumb_buckets["images"]

    if update:
        await db.auctions.update_one({"id": auction_id}, {"$set": update})

    # Regenerate OG image in the background when any field that
    # actually appears on the share card changes. We fire-and-forget so
    # the admin UI stays snappy — the retry helper handles transient
    # failures.
    _og_relevant = {
        "title", "make", "model", "year",
        "current_bid_eur", "starting_bid_eur", "bid_count",
        "ends_at", "images", "thumbnails", "featured",
    }
    if any(k in update for k in _og_relevant):
        asyncio.create_task(_retry_og_image(auction_id, delay_sec=0))

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
    """Restore a removed/withdrawn/archived auction — sets status to 'live' if end date is in the future, otherwise 'ended', and clears is_archived."""
    a = await db.auctions.find_one({"id": auction_id}, {"_id": 0})
    if not a:
        raise HTTPException(status_code=404, detail="Обявата не е намерена")
    try:
        end = datetime.fromisoformat(a["ends_at"])
    except Exception:
        end = datetime.now(timezone.utc) - timedelta(days=1)
    new_status = "live" if end > datetime.now(timezone.utc) else "ended"
    await db.auctions.update_one(
        {"id": auction_id},
        {"$set": {"status": new_status, "is_archived": False}, "$unset": {"archived_at": ""}},
    )
    return {"ok": True, "status": new_status}


@api.delete("/admin/auctions/{auction_id}")
async def admin_hard_delete_auction(auction_id: str, request: Request, _admin: dict = Depends(require_admin)):
    """SOFT-deletes an auction (sets is_archived=true) — never destroys data.

    Behaviour change (2026-02): auction documents are NEVER physically
    removed from MongoDB anymore. They are flagged as `is_archived` so
    they disappear from public listings and from the admin live grid,
    but remain recoverable. Linked bids stay in PostgreSQL untouched.

    To force a true hard delete (legal/compliance requirement, e.g.
    DSAR), pass `?hard=1`. This is intentionally noisy in audit log.
    """
    hard = request.query_params.get("hard") in ("1", "true", "yes")

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

    if not hard:
        await db.auctions.update_one(
            {"id": auction_id},
            {"$set": {
                "is_archived": True,
                "archived_at": now_iso,
                "status": "archived",
            }},
        )
        return {"ok": True, "soft_deleted": True, "auction_id": auction_id}

    # Hard delete branch (use only with explicit ?hard=1)
    res_bids_count = await bidding_svc.delete_bids_for_auction(auction_id)
    res_comments = await db.comments.delete_many({"auction_id": auction_id})
    res_watches = await db.watches.delete_many({"auction_id": auction_id})
    res_credits = await db.bidding_credits.delete_many({"auction_id": auction_id})
    res_vin = await db.vin_requests.delete_many({"auction_id": auction_id})
    await db.auctions.delete_one({"id": auction_id})
    return {
        "ok": True,
        "hard_deleted": True,
        "deleted": {
            "auction": 1,
            "bids": res_bids_count,
            "comments": res_comments.deleted_count,
            "watches": res_watches.deleted_count,
            "bidding_credits": res_credits.deleted_count,
            "vin_requests": res_vin.deleted_count,
        },
    }


@api.post("/admin/auctions/{auction_id}/restore-archived")
async def admin_restore_archived_auction(auction_id: str, _admin: dict = Depends(require_admin)):
    """Alias for restore — kept for clarity in admin UI ("restore from archive")."""
    return await admin_restore_auction(auction_id, _admin)


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


@api.post("/admin/auctions/{auction_id}/reset-timer")
async def admin_reset_timer(
    auction_id: str,
    hours: float = Query(default=None, ge=0.5, le=720),
    days: int = Query(default=None, ge=1, le=60),
    _admin: dict = Depends(require_admin),
):
    """Reset the timer of an active (or paused) auction to now + (days|hours).

    Use cases:
      * Snipe disputes — extend a heated auction by a few hours
      * Operational — give bidders more time after a brief downtime
    Either `hours` or `days` must be provided. Anti-snipe `ending_soon`
    notification flag is reset so users get a fresh 1h-before reminder.
    """
    if (hours is None) and (days is None):
        raise HTTPException(status_code=400, detail="Подайте `hours` или `days`")
    a = await db.auctions.find_one({"id": auction_id}, {"_id": 0})
    if not a:
        raise HTTPException(status_code=404, detail="Обявата не е намерена")
    if a.get("status") not in ("live", "paused"):
        raise HTTPException(
            status_code=400,
            detail="Reset на таймера е достъпен само за активни (live) или паузирани обяви",
        )
    now = datetime.now(timezone.utc)
    delta = timedelta(hours=hours) if hours is not None else timedelta(days=int(days))
    new_ends = now + delta
    set_doc = {
        "ends_at": new_ends.isoformat(),
        "timer_reset_at": now.isoformat(),
    }
    # Reset the "ending soon" flag so watchers/bidders get a fresh 1h reminder.
    await db.auctions.update_one(
        {"id": auction_id},
        {"$set": set_doc, "$unset": {"ending_soon_notified": "", "ending_soon_notified_at": ""}},
    )
    return {"ok": True, "ends_at": new_ends.isoformat()}


@api.get("/admin/unsold")
async def admin_unsold(
    _admin: dict = Depends(require_admin),
    limit: int = Query(default=200, ge=1, le=1000),
):
    """Return finalized auctions that did NOT result in a sale.

    Statuses considered "unsold":
      * `ended` — finished without bids or hit reserve threshold
      * `reserve_not_met` — had bids but reserve wasn't reached
      * `cancelled` — admin-cancelled
      * `withdrawn` — seller withdrew

    Excludes archived listings (so the tab stays focused on actionable items).
    """
    items = await db.auctions.find(
        {
            "status": {"$in": ["ended", "reserve_not_met", "cancelled", "withdrawn"]},
            "is_archived": {"$ne": True},
        },
        {"_id": 0},
    ).sort("finalized_at", -1).limit(limit).to_list(limit)
    # Enrich with high bidder details for the few unsold-with-bids cases —
    # admin may want to follow up directly with the top bidder.
    out = []
    for a in items:
        a_copy = {**a}
        hb_id = a.get("high_bidder_id")
        if hb_id:
            u = await db.users.find_one({"id": hb_id}, {"_id": 0, "email": 1, "name": 1})
            if u:
                a_copy["high_bidder_email"] = u.get("email")
                a_copy["high_bidder_name"] = u.get("name") or a.get("high_bidder_name")
        out.append(a_copy)
    return out


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
    try:
        await notify_auction_finalized(db, a)
    except Exception as e:
        logger.error("notify_auction_finalized failed: %s", e)
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
    u = await _resolve_user_by_identifier(
        user_id,
        {"_id": 0, "password_hash": 0, "email": 0},
    )
    if not u:
        raise HTTPException(status_code=404, detail="Потребителят не е намерен")
    # After slug resolution the actual Mongo `id` may differ from the
    # path segment — use the resolved one for every follow-up query.
    user_id = u["id"]
    sold_listings = await db.auctions.find(
        {"seller_id": user_id, "status": "sold", "is_archived": {"$ne": True}},
        {"_id": 0},
    ).sort("finalized_at", -1).limit(60).to_list(60)
    purchases = await db.auctions.find(
        {"high_bidder_id": user_id, "status": "sold", "is_archived": {"$ne": True}},
        {"_id": 0},
    ).sort("finalized_at", -1).limit(60).to_list(60)
    active = await db.auctions.find(
        {"seller_id": user_id, "status": "live", "is_archived": {"$ne": True}},
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
        "user": {
            "id": u["id"],
            "name": u["name"],
            "role": u.get("role", "user"),
            "member_since": u["created_at"],
            "profile_slug": u.get("profile_slug"),
            "is_verified_dealer": bool(u.get("is_verified_dealer")),
            "dealer_slug": u.get("dealer_slug"),
        },
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


# ---- Dealer public storefront ----
# Verified dealers get a vanity URL at `autoandbid.bg/{slug}` (e.g.
# `autoandbid.bg/MGT`). The slug is admin-assigned, case-insensitive,
# and stored alphanumeric-only on the user document as `dealer_slug`.
# React Router resolves it via the catch-all `/:slug` route AFTER all
# named routes, so reserved paths like `/sell`, `/auctions` always win.


_DEALER_SLUG_RE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_-]{1,29}$")


@api.get("/dealers/{slug}")
async def get_dealer_by_slug(slug: str):
    """Return dealer profile + up to 60 of their active/recently-sold
    listings. Used by the `/:slug` frontend route to render a public
    storefront page without requiring an account."""
    if not slug or not _DEALER_SLUG_RE.match(slug):
        raise HTTPException(status_code=404, detail="Дилърът не е намерен")
    # Case-insensitive match. Stored slugs are always lowercase so we
    # index on an exact-match field rather than a $regex scan.
    u = await db.users.find_one(
        {"dealer_slug": slug.lower(), "is_verified_dealer": True},
        {"_id": 0, "password_hash": 0, "email": 0, "phone": 0},
    )
    if not u:
        raise HTTPException(status_code=404, detail="Дилърът не е намерен")

    active = await db.auctions.find(
        {"seller_id": u["id"], "status": "live", "is_archived": {"$ne": True}},
        {"_id": 0},
    ).sort("created_at", -1).limit(60).to_list(60)
    recently_sold = await db.auctions.find(
        {"seller_id": u["id"], "status": "sold", "is_archived": {"$ne": True}},
        {"_id": 0},
    ).sort("finalized_at", -1).limit(12).to_list(12)

    # Aggregate rating (same formula as /users/{id}/profile)
    rating_vals = [int(r["rating"]) async for r in db.reviews.find(
        {"seller_id": u["id"]}, {"_id": 0, "rating": 1}
    )]
    rating_avg = round(sum(rating_vals) / len(rating_vals), 2) if rating_vals else 0.0

    return {
        "dealer": {
            "id": u["id"],
            "name": u.get("name"),
            "slug": u.get("dealer_slug"),
            "avatar_url": u.get("avatar_url"),
            "bio": u.get("bio"),
            "city": u.get("city"),
            "country": u.get("country"),
            "member_since": u.get("created_at"),
            "is_verified_dealer": True,
        },
        "rating": {"avg": rating_avg, "count": len(rating_vals)},
        "active_listings": [_list_shape(_public_auction(a)) for a in active],
        "recently_sold": [_list_shape(_public_auction(a)) for a in recently_sold],
        "counts": {
            "active": len(active),
            "sold_total": await db.auctions.count_documents(
                {"seller_id": u["id"], "status": "sold", "is_archived": {"$ne": True}}
            ),
        },
    }


class DealerSlugPayload(BaseModel):
    slug: Optional[str] = None  # None/empty clears the slug


@api.put("/admin/users/{user_id}/dealer-slug")
async def admin_set_dealer_slug(
    user_id: str, payload: DealerSlugPayload, _admin: dict = Depends(require_admin),
):
    """Assign or clear a dealer's vanity slug. Only verified dealers may
    hold a slug — we enforce `is_verified_dealer=True` on the same
    document to keep the storefront gate consistent."""
    u = await db.users.find_one({"id": user_id}, {"_id": 0, "is_verified_dealer": 1})
    if not u:
        raise HTTPException(status_code=404, detail="Потребителят не е намерен")

    new_slug = (payload.slug or "").strip().lower() or None
    if new_slug is not None:
        if not _DEALER_SLUG_RE.match(new_slug):
            raise HTTPException(
                status_code=400,
                detail="Slug-ът трябва да е 2-30 символа: латиница, цифри, тире, долна черта.",
            )
        if not u.get("is_verified_dealer"):
            raise HTTPException(
                status_code=400,
                detail="Само проверени дилъри могат да имат публичен slug. Първо маркирайте потребителя като verified dealer.",
            )
        # Reject if another user already holds this slug.
        clash = await db.users.find_one(
            {"dealer_slug": new_slug, "id": {"$ne": user_id}},
            {"_id": 0, "id": 1},
        )
        if clash:
            raise HTTPException(status_code=409, detail="Този slug вече е зает от друг дилър.")

    update = {"$set": {"dealer_slug": new_slug}} if new_slug else {"$unset": {"dealer_slug": ""}}
    await db.users.update_one({"id": user_id}, update)
    return {"ok": True, "slug": new_slug}


# ---- Seed ----
SEED_AUCTIONS = [
    {
        "title": "BMW M2 Coupé — Club Sport Pack, Manual",
        "make": "BMW", "model": "M2", "year": 2018, "mileage_km": 64000,
        "fuel": "Бензин", "transmission": "Ръчна", "body_type": "Купе",
        "power_hp": 410, "engine_cc": 2979, "color": "Long Beach Blue",
        "region": "София", "city": "София",
        "images": [
            "https://images.unsplash.com/photo-1607853554439-0069ec0f29b6?crop=entropy&cs=srgb&fm=jpg&q=85&w=1600",
            "https://images.unsplash.com/photo-1617531653332-bd46c24f2068?crop=entropy&cs=srgb&fm=jpg&q=85&w=1600",
            "https://images.unsplash.com/photo-1611821064430-0979d0e51e8b?crop=entropy&cs=srgb&fm=jpg&q=85&w=1600",
        ],
        "description": "M2 Competition с Club Sport Pack — без шумоизолация в багажника, fixed-back седалки, half-cage, спортно окачване. Документиран сервиз през Дилерска мрежа БМВ.",
        "starting_bid_eur": 45000, "current_bid": 52500, "featured": True, "days_left": 5, "extra_bids": 18,
        "vin": "WBS4Y91020AC78423",
    },
    {
        "title": "Mercedes-Benz C 43 AMG 4MATIC — 2020, FULL",
        "make": "Mercedes-Benz", "model": "C-Class", "year": 2020, "mileage_km": 71000,
        "fuel": "Бензин", "transmission": "Автоматична", "body_type": "Седан",
        "power_hp": 390, "engine_cc": 2996, "color": "Selenite Grey",
        "region": "Пловдив", "city": "Пловдив",
        "images": [
            "https://images.unsplash.com/photo-1617814076367-b759c7d7e738?crop=entropy&cs=srgb&fm=jpg&q=85&w=1600",
            "https://images.unsplash.com/photo-1606220588913-b3aacb4d2f46?crop=entropy&cs=srgb&fm=jpg&q=85&w=1600",
            "https://images.unsplash.com/photo-1606016159991-dfe4f2746ad5?crop=entropy&cs=srgb&fm=jpg&q=85&w=1600",
        ],
        "description": "C 43 AMG 4MATIC, biturbo V6, 9-speed AMG SPEEDSHIFT, AMG Performance изпускателна, Burmester, panoramic, керамичен покрив. Карбонов пакет, AMG Track Pace.",
        "starting_bid_eur": 48000, "current_bid": 54200, "featured": True, "days_left": 4, "extra_bids": 26,
        "vin": "WDD2050801F123456",
    },
    {
        "title": "BMW M240i xDrive — M-Performance, 2023",
        "make": "BMW", "model": "M240i", "year": 2023, "mileage_km": 22000,
        "fuel": "Бензин", "transmission": "Автоматична", "body_type": "Купе",
        "power_hp": 374, "engine_cc": 2998, "color": "Thundernight Metallic",
        "region": "Варна", "city": "Варна",
        "images": [
            "https://images.unsplash.com/photo-1555215695-3004980ad54e?crop=entropy&cs=srgb&fm=jpg&q=85&w=1600",
            "https://images.unsplash.com/photo-1614162883144-1f0d3f59db76?crop=entropy&cs=srgb&fm=jpg&q=85&w=1600",
            "https://images.unsplash.com/photo-1606016159991-dfe4f2746ad5?crop=entropy&cs=srgb&fm=jpg&q=85&w=1600",
        ],
        "description": "M240i xDrive с M Performance пакет — карбонови огледала, OPF delete, Akrapovič, M Sport диференциал. Гаранция БМВ до 2026.",
        "starting_bid_eur": 52000, "current_bid": 58800, "featured": True, "days_left": 6, "extra_bids": 33,
        "vin": "WBA2J71040VA53204",
    },
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
            "seller_name": "autoandbid.com",
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
            "seller_name": "autoandbid.com",
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
    email = os.environ.get("ADMIN_EMAIL", "admin@autoandbid.com")
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
            # Admin is implicitly trusted — never gate it behind email
            # verification (would otherwise lock first-deploy admins out
            # of their own /admin panel before SMTP is wired up).
            "email_verified": True,
            "verification_required": False,
        })
    else:
        # Ensure existing admins are never gated out by a stale verification flag.
        patch = {}
        if not existing.get("email_verified"):
            patch["email_verified"] = True
        if existing.get("verification_required"):
            patch["verification_required"] = False
        if not verify_password(password, existing["password_hash"]):
            patch["password_hash"] = hash_password(password)
        if patch:
            await db.users.update_one({"email": email}, {"$set": patch})

@app.on_event("startup")
async def on_startup():
    # ----- Storage writability self-check -----
    # Production has lost photos to misconfigured UPLOAD_DIR more than
    # once. Probe the configured backend at boot and log loudly if it
    # can't write — ops sees the message in `journalctl -u backend`
    # before the first sell submission fails with a cryptic 500.
    try:
        from storage import _get_backend
        backend = _get_backend()
        backend_name = getattr(backend, "name", "?")
        root = getattr(backend, "root", None)
        if backend_name == "inline":
            logger.warning(
                "STORAGE_BACKEND=inline — image bytes will be saved as data: URLs in MongoDB. "
                "This is fine for tests but will balloon DB size in production. Set STORAGE_BACKEND=disk."
            )
        elif backend_name == "disk":
            test_data = "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNkAAEAAAcAAc+8aFQAAAAASUVORK5CYII="
            try:
                ref = backend.store(test_data)
                if ref.startswith(("/api/uploads/", "/uploads/", "http://", "https://")):
                    logger.info("Storage probe OK: backend=disk root=%s → %s", root, ref[:80])
                else:
                    logger.error(
                        "Storage probe FAILED: backend=disk returned non-URL ref=%r — uploads will leak as data: URLs",
                        ref[:80],
                    )
            except Exception as e:  # noqa: BLE001
                logger.error(
                    "Storage probe FAILED: backend=disk root=%s NOT writable: %s. "
                    "Check directory exists and is owned by the backend user.",
                    root, e,
                )
    except Exception as e:  # noqa: BLE001
        logger.warning("Storage probe skipped: %s", e)

    # ----- Email templates: seed system defaults into site_settings -----
    try:
        from email_templates import seed_defaults_on_startup as _seed_templates
        n = await _seed_templates(db)
        if n:
            logger.info("Email templates: seeded %d system defaults into site_settings", n)
    except Exception as e:  # noqa: BLE001
        logger.warning("Email templates seed skipped: %s", e)

    # ----- Image optimization queue: init + resume pending jobs -----
    try:
        from services import image_optimization_queue as _ioq
        _ioq.init(db)
        # Resume any jobs that were mid-flight when the previous process
        # restarted. Runs in the background so startup isn't blocked.
        asyncio.create_task(_ioq.resume_pending())
        logger.info("Image optimization queue initialised.")
    except Exception as e:  # noqa: BLE001
        logger.warning("Image queue init skipped: %s", e)

    # ----- MongoDB: wait until reachable before creating indexes -----
    # On cold container starts, both Mongo and the API spin up in parallel.
    # We retry up to ~60s instead of crashing the worker loop.
    mongo_ready = False
    for attempt in range(1, 31):  # ~60s max wait
        try:
            await db.users.create_index("email", unique=True)
            mongo_ready = True
            if attempt > 1:
                logger.warning("MongoDB became ready after %d retries", attempt)
            break
        except Exception as e:
            logger.warning("Mongo bootstrap attempt %d failed: %s", attempt, e)
            await asyncio.sleep(2)
    if not mongo_ready:
        logger.error("MongoDB still unavailable after 30 retries — proceeding (operations will surface errors)")
    await db.auctions.create_index("id", unique=True)
    await db.auctions.create_index([("status", 1), ("ends_at", 1)])
    # NOTE: legacy Mongo `bids` index kept for old archive data; new bids live in Postgres.
    await db.bids.create_index("auction_id")
    # Web Push subscriptions (one-doc-per-endpoint)
    await db.push_subscriptions.create_index("endpoint", unique=True)
    await db.push_subscriptions.create_index("user_id")
    await db.comments.create_index("auction_id")
    # Leaderboard/reputation: fast lookups by follower or followee.
    await db.user_follows.create_index([("follower_id", 1), ("followee_id", 1)], unique=True)
    await db.user_follows.create_index("followee_id")
    await db.watches.create_index([("user_id", 1), ("auction_id", 1)])
    await db.bidding_credits.create_index([("auction_id", 1), ("user_id", 1)])
    await db.makes.create_index("name", unique=True)
    await db.audit_log.create_index([("at", -1)])
    # Video-upload rate-limit log: per-user query for hourly/daily counts.
    await db.video_upload_log.create_index([("user_id", 1), ("created_at", -1)])
    # Passkey storage + audit + auto-expiring challenges.
    await db.passkey_credentials.create_index([("user_id", 1)])
    await db.passkey_credentials.create_index([("credential_id", 1)], unique=True)
    await db.passkey_audit_log.create_index([("user_id", 1), ("at", -1)])
    # TTL on `expires_at` — challenges auto-deleted ~10 min after creation.
    await db.passkey_challenges.create_index([("expires_at", 1)], expireAfterSeconds=0)
    await db.passkey_challenges.create_index([("user_id", 1), ("operation", 1)])
    # Stripe webhook idempotency dedupe collection (unique on Stripe event id).
    try:
        await db.stripe_processed_events.create_index("id", unique=True)
        await db.stripe_processed_events.create_index([("received_at", -1)])
    except Exception:
        pass
    # PostgreSQL bidding subsystem — retry with backoff so transient PG
    # readiness issues at boot don't crash the entire app. Cold-start
    # scenarios where PG binaries need re-installation can take up to
    # 2 minutes, so we keep retrying for ~5 minutes total.
    from db_pg import init_pg_schema, dispose_engine
    pg_ready = False
    for attempt in range(1, 151):  # ~5 minutes max wait (150 × 2s)
        try:
            await init_pg_schema()
            pg_ready = True
            if attempt > 1:
                logger.warning("PostgreSQL became ready after %d retries", attempt)
            break
        except Exception as e:
            # Backoff: log only every 5 attempts to keep the log readable on
            # long cold starts.
            if attempt % 5 == 1:
                logger.warning("init_pg_schema attempt %d failed: %s", attempt, e)
            # Drop any cached engine state so the next try uses a fresh
            # connection — prevents the SQLAlchemy pool from latching onto
            # a stale "starting up" socket.
            try:
                await dispose_engine()
            except Exception:
                pass
            await asyncio.sleep(2)
    if not pg_ready:
        # Don't crash — the API still serves all Mongo-backed endpoints.
        # Bid endpoints will surface their own errors when the user tries.
        logger.error("PostgreSQL still unavailable after 150 retries — starting in degraded mode")
    # Transactional-outbox worker (drains bid_events → MongoDB)
    from services import outbox_worker
    app.state._outbox_stop = asyncio.Event()
    app.state._outbox_task = asyncio.create_task(outbox_worker.run_worker(app.state._outbox_stop))
    await _load_settings_cache()
    await seed_admin()
    await seed()
    await _seed_makes()
    await _backfill_profile_slugs()
    await _setup_notifications_ttl()
    # Start background scheduler for auction finalization
    asyncio.create_task(_auction_finalizer_loop())
    # Start background scheduler for "ending soon" notifications (≈1h before end)
    asyncio.create_task(_ending_soon_loop())
    # Stripe authorization lifecycle worker (7-day auto-extend)
    from services import stripe_lifecycle
    stripe_lifecycle.start_worker(db)
    # 3-day digest emails (new listings + ending soon)
    from services import digest_worker
    digest_worker.start(db)


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


async def _ending_soon_loop():
    """Runs every 5 minutes. Notifies watchers + active bidders ~1h before
    a live auction ends. Idempotent via the `ending_soon_notified` flag."""
    # Stagger start so it doesn't race with the finalizer on the same tick.
    await asyncio.sleep(20)
    while True:
        try:
            await _notify_ending_soon_once()
        except Exception as e:
            logger.error("Ending-soon notifier error: %s", e)
        await asyncio.sleep(300)


async def _notify_ending_soon_once():
    """Find live auctions ending in 55–65 minutes that haven't been
    notified yet, and dispatch email + push to:
      - users on the watchlist for that auction, AND
      - users who have placed at least one bid on that auction.
    """
    from services import notif_prefs as _nprefs
    from services import push_templates
    now = datetime.now(timezone.utc)
    window_start = (now + timedelta(minutes=55)).isoformat()
    window_end = (now + timedelta(minutes=65)).isoformat()
    cursor = db.auctions.find(
        {
            "status": "live",
            "ends_at": {"$gte": window_start, "$lte": window_end},
            "ending_soon_notified": {"$ne": True},
        },
        {"_id": 0, "id": 1, "title": 1, "ends_at": 1, "current_bid_eur": 1, "is_archived": 1},
    )
    candidates = await cursor.to_list(200)
    for a in candidates:
        if a.get("is_archived"):
            continue
        auction_id = a["id"]
        # Mark first to avoid double-fire if the loop overlaps another instance
        marked = await db.auctions.update_one(
            {"id": auction_id, "ending_soon_notified": {"$ne": True}},
            {"$set": {"ending_soon_notified": True, "ending_soon_notified_at": now.isoformat()}},
        )
        if marked.modified_count == 0:
            continue

        # Collect recipients: watchers + active bidders
        recipients: dict[str, str] = {}  # user_id → role ("watcher"|"bidder")
        async for w in db.watches.find({"auction_id": auction_id}, {"_id": 0, "user_id": 1}).limit(2000):
            recipients[w["user_id"]] = "watcher"
        try:
            from services import bidding as _bidding
            bidder_ids = await _bidding.collect_bidder_ids(auction_id, exclude_user_id=None, limit=2000)
            for uid in bidder_ids:
                # Bidder role wins over watcher (the email title differs)
                recipients[uid] = "bidder"
        except Exception as e:
            logger.warning("ending_soon: collect_bidder_ids failed: %s", e)

        if not recipients:
            continue

        users = await db.users.find({"id": {"$in": list(recipients.keys())}}, {"_id": 0}).to_list(2000)
        title = a.get("title", "")
        amount = float(a.get("current_bid_eur", 0))
        for u in users:
            uid = u["id"]
            role = recipients.get(uid, "watcher")
            if u.get("email") and _nprefs.is_enabled(u, "email", "ending_soon"):
                try:
                    from emails import email_ending_soon
                    await email_ending_soon(u["email"], u.get("name", ""), title, auction_id, amount, role, lang=u.get("lang") or "bg")
                except Exception as e:
                    logger.error("email_ending_soon failed for %s: %s", uid, e)
            if _nprefs.is_enabled(u, "push", "ending_soon"):
                try:
                    await push_templates.send_template(
                        uid,
                        "ending_soon",
                        fmt_args={"title": title[:60], "amount": f"{int(amount):,}"},
                        url=f"/auctions/{auction_id}",
                        tag=f"ending-soon-{auction_id}",
                    )
                except Exception as e:
                    logger.error("push ending_soon failed for %s: %s", uid, e)


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
            # Release any Stripe holds tied to this auction (rare — usually no holds without bids)
            try:
                from routers.stripe_holds import cancel_authorization as _cancel_auth
                async for sa in db.bid_authorizations.find(
                    {"auction_id": auction_id, "authorization_status": {"$in": ["active", "pending"]}},
                    {"_id": 0, "id": 1},
                ):
                    try: await _cancel_auth(db, sa["id"])
                    except Exception: pass
            except Exception as e:
                logger.warning("[stripe] cancel-on-no-bids failed: %s", e)
            try:
                from routers.inbox import notify_admins as _notify_admins, notify_user as _notify_user
                await _notify_admins(
                    db, type="auction_no_bids",
                    data={"title": a.get("title", "")},
                    auction_id=auction_id,
                    push_template_id="admin_auction_no_bids",
                    push_fmt={"title": (a.get("title") or "")[:80]},
                )
                if a.get("seller_id") and a["seller_id"] != "platform":
                    await _notify_user(db, user_id=a["seller_id"],
                                       type="auction_no_bids_seller",
                                       data={"title": a.get("title", "")},
                                       auction_id=auction_id)
            except Exception as e:
                logger.warning("notify ended-no-bids failed: %s", e)
            logger.info("Auto-finalized auction %s → ended (no bids)", auction_id)
            continue

        if has_reserve and current_bid < float(reserve):
            # Reserve not met → open negotiation window (lazy-created on first GET)
            await db.auctions.update_one(
                {"id": auction_id},
                {"$set": {"status": "reserve_not_met", "finalized_at": now_iso}},
            )
            try:
                from routers.inbox import notify_admins as _notify_admins, notify_user as _notify_user
                gap = float(reserve) - current_bid
                payload = {
                    "title": a.get("title", ""),
                    "bid": int(current_bid),
                    "reserve": int(reserve),
                    "gap": int(gap),
                }
                await _notify_admins(
                    db, type="auction_below_reserve", data=payload, auction_id=auction_id,
                )
                if a.get("seller_id") and a["seller_id"] != "platform":
                    await _notify_user(db, user_id=a["seller_id"],
                                       type="auction_below_reserve_seller",
                                       data=payload, auction_id=auction_id)
                if a.get("high_bidder_id"):
                    await _notify_user(db, user_id=a["high_bidder_id"],
                                       type="auction_below_reserve_buyer",
                                       data=payload, auction_id=auction_id)
            except Exception as e:
                logger.warning("notify reserve_not_met failed: %s", e)
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
        try:
            from routers.inbox import notify_admins as _notify_admins, notify_user as _notify_user
            margin = current_bid - float(reserve) if has_reserve else 0
            vat = _admin_notif_vat_fields(current_bid, a)
            payload = {
                "title": a.get("title", ""),
                # Show the GROSS (incl. VAT) amount to both seller and
                # buyer — matches the "prices WITH VAT" rule used
                # everywhere else in the UI. Without this, the buyer's
                # "Купихте този автомобил" notification reads with the
                # net price while every other UI surface (auction page,
                # invoice, my-bids) shows gross — a confusing mismatch.
                "bid": vat["gross"],
                "bid_gross": vat["gross"],
                "vat_suffix": vat["vat_suffix"],
                "commission": vat["commission"],
                "margin": int(margin) if has_reserve else 0,
                "has_reserve": has_reserve,
            }
            await _notify_admins(
                db,
                type="auction_sold_above_reserve" if has_reserve else "auction_sold_no_reserve",
                data=payload, auction_id=auction_id,
                push_template_id="admin_auction_sold_above_reserve" if has_reserve else "admin_auction_sold_no_reserve",
                push_fmt={
                    "title": (a.get("title") or "")[:80],
                    # GROSS price in the body — see `_admin_notif_vat_fields`
                    # for why: 2 % commission is based on the gross figure.
                    "bid": vat["gross"],
                    "vat_suffix": vat["vat_suffix"],
                    "commission": vat["commission"],
                    "margin": int(margin) if has_reserve else 0,
                },
            )
            if a.get("seller_id") and a["seller_id"] != "platform":
                await _notify_user(db, user_id=a["seller_id"], type="auction_sold_seller",
                                   data=payload, auction_id=auction_id)
            if a.get("high_bidder_id"):
                await _notify_user(db, user_id=a["high_bidder_id"], type="auction_won",
                                   data=payload, auction_id=auction_id)
        except Exception as e:
            logger.warning("notify sold failed: %s", e)
        # Release losing bidders' preauths (keep winner's active for capture)
        from services import bidding as bidding_svc
        await bidding_svc.release_losing_preauths(auction_id, a["high_bidder_id"])
        await db.bidding_credits.update_many(
            {"auction_id": auction_id, "status": "authorized", "user_id": {"$ne": a["high_bidder_id"]}},
            {"$set": {"status": "released", "released_at": now_iso}},
        )
        # Stripe holds:
        #   • Per-auction winner authorization → capture immediately
        #     (legacy flow, only fires when auction was bid via the
        #     deprecated per-auction hold model).
        #   • Account-level winner credit → partial-capture buyer fee
        #     and IMMEDIATELY re-issue a fresh hold for the unspent
        #     remainder so the universal credit pool stays funded for
        #     other auctions (Stripe auto-releases on partial-capture).
        #   • Losers' authorizations → keep ACTIVE for 24h grace, then
        #     auto-release.
        try:
            from routers.stripe_holds import capture_authorization as _capture_auth
            from services.stripe_lifecycle import capture_and_reissue as _capture_reissue
            grace_until = (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()
            # 1) Per-auction holds tied to *this* auction.
            async for sa in db.bid_authorizations.find(
                {"auction_id": auction_id, "authorization_status": "active"}, {"_id": 0, "id": 1, "user_id": 1}
            ):
                if sa["user_id"] == a["high_bidder_id"]:
                    try:
                        await _capture_auth(db, sa["id"])
                        logger.info("[stripe] captured winner per-auction hold %s for auction %s", sa["id"], auction_id)
                    except Exception as e:
                        logger.error("[stripe] winner capture failed for %s: %s", sa["id"], e)
                else:
                    await db.bid_authorizations.update_one(
                        {"id": sa["id"]},
                        {"$set": {"authorization_status": "loser_grace",
                                  "release_at": grace_until,
                                  "updated_at": now_iso}},
                    )
                    logger.info("[stripe] loser %s scheduled to release at %s", sa["id"], grace_until)
            # 2) Universal credit pool: partial-capture buyer fee from
            #    the winner's account-level hold(s) and re-issue the
            #    rest. Walk holds oldest-first so we drain the closest-
            #    to-expiry authorizations first.
            buyer_fee = round(_buyer_fee_on_auction(current_bid, a), 2)
            remaining_fee = buyer_fee
            account_holds_cursor = db.bid_authorizations.find(
                {"user_id": a["high_bidder_id"], "auction_id": None,
                 "authorization_status": "active"},
                {"_id": 0, "id": 1, "amount_authorized_eur": 1, "bidding_limit_eur": 1,
                 "created_at": 1},
                sort=[("created_at", 1)],
            )
            async for hold in account_holds_cursor:
                if remaining_fee <= 0.01:
                    break
                hold_amount = float(hold.get("amount_authorized_eur") or 0)
                take = min(remaining_fee, hold_amount)
                try:
                    result = await _capture_reissue(
                        db, auth_id=hold["id"], capture_amount_eur=take,
                    )
                    logger.info(
                        "[stripe] capture+reissue auction=%s hold=%s captured=%s reissued=%s",
                        auction_id, hold["id"], result.get("captured_eur"), result.get("reissued_id"),
                    )
                    remaining_fee = round(remaining_fee - float(result.get("captured_eur") or 0), 2)
                except Exception as e:
                    logger.error("[stripe] capture+reissue failed for hold %s: %s", hold["id"], e)
                    # Move on to next hold to avoid blocking finalization.
                    continue
            if remaining_fee > 0.5:
                logger.warning(
                    "[stripe] auction %s winner %s short on account credit by €%.2f — manual reconciliation needed",
                    auction_id, a["high_bidder_id"], remaining_fee,
                )
        except Exception as e:
            logger.warning("[stripe] capture/grace pipeline failed for %s: %s", auction_id, e)
        # Notify winner + seller
        try:
            await notify_auction_finalized(db, a)
        except Exception as e:
            logger.error("notify_auction_finalized auto-finalize failed for %s: %s", auction_id, e)
        logger.info("Auto-finalized auction %s → sold (€%.0f)", auction_id, current_bid)

    # ---- Process expired "loser_grace" Stripe holds (released after 24h) ----
    try:
        from routers.stripe_holds import cancel_authorization as _cancel_auth
        now_iso2 = datetime.now(timezone.utc).isoformat()
        cursor = db.bid_authorizations.find(
            {"authorization_status": "loser_grace", "release_at": {"$lt": now_iso2}},
            {"_id": 0, "id": 1},
        )
        async for sa in cursor:
            try:
                await _cancel_auth(db, sa["id"])
                logger.info("[stripe] loser-grace hold %s released", sa["id"])
            except Exception as e:
                logger.warning("[stripe] loser-grace release failed for %s: %s", sa["id"], e)
    except Exception as e:
        logger.warning("[stripe] loser-grace sweep failed: %s", e)

@api.post("/admin/reseed")
async def reseed(_admin: dict = Depends(require_admin)):
    """Adds any missing seed/demo listings — NEVER touches user-owned data.

    Safety guards (added 2026-02 after we accidentally wiped real user
    listings during dev):
      • Only deletes platform-owned auctions (seller_id == 'platform')
      • Does NOT touch user-owned auctions, bids, comments, or watches
      • Insert is idempotent on (title, seller_id='platform') so calling
        reseed twice doesn't duplicate seed rows
    """
    # 1) Remove ONLY the platform demo auctions — leave user listings intact.
    platform_auctions = await db.auctions.find(
        {"seller_id": "platform"}, {"_id": 0, "id": 1}
    ).to_list(500)
    platform_ids = [a["id"] for a in platform_auctions]
    if platform_ids:
        await db.auctions.delete_many({"id": {"$in": platform_ids}})
        # Bids / comments / watches tied to platform listings only
        from services import bidding as bidding_svc
        for aid in platform_ids:
            await bidding_svc.delete_bids_for_auction(aid)
        await db.comments.delete_many({"auction_id": {"$in": platform_ids}})
        await db.watches.delete_many({"auction_id": {"$in": platform_ids}})
    # 2) Re-insert seed listings (idempotent — guard inside seed())
    await seed()
    return {"ok": True, "platform_listings_reset": len(platform_ids)}


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

# SSO cross-domain handoff (autoandbid.com ↔ .bg ↔ .ro). Browsers
# cannot share cookies across different public-suffix TLDs, so we
# implement a 60 s nonce-token handoff. See routers/sso.py for the
# full flow + security model.
from routers import sso as _sso_router  # noqa: E402
api.include_router(_sso_router.build_sso_router(
    db=db,
    create_token=create_token,
    get_current_user=get_current_user,
    set_auth_cookies=_auth_router._set_auth_cookies,
))

# In-app notification inbox (durable per-user message log)
from routers import inbox as _inbox_router
_inbox = _inbox_router.build_inbox_router(db, get_current_user)
app.include_router(_inbox)

# WebAuthn / FIDO2 passkey login (alternative to TOTP 2FA + standalone).
# RP ID is `autoandbid.bg`; passkeys created on any of the three brand
# TLDs work cross-domain via the `/.well-known/webauthn` manifest.
from routers import passkey as _passkey_router  # noqa: E402

async def _verify_password_for_passkey(user_doc, password_str: str) -> bool:
    """Re-auth helper used by add/remove passkey endpoints.

    `get_current_user` strips `password_hash` from its returned dict
    (line 125), so we re-fetch the full user document with the hash
    intact before delegating to the standard verifier.
    """
    if not password_str:
        return False
    full = await db.users.find_one(
        {"id": user_doc["id"]}, {"_id": 0, "password_hash": 1}
    )
    if not full or not full.get("password_hash"):
        return False
    return verify_password(password_str, full["password_hash"])

api.include_router(_passkey_router.build_passkey_router(
    db=db,
    get_current_user=get_current_user,
    verify_password=_verify_password_for_passkey,
    create_token=_auth_router._create_token,
    create_session=_auth_router._create_session,
    set_auth_cookies=_auth_router._set_auth_cookies,
    remember_ttl_days=_auth_router.REMEMBER_TTL_DAYS,
    cookie_ttl_days=_auth_router.COOKIE_TTL_DAYS,
    sanitize_user=_auth_router._sanitize,
))


@app.get("/.well-known/webauthn")
@api.get("/.well-known/webauthn")
async def webauthn_related_origins():
    """Related Origin Requests manifest — lets passkeys created with
    `rp.id = autoandbid.bg` be used on autoandbid.com / autoandbid.ro
    too (Chromium 128+, Safari 18+). See:
    https://developer.mozilla.org/en-US/docs/Web/API/Web_Authentication_API/Related_Origin_Requests
    """
    return {
        "origins": [
            "https://autoandbid.bg",
            "https://www.autoandbid.bg",
            "https://autoandbid.com",
            "https://www.autoandbid.com",
            "https://autoandbid.ro",
            "https://www.autoandbid.ro",
        ]
    }


# Two-way chat between users and admins/moderators.
from routers import chat as _chat_router
_chat = _chat_router.build_chat_router(db, get_current_user, require_admin_or_moderator)
app.include_router(_chat)

# Stripe Checkout — manual-capture authorization holds for bidding deposits.
# Card data is collected ONLY by Stripe's hosted Checkout — never by our website.
from routers import stripe_holds as _stripe_holds
_stripe_router = _stripe_holds.build_stripe_router(db, get_current_user)
app.include_router(_stripe_router)

# Leaderboard (top sellers/commenters/bidders + composite reputation).
# Self-contained; depends only on `db`. Extracted from server.py 2026-05-04.
from routers import leaderboard as _leaderboard_router
app.include_router(_leaderboard_router.build_leaderboard_router(db))

# Watchlist + /me/listings + /me/bids — extracted 2026-05-04.
from routers import watchlist as _watchlist_router
app.include_router(_watchlist_router.build_watchlist_router(
    db, get_current_user, _auction_status, _public_auction,
))


@api.get("/admin/bid-outbox")
async def admin_bid_outbox(_admin: dict = Depends(require_admin_or_moderator)):
    """Outbox health: pending count, dead-letter count, oldest pending age."""
    from services import outbox_worker
    return await outbox_worker.get_outbox_health()


@api.get("/admin/bid-outbox/dead-letter")
async def admin_bid_outbox_dead_letter(_admin: dict = Depends(require_admin_or_moderator)):
    from services import outbox_worker
    return await outbox_worker.list_dead_letter_events(limit=200)


@api.post("/admin/bid-outbox/{event_id}/retry")
async def admin_bid_outbox_retry(event_id: str, _admin: dict = Depends(require_admin)):
    from services import outbox_worker
    ok = await outbox_worker.retry_dead_letter_event(event_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Събитието не е намерено")
    return {"ok": True}


@api.post("/admin/stripe/lifecycle/scan")
async def admin_run_lifecycle_scan(_admin: dict = Depends(require_admin)):
    """Manually trigger the Stripe authorization extension scan.

    Returns counters: scanned / extended / failed / skipped_no_pm.
    Useful for forcing a sweep before the next hourly tick (e.g.
    after deploying or to test in staging). The scheduled background
    worker runs hourly regardless.
    """
    from services import stripe_lifecycle
    return await stripe_lifecycle.extend_expiring_authorizations(db)


@api.get("/health")
async def health_check():
    """Live status of every backing service the API depends on.

    Returns 200 OK as long as Mongo is reachable (Mongo is the primary store);
    PostgreSQL/outbox/push are reported as warning-level so admin panels can
    show a yellow indicator without paging the on-call team.

    Each subsystem is probed independently with a short timeout — one slow
    dependency should not block the whole health check.
    """
    import time
    from datetime import datetime, timezone, timedelta

    started = time.perf_counter()
    out: dict = {
        "status": "ok",
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "services": {},
    }

    async def _ping(coro, name: str, critical: bool):
        t0 = time.perf_counter()
        try:
            await asyncio.wait_for(coro, timeout=3.0)
            out["services"][name] = {
                "status": "ok",
                "latency_ms": round((time.perf_counter() - t0) * 1000, 1),
            }
        except Exception as e:
            out["services"][name] = {
                "status": "error",
                "error": str(e)[:160],
                "latency_ms": round((time.perf_counter() - t0) * 1000, 1),
            }
            if critical:
                out["status"] = "error"
            elif out["status"] == "ok":
                out["status"] = "degraded"

    # Mongo: cheap ping by counting users (covered by the index → fast).
    await _ping(db.command("ping"), "mongo", critical=True)

    # PostgreSQL: SELECT 1 round-trip via SQLAlchemy.
    async def _pg():
        from db_pg import engine
        from sqlalchemy import text
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))

    await _ping(_pg(), "postgres", critical=False)

    # Outbox worker: how many events are stuck in pending/dead state?
    async def _outbox():
        from db_pg import engine
        from sqlalchemy import text
        async with engine.connect() as conn:
            r = await conn.execute(text(
                "SELECT "
                "  COALESCE(SUM(CASE WHEN attempt_count > 0 AND attempt_count < 12 THEN 1 ELSE 0 END), 0) AS pending, "
                "  COALESCE(SUM(CASE WHEN attempt_count >= 12 THEN 1 ELSE 0 END), 0) AS dead "
                "FROM bid_events WHERE applied_at IS NULL"
            ))
            row = r.first()
            stats = {"pending": int(row[0]), "dead": int(row[1])} if row else {"pending": 0, "dead": 0}
            out["services"]["outbox"] = {
                "status": "error" if stats["dead"] > 0 else ("degraded" if stats["pending"] > 50 else "ok"),
                "pending": stats["pending"],
                "dead_letter": stats["dead"],
            }
            if stats["dead"] > 0 and out["status"] == "ok":
                out["status"] = "degraded"

    try:
        await asyncio.wait_for(_outbox(), timeout=3.0)
    except Exception as e:
        out["services"]["outbox"] = {"status": "unknown", "error": str(e)[:160]}

    # Push subscriptions count — sanity check.
    try:
        push_count = await db.push_subscriptions.count_documents({})
        out["services"]["push"] = {"status": "ok", "subscriptions": int(push_count)}
    except Exception as e:
        out["services"]["push"] = {"status": "unknown", "error": str(e)[:160]}

    # Active live auctions count — useful operations metric.
    try:
        live = await db.auctions.count_documents({"status": "live"})
        ending_soon = await db.auctions.count_documents({
            "status": "live",
            "ends_at": {"$lte": (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()},
        })
        out["services"]["auctions"] = {
            "status": "ok",
            "live": int(live),
            "ending_within_1h": int(ending_soon),
        }
    except Exception as e:
        out["services"]["auctions"] = {"status": "unknown", "error": str(e)[:160]}

    out["total_latency_ms"] = round((time.perf_counter() - started) * 1000, 1)
    return out


app.include_router(api)

app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=os.environ.get('CORS_ORIGINS', '*').split(','),
    allow_methods=["*"],
    allow_headers=["*"],
)

# NOTE: We deliberately do NOT add Starlette's `GZipMiddleware` here.
# It uses pure ASGI streaming and breaks `BaseHTTPMiddleware`-style
# decorator middlewares (waf, csrf, maintenance_mode) with
# `RuntimeError: No response returned.` — a known upstream issue.
# Compression is handled instead by:
#   • Cloudflare (production: autoandbid.bg / .ro / .com)
#   • nginx (Hetzner: gzip on, gzip_types application/json)
#   • k8s ingress (preview env): auto-gzips compressible MIME types
# All three apply on the wire, so JSON payloads still arrive ~80% smaller
# without us having to touch the FastAPI middleware stack.


# Serve uploaded images from disk when STORAGE_BACKEND=disk (default).
# This lets the disk storage backend return relative `/api/uploads/...` URLs
# that work behind the k8s preview ingress (which only routes `/api/*` to
# the backend) AND on a Hetzner deploy where nginx can short-circuit the
# same path. Both backend and reverse proxy share a single canonical
# directory configured via UPLOAD_DIR (default `/opt/autobids/uploads`;
# preview overrides via .env to keep files next to the code).
try:
    from fastapi.staticfiles import StaticFiles
    from starlette.responses import FileResponse  # for cache-header subclass

    class CachedStaticFiles(StaticFiles):
        """StaticFiles subclass that adds aggressive cache headers to
        content-addressed variant files. Filenames inside `/variants/`
        embed the sha256 of the source bytes, so the URL is *immutable*
        — we hand the client (and any CDN sitting in front of nginx)
        a `Cache-Control: public, max-age=31536000, immutable` header
        so they never re-fetch.

        Outside `/variants/` (legacy auction JPEGs uploaded before
        variant generation) we use a more conservative 7-day max-age
        because those URLs *could* still be re-uploaded.
        """
        async def get_response(self, path: str, scope):  # noqa: D401
            resp = await super().get_response(path, scope)
            if isinstance(resp, FileResponse):
                if path.startswith("variants/"):
                    resp.headers["Cache-Control"] = (
                        "public, max-age=31536000, immutable"
                    )
                else:
                    resp.headers["Cache-Control"] = "public, max-age=604800"
            return resp

    _UPLOAD_DIR = os.path.abspath(os.environ.get("UPLOAD_DIR", "/opt/autobids/uploads"))
    # Fail soft: if the target isn't creatable (e.g. read-only /app),
    # fall back to a temp dir so the app still boots. Disk storage will
    # attempt the same path again per-request and surface a 500 only on
    # the offending upload, never on unrelated routes.
    try:
        os.makedirs(_UPLOAD_DIR, exist_ok=True)
    except OSError as _e:
        logging.getLogger(__name__).warning(
            "UPLOAD_DIR %s is not writable (%s). Uploads will fail — "
            "check Ansible backend role + /opt/autobids/uploads permissions.",
            _UPLOAD_DIR, _e,
        )
    if os.path.isdir(_UPLOAD_DIR):
        # ── Lazy variant generation (CDN architecture, 2026-05-17) ──────
        # Nginx on the CDN subdomain (img.autoandbid.bg) uses
        # `try_files $uri @generate` for `/variants/`. On cold miss, the
        # @generate location proxies here. We mint the SPECIFIC variant
        # the browser asked for, write it to disk, and return the bytes.
        # The next request for the same URL hits nginx's `alias` directly
        # — zero backend involvement, zero uvicorn time.
        #
        # Path schema (matches `services.image_variants._variant_path`):
        #     /uploads/variants/<aa>/<bb>/<sha>/<size>.<ext>
        # where <aa> = sha[:2], <bb> = sha[2:4]. Both `/uploads/` and
        # `/api/uploads/` prefixes are accepted (legacy ingress).
        from fastapi import Path as _PathParam
        from fastapi.responses import Response as _FastResponse

        async def _lazy_variant(aa: str, bb: str, sha: str, name: str):
            from services.image_variants import generate_one_variant
            size_name, _dot, ext = name.rpartition(".")
            if not size_name or not ext:
                raise HTTPException(status_code=404, detail="Невалиден път")
            # Sanity-check shard prefixes — nginx only forwards
            # well-formed paths, but a curl-by-hand could bypass that.
            if not (len(sha) == 64 and sha[:2] == aa and sha[2:4] == bb
                    and all(c in "0123456789abcdef" for c in sha)):
                raise HTTPException(status_code=404, detail="Невалиден sha")
            data = generate_one_variant(sha, size_name, ext)
            if data is None:
                raise HTTPException(status_code=404, detail="Картинката не е намерена")
            media = {
                "avif": "image/avif", "webp": "image/webp",
                "jpg": "image/jpeg", "jpeg": "image/jpeg",
            }.get(ext.lower(), "application/octet-stream")
            return _FastResponse(
                content=data,
                media_type=media,
                headers={"Cache-Control": "public, max-age=31536000, immutable"},
            )

        @app.get("/uploads/variants/{aa}/{bb}/{sha}/{name}", include_in_schema=False)
        async def lazy_variant_clean(
            aa: str = _PathParam(..., min_length=2, max_length=2),
            bb: str = _PathParam(..., min_length=2, max_length=2),
            sha: str = _PathParam(..., min_length=64, max_length=64),
            name: str = _PathParam(...),
        ):
            return await _lazy_variant(aa, bb, sha, name)

        @app.get("/api/uploads/variants/{aa}/{bb}/{sha}/{name}", include_in_schema=False)
        async def lazy_variant_legacy(
            aa: str = _PathParam(..., min_length=2, max_length=2),
            bb: str = _PathParam(..., min_length=2, max_length=2),
            sha: str = _PathParam(..., min_length=64, max_length=64),
            name: str = _PathParam(...),
        ):
            return await _lazy_variant(aa, bb, sha, name)

        # Short path used by `img.autoandbid.bg/variants/...` (nginx
        # location `/variants/` rewrites the URI back to the backend
        # 1:1 on cold miss, without the `/uploads/` prefix).
        @app.get("/variants/{aa}/{bb}/{sha}/{name}", include_in_schema=False)
        async def lazy_variant_short(
            aa: str = _PathParam(..., min_length=2, max_length=2),
            bb: str = _PathParam(..., min_length=2, max_length=2),
            sha: str = _PathParam(..., min_length=64, max_length=64),
            name: str = _PathParam(...),
        ):
            return await _lazy_variant(aa, bb, sha, name)

        # Two mounts pointing at the same directory:
        #   • `/api/uploads/...` — legacy path used by the k8s preview
        #     ingress and by older listings already in MongoDB.
        #   • `/uploads/...` — clean path consumed by the CDN subdomain
        #     (`img.autoandbid.bg/uploads/...`). nginx on the frontend
        #     host proxies straight through to this mount.
        # Both serve the same content so old listings keep working while
        # new ones get CDN URLs.
        # NB: the lazy-variant routes above are registered BEFORE these
        # mounts so they take precedence for missing files (a present
        # variant file is served by StaticFiles first thanks to FastAPI's
        # route-then-mount resolution order).
        app.mount("/api/uploads", CachedStaticFiles(directory=_UPLOAD_DIR), name="uploads")
        app.mount("/uploads", CachedStaticFiles(directory=_UPLOAD_DIR), name="uploads_cdn")
except Exception as _e:  # pragma: no cover — never block boot on this
    logging.getLogger(__name__).warning("Could not mount /api/uploads: %s", _e)


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


# ---- Slug-suffix URL resolution for /api/auctions/... ----
# Frontend builds pretty URLs like `/auctions/bmw-m240i-xdrive-a1b2c3d4`.
# React-Router keeps that whole string as the `id` path param and the
# frontend API client forwards it to `/api/auctions/<slug-suffix>/...`.
# This middleware looks up the canonical auction UUID (by the 8-char
# suffix after the last `-`) and rewrites the path in-place BEFORE the
# router sees it — so every single `/auctions/{id}` handler (20+) keeps
# working without per-endpoint changes.
_UUID_RE = re.compile(r"^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}$", re.IGNORECASE)
_AUCTION_PATH_RE = re.compile(r"^/api/auctions/([^/]+)(/.*)?$")


async def _resolve_raw_auction_id(raw: str) -> Optional[str]:
    """Return the canonical auction UUID for a raw path segment — accepts
    either a full UUID (fast path, no DB hit) or a `slug-suffix` form where
    the suffix is the first 6-12 chars of the UUID. None if not found."""
    if not raw:
        return None
    if _UUID_RE.match(raw):
        return raw
    # Slug-suffix: last segment after the final '-'
    parts = raw.rsplit("-", 1)
    if len(parts) != 2:
        return None
    suffix = parts[1]
    if not re.fullmatch(r"[a-f0-9]{6,12}", suffix, re.IGNORECASE):
        return None
    doc = await db.auctions.find_one(
        {"id": {"$regex": f"^{re.escape(suffix.lower())}"}},
        {"_id": 0, "id": 1},
    )
    return doc["id"] if doc else None


@app.middleware("http")
async def auction_slug_middleware(request: Request, call_next):
    path = request.scope.get("path", "")
    m = _AUCTION_PATH_RE.match(path)
    if m:
        raw = m.group(1)
        # Fast path — already a canonical UUID, skip DB roundtrip.
        if not _UUID_RE.match(raw):
            canonical = await _resolve_raw_auction_id(raw)
            if canonical:
                rest = m.group(2) or ""
                new_path = f"/api/auctions/{canonical}{rest}"
                request.scope["path"] = new_path
                request.scope["raw_path"] = new_path.encode()
    return await call_next(request)


# ---- Social-bot share rewrite ------------------------------------------
# When a SOCIAL CRAWLER (Facebook, Twitter, Slack, WhatsApp, LinkedIn,
# Telegram, Discord…) hits the public-facing `/auctions/{slug-or-uuid}`
# URL, we rewrite the request to `/api/share/auction/{id}` so the bot
# receives our SSR-rendered HTML with rich Open Graph + Twitter Card +
# JSON-LD meta tags. Real users see the React SPA exactly as before.
#
# Matches the exact bot User-Agents documented at:
#   • https://developers.facebook.com/docs/sharing/webmasters/crawler/
#   • https://developer.twitter.com/en/docs/twitter-for-websites/cards/guides/getting-started
#   • https://api.slack.com/robots
#   • whatsapp / telegrambot / linkedinbot / discordbot — UA strings are stable
_SOCIAL_BOTS_RE = re.compile(
    r"(facebookexternalhit|facebot|twitterbot|slackbot|"
    r"whatsapp|telegrambot|linkedinbot|discordbot|"
    r"pinterestbot|skypeuripreview|redditbot|vkshare|"
    r"applebot|googlebot-image)",
    re.IGNORECASE,
)
_PUBLIC_AUCTION_PATH_RE = re.compile(r"^/auctions/([A-Za-z0-9_-]+)(?:/.*)?$")


@app.middleware("http")
async def social_bot_share_middleware(request: Request, call_next):
    method = request.method.upper()
    if method not in ("GET", "HEAD"):
        return await call_next(request)
    path = request.scope.get("path", "")
    m = _PUBLIC_AUCTION_PATH_RE.match(path)
    if not m:
        return await call_next(request)
    ua = (request.headers.get("user-agent") or "").lower()
    if not _SOCIAL_BOTS_RE.search(ua):
        return await call_next(request)
    raw = m.group(1)
    # Resolve the slug → canonical UUID. If we can't, fall through and let
    # the SPA render its own error page.
    if _UUID_RE.match(raw):
        canonical = raw
    else:
        canonical = await _resolve_raw_auction_id(raw)
    if not canonical:
        return await call_next(request)
    new_path = f"/api/share/auction/{canonical}"
    request.scope["path"] = new_path
    request.scope["raw_path"] = new_path.encode()
    return await call_next(request)


# ---- Deindex mode: stamp X-Robots-Tag on every response when enabled ----
# Admin can flip this via /admin/settings → Deindex mode. Use case: pre-launch
# sites that must remain fully testable but must NOT be indexed. We read the
# cached settings dict (zero DB round-trip per request) and short-circuit
# when disabled.
_NOINDEX_HEADER = "noindex, nofollow, noarchive, nosnippet"


@app.middleware("http")
async def deindex_headers_middleware(request: Request, call_next):
    response = await call_next(request)
    try:
        if _settings_cache.get("deindex_mode"):
            # Don't clobber an existing header set by a more specific handler
            response.headers.setdefault("X-Robots-Tag", _NOINDEX_HEADER)
    except Exception:
        pass
    return response


# ---- CSRF middleware (C3): double-submit cookie ----
# Защита срещу CSRF за заявки, автентикирани чрез httpOnly access_token cookie.
# Заявки с `Authorization: Bearer ...` (стар flow или сървърни тестове) или
# без access_token cookie се пропускат.  Webhook-овете и login/register нямат
# нужда от CSRF, защото или нямат cookie, или сами създават такъв.
_CSRF_EXEMPT_PATHS = (
    "/api/webhooks/",
    "/api/auth/login",
    "/api/auth/register",
    "/api/auth/forgot-password",
    "/api/auth/reset-password",
    "/api/auth/2fa/verify",
    "/api/auth/csrf",
)


@app.middleware("http")
async def csrf_middleware(request: Request, call_next):
    method = request.method.upper()
    if method in ("GET", "HEAD", "OPTIONS"):
        return await call_next(request)
    path = request.url.path or ""
    if not path.startswith("/api/"):
        return await call_next(request)
    if any(path == p or path.startswith(p) for p in _CSRF_EXEMPT_PATHS):
        return await call_next(request)
    # Bearer auth flow остава освободен (CSRF е невъзможна без четене на токена).
    auth_h = request.headers.get("Authorization", "")
    if auth_h.startswith("Bearer "):
        return await call_next(request)
    cookie_token = request.cookies.get("access_token")
    if not cookie_token:
        # Неавтентикирана заявка — нека endpoint-ът връща 401, ако се изисква auth.
        return await call_next(request)
    csrf_cookie = request.cookies.get("csrf_token") or ""
    csrf_header = request.headers.get("X-CSRF-Token") or request.headers.get("x-csrf-token") or ""
    import hmac as _hmac
    if not csrf_cookie or not csrf_header or not _hmac.compare_digest(csrf_cookie, csrf_header):
        from fastapi.responses import JSONResponse
        return JSONResponse({"detail": "CSRF токенът липсва или е невалиден."}, status_code=403)
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
    # Gracefully stop outbox worker before closing connections
    try:
        if hasattr(app.state, "_outbox_stop"):
            app.state._outbox_stop.set()
        if hasattr(app.state, "_outbox_task"):
            await asyncio.wait_for(app.state._outbox_task, timeout=5.0)
    except Exception as e:
        logger.warning("Outbox worker shutdown: %s", e)
    try:
        from services import stripe_lifecycle
        stripe_lifecycle.stop_worker()
    except Exception as e:
        logger.warning("Stripe lifecycle worker shutdown: %s", e)
    client.close()
