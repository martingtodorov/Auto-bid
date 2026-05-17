"""3-day digest email worker.

Sends every user with at least one email opt-in a periodic summary of:
  • Newly published auctions (in the last 3 days)
  • Auctions ending soon (next 48 hours)

Cadence
-------
A single asyncio task started by `server.py` on app startup. It loops
every `POLL_SEC` seconds and dispatches to recipients whose
`last_digest_3day_at` is older than `INTERVAL_DAYS` days (default 3).

We track the last-sent timestamp on the user document so a backend restart
doesn't cause a flood. The first time the worker sees a user without a
timestamp, it stamps "now" and skips, ensuring no immediate blast on a
fresh deploy.

Opt-out
-------
Respects `notification_prefs.email.digest_3day = False`. Users who clicked
the email-footer Unsubscribe link have `email_unsubscribed_at` set AND all
email kinds set to False — both checks gate sending.
"""
from __future__ import annotations
import asyncio
import logging
import os
from datetime import datetime, timedelta, timezone

logger = logging.getLogger(__name__)

INTERVAL_DAYS = int(os.environ.get("DIGEST_3DAY_INTERVAL_DAYS", "3"))
POLL_SEC = int(os.environ.get("DIGEST_3DAY_POLL_SEC", "3600"))  # 1h
NEW_LISTINGS_WINDOW_DAYS = 3
ENDING_WINDOW_HOURS = 48
MAX_PER_SECTION = 6  # cap rows per section to keep emails short
_task: asyncio.Task | None = None


