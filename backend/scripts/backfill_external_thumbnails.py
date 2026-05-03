"""One-shot backfill: rewrite `thumbnails` of imported (hosted-URL) auctions.

When mobile.bg listings were scraped we stored the same `/big1/` URL in
both `images` and `thumbnails`. Run this script once to swap the thumb
URLs over to the CDN's small variant (~16 KB instead of ~270 KB).

Usage:
    cd /app/backend && python -m scripts.backfill_external_thumbnails
"""
from __future__ import annotations

import asyncio
import os
import sys

# Make `backend/` importable when invoked as a module
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from motor.motor_asyncio import AsyncIOMotorClient  # noqa: E402

from services.image_processing import derive_external_thumbnail  # noqa: E402


async def main() -> None:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".env"))
    mongo_url = os.environ["MONGO_URL"]
    db_name = os.environ["DB_NAME"]
    client = AsyncIOMotorClient(mongo_url)
    db = client[db_name]

    cursor = db.auctions.find(
        {"thumbnails": {"$exists": True, "$ne": []}},
        {"_id": 0, "id": 1, "thumbnails": 1},
    )
    updated = 0
    skipped = 0
    async for a in cursor:
        thumbs = a.get("thumbnails") or []
        new_thumbs = [derive_external_thumbnail(u) for u in thumbs]
        if new_thumbs == thumbs:
            skipped += 1
            continue
        await db.auctions.update_one(
            {"id": a["id"]},
            {"$set": {"thumbnails": new_thumbs}},
        )
        updated += 1
        print(f"  ✓ {a['id']}  ({sum(1 for n, o in zip(new_thumbs, thumbs) if n != o)}/{len(thumbs)} thumbs rewritten)")

    print(f"\nDone. Updated: {updated}  Skipped: {skipped}")


if __name__ == "__main__":
    asyncio.run(main())
