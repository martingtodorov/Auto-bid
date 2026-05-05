"""
Stripe authorization lifecycle helpers.

Two long-running concerns this module handles:

1. **7-day hold extension** — Stripe card authorizations expire after
   ~7 days. To keep the user's bidding credit alive across week-long
   auctions, a background coroutine scans for holds expiring within
   24 hours and creates a new authorization off-session against the
   saved card, then releases the old hold once the new one is active.

2. **Capture-and-reissue at win** — when a user wins an auction the
   buyer fee (commission) is captured from a portion of their account
   credit. Stripe auto-releases the *remainder* of the authorization
   once you partial-capture, which would zero out the user's credit
   pool. To preserve the available pool we immediately re-issue a new
   hold for the unspent portion using the same saved PM.

Both flows depend on the user having a saved default payment method
(`stripe_default_payment_method_id` on the user doc) — without one,
we just send a notification email asking them to top-up manually.
"""
from __future__ import annotations

import asyncio
import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Optional
from uuid import uuid4

import stripe

logger = logging.getLogger(__name__)

# Same constants as routers/stripe_holds.py — keep in sync if changed.
AUTHORIZATION_TTL_DAYS = 7
# How many hours before expiry to attempt the auto-extend. A 24h
# buffer gives us multiple retry attempts before the user's hold
# actually drops.
EXTEND_BEFORE_HOURS = 24
# Poll cadence for the background loop. 1h is a reasonable balance —
# we extend within at most 1h of the threshold being crossed.
POLL_INTERVAL_SEC = 60 * 60
# Minimum hold age before we consider re-issuing — prevents an
# infinite extend loop if the loop runs against a freshly-issued hold.
MIN_AGE_BEFORE_EXTEND_HOURS = 24


def _stripe_obj_get(obj, key, default=None):
    """Mirror of routers/stripe_holds._stripe_obj_get (StripeObject-safe)."""
    if obj is None:
        return default
    if isinstance(obj, dict):
        return obj.get(key, default)
    val = getattr(obj, key, None)
    if val is not None:
        return val
    try:
        return obj[key]
    except (KeyError, TypeError):
        return default


async def _create_offsession_hold(
    db,
    *,
    user: dict,
    bidding_limit_eur: float,
    amount_authorized_eur: float,
    auction_id: Optional[str] = None,
    description: str = "Bidding credit extension",
) -> Optional[dict]:
    """Create a fresh `bid_authorization` off-session against saved PM.

    Returns the inserted Mongo doc on success, or None on failure
    (no saved PM, Stripe declined, etc.). Caller is responsible for
    sending email/notifications based on the outcome.
    """
    pm_id = user.get("stripe_default_payment_method_id")
    customer_id = user.get("stripe_customer_id")
    if not pm_id or not customer_id:
        logger.info("[lifecycle] no saved PM for user %s — skipping off-session hold", user["id"])
        return None

    amount_cents = int(round(float(amount_authorized_eur) * 100))
    try:
        pi = stripe.PaymentIntent.create(
            amount=amount_cents,
            currency="eur",
            customer=customer_id,
            payment_method=pm_id,
            off_session=True,
            confirm=True,
            capture_method="manual",
            description=description,
            metadata={
                "user_id": user["id"],
                "bidding_limit_eur": str(round(float(bidding_limit_eur), 2)),
                "lifecycle_source": "auto_extend" if auction_id is None else "capture_reissue",
                "auction_id": auction_id or "",
            },
        )
    except stripe.error.CardError as e:
        # SCA / 3DS challenge or hard decline — we can't continue
        # off-session. The user must come back and authenticate.
        logger.warning("[lifecycle] off-session PI for %s declined: %s", user["id"], e.user_message)
        return None
    except stripe.error.StripeError:
        logger.exception("[lifecycle] off-session PI create failed")
        return None

    status = _stripe_obj_get(pi, "status")
    if status not in ("requires_capture", "succeeded"):
        # `requires_action` etc. — we can't capture later off-session.
        try:
            stripe.PaymentIntent.cancel(_stripe_obj_get(pi, "id"))
        except stripe.error.StripeError:
            pass
        logger.warning("[lifecycle] off-session PI ended in status=%s — cancelled", status)
        return None

    now = datetime.now(timezone.utc)
    doc = {
        "id": str(uuid4()),
        "stripe_payment_intent_id": _stripe_obj_get(pi, "id"),
        "stripe_checkout_session_id": None,
        "user_id": user["id"],
        "auction_id": auction_id,
        "bidding_limit_eur": float(bidding_limit_eur),
        "amount_authorized_eur": float(amount_authorized_eur),
        "amount_captured_eur": 0.0,
        "currency": "eur",
        "authorization_status": "active",
        "authorization_expires_at": (now + timedelta(days=AUTHORIZATION_TTL_DAYS)).isoformat(),
        "created_at": now.isoformat(),
        "updated_at": now.isoformat(),
        "lifecycle_source": "auto_extend" if auction_id is None else "capture_reissue",
    }
    await db.bid_authorizations.insert_one(doc)
    logger.info("[lifecycle] reissued hold %s for user=%s amount=%s EUR limit=%s EUR",
                doc["id"], user["id"], amount_authorized_eur, bidding_limit_eur)
    return doc


async def _release_old_hold(db, auth_id: str, *, reason: str) -> None:
    """Cancel the underlying PI and mark the row released."""
    auth = await db.bid_authorizations.find_one({"id": auth_id}, {"_id": 0})
    if not auth or auth.get("authorization_status") not in ("active", "pending"):
        return
    pi_id = auth.get("stripe_payment_intent_id")
    if pi_id:
        try:
            stripe.PaymentIntent.cancel(pi_id)
        except stripe.error.StripeError as e:
            logger.warning("[lifecycle] cancel old PI %s failed: %s", pi_id, e)
    now_iso = datetime.now(timezone.utc).isoformat()
    await db.bid_authorizations.update_one(
        {"id": auth_id},
        {"$set": {
            "authorization_status": "released",
            "released_at": now_iso,
            "updated_at": now_iso,
            "release_reason": reason,
        }},
    )


async def _emit_expiring_alert(db, user: dict, *, reason: str, hold_id: str) -> None:
    """Send an in-app notification + Web Push when the auto-extend
    couldn't roll over a hold. Idempotent per (user, hold) — tracked via
    `lifecycle_alerts_sent` collection so the user isn't spammed if the
    loop sweeps the same hold across multiple ticks.

    `reason` ∈ {"no_saved_pm", "card_declined", "stripe_error"}.
    """
    try:
        sent = await db.lifecycle_alerts_sent.find_one(
            {"user_id": user["id"], "hold_id": hold_id, "reason": reason},
            {"_id": 0, "id": 1},
        )
        if sent:
            return
        await db.lifecycle_alerts_sent.insert_one({
            "id": str(uuid4()),
            "user_id": user["id"],
            "hold_id": hold_id,
            "reason": reason,
            "created_at": datetime.now(timezone.utc).isoformat(),
        })
        # Pick the right push template based on failure reason.
        tmpl = "credit_expiring_no_pm" if reason == "no_saved_pm" else "credit_expiring_declined"
        # Use the inbox notify_user helper so the user gets BOTH an
        # in-app notification (badge on the bell) and a Web Push, and
        # the bell's "/inbox" history records it.
        from routers.inbox import notify_user as _notify_user
        await _notify_user(
            db,
            user_id=user["id"],
            type="credit_expiring",
            data={"reason": reason},
            link="/settings",
            push_template_id=tmpl,
            push_fmt={},
            push_kind=None,  # operational alert — bypass user opt-out
        )
    except Exception:
        logger.exception("[lifecycle] failed to emit expiring alert for user=%s hold=%s",
                         user.get("id"), hold_id)



async def extend_expiring_authorizations(db) -> dict:
    """Scan for active account-level holds expiring within `EXTEND_BEFORE_HOURS`
    and attempt to roll them over to a fresh authorization.

    Account-level only (`auction_id=None`) — per-auction holds are
    short-lived and tied to a specific auction's lifecycle.

    Returns counters for observability.
    """
    if not stripe.api_key:
        return {"scanned": 0, "extended": 0, "failed": 0, "skipped_no_pm": 0}

    now = datetime.now(timezone.utc)
    threshold_iso = (now + timedelta(hours=EXTEND_BEFORE_HOURS)).isoformat()
    min_age_iso = (now - timedelta(hours=MIN_AGE_BEFORE_EXTEND_HOURS)).isoformat()
    cursor = db.bid_authorizations.find(
        {
            "authorization_status": "active",
            "auction_id": None,
            "authorization_expires_at": {"$lte": threshold_iso},
            "created_at": {"$lte": min_age_iso},
            # Avoid extending an already-extended chain twice in a row
            # within the same window.
            "extension_locked_until": {"$not": {"$gt": now.isoformat()}},
        },
        {"_id": 0},
    )
    counters = {"scanned": 0, "extended": 0, "failed": 0, "skipped_no_pm": 0}
    async for old in cursor:
        counters["scanned"] += 1
        # Lock for 6h so two concurrent loop instances don't race.
        lock_until = (now + timedelta(hours=6)).isoformat()
        lock_res = await db.bid_authorizations.update_one(
            {"id": old["id"], "authorization_status": "active",
             "extension_locked_until": {"$not": {"$gt": now.isoformat()}}},
            {"$set": {"extension_locked_until": lock_until}},
        )
        if not getattr(lock_res, "modified_count", 0):
            continue

        user = await db.users.find_one({"id": old["user_id"]}, {"_id": 0})
        if not user:
            counters["failed"] += 1
            continue
        if not user.get("stripe_default_payment_method_id"):
            counters["skipped_no_pm"] += 1
            await _emit_expiring_alert(db, user, reason="no_saved_pm", hold_id=old["id"])
            continue

        new_doc = await _create_offsession_hold(
            db,
            user=user,
            bidding_limit_eur=float(old.get("bidding_limit_eur") or 0),
            amount_authorized_eur=float(old.get("amount_authorized_eur") or 0),
            auction_id=None,
            description=f"Bidding credit auto-extension (was {old['id'][:8]})",
        )
        if not new_doc:
            counters["failed"] += 1
            # Most common reason: card declined / SCA challenge required.
            await _emit_expiring_alert(db, user, reason="card_declined", hold_id=old["id"])
            continue

        await _release_old_hold(db, old["id"], reason="auto_extend_replaced")
        counters["extended"] += 1

    return counters


