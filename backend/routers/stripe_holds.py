"""Stripe Checkout (manual capture / preauthorization holds) for auction bidding.

──────────────────────────────────────────────────────────────────────────────
Architecture
──────────────────────────────────────────────────────────────────────────────
1. The browser **never** handles raw card data — Stripe's hosted Checkout page
   collects the PAN. Our frontend only calls our backend to mint a Checkout
   Session URL and then `window.location` redirects there.

2. We open the Checkout in **manual-capture** mode (`capture_method=manual`)
   so the resulting PaymentIntent transitions to `requires_capture` — i.e.
   funds are HELD on the card but NOT yet charged.

3. Webhooks are the **source of truth**. We verify every webhook with
   `STRIPE_WEBHOOK_SECRET` and only mark an authorization as `active` after
   we've seen `payment_intent.amount_capturable_updated` or the PaymentIntent
   reaches `requires_capture`. We DO NOT trust the success-redirect alone.

4. Bidding gate: a user is allowed to place a bid on auction X only if she
   owns an authorization with `auction_id == X`, `status == "active"`, and
   `authorization_expires_at > now`. Expired holds are auto-marked.

5. Lifecycle:
       Checkout → requires_capture → ACTIVE  (bidding allowed)
       won      → capture          → CAPTURED
       lost     → cancel           → RELEASED
       expired  → mark expired     → EXPIRED
       failed   → mark failed      → FAILED

──────────────────────────────────────────────────────────────────────────────
Environment variables (test mode by default)
──────────────────────────────────────────────────────────────────────────────
  STRIPE_API_KEY            sk_test_… (already provisioned in this pod)
  STRIPE_WEBHOOK_SECRET     whsec_…   (set after configuring the endpoint
                                       in the Stripe Dashboard or stripe-cli)
  DEFAULT_FRONTEND_URL      Static-fallback origin used when the inbound
                            request has no allowed Origin/Referer (e.g.
                            CLI cron, server-to-server). FRONTEND_URL is
                            still honoured for backwards-compat.

Multi-domain redirects
──────────────────────────────────────────────────────────────────────────────
The site lives on three TLDs (.com, .bg, .ro) which DO NOT share
cookies. Stripe Checkout success/cancel URLs are therefore built
**dynamically** from the inbound request's Origin/Referer, validated
against an allow-list (`ALLOWED_PROD_ORIGINS` + dev preview patterns).
Hardcoded STRIPE_SUCCESS_URL / STRIPE_CANCEL_URL env overrides have
been **removed** — they would force every user back to one TLD.

To switch to live mode, swap STRIPE_API_KEY → sk_live_… and
STRIPE_WEBHOOK_SECRET to the live-mode whsec_…  No code changes needed.
"""
from __future__ import annotations
import os
import re
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

import stripe
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

logger = logging.getLogger(__name__)

# Authorization holds are valid for ~7 days (Stripe caps at 7 days for cards).
AUTHORIZATION_TTL_DAYS = 7

# Hold percentage of the bidder's stated bidding limit.
HOLD_PERCENT = 0.02
HOLD_MIN_EUR = 150.0
HOLD_MAX_EUR = 4000.0


def _hold_amount_eur(bidding_limit_eur: float) -> float:
    """Compute the deposit/buyer-premium hold for a given bidding limit.
    Backend-only — never accept the amount from the frontend."""
    raw = max(0.0, float(bidding_limit_eur or 0)) * HOLD_PERCENT
    return float(round(min(HOLD_MAX_EUR, max(HOLD_MIN_EUR, raw)), 2))


# ─── Stripe redirect origin resolver ─────────────────────────────────────
# autoandbid.bg and autoandbid.com intentionally do not share cookies
# (separate public suffixes), so returning a user from Stripe to the
# wrong host silently logs them out and loses the session/JWT. We must
# pick the *same* host the request came from.
#
# Security: we **never** trust an arbitrary Origin/Referer/body value.
# Each candidate must match either:
#   • A hard-coded allow-list of production hosts (the three TLDs we
#     actually own), OR
#   • A regex pattern for development / preview hosts (Emergent preview
#     subdomains, localhost), OR
#   • The DEFAULT_FRONTEND_URL env var verbatim.
# Anything else falls through to DEFAULT_FRONTEND_URL.
#
# Priority of candidates (first allowed wins):
#   1. Explicit `origin` from the request body (frontend passes
#      `window.location.origin`).
#   2. `Origin` header — set by browsers on CORS/preflighted requests.
#   3. Scheme+host parsed from `Referer` — set on normal navigations.
#   4. DEFAULT_FRONTEND_URL fallback (FRONTEND_URL retained for
#      backwards compat).
ALLOWED_PROD_ORIGINS = (
    "https://autoandbid.com",
    "https://www.autoandbid.com",
    "https://autoandbid.bg",
    "https://www.autoandbid.bg",
    "https://autoandbid.ro",
    "https://www.autoandbid.ro",
)

