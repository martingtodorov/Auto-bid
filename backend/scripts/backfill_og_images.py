"""One-shot backfill: generate and persist OG images for every live /
pending auction that doesn't yet have an `og_image_url` on its document.

Run this after deploying the eager-OG change so existing listings get
the same stable, pre-rendered share image behaviour as newly-approved
ones. The script is idempotent — re-running it on already-populated
auctions just recomputes the PNG (same content-addressed path) and
bumps the `?v=` cache buster to the current updated_at.

Usage:
    cd /app/backend && python -m scripts.backfill_og_images
"""
from __future__ import annotations

import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


async def main() -> None:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".env"))

    from motor.motor_asyncio import AsyncIOMotorClient
    from services.og_image import build_and_persist
    from datetime import datetime, timezone

    client = AsyncIOMotorClient(os.environ["MONGO_URL"])
    db = client[os.environ["DB_NAME"]]

    # Only rebuild visible auctions. "removed" / "ended" / "sold" are
    # still reachable via permalinks but their share image is frozen in
    # the state it had when the listing was last active.
    cursor = db.auctions.find(
        {"status": {"$in": ["live", "pending", "ended", "sold"]},
         "is_archived": {"$ne": True}},
        {"_id": 0},
    )
    ok, fail = 0, 0
    async for a in cursor:
        try:
            og_url = await build_and_persist(a)
            await db.auctions.update_one(
                {"id": a["id"]},
                {"$set": {
                    "og_image_url": og_url,
                    "og_image_updated_at": datetime.now(timezone.utc).isoformat(),
                }},
            )
            ok += 1
            print(f"  ✓ {a['id']}  →  {og_url}")
        except Exception as e:
            fail += 1
            print(f"  ✗ {a['id']}  failed: {e}")

    print(f"\nDone. ok={ok}  failed={fail}")


if __name__ == "__main__":
    asyncio.run(main())