def _row_html(a: dict, app_url: str, ending: bool = False) -> str:
    """Render one auction row for the digest body."""
    title = (a.get("title") or "").replace("<", "&lt;").replace(">", "&gt;")
    price = int(a.get("current_bid_eur") or a.get("starting_bid_eur") or 0)
    year = a.get("year") or ""
    city = (a.get("city") or "").replace("<", "&lt;").replace(">", "&gt;")
    aid = a.get("id") or ""
    meta_parts = [str(year), city]
    meta = " · ".join([p for p in meta_parts if p])
    badge = ""
    if ending and a.get("end_at"):
        try:
            end_dt = datetime.fromisoformat(a["end_at"].replace("Z", "+00:00"))
            remaining = end_dt - datetime.now(timezone.utc)
            hrs = max(0, int(remaining.total_seconds() // 3600))
            badge = f'<span style="background:#fef3c7;color:#92400e;padding:2px 8px;border-radius:999px;font-size:11px;font-weight:600;">~{hrs}h</span>'
        except Exception:
            pass
    return (
        '<a href="' + f"{app_url}/auctions/{aid}" + '" '
        'style="display:block;margin:10px 0;padding:14px 16px;border:1px solid #e5e7eb;'
        'border-radius:12px;text-decoration:none;color:#111827;">'
        f'<div style="font-size:15px;font-weight:600;color:#0b0f1a;">{title}</div>'
        f'<div style="font-size:13px;color:#6b7280;margin-top:4px;">{meta}</div>'
        f'<div style="margin-top:8px;display:flex;justify-content:space-between;align-items:center;">'
        f'<span style="font-size:15px;font-weight:700;color:#1B4D3E;">€{price:,}</span>{badge}</div>'
        '</a>'
    )


async def _collect_payload(db, app_url: str) -> tuple[str, str, int, int]:
    """Build the new-listings + ending-soon HTML chunks once per cycle.

    All recipients in this cycle share the same rendered HTML, so we compute
    it once before fanning out — keeps DB churn minimal even at scale.
    """
    now = datetime.now(timezone.utc)
    cutoff_new = (now - timedelta(days=NEW_LISTINGS_WINDOW_DAYS)).isoformat()
    cutoff_end = (now + timedelta(hours=ENDING_WINDOW_HOURS)).isoformat()
    # New listings — sort by published_at descending
    new_cursor = db.auctions.find(
        {
            "status": {"$in": ["live", "approved"]},
            "$or": [
                {"published_at": {"$gte": cutoff_new}},
                {"created_at": {"$gte": cutoff_new}},
            ],
        },
        {"_id": 0, "id": 1, "title": 1, "year": 1, "city": 1,
         "current_bid_eur": 1, "starting_bid_eur": 1, "end_at": 1},
    ).sort([("published_at", -1)]).limit(MAX_PER_SECTION)
    new_rows = [a async for a in new_cursor]
    # Ending soon — sort by end_at ascending
    end_cursor = db.auctions.find(
        {"status": "live", "end_at": {"$gte": now.isoformat(), "$lte": cutoff_end}},
        {"_id": 0, "id": 1, "title": 1, "year": 1, "city": 1,
         "current_bid_eur": 1, "starting_bid_eur": 1, "end_at": 1},
    ).sort([("end_at", 1)]).limit(MAX_PER_SECTION)
    end_rows = [a async for a in end_cursor]
    new_html = "".join(_row_html(a, app_url, ending=False) for a in new_rows) or (
        '<p style="color:#6b7280;font-size:14px;">—</p>'
    )
    ending_html = "".join(_row_html(a, app_url, ending=True) for a in end_rows) or (
        '<p style="color:#6b7280;font-size:14px;">—</p>'
    )
    return new_html, ending_html, len(new_rows), len(end_rows)


async def _process_batch(db) -> dict:
    """One pass: ship the digest to everyone who is due."""
    from emails import APP_URL, email_digest_3day
    from services import notif_prefs as _nprefs
    now = datetime.now(timezone.utc)
    cutoff_due = (now - timedelta(days=INTERVAL_DAYS)).isoformat()
    new_html, ending_html, new_count, end_count = await _collect_payload(db, APP_URL)
    # Nothing fresh to share → skip the whole cycle (avoid sending an empty digest)
    if new_count == 0 and end_count == 0:
        return {"skipped": True, "reason": "no_content"}
    sent = 0
    skipped_optout = 0
    cursor = db.users.find(
        {
            "email": {"$nin": [None, ""]},
            "$or": [
                {"last_digest_3day_at": {"$lt": cutoff_due}},
                {"last_digest_3day_at": {"$exists": False}},
            ],
        },
        {"_id": 0, "id": 1, "email": 1, "name": 1, "lang": 1,
         "notification_prefs": 1, "last_digest_3day_at": 1,
         "email_unsubscribed_at": 1},
    )
    async for u in cursor:
        # Respect global + per-kind opt-out
        if u.get("email_unsubscribed_at"):
            skipped_optout += 1
            continue
        if not _nprefs.is_enabled(u, "email", "digest_3day"):
            skipped_optout += 1
            continue
        # First sighting of this user → stamp now & skip (no immediate blast)
        if not u.get("last_digest_3day_at"):
            await db.users.update_one(
                {"id": u["id"]},
                {"$set": {"last_digest_3day_at": now.isoformat()}},
            )
            continue
        try:
            await email_digest_3day(
                u["email"], u.get("name") or "",
                new_html=new_html, ending_html=ending_html,
                lang=(u.get("lang") or "bg"),
            )
            await db.users.update_one(
                {"id": u["id"]},
                {"$set": {"last_digest_3day_at": now.isoformat()}},
            )
            sent += 1
        except Exception as e:
            logger.error("digest_3day send failed for %s: %s", u.get("email"), e)
    logger.info("digest_3day: sent=%d skipped_optout=%d new=%d ending=%d",
                sent, skipped_optout, new_count, end_count)
    return {"sent": sent, "skipped_optout": skipped_optout,
            "new": new_count, "ending": end_count}


async def _loop(db) -> None:
    # Stagger first run by 5 minutes to avoid hammering the DB on boot
    await asyncio.sleep(int(os.environ.get("DIGEST_3DAY_INITIAL_DELAY_SEC", "300")))
    while True:
        try:
            await _process_batch(db)
        except Exception as e:
            logger.error("digest_3day loop error: %s", e)
        await asyncio.sleep(POLL_SEC)


def start(db) -> None:
    """Spawn the background task. Idempotent — multiple calls are a no-op."""
    global _task
    if _task is not None and not _task.done():
        return
    _task = asyncio.create_task(_loop(db), name="digest_3day_worker")
    logger.info("digest_3day worker started (poll=%ds, interval=%dd)",
                POLL_SEC, INTERVAL_DAYS)


def stop() -> None:
    global _task
    if _task and not _task.done():
        _task.cancel()
    _task = None