# Dev / preview origin allow-list. Keep these tight — only Emergent's
# own preview hostnames + localhost. Wildcarding anything broader would
# defeat the whole point of the whitelist.
_DEV_ORIGIN_PATTERNS = (
    re.compile(r"^https://[a-z0-9\-]+\.preview\.emergentagent\.com$", re.IGNORECASE),
    re.compile(r"^https://[a-z0-9\-]+\.cluster-[a-z0-9\-]+\.preview\.emergentcf\.cloud$", re.IGNORECASE),
    re.compile(r"^https://[a-z0-9\-]+\.preview\.emergentcf\.cloud$", re.IGNORECASE),
    re.compile(r"^http://localhost(:\d+)?$", re.IGNORECASE),
    re.compile(r"^http://127\.0\.0\.1(:\d+)?$", re.IGNORECASE),
)


def _default_frontend_url() -> str:
    """Static fallback origin. `DEFAULT_FRONTEND_URL` is the new
    canonical name; `FRONTEND_URL` is kept for backwards compatibility
    with older deployments."""
    raw = (
        os.environ.get("DEFAULT_FRONTEND_URL")
        or os.environ.get("FRONTEND_URL")
        or "https://autoandbid.com"
    )
    return raw.strip().rstrip("/")


def _is_allowed_origin(origin: str) -> bool:
    """Return True iff `origin` matches the production allow-list, the
    dev preview pattern set, or the env-configured default."""
    if not origin:
        return False
    o = str(origin).strip().rstrip("/")
    if not (o.startswith("http://") or o.startswith("https://")):
        return False
    if o in ALLOWED_PROD_ORIGINS:
        return True
    for pat in _DEV_ORIGIN_PATTERNS:
        if pat.match(o):
            return True
    if o == _default_frontend_url():
        return True
    return False


def resolve_stripe_redirect_origin(body_origin: Optional[str], request) -> str:
    """Pick the redirect origin for a Stripe Checkout session.

    Each candidate is validated against the allow-list before being
    returned. Untrusted values (e.g. an attacker-supplied Origin header
    pointing at evil.com) are silently dropped and we fall through to
    the configured DEFAULT_FRONTEND_URL.
    """
    from urllib.parse import urlparse
    candidates: list[str] = []
    if body_origin:
        candidates.append(str(body_origin))
    try:
        oh = request.headers.get("origin")
        if oh:
            candidates.append(oh)
        ref = request.headers.get("referer")
        if ref:
            parsed = urlparse(ref)
            if parsed.scheme and parsed.netloc:
                candidates.append(f"{parsed.scheme}://{parsed.netloc}")
    except Exception:
        pass
    for c in candidates:
        c2 = str(c).strip().rstrip("/")
        if _is_allowed_origin(c2):
            return c2
    # Final fallback — guaranteed-safe configured default.
    return _default_frontend_url()





class CreateAuthBody(BaseModel):
    auction_id: str
    bidding_limit_eur: float
    origin: Optional[str] = None  # frontend's window.location.origin
    use_saved_card: Optional[bool] = False  # ако True и user има saved PM, ползвай него


class SetupCardBody(BaseModel):
    origin: Optional[str] = None  # frontend's window.location.origin


async def _get_or_create_stripe_customer(db, user: dict) -> str:
    """Връща `stripe_customer_id` за този потребител; създава, ако липсва."""
    cid = user.get("stripe_customer_id")
    if cid:
        return cid
    try:
        customer = stripe.Customer.create(
            email=user.get("email"),
            name=user.get("name") or user.get("email"),
            metadata={"user_id": user["id"]},
        )
    except stripe.error.AuthenticationError as e:
        logger.error("[stripe] customer.create auth failed (placeholder API key?): %s", e)
        raise HTTPException(status_code=503, detail="Stripe API ключът не е валиден. Свържете се с администратор.")
    except stripe.error.StripeError as e:
        raise HTTPException(status_code=502, detail=f"Stripe грешка: {getattr(e, 'user_message', str(e))}")
    cid = customer["id"]
    await db.users.update_one({"id": user["id"]}, {"$set": {"stripe_customer_id": cid}})
    return cid


async def _saved_card_brief(db, user: dict) -> Optional[dict]:
    """Чете запазената карта (ако има) и връща {brand, last4, exp_month, exp_year, pm_id}."""
    pm_id = user.get("stripe_default_payment_method_id")
    if not pm_id:
        return None
    try:
        pm = stripe.PaymentMethod.retrieve(pm_id)
        card = pm.get("card") or {}
        return {
            "pm_id": pm_id,
            "brand": card.get("brand"),
            "last4": card.get("last4"),
            "exp_month": card.get("exp_month"),
            "exp_year": card.get("exp_year"),
        }
    except stripe.error.StripeError as e:
        logger.warning("[stripe] saved PM retrieve failed: %s", e)
        return None


