"""
Bidding service — all bid persistence happens here.

Source-of-truth: PostgreSQL (`bids`, `bid_state`).
Mongo `auctions` document still keeps a denormalised
`current_bid_eur`, `bid_count`, `high_bidder_id`, `high_bidder_name`,
`ends_at` so the rest of the app (filters, listings, sitemap, sorting)
keeps working without a join.

The endpoint in server.py uses `place_bid` which:
  1. Opens a tx
  2. SELECT FOR UPDATE on bid_state row (serialises concurrent bidders)
  3. Re-validates min next bid
  4. INSERTs the bid
  5. UPDATEs bid_state
  6. COMMITs
  7. Caller mirrors changes to Mongo + broadcasts WebSocket
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional

from sqlalchemy import select, update, func
from sqlalchemy.dialects.postgresql import insert as pg_insert

from db_pg import pg_session
from models_pg import Bid, BidState

logger = logging.getLogger(__name__)


def _to_iso(dt: Optional[datetime]) -> Optional[str]:
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.isoformat().replace("+00:00", "Z")


def _bid_row_to_dict(b: Bid) -> dict:
    return {
        "id": b.id,
        "auction_id": b.auction_id,
        "user_id": b.user_id,
        "user_name": b.user_name,
        "amount_eur": float(b.amount_eur),
        "created_at": _to_iso(b.created_at),
        "preauth_id": b.preauth_id,
        "preauth_status": b.preauth_status,
        "preauth_amount_eur": float(b.preauth_amount_eur) if b.preauth_amount_eur is not None else None,
        "preauth_released_at": _to_iso(b.preauth_released_at),
        "preauth_captured_amount_eur": float(b.preauth_captured_amount_eur) if b.preauth_captured_amount_eur is not None else None,
        "preauth_captured_at": _to_iso(b.preauth_captured_at),
        "card_last4": b.card_last4,
        "credit_id": b.credit_id,
        "triggered_extension": b.triggered_extension,
        "is_winning": b.is_winning,
    }


# --------------------------------------------------------------- read helpers

async def list_bids(auction_id: str, limit: int = 50) -> list[dict]:
    async with pg_session() as s:
        rows = (await s.execute(
            select(Bid).where(Bid.auction_id == auction_id)
            .order_by(Bid.amount_eur.desc()).limit(limit)
        )).scalars().all()
        return [_bid_row_to_dict(b) for b in rows]


async def list_user_bids(user_id: str, limit: int = 200) -> list[dict]:
    async with pg_session() as s:
        rows = (await s.execute(
            select(Bid).where(Bid.user_id == user_id)
            .order_by(Bid.created_at.desc()).limit(limit)
        )).scalars().all()
        return [_bid_row_to_dict(b) for b in rows]


async def has_user_bid(auction_id: str, user_id: str) -> bool:
    async with pg_session() as s:
        row = (await s.execute(
            select(Bid.id).where(
                Bid.auction_id == auction_id, Bid.user_id == user_id
            ).limit(1)
        )).first()
        return row is not None


async def collect_bidder_ids(auction_id: str, exclude_user_id: Optional[str] = None, limit: int = 500) -> list[str]:
    async with pg_session() as s:
        q = select(Bid.user_id).where(Bid.auction_id == auction_id).distinct().limit(limit)
        rows = (await s.execute(q)).scalars().all()
        if exclude_user_id:
            return [u for u in rows if u != exclude_user_id]
        return list(rows)


async def get_winning_bid(auction_id: str) -> Optional[dict]:
    async with pg_session() as s:
        row = (await s.execute(
            select(Bid).where(Bid.auction_id == auction_id)
            .order_by(Bid.amount_eur.desc(), Bid.created_at.asc()).limit(1)
        )).scalar_one_or_none()
        return _bid_row_to_dict(row) if row else None


async def get_state(auction_id: str) -> Optional[dict]:
    async with pg_session() as s:
        st = (await s.execute(
            select(BidState).where(BidState.auction_id == auction_id)
        )).scalar_one_or_none()
        if not st:
            return None
        return {
            "auction_id": st.auction_id,
            "current_bid_eur": float(st.current_bid_eur),
            "bid_count": st.bid_count,
            "high_bidder_id": st.high_bidder_id,
            "high_bidder_name": st.high_bidder_name,
            "ends_at": _to_iso(st.ends_at),
        }


# --------------------------------------------------------------- write paths

async def ensure_state(auction_id: str, starting_bid_eur: float, ends_at: Optional[datetime] = None) -> None:
    """Idempotent: create state row when an auction is created or first bid arrives."""
    async with pg_session() as s:
        stmt = pg_insert(BidState).values(
            auction_id=auction_id,
            current_bid_eur=Decimal(str(starting_bid_eur)),
            starting_bid_eur=Decimal(str(starting_bid_eur)),
            bid_count=0,
            ends_at=ends_at,
        ).on_conflict_do_nothing(index_elements=["auction_id"])
        await s.execute(stmt)


async def place_bid(
    *,
    auction_id: str,
    user_id: str,
    user_name: str,
    amount_eur: float,
    bid_id: str,
    preauth_id: Optional[str],
    preauth_status: str,
    preauth_amount_eur: float,
    card_last4: Optional[str],
    credit_id: Optional[str],
    fallback_starting_bid_eur: float,
    fallback_ends_at: datetime,
    bid_step_fn,
    extension_minutes: int = 2,
) -> dict:
    """ACID-safe bid placement.

    Locks the bid_state row, re-validates min next bid, inserts the bid,
    updates state. Returns dict with new state + bid + triggered_extension.
    Raises ValueError("min_bid:<float>") if amount is below current+step.
    """
    amount = Decimal(str(amount_eur))
    now = datetime.now(timezone.utc)

    async with pg_session() as s:
        # 1) ensure state exists (no-op if present)
        await s.execute(
            pg_insert(BidState).values(
                auction_id=auction_id,
                current_bid_eur=Decimal(str(fallback_starting_bid_eur)),
                starting_bid_eur=Decimal(str(fallback_starting_bid_eur)),
                bid_count=0,
                ends_at=fallback_ends_at,
            ).on_conflict_do_nothing(index_elements=["auction_id"])
        )

        # 2) lock the row (serialises concurrent bidders for this auction)
        st = (await s.execute(
            select(BidState).where(BidState.auction_id == auction_id).with_for_update()
        )).scalar_one()

        # 3) validate min next bid against locked current
        current = float(st.current_bid_eur)
        step = bid_step_fn(current)
        min_next = current + step
        if float(amount) < min_next:
            raise ValueError(f"min_bid:{min_next}")

        # 4) anti-snipe check using locked ends_at
        ends_at = st.ends_at or fallback_ends_at
        if ends_at.tzinfo is None:
            ends_at = ends_at.replace(tzinfo=timezone.utc)
        seconds_left = (ends_at - now).total_seconds()
        triggered_extension = seconds_left < (extension_minutes * 60)
        new_ends_at = ends_at
        if triggered_extension:
            from datetime import timedelta
            new_ends_at = now + timedelta(minutes=extension_minutes)

        # 5) insert bid
        bid_row = Bid(
            id=bid_id,
            auction_id=auction_id,
            user_id=user_id,
            user_name=user_name,
            amount_eur=amount,
            created_at=now,
            preauth_id=preauth_id,
            preauth_status=preauth_status,
            preauth_amount_eur=Decimal(str(preauth_amount_eur)),
            card_last4=card_last4,
            credit_id=credit_id,
            triggered_extension=triggered_extension,
        )
        s.add(bid_row)
        await s.flush()

        # 6) update state
        st.current_bid_eur = amount
        st.bid_count = (st.bid_count or 0) + 1
        st.high_bidder_id = user_id
        st.high_bidder_name = user_name
        st.ends_at = new_ends_at
        st.updated_at = now

        return {
            "bid": _bid_row_to_dict(bid_row),
            "current_bid_eur": float(amount),
            "bid_count": st.bid_count,
            "high_bidder_id": user_id,
            "high_bidder_name": user_name,
            "ends_at": _to_iso(new_ends_at),
            "triggered_extension": triggered_extension,
        }


async def release_user_active_preauths(auction_id: str, user_id: str) -> None:
    """Mark all `authorized` bids by user on this auction as released."""
    async with pg_session() as s:
        await s.execute(
            update(Bid)
            .where(Bid.auction_id == auction_id, Bid.user_id == user_id, Bid.preauth_status == "authorized")
            .values(preauth_status="released", preauth_released_at=datetime.now(timezone.utc))
        )


async def release_all_active_preauths(auction_id: str) -> None:
    """At settlement: mark every still-`authorized` bid as released."""
    async with pg_session() as s:
        await s.execute(
            update(Bid)
            .where(Bid.auction_id == auction_id, Bid.preauth_status == "authorized")
            .values(preauth_status="released", preauth_released_at=datetime.now(timezone.utc))
        )


async def mark_winner_capture(auction_id: str, winning_bid_id: str, captured_amount_eur: float) -> None:
    async with pg_session() as s:
        await s.execute(
            update(Bid)
            .where(Bid.id == winning_bid_id)
            .values(
                preauth_status="captured",
                preauth_captured_amount_eur=Decimal(str(captured_amount_eur)),
                preauth_captured_at=datetime.now(timezone.utc),
                is_winning=True,
            )
        )


async def delete_bids_for_auction(auction_id: str) -> int:
    async with pg_session() as s:
        from sqlalchemy import delete
        r1 = await s.execute(delete(Bid).where(Bid.auction_id == auction_id))
        await s.execute(delete(BidState).where(BidState.auction_id == auction_id))
        return r1.rowcount or 0


async def release_losing_preauths(auction_id: str, winner_user_id: Optional[str]) -> None:
    """Release every still-`authorized` bid except those by the winner."""
    async with pg_session() as s:
        q = update(Bid).where(
            Bid.auction_id == auction_id,
            Bid.preauth_status == "authorized",
        )
        if winner_user_id:
            q = q.where(Bid.user_id != winner_user_id)
        await s.execute(q.values(preauth_status="released", preauth_released_at=datetime.now(timezone.utc)))


async def delete_all_bids() -> None:
    """Wipe all bidding rows (used by /admin/reseed)."""
    async with pg_session() as s:
        from sqlalchemy import delete
        await s.execute(delete(Bid))
        await s.execute(delete(BidState))


async def delete_bids_for_user(user_id: str) -> int:
    """Delete every bid placed by a given user (admin user-delete cascade)."""
    async with pg_session() as s:
        from sqlalchemy import delete
        r = await s.execute(delete(Bid).where(Bid.user_id == user_id))
        return r.rowcount or 0


async def count_bids(since: Optional[datetime] = None) -> int:
    """Total bid count (optionally since a date) for admin metrics."""
    async with pg_session() as s:
        from sqlalchemy import select as _select
        q = _select(func.count(Bid.id))
        if since:
            q = q.where(Bid.created_at >= since)
        return int((await s.execute(q)).scalar() or 0)


async def list_bids_for_admin(auction_id: str, limit: int = 500) -> list[dict]:
    """Admin bid log — newest first, no truncation by amount."""
    async with pg_session() as s:
        rows = (await s.execute(
            select(Bid).where(Bid.auction_id == auction_id)
            .order_by(Bid.created_at.desc()).limit(limit)
        )).scalars().all()
        return [_bid_row_to_dict(b) for b in rows]


async def get_bid(bid_id: str) -> Optional[dict]:
    async with pg_session() as s:
        b = (await s.execute(select(Bid).where(Bid.id == bid_id))).scalar_one_or_none()
        return _bid_row_to_dict(b) if b else None


async def invalidate_bid(bid_id: str) -> None:
    """Mark a bid as released (admin invalidation)."""
    async with pg_session() as s:
        await s.execute(
            update(Bid).where(Bid.id == bid_id).values(
                preauth_status="released",
                preauth_released_at=datetime.now(timezone.utc),
            )
        )


async def get_top_active_bid(auction_id: str) -> Optional[dict]:
    """Highest bid that is NOT released (used after admin invalidates a bid)."""
    async with pg_session() as s:
        row = (await s.execute(
            select(Bid).where(
                Bid.auction_id == auction_id,
                Bid.preauth_status != "released",
            ).order_by(Bid.amount_eur.desc(), Bid.created_at.asc()).limit(1)
        )).scalar_one_or_none()
        return _bid_row_to_dict(row) if row else None


async def reset_state_for_relist(auction_id: str, starting_bid_eur: float, ends_at: Optional[datetime] = None) -> None:
    """When a relisted auction reuses an id (rare) or starting bid changes."""
    async with pg_session() as s:
        await s.execute(
            update(BidState)
            .where(BidState.auction_id == auction_id)
            .values(
                current_bid_eur=Decimal(str(starting_bid_eur)),
                starting_bid_eur=Decimal(str(starting_bid_eur)),
                bid_count=0,
                high_bidder_id=None,
                high_bidder_name=None,
                ends_at=ends_at,
            )
        )
