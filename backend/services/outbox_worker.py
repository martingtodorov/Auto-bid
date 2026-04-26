"""
Bid outbox worker — drains `bid_events` (Postgres) → MongoDB.

This implements the **transactional outbox pattern**:
  • Each bid INSERT in Postgres also inserts a `bid_events` row in
    the SAME transaction.
  • A background asyncio task (started from server.py on FastAPI
    startup) polls for unapplied events, applies them to Mongo,
    and marks them `applied_at`.
  • If Mongo is unreachable or a write fails, the row stays
    pending and is retried with exponential backoff. After
    `MAX_ATTEMPTS` it is moved to the dead-letter "applied with
    error" state for manual inspection (`/api/admin/bid-outbox`).

Idempotency:
  • Mongo `auction` updates are idempotent — they only `$max` the
    bid_count and only overwrite if the incoming bid_count is
    greater than the stored one. So replays are safe.
  • For `last_applied_event_id` we still mark applied_at in Postgres
    so the same row is never re-processed twice on the happy path.

Crash safety:
  • Catch-up on startup: any pending events are processed before
    the worker enters its normal poll loop.
  • Idempotent writes mean a Mongo update that committed before the
    backend crashed (but didn't get marked applied in Postgres)
    is harmless to apply again.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import select, update
from sqlalchemy.exc import SQLAlchemyError

from db_pg import pg_session
from models_pg import BidEvent
from deps import db

logger = logging.getLogger(__name__)

POLL_INTERVAL_SECONDS = 0.25       # how often to check for pending events
BATCH_SIZE = 50                    # max events per poll cycle
MAX_ATTEMPTS = 12                  # stop retrying after this many failures
BACKOFF_BASE_SECONDS = 1.0         # exponential backoff base


def _backoff_delay(attempt: int) -> timedelta:
    """Exponential backoff: 1s, 2s, 4s, 8s … capped at 5 min."""
    delay = min(BACKOFF_BASE_SECONDS * (2 ** max(0, attempt - 1)), 300.0)
    return timedelta(seconds=delay)


# --------------------------------------------------------------------- apply

async def _apply_bid_placed(payload: dict) -> None:
    """Idempotent Mongo update — only writes if this event would
    advance the auction (bid_count strictly greater than current)."""
    auction_id = payload["auction_id"]
    new_bid_count = int(payload["bid_count"])

    # Use $max-style guard: only overwrite when the incoming event
    # represents a newer state. Replays of older events are no-ops.
    update_doc = {
        "$set": {
            "current_bid_eur": float(payload["amount_eur"]),
            "bid_count": new_bid_count,
            "high_bidder_id": payload["high_bidder_id"],
            "high_bidder_name": payload["high_bidder_name"],
        }
    }
    if payload.get("triggered_extension") and payload.get("ends_at"):
        update_doc["$set"]["ends_at"] = payload["ends_at"]

    # Conditional write — guarantees we never roll the count backwards.
    await db.auctions.update_one(
        {"id": auction_id, "$or": [
            {"bid_count": {"$lt": new_bid_count}},
            {"bid_count": {"$exists": False}},
        ]},
        update_doc,
    )


_DISPATCH = {
    "bid_placed": _apply_bid_placed,
}


# --------------------------------------------------------------------- worker

async def _process_one(event: BidEvent) -> tuple[bool, Optional[str]]:
    """Apply a single event. Returns (success, error_message)."""
    handler = _DISPATCH.get(event.event_type)
    if not handler:
        return False, f"unknown event_type={event.event_type}"
    try:
        await handler(event.payload or {})
        return True, None
    except Exception as e:  # noqa: BLE001
        return False, f"{type(e).__name__}: {e}"[:500]


async def _drain_once() -> int:
    """Pull a batch of pending events, apply them, mark applied or schedule retry.
    Returns the number of events processed (success + fail)."""
    now = datetime.now(timezone.utc)
    processed = 0

    async with pg_session() as s:
        rows = (await s.execute(
            select(BidEvent).where(
                BidEvent.applied_at.is_(None),
                (BidEvent.next_attempt_at.is_(None)) | (BidEvent.next_attempt_at <= now),
                BidEvent.attempt_count < MAX_ATTEMPTS,
            ).order_by(BidEvent.created_at.asc()).limit(BATCH_SIZE)
            .with_for_update(skip_locked=True)  # crash-safe: another worker can't grab the same row
        )).scalars().all()

        for ev in rows:
            ok, err = await _process_one(ev)
            ev.attempt_count = (ev.attempt_count or 0) + 1
            if ok:
                ev.applied_at = datetime.now(timezone.utc)
                ev.last_error = None
                ev.next_attempt_at = None
            else:
                ev.last_error = err
                ev.next_attempt_at = datetime.now(timezone.utc) + _backoff_delay(ev.attempt_count)
                logger.warning("bid_event %s failed (attempt %s): %s",
                               ev.id, ev.attempt_count, err)
            processed += 1

    return processed


async def run_worker(stop_event: asyncio.Event) -> None:
    """Long-running coroutine — drains the outbox until told to stop."""
    logger.info("Bid outbox worker started (poll=%.2fs, batch=%d, max_attempts=%d)",
                POLL_INTERVAL_SECONDS, BATCH_SIZE, MAX_ATTEMPTS)

    while not stop_event.is_set():
        try:
            n = await _drain_once()
            # If we drained a full batch, immediately try again — there might be more.
            if n >= BATCH_SIZE:
                continue
        except SQLAlchemyError as e:
            logger.exception("Bid outbox SQL error: %s", e)
        except Exception as e:  # noqa: BLE001
            logger.exception("Bid outbox unexpected error: %s", e)

        # Wait but wake on stop signal
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=POLL_INTERVAL_SECONDS)
        except asyncio.TimeoutError:
            pass

    logger.info("Bid outbox worker stopped")


# --------------------------------------------------------------------- admin

async def get_outbox_health() -> dict:
    """Stats for /api/admin/bid-outbox health endpoint."""
    async with pg_session() as s:
        from sqlalchemy import func as _func
        pending = (await s.execute(
            select(_func.count(BidEvent.id)).where(BidEvent.applied_at.is_(None))
        )).scalar() or 0
        dead = (await s.execute(
            select(_func.count(BidEvent.id)).where(
                BidEvent.applied_at.is_(None),
                BidEvent.attempt_count >= MAX_ATTEMPTS,
            )
        )).scalar() or 0
        oldest_pending = (await s.execute(
            select(BidEvent.created_at).where(BidEvent.applied_at.is_(None))
            .order_by(BidEvent.created_at.asc()).limit(1)
        )).scalar()
        return {
            "pending": int(pending),
            "dead_letter": int(dead),
            "oldest_pending_at": oldest_pending.isoformat() if oldest_pending else None,
        }


async def list_dead_letter_events(limit: int = 100) -> list[dict]:
    async with pg_session() as s:
        rows = (await s.execute(
            select(BidEvent).where(
                BidEvent.applied_at.is_(None),
                BidEvent.attempt_count >= MAX_ATTEMPTS,
            ).order_by(BidEvent.created_at.desc()).limit(limit)
        )).scalars().all()
        return [
            {
                "id": e.id,
                "auction_id": e.auction_id,
                "event_type": e.event_type,
                "created_at": e.created_at.isoformat(),
                "attempt_count": e.attempt_count,
                "last_error": e.last_error,
                "payload": e.payload,
            }
            for e in rows
        ]


async def retry_dead_letter_event(event_id: str) -> bool:
    """Reset attempt count + next_attempt_at so the worker picks it up again."""
    async with pg_session() as s:
        r = await s.execute(
            update(BidEvent).where(BidEvent.id == event_id).values(
                attempt_count=0,
                next_attempt_at=datetime.now(timezone.utc),
                last_error=None,
            )
        )
        return (r.rowcount or 0) > 0