def build_stripe_router(db, get_current_user):
    router = APIRouter(prefix="/api/stripe", tags=["stripe"])
    api_key = os.environ.get("STRIPE_API_KEY", "")
    webhook_secret = os.environ.get("STRIPE_WEBHOOK_SECRET", "")
    if api_key:
        stripe.api_key = api_key

    # ─── Slug → canonical UUID resolver ──────────────────────────────────
    # The `/api/auctions/{id}` middleware rewrites slug-suffix URLs on the
    # path, but endpoints that receive the id via request body or query
    # param (e.g. `/stripe/authorizations/create-checkout`) bypass that
    # rewrite. Without this helper, clicking "Оторизирай и наддай" on a
    # slug-URL (`/auctions/bmw-m2-...-5a476c7a`) would send the raw slug
    # to Stripe-side endpoints, the Mongo lookup would miss, and the
    # user would see "Търгът не е намерен".
    import re as _re
    _UUID_RE = _re.compile(
        r"^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}$",
        _re.IGNORECASE,
    )

    async def _resolve_auction_id(raw: str) -> Optional[str]:
        """Return the canonical UUID for either a raw UUID or a
        `slug-<6-12-hex-chars>` string. Falls back to `None` when the
        suffix matches nothing."""
        if not raw:
            return None
        if _UUID_RE.match(raw):
            return raw
        parts = raw.rsplit("-", 1)
        if len(parts) != 2:
            return None
        suffix = parts[1]
        if not _re.fullmatch(r"[a-f0-9]{6,12}", suffix, _re.IGNORECASE):
            return None
        doc = await db.auctions.find_one(
            {"id": {"$regex": f"^{_re.escape(suffix.lower())}"}},
            {"_id": 0, "id": 1},
        )
        return doc["id"] if doc else None

    @router.get("/config")
    async def stripe_config():
        """Returns whether Stripe is wired (test/live indicator)."""
        return {
            "configured": bool(api_key),
            "mode": "live" if api_key.startswith("sk_live_") else "test",
            "hold_percent": HOLD_PERCENT,
            "hold_min_eur": HOLD_MIN_EUR,
            "hold_max_eur": HOLD_MAX_EUR,
            "ttl_days": AUTHORIZATION_TTL_DAYS,
        }

    @router.post("/authorizations/create-checkout")
    async def create_checkout(body: CreateAuthBody, request: Request, user: dict = Depends(get_current_user)):
        """Mint a Stripe Checkout Session that places a hold (manual capture).

        Frontend calls this with `auction_id` and a `bidding_limit_eur`.
        Backend computes the hold amount, creates the Session, and returns
        the URL — the browser then `location.href = url` to redirect.

        Ако `use_saved_card=True` и user има запазена карта, се прави директен
        off-session PaymentIntent.create(capture_method=manual) и не се
        изисква redirect — функцията връща `{redirect: false, status: ...}`.
        """
        if not api_key:
            raise HTTPException(status_code=503, detail="Stripe не е конфигуриран. Свържете се с администратор.")
        # Accept either canonical UUID or a slug-suffix string (the URL
        # param passed down from `AuctionDetailPage`). All downstream DB
        # lookups and Stripe metadata use the canonical id.
        canonical_id = await _resolve_auction_id(body.auction_id)
        if not canonical_id:
            raise HTTPException(status_code=404, detail="Търгът не е намерен")
        body.auction_id = canonical_id
        # ---- Validate auction ----
        a = await db.auctions.find_one({"id": body.auction_id}, {"_id": 0, "id": 1, "title": 1, "status": 1, "seller_id": 1})
        if not a:
            raise HTTPException(status_code=404, detail="Търгът не е намерен")
        if a.get("status") != "live":
            raise HTTPException(status_code=400, detail="Само активни търгове позволяват авторизация.")
        if user["id"] == a.get("seller_id"):
            raise HTTPException(status_code=400, detail="Не можете да авторизирате карта за собствения си търг.")

        # ---- Compute amount server-side (NEVER trust frontend) ----
        amount_eur = _hold_amount_eur(body.bidding_limit_eur)
        amount_cents = int(round(amount_eur * 100))

        # ---- Saved-card fast path: off-session PaymentIntent ----
        if body.use_saved_card and user.get("stripe_default_payment_method_id"):
            try:
                customer_id = await _get_or_create_stripe_customer(db, user)
                pi = stripe.PaymentIntent.create(
                    amount=amount_cents,
                    currency="eur",
                    customer=customer_id,
                    payment_method=user["stripe_default_payment_method_id"],
                    off_session=True,
                    confirm=True,
                    capture_method="manual",
                    description=f"Hold за търг: {a.get('title','')[:90]}",
                    metadata={
                        "user_id": user["id"],
                        "auction_id": body.auction_id,
                        "bidding_limit_eur": str(round(float(body.bidding_limit_eur), 2)),
                        "authorization_type": "auction_bid_hold",
                        "use_saved_card": "1",
                    },
                )
            except stripe.error.CardError as e:
                # Картата изисква 3D Secure / друга верификация → fall back to redirect.
                logger.info("[stripe] off-session PI failed (CardError): %s — falling back to Checkout", e)
            except stripe.error.StripeError as e:
                logger.warning("[stripe] off-session PI error: %s — falling back to Checkout", e)
            else:
                now = datetime.now(timezone.utc)
                doc = {
                    "id": pi["id"],  # използваме PI id като canonical id за този flow
                    "stripe_checkout_session_id": None,
                    "stripe_payment_intent_id": pi["id"],
                    "user_id": user["id"],
                    "auction_id": body.auction_id,
                    "bidding_limit_eur": float(body.bidding_limit_eur),
                    "amount_authorized_eur": amount_eur,
                    "amount_captured_eur": 0.0,
                    "currency": "eur",
                    "authorization_status": "active" if pi["status"] == "requires_capture" else "pending",
                    "authorization_expires_at": (now + timedelta(days=AUTHORIZATION_TTL_DAYS)).isoformat(),
                    "created_at": now.isoformat(),
                    "updated_at": now.isoformat(),
                    "via_saved_card": True,
                }
                await db.bid_authorizations.insert_one(doc)
                logger.info("[stripe] off-session PI %s for user=%s auction=%s amount=%s EUR status=%s",
                            pi["id"], user["id"], body.auction_id, amount_eur, pi["status"])
                return {
                    "redirect": False,
                    "id": pi["id"],
                    "status": doc["authorization_status"],
                    "amount_eur": amount_eur,
                }

        # ---- Build URLs ----
        # Domain-aware: the user is sent back to the same TLD they
        # checked out from (.bg / .ro / .com). Hardcoded
        # STRIPE_SUCCESS_URL / STRIPE_CANCEL_URL env overrides have
        # been removed — they made multi-domain returns impossible.
        origin = resolve_stripe_redirect_origin(body.origin, request)
        success_url = f"{origin}/auctions/{body.auction_id}?stripe_session_id={{CHECKOUT_SESSION_ID}}"
        cancel_url = f"{origin}/auctions/{body.auction_id}?stripe_cancelled=1"

        try:
            session = stripe.checkout.Session.create(
                mode="payment",
                line_items=[{
                    "price_data": {
                        "currency": "eur",
                        "product_data": {
                            "name": "Авторизация за наддаване",
                            "description": f"Депозит за търг: {a.get('title','')[:90]}",
                        },
                        "unit_amount": amount_cents,
                    },
                    "quantity": 1,
                }],
                # MANUAL CAPTURE → funds are held, not charged.
                # Capture happens later when the bidder wins (capture endpoint).
                # Cancel happens when the bidder loses (cancel endpoint).
                payment_intent_data={
                    "capture_method": "manual",
                    "setup_future_usage": "off_session",  # позволи запазване след success
                    "metadata": {
                        "user_id": user["id"],
                        "auction_id": body.auction_id,
                        "bidding_limit_eur": str(round(float(body.bidding_limit_eur), 2)),
                        "authorization_type": "auction_bid_hold",
                    },
                },
                metadata={
                    "user_id": user["id"],
                    "auction_id": body.auction_id,
                    "bidding_limit_eur": str(round(float(body.bidding_limit_eur), 2)),
                },
                success_url=success_url,
                cancel_url=cancel_url,
            )
        except stripe.error.StripeError as e:
            logger.exception("stripe.checkout.create failed")
            raise HTTPException(status_code=502, detail=f"Stripe error: {getattr(e, 'user_message', str(e))}")

        # Persist a pending authorization record. Webhook updates state to active.
        now = datetime.now(timezone.utc)
        doc = {
            "id": session["id"],  # stripe_checkout_session_id is the canonical id
            "stripe_checkout_session_id": session["id"],
            "stripe_payment_intent_id": getattr(session, "payment_intent", None),
            "user_id": user["id"],
            "auction_id": body.auction_id,
            "bidding_limit_eur": float(body.bidding_limit_eur),
            "amount_authorized_eur": amount_eur,
            "amount_captured_eur": 0.0,
            "currency": "eur",
            "authorization_status": "pending",  # pending → active → captured/released/expired/failed
            "authorization_expires_at": (now + timedelta(days=AUTHORIZATION_TTL_DAYS)).isoformat(),
            "created_at": now.isoformat(),
            "updated_at": now.isoformat(),
        }
        await db.bid_authorizations.insert_one(doc)
        logger.info("[stripe] checkout.session.created %s for user=%s auction=%s amount=%s EUR",
                    session["id"], user["id"], body.auction_id, amount_eur)
        return {"redirect": True, "id": session["id"], "url": session["url"], "amount_eur": amount_eur}

    # ---- Saved cards (Stripe SetupIntent flow) ----

    @router.post("/cards/setup-checkout")
    async def setup_card_checkout(body: SetupCardBody, request: Request, user: dict = Depends(get_current_user)):
        """Създава Stripe Checkout Session в `mode=setup`, която записва
        картата на потребителя без да я таксува.  След redirect frontend-ът
        вика `/cards/finalize` с върнатия `session_id`.
        """
        if not api_key:
            raise HTTPException(status_code=503, detail="Stripe не е конфигуриран.")
        customer_id = await _get_or_create_stripe_customer(db, user)
        origin = resolve_stripe_redirect_origin(body.origin, request)
        success_url = f"{origin}/settings?stripe_setup_session_id={{CHECKOUT_SESSION_ID}}"
        cancel_url = f"{origin}/settings?stripe_setup_cancelled=1"
        try:
            session = stripe.checkout.Session.create(
                mode="setup",
                customer=customer_id,
                payment_method_types=["card"],
                success_url=success_url,
                cancel_url=cancel_url,
                metadata={"user_id": user["id"], "purpose": "save_card"},
            )
        except stripe.error.StripeError as e:
            logger.exception("stripe setup checkout failed")
            raise HTTPException(status_code=502, detail=f"Stripe error: {getattr(e, 'user_message', str(e))}")
        return {"id": session["id"], "url": session["url"]}

    @router.post("/cards/finalize")
    async def finalize_saved_card(body: dict, user: dict = Depends(get_current_user)):
        """След redirect от Stripe — взема SetupIntent от session, attach-ва
        PaymentMethod към customer-а и записва default PM в user документа."""
        if not api_key:
            raise HTTPException(status_code=503, detail="Stripe не е конфигуриран.")
        sid = (body or {}).get("session_id") or ""
        if not sid:
            raise HTTPException(status_code=400, detail="session_id липсва")
        try:
            session = stripe.checkout.Session.retrieve(sid, expand=["setup_intent"])
        except stripe.error.StripeError as e:
            raise HTTPException(status_code=502, detail=f"Stripe retrieve: {e}")
        # Сигурност: session трябва да е на този потребител.
        # Stripe's `StripeObject` (SDK ≥ 8) is **not** a dict subclass —
        # `.get()` is missing entirely. Use attribute access with a
        # safe fallback so wrong-user sessions are still rejected.
        session_metadata = getattr(session, "metadata", None) or {}
        if isinstance(session_metadata, dict):
            uid = session_metadata.get("user_id")
        else:
            uid = getattr(session_metadata, "user_id", None)
        if uid != user["id"]:
            raise HTTPException(status_code=403, detail="Сесията не принадлежи на този потребител.")
        si = getattr(session, "setup_intent", None) or {}
        pm_id = (
            getattr(si, "payment_method", None)
            if hasattr(si, "payment_method") or isinstance(si, dict)
            else None
        )
        if not pm_id and isinstance(si, dict):
            pm_id = si.get("payment_method")
        if not pm_id:
            raise HTTPException(status_code=400, detail="SetupIntent не е завършен — карта не е записана.")
        customer_id = await _get_or_create_stripe_customer(db, user)
        try:
            stripe.PaymentMethod.attach(pm_id, customer=customer_id)
            stripe.Customer.modify(customer_id, invoice_settings={"default_payment_method": pm_id})
        except stripe.error.InvalidRequestError as e:
            # Може вече да е attach-нат — игнорирай това състояние
            if "already been attached" not in str(e):
                raise HTTPException(status_code=502, detail=f"Attach failed: {e}")
        except stripe.error.StripeError as e:
            raise HTTPException(status_code=502, detail=f"Stripe error: {e}")
        await db.users.update_one(
            {"id": user["id"]},
            {"$set": {
                "stripe_default_payment_method_id": pm_id,
                "stripe_customer_id": customer_id,
                "stripe_card_saved_at": datetime.now(timezone.utc).isoformat(),
            }},
        )
        # Зарежда card brief за return
        fresh = await db.users.find_one({"id": user["id"]}, {"_id": 0})
        brief = await _saved_card_brief(db, fresh)
        return {"ok": True, "card": brief}

    @router.get("/cards/saved")
    async def get_saved_card(user: dict = Depends(get_current_user)):
        """Връща brief на запазената карта (brand, last4, exp) или null."""
        if not api_key:
            return {"card": None}
        return {"card": await _saved_card_brief(db, user)}

    @router.delete("/cards/saved")
    async def delete_saved_card(user: dict = Depends(get_current_user)):
        """Detach-ва картата от Stripe customer-а и изчиства user.default_pm."""
        pm_id = user.get("stripe_default_payment_method_id")
        if pm_id and api_key:
            try:
                stripe.PaymentMethod.detach(pm_id)
            except stripe.error.StripeError as e:
                logger.warning("[stripe] detach failed: %s — clearing user doc anyway", e)
        await db.users.update_one(
            {"id": user["id"]},
            {"$unset": {"stripe_default_payment_method_id": ""}},
        )
        return {"ok": True}

    async def _promote_pending_authorizations(user_id: str, auction_id: Optional[str] = None) -> int:
        """Polling fallback for missing Stripe webhooks.

        Stripe webhooks are the source of truth for `pending → active`
        transitions, but in prod they can fail silently when the
        webhook secret is wrong, the endpoint isn't registered, or
        Cloudflare blocks the inbound request. Without a fallback the
        user sees their card charged on Stripe but no credit on our
        site.

        This helper queries Stripe directly for any `pending` rows
        belonging to the user (optionally narrowed to one auction) and
        promotes them to `active` when the underlying PaymentIntent is
        in `requires_capture`. Idempotent — safe to call on every
        read.
        """
        if not api_key:
            return 0
        q = {"user_id": user_id, "authorization_status": "pending"}
        if auction_id:
            q["auction_id"] = auction_id
        promoted = 0
        pending_count = await db.bid_authorizations.count_documents(q)
        if pending_count:
            logger.info("[stripe.promote] checking %d pending row(s) for user=%s", pending_count, user_id)
        async for row in db.bid_authorizations.find(q, {"_id": 0}):
            sid = row.get("stripe_checkout_session_id") or row.get("id")
            pi_id = row.get("stripe_payment_intent_id")
            try:
                # Prefer the PI if we already have it; otherwise pull
                # the Checkout Session and follow the link. Two extra
                # round-trips at most; runs only once per pending row.
                if not pi_id and sid:
                    sess = stripe.checkout.Session.retrieve(sid)
                    pi_id = getattr(sess, "payment_intent", None) or (
                        sess.get("payment_intent") if isinstance(sess, dict) else None
                    )
                if not pi_id:
                    continue
                pi = stripe.PaymentIntent.retrieve(pi_id)
                status = pi["status"]
                now_iso = datetime.now(timezone.utc).isoformat()
                if status == "requires_capture":
                    await db.bid_authorizations.update_one(
                        {"id": row["id"]},
                        {"$set": {
                            "authorization_status": "active",
                            "stripe_payment_intent_id": pi_id,
                            "amount_authorized_eur": round(int(pi.get("amount_capturable", 0)) / 100.0, 2),
                            "updated_at": now_iso,
                        }},
                    )
                    promoted += 1
                    logger.info("[stripe] promoted pending→active via polling: auth=%s pi=%s", row["id"], pi_id)
                elif status in ("canceled",):
                    await db.bid_authorizations.update_one(
                        {"id": row["id"]},
                        {"$set": {"authorization_status": "released",
                                  "released_at": now_iso, "updated_at": now_iso}},
                    )
                elif status in ("requires_payment_method", "requires_action"):
                    # Still in the middle of 3DS — leave pending.
                    pass
            except stripe.error.StripeError as e:
                logger.warning("[stripe] promote check failed for auth %s: %s", row.get("id"), e)
                continue
        return promoted

    @router.get("/authorizations/active")
    async def my_active_authorization(auction_id: str, user: dict = Depends(get_current_user)):
        """Return the user's currently active hold for this auction (if any)."""
        await _expire_stale_authorizations(db)
        # Mirror `create_checkout`: the frontend may pass either a
        # canonical UUID or a slug-suffix string. Always resolve first.
        canonical_id = await _resolve_auction_id(auction_id)
        if not canonical_id:
            return {}
        # Fallback: if the Stripe webhook never arrived (wrong secret,
        # blocked endpoint, etc.) we still need to surface the active
        # hold to the bidder. Query Stripe directly for any pending row
        # on this auction.
        await _promote_pending_authorizations(user["id"], canonical_id)
        doc = await db.bid_authorizations.find_one(
            {
                "user_id": user["id"],
                "auction_id": canonical_id,
                "authorization_status": "active",
            },
            {"_id": 0, "id": 1, "amount_authorized_eur": 1, "bidding_limit_eur": 1,
             "authorization_expires_at": 1, "currency": 1, "stripe_payment_intent_id": 1,
             "authorization_status": 1},
        )
        return doc or {}

    @router.get("/authorizations/my-credits")
    async def my_credits_summary(user: dict = Depends(get_current_user)):
        """Return a rolled-up view of the user's bidding credits. Powers
        the profile-menu counter AND the /my-bids page header.

        `available_eur` = bidding_limit - already-committed (current high
        bid on the auction the hold is tied to). This matches the mental
        model "how much I can still spend" shown in the UI bell section.
        """
        await _expire_stale_authorizations(db)
        # Promote any pending rows that have already been authorized on
        # Stripe but whose webhook never reached us — without this, a
        # user who just paid sees a `0€/0€` counter even though their
        # card has been held.
        await _promote_pending_authorizations(user["id"])
        cursor = db.bid_authorizations.find(
            {"user_id": user["id"],
             "authorization_status": {"$in": ["active", "loser_grace"]}},
            {"_id": 0, "id": 1, "auction_id": 1, "bidding_limit_eur": 1,
             "amount_authorized_eur": 1, "authorization_status": 1,
             "authorization_expires_at": 1, "currency": 1},
        )
        rows = await cursor.to_list(200)
        if not rows:
            return {"holds": [], "total_hold_eur": 0.0, "total_limit_eur": 0.0,
                    "total_available_eur": 0.0, "count": 0}

        # Pull current bids for all involved auctions in a single batched
        # query (avoid N+1 round-trips on users with many active holds).
        auction_ids = [r["auction_id"] for r in rows]
        a_cursor = db.auctions.find(
            {"id": {"$in": auction_ids}},
            {"_id": 0, "id": 1, "title": 1, "current_bid_eur": 1,
             "high_bidder_id": 1, "status": 1, "slug": 1, "ends_at": 1,
             "thumbnails": 1, "images": 1},
        )
        by_id = {a["id"]: a async for a in a_cursor}

        out_holds = []
        total_limit = 0.0
        total_hold = 0.0
        total_avail = 0.0
        for r in rows:
            a = by_id.get(r["auction_id"], {})
            limit = float(r.get("bidding_limit_eur") or 0)
            hold = float(r.get("amount_authorized_eur") or 0)
            # `current_bid` on an auction where the user is high-bidder
            # counts toward "used" credits. Lost-race auctions return
            # full limit back to available.
            is_leading = a.get("high_bidder_id") == user["id"]
            used = float(a.get("current_bid_eur") or 0) if is_leading else 0.0
            available = max(0.0, limit - used)
            total_limit += limit
            total_hold += hold
            total_avail += available
            out_holds.append({
                "authorization_id": r["id"],
                "auction_id": r["auction_id"],
                "auction_title": a.get("title", ""),
                "auction_slug": a.get("slug"),
                "auction_status": a.get("status"),
                "auction_ends_at": a.get("ends_at"),
                "auction_thumb": (a.get("thumbnails") or a.get("images") or [None])[0],
                "bidding_limit_eur": round(limit, 2),
                "hold_eur": round(hold, 2),
                "current_bid_eur": float(a.get("current_bid_eur") or 0),
                "is_leading": is_leading,
                "available_eur": round(available, 2),
                "authorization_status": r.get("authorization_status"),
                "expires_at": r.get("authorization_expires_at"),
                "currency": r.get("currency") or "eur",
            })
        return {
            "holds": out_holds,
            "count": len(out_holds),
            "total_limit_eur": round(total_limit, 2),
            "total_hold_eur": round(total_hold, 2),
            "total_available_eur": round(total_avail, 2),
        }

    @router.post("/authorizations/{auth_id}/release")
    async def release_authorization_route(auth_id: str, user: dict = Depends(get_current_user)):
        """User-initiated release of a hold. The user may release a hold
        **only** if they are not currently the highest bidder on its
        auction — otherwise we'd cancel their own winning bid. For
        already-finalized auctions we always allow release so the user
        can instantly free their card.
        """
        doc = await db.bid_authorizations.find_one(
            {"id": auth_id, "user_id": user["id"]},
            {"_id": 0},
        )
        if not doc:
            raise HTTPException(status_code=404, detail="Авторизация не е намерена.")
        if doc.get("authorization_status") == "released":
            return {"ok": True, "already_released": True}
        if doc.get("authorization_status") not in ("active", "loser_grace"):
            raise HTTPException(status_code=400, detail="Тази авторизация не може да се освободи ръчно.")

        a = await db.auctions.find_one(
            {"id": doc["auction_id"]},
            {"_id": 0, "high_bidder_id": 1, "status": 1},
        ) or {}
        if a.get("status") in ("live", "scheduled") and a.get("high_bidder_id") == user["id"]:
            raise HTTPException(
                status_code=409,
                detail="Не можете да освободите — вие сте текущ лидер. Изчакайте някой да Ви надмине или търгът да приключи.",
            )
        try:
            return await cancel_authorization(db, auth_id)
        except Exception as e:
            logger.exception("manual release failed")
            raise HTTPException(status_code=502, detail=f"Stripe release failed: {e}")


    @router.post("/webhook")
    async def stripe_webhook(request: Request):
        """Stripe webhook — verifies signature, transitions authorization state.

        Subscribed events:
            checkout.session.completed                  → mark active (if PI in requires_capture)
            payment_intent.amount_capturable_updated    → mark active
            payment_intent.canceled                     → mark released
            payment_intent.payment_failed               → mark failed
            checkout.session.expired                    → mark expired
        """
        if not webhook_secret:
            logger.warning("[stripe] webhook hit but STRIPE_WEBHOOK_SECRET is empty — refusing")
            raise HTTPException(status_code=503, detail="Webhook signing secret not configured")
        body = await request.body()
        sig = request.headers.get("stripe-signature", "")
        try:
            event = stripe.Webhook.construct_event(body, sig, webhook_secret)
        except Exception as e:
            logger.warning("[stripe] webhook signature verification failed: %s", e)
            raise HTTPException(status_code=400, detail="Invalid signature")

        # Idempotency: Stripe will retry on 5xx and may deliver an event up
        # to 3 days. Reject duplicate events so we don't double-apply state.
        event_id = event.get("id")
        if event_id:
            try:
                await db.stripe_processed_events.insert_one({
                    "id": event_id,
                    "type": event.get("type"),
                    "received_at": datetime.now(timezone.utc).isoformat(),
                })
            except Exception:
                # Duplicate key → already processed. Acknowledge with 200 so
                # Stripe stops retrying.
                logger.info("[stripe] duplicate webhook %s ignored", event_id)
                return {"received": True, "duplicate": True}

        et = event["type"]
        obj = event["data"]["object"]
        now_iso = datetime.now(timezone.utc).isoformat()

        if et == "checkout.session.completed":
            session_id = obj["id"]
            pi_id = obj.get("payment_intent")
            update = {"updated_at": now_iso}
            if pi_id:
                update["stripe_payment_intent_id"] = pi_id
                # Pull the PaymentIntent to confirm it is in requires_capture
                try:
                    pi = stripe.PaymentIntent.retrieve(pi_id)
                    if pi["status"] == "requires_capture":
                        update["authorization_status"] = "active"
                        update["amount_authorized_eur"] = round(int(pi.get("amount_capturable", 0)) / 100.0, 2)
                except stripe.error.StripeError as e:
                    logger.warning("[stripe] PI retrieve failed in webhook: %s", e)
            await db.bid_authorizations.update_one({"id": session_id}, {"$set": update})

        elif et == "payment_intent.amount_capturable_updated":
            pi_id = obj["id"]
            await db.bid_authorizations.update_one(
                {"stripe_payment_intent_id": pi_id},
                {"$set": {"authorization_status": "active", "updated_at": now_iso,
                          "amount_authorized_eur": round(int(obj.get("amount_capturable", 0)) / 100.0, 2)}},
            )

        elif et == "payment_intent.canceled":
            pi_id = obj["id"]
            await db.bid_authorizations.update_one(
                {"stripe_payment_intent_id": pi_id},
                {"$set": {"authorization_status": "released", "released_at": now_iso, "updated_at": now_iso}},
            )

        elif et == "payment_intent.payment_failed":
            pi_id = obj["id"]
            await db.bid_authorizations.update_one(
                {"stripe_payment_intent_id": pi_id},
                {"$set": {"authorization_status": "failed", "updated_at": now_iso}},
            )

        elif et == "checkout.session.expired":
            session_id = obj["id"]
            await db.bid_authorizations.update_one(
                {"id": session_id, "authorization_status": "pending"},
                {"$set": {"authorization_status": "expired", "updated_at": now_iso}},
            )

        elif et == "payment_intent.succeeded":
            # Will arrive after we capture. Just log captured_amount.
            pi_id = obj["id"]
            captured = round(int(obj.get("amount_received", 0)) / 100.0, 2)
            await db.bid_authorizations.update_one(
                {"stripe_payment_intent_id": pi_id},
                {"$set": {"authorization_status": "captured",
                          "amount_captured_eur": captured,
                          "captured_at": now_iso, "updated_at": now_iso}},
            )

        return {"ok": True, "type": et}

    return router


