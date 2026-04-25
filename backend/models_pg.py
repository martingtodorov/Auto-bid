"""
SQLAlchemy ORM models for the bidding subsystem (PostgreSQL).

Tables:
- bids        — append-only bid history (one row per placed bid)
- bid_state   — per-auction current state (locked with SELECT FOR UPDATE
                during placement to serialise concurrent bidders)
"""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import (
    Boolean, DateTime, Index, Numeric, String, func,
)
from sqlalchemy.orm import Mapped, mapped_column

from db_pg import Base


class Bid(Base):
    __tablename__ = "bids"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    auction_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    user_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    user_name: Mapped[Optional[str]] = mapped_column(String(255))
    amount_eur: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    # Pre-authorisation / capture lifecycle (mirrors the legacy Mongo bid doc)
    preauth_id: Mapped[Optional[str]] = mapped_column(String(128))
    preauth_status: Mapped[Optional[str]] = mapped_column(String(32), index=True)
    preauth_amount_eur: Mapped[Optional[Decimal]] = mapped_column(Numeric(14, 2))
    preauth_released_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    preauth_captured_amount_eur: Mapped[Optional[Decimal]] = mapped_column(Numeric(14, 2))
    preauth_captured_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    card_last4: Mapped[Optional[str]] = mapped_column(String(4))
    credit_id: Mapped[Optional[str]] = mapped_column(String(64))

    # Anti-snipe + finalisation flags
    triggered_extension: Mapped[bool] = mapped_column(Boolean, default=False)
    is_winning: Mapped[bool] = mapped_column(Boolean, default=False)

    __table_args__ = (
        Index("ix_bids_auction_amount", "auction_id", "amount_eur"),
        Index("ix_bids_auction_user", "auction_id", "user_id"),
    )


class BidState(Base):
    """One row per auction. Locked via SELECT FOR UPDATE during placement.

    Source-of-truth for current_bid_eur, bid_count, high_bidder, ends_at.
    Mongo holds a denormalised copy that is updated post-commit.
    """
    __tablename__ = "bid_state"

    auction_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    current_bid_eur: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False, default=0)
    starting_bid_eur: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False, default=0)
    bid_count: Mapped[int] = mapped_column(default=0)
    high_bidder_id: Mapped[Optional[str]] = mapped_column(String(64))
    high_bidder_name: Mapped[Optional[str]] = mapped_column(String(255))
    ends_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )
