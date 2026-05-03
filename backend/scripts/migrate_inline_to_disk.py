"""One-shot migration: convert any inline base64 data URLs in MongoDB to
disk-stored files served from `/uploads/...`.

Walks all auctions and rewrites these fields when they contain data URLs:
    images, thumbnails, images_exterior, images_interior,
    images_wheels, images_bumper

Also rewrites user avatars (`users.avatar_url`) and per-listing
`seller_avatar_url` snapshots, and per-comment `user_avatar_url`.

Idempotent — running twice is a no-op (DiskStorage detects the existing
hash and returns the same URL without re-writing the file).

Usage:
    cd /app/backend && python -m scripts.migrate_inline_to_disk
"""
from __future__ import annotations

import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _is_data_url(v) -> bool:
    return isinstance(v, str) and v.startswith("data:image/")


def _normalise_path(v, public_base: str) -> str | None:
    """Rewrite a stored URL to the current PUBLIC_UPLOAD_BASE so previous
    migration runs (which used different prefixes) get normalised. Returns
    the new value, or None if no change is needed."""
    if not isinstance(v, str):
        return None
    # Detect legacy `/uploads/...` (without `/api/` prefix) and rewrite.
    if v.startswith("/uploads/") and public_base != "/uploads":
        return public_base + v[len("/uploads"):]
    return None


async def main() -> None:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".env"))

    # Force disk backend for the migration regardless of env.
    os.environ["STORAGE_BACKEND"] = "disk"

    from motor.motor_asyncio import AsyncIOMotorClient
    from storage import store_image, _get_backend

    client = AsyncIOMotorClient(os.environ["MONGO_URL"])
    db = client[os.environ["DB_NAME"]]
    public_base = _get_backend().public_base if hasattr(_get_backend(), "public_base") else "/api/uploads"

    # ---- Auctions ----
    image_fields = (
        "images", "thumbnails",
        "images_exterior", "images_interior",
        "images_wheels", "images_bumper",
    )
    cursor = db.auctions.find({}, {"_id": 0, "id": 1, **{f: 1 for f in image_fields}})
    auctions_updated = 0
    auctions_total_files = 0
    async for a in cursor:
        update = {}
        for f in image_fields:
            arr = a.get(f) or []
            if not arr:
                continue
            new_arr = []
            changed = False
            for u in arr:
                if _is_data_url(u):
                    new_url = store_image(u)  # writes to disk if not already there
                    new_arr.append(new_url)
                    if new_url != u:
                        changed = True
                        auctions_total_files += 1
                else:
                    rewritten = _normalise_path(u, public_base)
                    if rewritten:
                        new_arr.append(rewritten)
                        changed = True
                    else:
                        new_arr.append(u)
            if changed:
                update[f] = new_arr
        if update:
            await db.auctions.update_one({"id": a["id"]}, {"$set": update})
            auctions_updated += 1
            print(f"  ✓ auction {a['id']}  ({len(update)} fields updated)")

    # ---- Users (avatar_url) ----
    users_updated = 0
    cursor = db.users.find(
        {"$or": [
            {"avatar_url": {"$regex": "^data:image/"}},
            {"avatar_url": {"$regex": "^/uploads/"}},
        ]},
        {"_id": 0, "id": 1, "avatar_url": 1},
    )
    async for u in cursor:
        old = u["avatar_url"]
        if _is_data_url(old):
            new_url = store_image(old)
        else:
            new_url = _normalise_path(old, public_base) or old
        if new_url != old:
            await db.users.update_one({"id": u["id"]}, {"$set": {"avatar_url": new_url}})
            await db.auctions.update_many(
                {"seller_id": u["id"], "seller_avatar_url": old},
                {"$set": {"seller_avatar_url": new_url}},
            )
            await db.comments.update_many(
                {"user_id": u["id"], "user_avatar_url": old},
                {"$set": {"user_avatar_url": new_url}},
            )
            users_updated += 1
            print(f"  ✓ user {u['id']} avatar migrated")

    print()
    print(f"Done. Auctions: {auctions_updated} updated, {auctions_total_files} files written.")
    print(f"      Users:    {users_updated} avatars migrated.")


if __name__ == "__main__":
    asyncio.run(main())