# ---- Capture / Cancel helpers (called from auction finalization elsewhere) ----

async def capture_authorization(db, auth_id: str, amount_eur: Optional[float] = None) -> dict:
    """Capture a held PaymentIntent. If `amount_eur` is None, captures the full hold."""
    auth = await db.bid_authorizations.find_one({"id": auth_id}, {"_id": 0})
    if not auth:
        raise HTTPException(status_code=404, detail="Authorization not found")
    if auth["authorization_status"] != "active":
        raise HTTPException(status_code=400, detail=f"Cannot capture — status={auth['authorization_status']}")
    pi_id = auth.get("stripe_payment_intent_id")
    if not pi_id:
        raise HTTPException(status_code=400, detail="No payment_intent recorded")
    kwargs = {}
    if amount_eur is not None:
        kwargs["amount_to_capture"] = int(round(float(amount_eur) * 100))
    try:
        pi = stripe.PaymentIntent.capture(pi_id, **kwargs)
    except stripe.error.StripeError as e:
        logger.exception("[stripe] capture failed")
        raise HTTPException(status_code=502, detail=f"Capture failed: {e}")
    captured = round(int(pi.get("amount_received", 0)) / 100.0, 2)
    now_iso = datetime.now(timezone.utc).isoformat()
    await db.bid_authorizations.update_one(
        {"id": auth_id},
        {"$set": {"authorization_status": "captured", "amount_captured_eur": captured,
                  "captured_at": now_iso, "updated_at": now_iso}},
    )
    return {"ok": True, "captured_eur": captured}


async def cancel_authorization(db, auth_id: str) -> dict:
    """Release the hold (cancel the PaymentIntent) — used when the bidder loses."""
    auth = await db.bid_authorizations.find_one({"id": auth_id}, {"_id": 0})
    if not auth:
        raise HTTPException(status_code=404, detail="Authorization not found")
    if auth["authorization_status"] not in ("active", "pending", "loser_grace"):
        return {"ok": True, "skipped": True, "reason": auth["authorization_status"]}
    pi_id = auth.get("stripe_payment_intent_id")
    if pi_id:
        try:
            stripe.PaymentIntent.cancel(pi_id)
        except stripe.error.StripeError as e:
            logger.warning("[stripe] cancel returned %s — proceeding with DB mark", e)
    now_iso = datetime.now(timezone.utc).isoformat()
    await db.bid_authorizations.update_one(
        {"id": auth_id},
        {"$set": {"authorization_status": "released", "released_at": now_iso, "updated_at": now_iso}},
    )
    return {"ok": True}


async def has_active_authorization(db, *, user_id: str, auction_id: str, min_amount_eur: Optional[float] = None) -> bool:
    """Bidding gate — returns True iff the user has a non-expired ACTIVE hold."""
    await _expire_stale_authorizations(db)
    q = {
        "user_id": user_id,
        "auction_id": auction_id,
        "authorization_status": "active",
    }
    if min_amount_eur is not None:
        q["bidding_limit_eur"] = {"$gte": float(min_amount_eur)}
    return bool(await db.bid_authorizations.count_documents(q))


async def _expire_stale_authorizations(db) -> int:
    """Mark any active hold whose authorization_expires_at has passed as 'expired'.
    Idempotent — safe to call on every read."""
    now_iso = datetime.now(timezone.utc).isoformat()
    result = await db.bid_authorizations.update_many(
        {"authorization_status": {"$in": ["active", "pending"]},
         "authorization_expires_at": {"$lt": now_iso}},
        {"$set": {"authorization_status": "expired", "updated_at": now_iso}},
    )
    return int(getattr(result, "modified_count", 0) or 0)
