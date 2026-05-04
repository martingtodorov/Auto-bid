"""Watchlist — per-user "favourite auctions" list.

Extracted from server.py during the 2026-05-04 refactor pass. Only
depends on the `watches` and `auctions` collections. Logic kept
verbatim from the original implementation; the only structural change
is the builder-pattern wrapper used by every other router in this
folder.
"""
from __future__ import annotations
import uuid
from datetime import datetime, timezone
from fastapi import APIRouter, Depends


def build_watchlist_router(db, get_current_user, auction_status_fn, public_auction_fn):
    """Wire up `/auctions/{id}/watch`, `/watch-status`, `/me/watchlist`,
    `/me/listings` and `/me/bids`.

    `auction_status_fn` is `server._auction_status` and `public_auction_fn`
    is `server._public_auction` — passed in (rather than imported) to keep
    the router free of circular deps with server.py's helper soup.
    """
    router = APIRouter(prefix="/api", tags=["watchlist"])

    @router.get("/auctions/{auction_id}/watch-status")
    async def watch_status(auction_id: str, user: dict = Depends(get_current_user)):
        existing = await db.watches.find_one(
            {"auction_id": auction_id, "user_id": user["id"]},
        )
        return {"watching": bool(existing)}

    @router.post("/auctions/{auction_id}/watch")
    async def toggle_watch(auction_id: str, user: dict = Depends(get_current_user)):
        existing = await db.watches.find_one(
            {"auction_id": auction_id, "user_id": user["id"]},
        )
        if existing:
            await db.watches.delete_one(
                {"auction_id": auction_id, "user_id": user["id"]},
            )
            return {"watching": False}
        await db.watches.insert_one({
            "id": str(uuid.uuid4()),
            "auction_id": auction_id,
            "user_id": user["id"],
            "created_at": datetime.now(timezone.utc).isoformat(),
        })
        return {"watching": True}

    @router.get("/me/watchlist")
    async def my_watchlist(user: dict = Depends(get_current_user)):
        watches = await db.watches.find(
            {"user_id": user["id"]}, {"_id": 0},
        ).to_list(200)
        ids = [w["auction_id"] for w in watches]
        if not ids:
            return []
        items = await db.auctions.find(
            {"id": {"$in": ids}}, {"_id": 0},
        ).to_list(200)
        for a in items:
            a["status"] = auction_status_fn(a)
        return items

    @router.get("/me/listings")
    async def my_listings(user: dict = Depends(get_current_user)):
        items = await db.auctions.find(
            {"seller_id": user["id"]}, {"_id": 0},
        ).sort("created_at", -1).to_list(500)
        return [public_auction_fn(a, user) for a in items]

    @router.get("/me/bids")
    async def my_bids(user: dict = Depends(get_current_user)):
        from services import bidding as bidding_svc
        return await bidding_svc.list_user_bids(user["id"], limit=200)

    return router
