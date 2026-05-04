"""Leaderboard — top sellers / commenters / bidders / overall reputation.

Extracted from server.py during the 2026-05-04 refactor pass. The
endpoint and its private helpers (`_leaderboard_*`, `_period_since`,
in-memory `_LEADERBOARD_CACHE`) are 100 % self-contained — they only
read from `db` and don't share any helpers with the auctions/bidding
hot path. Moving them here cuts ~150 lines from `server.py`.

Cache: 60-second TTL keyed by `type:period:limit`. Anonymous endpoint —
no authentication required, so we use the builder pattern but ignore
`get_current_user` (kept in the signature for symmetry with other
routers in this folder).
"""
from __future__ import annotations
import time
from datetime import datetime, timedelta, timezone
from typing import Optional
from fastapi import APIRouter, Query


_LEADERBOARD_CACHE: dict = {}
_LEADERBOARD_TTL_SEC = 60


def _period_since(period: str) -> Optional[str]:
    """ISO timestamp cut-off for `period=month`, or `None` for all-time."""
    if period == "month":
        return (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()
    return None


def build_leaderboard_router(db):
    router = APIRouter(prefix="/api", tags=["leaderboard"])

    async def _leaderboard_sellers(period: str, limit: int) -> list:
        match: dict = {"status": "sold", "is_archived": {"$ne": True}}
        since = _period_since(period)
        if since:
            match["finalized_at"] = {"$gte": since}
        pipeline = [
            {"$match": match},
            {"$group": {
                "_id": "$seller_id",
                "count": {"$sum": 1},
                "total_eur": {"$sum": "$current_bid_eur"},
            }},
            {"$sort": {"count": -1, "total_eur": -1}},
            {"$limit": limit},
        ]
        rows = await db.auctions.aggregate(pipeline).to_list(limit)
        return [{"user_id": r["_id"], "score": r["count"], "metric": r["count"],
                 "extra": {"total_eur": int(r["total_eur"] or 0)}} for r in rows if r["_id"]]

    async def _leaderboard_commenters(period: str, limit: int) -> list:
        match: dict = {"deleted": {"$ne": True}}
        since = _period_since(period)
        if since:
            match["created_at"] = {"$gte": since}
        pipeline = [
            {"$match": match},
            {"$project": {
                "user_id": 1,
                "ups": {"$size": {"$ifNull": ["$upvotes", []]}},
                "downs": {"$size": {"$ifNull": ["$downvotes", []]}},
            }},
            {"$group": {
                "_id": "$user_id",
                "score": {"$sum": {"$subtract": ["$ups", "$downs"]}},
                "comments": {"$sum": 1},
            }},
            {"$match": {"score": {"$gt": 0}}},
            {"$sort": {"score": -1, "comments": -1}},
            {"$limit": limit},
        ]
        rows = await db.comments.aggregate(pipeline).to_list(limit)
        return [{"user_id": r["_id"], "score": r["score"], "metric": r["score"],
                 "extra": {"comments": r["comments"]}} for r in rows if r["_id"]]

    async def _leaderboard_bidders(period: str, limit: int) -> list:
        match: dict = {}
        since = _period_since(period)
        if since:
            match["created_at"] = {"$gte": since}
        pipeline = [
            {"$match": match} if match else {"$match": {}},
            {"$group": {
                "_id": "$user_id",
                "count": {"$sum": 1},
                "total_eur": {"$sum": "$amount_eur"},
            }},
            {"$sort": {"count": -1, "total_eur": -1}},
            {"$limit": limit},
        ]
        rows = await db.bids.aggregate(pipeline).to_list(limit)
        return [{"user_id": r["_id"], "score": r["count"], "metric": r["count"],
                 "extra": {"total_eur": int(r["total_eur"] or 0)}} for r in rows if r["_id"]]

    async def _leaderboard_reputation(period: str, limit: int) -> list:
        """Composite score: sold × 10 + comment_score × 1 + bids × 0.5.

        Separate pipelines for each component are unioned in Python — the
        dataset is small enough (<100k users) that a Mongo $unionWith
        would be premature complexity.
        """
        by_user: dict = {}
        for row in await _leaderboard_sellers(period, 200):
            by_user.setdefault(row["user_id"], {}).update({"sold": row["score"]})
        for row in await _leaderboard_commenters(period, 200):
            by_user.setdefault(row["user_id"], {}).update({"karma": row["score"]})
        for row in await _leaderboard_bidders(period, 200):
            by_user.setdefault(row["user_id"], {}).update({"bids": row["score"]})
        results = []
        for uid, parts in by_user.items():
            sold = parts.get("sold", 0)
            karma = parts.get("karma", 0)
            bids = parts.get("bids", 0)
            rep = sold * 10 + karma + int(bids * 0.5)
            if rep <= 0:
                continue
            results.append({
                "user_id": uid,
                "score": rep,
                "metric": rep,
                "extra": {"sold": sold, "karma": karma, "bids": bids},
            })
        results.sort(key=lambda r: r["score"], reverse=True)
        return results[:limit]

    @router.get("/leaderboard")
    async def leaderboard(
        type: str = Query("reputation", regex="^(sellers|commenters|bidders|reputation)$"),
        period: str = Query("all", regex="^(all|month)$"),
        limit: int = Query(20, ge=1, le=50),
    ):
        cache_key = f"{type}:{period}:{limit}"
        cached = _LEADERBOARD_CACHE.get(cache_key)
        if cached and (time.time() - cached["at"] < _LEADERBOARD_TTL_SEC):
            return cached["data"]

        if type == "sellers":
            rows = await _leaderboard_sellers(period, limit)
        elif type == "commenters":
            rows = await _leaderboard_commenters(period, limit)
        elif type == "bidders":
            rows = await _leaderboard_bidders(period, limit)
        else:
            rows = await _leaderboard_reputation(period, limit)

        # Hydrate with user metadata in a single query.
        uids = [r["user_id"] for r in rows]
        users = {}
        async for u in db.users.find(
            {"id": {"$in": uids}},
            {"_id": 0, "id": 1, "name": 1, "avatar_url": 1,
             "is_verified_dealer": 1, "dealer_slug": 1, "role": 1,
             "profile_slug": 1},
        ):
            users[u["id"]] = u
        out = []
        for idx, r in enumerate(rows, start=1):
            u = users.get(r["user_id"]) or {}
            out.append({
                "rank": idx,
                "user_id": r["user_id"],
                "name": u.get("name") or "—",
                "avatar_url": u.get("avatar_url"),
                "is_verified_dealer": bool(u.get("is_verified_dealer")),
                "dealer_slug": u.get("dealer_slug"),
                "profile_slug": u.get("profile_slug"),
                "role": u.get("role"),
                "score": r["score"],
                "metric": r["metric"],
                "extra": r.get("extra", {}),
            })
        _LEADERBOARD_CACHE[cache_key] = {"at": time.time(), "data": out}
        return out

    return router
