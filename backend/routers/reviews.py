"""
Buyer → Seller reviews (rating + text).

Rules:
- Only buyers of a `sold` auction may review that auction's seller.
- One review per (buyer, auction) pair.
- Reviews are public; the author's name is shown.
- Aggregate rating (avg + count) is exposed via /api/users/{id}/rating and
  embedded in the public profile response for JSON-LD AggregateRating.
"""
import logging
import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, Field

from deps import db

router = APIRouter()
logger = logging.getLogger(__name__)

_get_current_user = None


def configure(*, get_current_user):
    global _get_current_user
    _get_current_user = get_current_user


class ReviewCreate(BaseModel):
    auction_id: str
    rating: int = Field(ge=1, le=5)
    text: str = Field(min_length=3, max_length=1200)


def _pub(r: dict) -> dict:
    return {
        "id": r["id"],
        "seller_id": r["seller_id"],
        "buyer_id": r["buyer_id"],
        "buyer_name": r.get("buyer_name", ""),
        "auction_id": r["auction_id"],
        "auction_title": r.get("auction_title", ""),
        "rating": int(r.get("rating", 0)),
        "text": r.get("text", ""),
        "created_at": r["created_at"],
    }


async def _aggregate(seller_id: str) -> dict:
    cur = db.reviews.find({"seller_id": seller_id}, {"_id": 0, "rating": 1})
    ratings = [int(r["rating"]) async for r in cur]
    count = len(ratings)
    avg = round(sum(ratings) / count, 2) if count else 0.0
    return {"avg": avg, "count": count}


def register_routes():
    assert _get_current_user is not None, "reviews router not configured"

    @router.post("/users/{seller_id}/reviews")
    async def create_review(
        seller_id: str,
        payload: ReviewCreate,
        user=Depends(_get_current_user),
    ):
        if user["id"] == seller_id:
            raise HTTPException(status_code=400, detail="Не можете да оцените собствения си профил.")

        auc = await db.auctions.find_one(
            {"id": payload.auction_id}, {"_id": 0}
        )
        if not auc:
            raise HTTPException(status_code=404, detail="Обявата не е намерена.")
        if auc.get("seller_id") != seller_id:
            raise HTTPException(status_code=400, detail="Тази обява не принадлежи на посочения продавач.")
        if auc.get("status") != "sold":
            raise HTTPException(status_code=400, detail="Можете да оценявате само приключили с продажба търгове.")
        if auc.get("high_bidder_id") != user["id"]:
            raise HTTPException(status_code=403, detail="Само купувачът на обявата може да остави отзив.")

        exists = await db.reviews.find_one(
            {"auction_id": payload.auction_id, "buyer_id": user["id"]}, {"_id": 0, "id": 1}
        )
        if exists:
            raise HTTPException(status_code=400, detail="Вече сте оставили отзив за тази сделка.")

        doc = {
            "id": str(uuid.uuid4()),
            "seller_id": seller_id,
            "buyer_id": user["id"],
            "buyer_name": user.get("name") or "Купувач",
            "auction_id": payload.auction_id,
            "auction_title": auc.get("title", ""),
            "rating": int(payload.rating),
            "text": payload.text.strip(),
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        await db.reviews.insert_one(doc)
        doc.pop("_id", None)
        return _pub(doc)

    @router.get("/users/{seller_id}/reviews")
    async def list_reviews(seller_id: str, limit: int = 50):
        limit = max(1, min(200, int(limit)))
        cur = db.reviews.find({"seller_id": seller_id}, {"_id": 0}).sort("created_at", -1).limit(limit)
        items = [_pub(r) async for r in cur]
        agg = await _aggregate(seller_id)
        return {"items": items, "rating": agg}

    @router.get("/users/{seller_id}/rating")
    async def rating(seller_id: str):
        return await _aggregate(seller_id)

    @router.get("/users/{seller_id}/reviews/eligible/{auction_id}")
    async def eligibility(seller_id: str, auction_id: str, user=Depends(_get_current_user)):
        """Tell the frontend whether the current user may leave a review for this sale."""
        auc = await db.auctions.find_one({"id": auction_id}, {"_id": 0})
        if not auc:
            return {"eligible": False, "reason": "auction_not_found"}
        if auc.get("seller_id") != seller_id:
            return {"eligible": False, "reason": "seller_mismatch"}
        if auc.get("status") != "sold":
            return {"eligible": False, "reason": "not_sold"}
        if auc.get("high_bidder_id") != user["id"]:
            return {"eligible": False, "reason": "not_buyer"}
        exists = await db.reviews.find_one(
            {"auction_id": auction_id, "buyer_id": user["id"]}, {"_id": 0, "id": 1}
        )
        if exists:
            return {"eligible": False, "reason": "already_reviewed"}
        return {"eligible": True}

    @router.get("/me/reviewable")
    async def my_reviewable_purchases(user=Depends(_get_current_user)):
        """Purchases by the user that are still pending a review."""
        cur = db.auctions.find(
            {"high_bidder_id": user["id"], "status": "sold"},
            {"_id": 0, "id": 1, "title": 1, "seller_id": 1, "seller_name": 1, "images": 1, "current_bid_eur": 1, "finalized_at": 1},
        ).sort("finalized_at", -1).limit(100)
        purchases = await cur.to_list(100)
        if not purchases:
            return {"items": []}
        reviewed_ids = set()
        rev_cur = db.reviews.find({"buyer_id": user["id"]}, {"_id": 0, "auction_id": 1})
        async for r in rev_cur:
            reviewed_ids.add(r["auction_id"])
        out = []
        for a in purchases:
            if a["id"] in reviewed_ids:
                continue
            out.append({
                "auction_id": a["id"],
                "auction_title": a.get("title", ""),
                "seller_id": a.get("seller_id", ""),
                "seller_name": a.get("seller_name", ""),
                "cover_image": (a.get("images") or [None])[0],
                "price_eur": a.get("current_bid_eur", 0),
                "finalized_at": a.get("finalized_at"),
            })
        return {"items": out}