async def capture_and_reissue(
    db,
    *,
    auth_id: str,
    capture_amount_eur: float,
) -> dict:
    """Capture `capture_amount_eur` from a hold and immediately re-issue
    a fresh hold for the unspent portion.

    Stripe auto-releases the unspent part of an authorization when you
    partial-capture — so without re-issuing the user would lose their
    available credit pool the moment they win their first auction.

    Returns: {"captured_eur": float, "reissued_id": str|None}
    """
    auth = await db.bid_authorizations.find_one({"id": auth_id}, {"_id": 0})
    if not auth:
        raise ValueError(f"Authorization {auth_id} not found")
    if auth.get("authorization_status") != "active":
        raise ValueError(f"Cannot capture — status={auth.get('authorization_status')}")

    pi_id = auth.get("stripe_payment_intent_id")
    if not pi_id:
        raise ValueError("No PaymentIntent on authorization")

    capture_amount_eur = round(float(capture_amount_eur), 2)
    auth_amount = float(auth.get("amount_authorized_eur") or 0)
    if capture_amount_eur <= 0 or capture_amount_eur > auth_amount:
        raise ValueError(f"Invalid capture amount: {capture_amount_eur} (hold={auth_amount})")

    # 1. Partial-capture the buyer fee.
    try:
        pi = stripe.PaymentIntent.capture(
            pi_id,
            amount_to_capture=int(round(capture_amount_eur * 100)),
        )
    except stripe.error.StripeError:
        logger.exception("[lifecycle] capture failed for %s", auth_id)
        raise

    received = _stripe_obj_get(pi, "amount_received", 0) or 0
    captured = round(int(received) / 100.0, 2)
    now_iso = datetime.now(timezone.utc).isoformat()
    await db.bid_authorizations.update_one(
        {"id": auth_id},
        {"$set": {
            "authorization_status": "captured",
            "amount_captured_eur": captured,
            "captured_at": now_iso,
            "updated_at": now_iso,
        }},
    )

    # 2. Re-issue a fresh hold for the unspent portion. We keep the
    #    original `bidding_limit_eur` so the user's bidding ceiling
    #    survives the win unchanged (their fee was a fraction of it).
    remaining_authorization = round(auth_amount - captured, 2)
    if remaining_authorization < 1.0:
        # Sub-euro residue — not worth a fresh authorization.
        return {"captured_eur": captured, "reissued_id": None, "remaining_eur": remaining_authorization}

    user = await db.users.find_one({"id": auth["user_id"]}, {"_id": 0})
    if not user or not user.get("stripe_default_payment_method_id"):
        # User has no saved PM (legacy account). They lose the residual
        # but the win still settles correctly.
        return {"captured_eur": captured, "reissued_id": None, "remaining_eur": remaining_authorization,
                "skipped_reissue": "no_saved_pm"}

    new_doc = await _create_offsession_hold(
        db,
        user=user,
        bidding_limit_eur=float(auth.get("bidding_limit_eur") or 0),
        amount_authorized_eur=remaining_authorization,
        auction_id=None,  # account-level pool
        description=f"Credit reissue after auction win (from {auth_id[:8]})",
    )
    return {
        "captured_eur": captured,
        "reissued_id": (new_doc or {}).get("id"),
        "remaining_eur": remaining_authorization,
    }


# ---- Background worker ----

_worker_task: Optional[asyncio.Task] = None


async def _worker_loop(db):
    """Long-running coroutine that drives `extend_expiring_authorizations`
    on a `POLL_INTERVAL_SEC` cadence. First tick happens after a small
    initial delay so app startup isn't blocked."""
    await asyncio.sleep(60)  # initial delay
    while True:
        try:
            counters = await extend_expiring_authorizations(db)
            if counters.get("scanned"):
                logger.info("[lifecycle] extend pass: %s", counters)
        except Exception:  # noqa: BLE001
            logger.exception("[lifecycle] extend loop iteration failed")
        await asyncio.sleep(POLL_INTERVAL_SEC)


def start_worker(db) -> None:
    """Boot the background lifecycle loop. Idempotent."""
    global _worker_task
    if _worker_task and not _worker_task.done():
        return
    if not os.environ.get("STRIPE_API_KEY"):
        logger.info("[lifecycle] STRIPE_API_KEY not set — worker disabled")
        return
    _worker_task = asyncio.create_task(_worker_loop(db))
    logger.info("[lifecycle] background worker started (poll=%ss, threshold=%sh)",
                POLL_INTERVAL_SEC, EXTEND_BEFORE_HOURS)


def stop_worker() -> None:
    """Cancel the background loop on app shutdown."""
    global _worker_task
    if _worker_task and not _worker_task.done():
        _worker_task.cancel()
        _worker_task = None
        logger.info("[lifecycle] background worker stopped")
