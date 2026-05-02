"""
One-off backfill: generate 400px JPEG thumbnails for auctions that were
created before card-thumbnails were added to the pipeline.

Usage (from inside the backend venv / pod):
    python3 /app/backend/scripts/backfill_thumbnails.py

Idempotent — only auctions whose `thumbnails` list is missing / empty OR is
shorter than their `images` list get reprocessed. Re-running is safe.
"""
from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

# Allow `import services.image_processing` even when run from elsewhere.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dotenv import load_dotenv  # noqa: E402
load_dotenv(str(Path(__file__).resolve().parents[1] / ".env"))

from motor.motor_asyncio import AsyncIOMotorClient  # noqa: E402
from services import image_processing as imgproc    # noqa: E402


BUCKETS = ("images", "images_exterior", "images_interior", "images_damage", "images_engine", "images_underside")


async def process_one(db, a: dict) -> bool:
    """Return True when the document was updated."""
    update: dict = {}
    # Primary bucket drives the "thumbnails" field (used by listing cards).
    for bucket in BUCKETS:
        raw_list = a.get(bucket) or []
        if not raw_list:
            continue
        web_list, thumb_list, _errs = await asyncio.to_thread(imgproc.optimize_many, raw_list)
        if not thumb_list:
            continue
        # Keep the original URL order; optimize_many preserves it.
        if bucket == "images":
            update["thumbnails"] = thumb_list
        # Also update the bucket itself if the web-optimized list came out
        # different (e.g. the cover was a huge un-compressed upload).
        if web_list != raw_list:
            update[bucket] = web_list
    if update:
        await db.auctions.update_one({"id": a["id"]}, {"$set": update})
        return True
    return False


async def main():
    client = AsyncIOMotorClient(os.environ["MONGO_URL"])
    db = client[os.environ["DB_NAME"]]
    query = {
        "$or": [
            {"thumbnails": {"$exists": False}},
            {"thumbnails": []},
            {"thumbnails": {"$type": "null"}},
        ]
    }
    total = await db.auctions.count_documents(query)
    print(f"Auctions needing backfill: {total}")
    updated = 0
    cursor = db.auctions.find(query, {"_id": 0})
    async for a in cursor:
        try:
            ok = await process_one(db, a)
            updated += 1 if ok else 0
            print(f"  · {a.get('id', '?')[:8]}  {a.get('title', '')[:60]:60}  {'✓' if ok else '—'}")
        except Exception as e:
            print(f"  ! {a.get('id', '?')[:8]}  FAILED: {e}")
    print(f"Done. {updated}/{total} updated.")


if __name__ == "__main__":
    asyncio.run(main())
