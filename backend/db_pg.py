"""
PostgreSQL async engine + session factory for the bidding subsystem.

Why a separate database? Bids must be ACID-correct under concurrency
(two users hitting "Bid" within milliseconds must serialise). We use
SELECT ... FOR UPDATE on a per-auction `bid_state` row to serialise
bid writes for the same auction while letting different auctions run
in parallel. The rest of the app (auctions, users, comments…) stays
on MongoDB; only the bidding write/read path lives here.
"""
from __future__ import annotations

import os
import logging
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

logger = logging.getLogger(__name__)


class Base(DeclarativeBase):
    """Declarative base for bidding models."""


_POSTGRES_URL = os.environ.get("POSTGRES_URL")
if not _POSTGRES_URL:
    raise RuntimeError("POSTGRES_URL is required for the bidding subsystem")

engine = create_async_engine(
    _POSTGRES_URL,
    echo=False,
    pool_pre_ping=True,
    pool_size=10,
    max_overflow=20,
)

AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    expire_on_commit=False,
    class_=AsyncSession,
)


@asynccontextmanager
async def pg_session():
    """Yield an AsyncSession; auto-rollback on exception, auto-commit otherwise.

    Bidding endpoints should wrap their critical section in this context
    so that the SELECT FOR UPDATE lock is released atomically.
    """
    session = AsyncSessionLocal()
    try:
        yield session
        await session.commit()
    except Exception:
        await session.rollback()
        raise
    finally:
        await session.close()


async def init_pg_schema() -> None:
    """Create all bidding tables if they don't exist (idempotent)."""
    # Import here so the models are registered on Base.metadata before create_all
    from models_pg import Bid, BidState  # noqa: F401

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    logger.info("PostgreSQL bidding schema ready")


async def dispose_engine() -> None:
    """Drop the SQLAlchemy connection pool so the next call uses fresh
    connections. Used between retries when PG is starting up — otherwise
    the pool may latch onto a half-open socket."""
    await engine.dispose()
