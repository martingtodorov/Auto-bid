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
  STRIPE_SUCCESS_URL        optional override; otherwise built from request
  STRIPE_CANCEL_URL         optional override; otherwise built from request

To switch to live mode, swap STRIPE_API_KEY → sk_live_… and
STRIPE_WEBHOOK_SECRET to the live-mode whsec_…  No code changes needed.
"""
from __future__ import annotations
import os
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


class CreateAuthBody(BaseModel):
    auction_id: str
    bidding_limit_eur: float
    origin: Optional[str] = None  # frontend's window.location.origin


def build_stripe_router(db, get_current_user):
    router = APIRouter(prefix="/api/stripe", tags=["stripe"])
    api_key = os.environ.get("STRIPE_API_KEY", "")
    webhook_secret = os.environ.get("STRIPE_WEBHOOK_SECRET", "")
    if api_key:
        stripe.api_key = api_key

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
        """
        if not api_key:
            raise HTTPException(status_code=503, detail="Stripe не е конфигуриран. Свържете се с администратор.")
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

        # ---- Build URLs ----
        origin = (body.origin or "").rstrip("/") or str(request.base_url).rstrip("/")
        success_override = os.environ.get("STRIPE_SUCCESS_URL", "").strip()
        cancel_override = os.environ.get("STRIPE_CANCEL_URL", "").strip()
        success_url = success_override or f"{origin}/auctions/{body.auction_id}?stripe_session_id={{CHECKOUT_SESSION_ID}}"
        cancel_url = cancel_override or f"{origin}/auctions/{body.auction_id}?stripe_cancelled=1"

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
            "stripe_payment_intent_id": session.get("payment_intent"),
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
        return {"id": session["id"], "url": session["url"], "amount_eur": amount_eur}

    @router.get("/authorizations/active")
    async def my_active_authorization(auction_id: str, user: dict = Depends(get_current_user)):
        """Return the user's currently active hold for this auction (if any)."""
        await _expire_stale_authorizations(db)
        doc = await db.bid_authorizations.find_one(
            {
                "user_id": user["id"],
                "auction_id": auction_id,
                "authorization_status": "active",
            },
            {"_id": 0, "id": 1, "amount_authorized_eur": 1, "bidding_limit_eur": 1,
             "authorization_expires_at": 1, "currency": 1, "stripe_payment_intent_id": 1,
             "authorization_status": 1},
        )
        return doc or {}

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
