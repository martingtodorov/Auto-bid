"""One-shot migration: pull every external image URL on existing auctions
into our local CDN. Idempotent — items that are already on
`/api/uploads/...` (or `data:image/...`) are skipped.

Run with:
    cd /app/backend && python3 -m scripts.migrate_external_images

Touches:
    * auctions.images           — full-resolution gallery
    * auctions.thumbnails       — 400px companion
    * auctions.images_variants  — AVIF/WebP/JPG × 4 sizes manifest
    * auctions.images_exterior / _wheels / _bumper / _interior

The legacy buckets stay populated so any pre-`<Picture>` consumer keeps
working. `images_variants` is regenerated from the same locally-stored
bytes so the responsive `<Picture>` pipeline serves AVIF/WebP from our
own CDN.
"""
from __future__ import annotations

import asyncio
import logging
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from motor.motor_asyncio import AsyncIOMotorClient

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("migrate_external_images")


IMAGE_BUCKETS = ("images", "thumbnails", "images_exterior", "images_wheels", "images_bumper", "images_interior")


def _is_external(url: str) -> bool:
    if not isinstance(url, str) or not url:
        return False
    if url.startswith(("data:image/", "/api/uploads/", "/uploads/")):
        return False
    return url.startswith(("http://", "https://"))


async def _migrate_doc(db, doc: dict) -> dict:
    from storage import fetch_remote_images_as_data_urls, store_image
    from services.image_processing import optimize_many
    from services.image_variants import variants_from_data_url

    aid = doc.get("id")
    title = (doc.get("title") or "")[:50]
    update: dict = {}

    # 1. Migrate each per-bucket image array independently.
    for key in IMAGE_BUCKETS:
        urls = doc.get(key) or []
        if not urls:
            continue
        if not any(_is_external(u) for u in urls):
            continue
        ext_count = sum(_is_external(u) for u in urls)
        logger.info("  [%s] %s — %d external URLs", aid[:8], key, ext_count)
        # `strict=True` returns "" for any URL that failed to fetch
        # (404 / network) so we drop those entries instead of letting
        # them pass through as external URLs on the persisted doc.
        data_urls = await fetch_remote_images_as_data_urls(urls, strict=True)
        # Drop failed fetches but keep already-local entries in place.
        kept = [u for u in data_urls if u]
        skipped = len(urls) - len(kept)
        if skipped:
            logger.warning("    [%s] %s: %d/%d URLs failed to fetch — dropping", aid[:8], key, skipped, len(urls))
        if not kept:
            logger.warning("    [%s] %s: ALL URLs failed — bucket left untouched", aid[:8], key)
            continue
        web, thumb, errs = await asyncio.to_thread(optimize_many, kept)
        if errs:
            logger.warning("    optimize errors for %s.%s: %s", aid, key, errs[:3])
        web_stored = [await asyncio.to_thread(store_image, u) for u in web]
        if key == "images":
            thumb_stored = [await asyncio.to_thread(store_image, u) for u in thumb]
            update["thumbnails"] = thumb_stored
        update[key] = web_stored

    # 2. Rebuild image variants for the canonical `images` array so the
    #    responsive <Picture> pipeline serves AVIF/WebP from local disk.
    canonical_images = update.get("images") or doc.get("images") or []
    if canonical_images and (update.get("images") or not doc.get("images_variants")):
        # Re-fetch the (now local) bytes so we can regenerate variants.
        # `fetch_remote_images_as_data_urls` handles /api/uploads paths by
        # passing them through unchanged — read from disk instead.
        from storage import _get_backend  # type: ignore
        backend = _get_backend()
        upload_root = getattr(backend, "root", None)
        manifests = []
        import base64
        for idx, ref in enumerate(canonical_images):
            data_url = None
            if ref.startswith("data:image/"):
                data_url = ref
            elif upload_root and ref.startswith("/api/uploads/"):
                rel = ref.split("/api/uploads/", 1)[1]
                path = os.path.join(upload_root, rel)
                ext = ref.rsplit(".", 1)[-1].lower()
                try:
                    with open(path, "rb") as f:
                        b64 = base64.b64encode(f.read()).decode("ascii")
                    data_url = f"data:image/{ext};base64,{b64}"
                except OSError as e:
                    logger.warning("    skip variant for %s: %s", path, e)
            if not data_url:
                continue
            m = await asyncio.to_thread(variants_from_data_url, data_url)
            if m:
                m["category"] = "main" if idx == 0 else "exterior"
                manifests.append(m)
        if manifests:
            update["images_variants"] = manifests

    if not update:
        logger.info("  [%s] %s — already local, skip", aid[:8], title)
        return {"id": aid, "changed": False}

    await db.auctions.update_one({"id": aid}, {"$set": update})
    logger.info("  [%s] %s — migrated %s buckets", aid[:8], title, list(update.keys()))
    return {"id": aid, "changed": True, "fields": list(update.keys())}


async def main():
    mongo_url = os.environ.get("MONGO_URL") or "mongodb://localhost:27017"
    db_name = os.environ.get("DB_NAME") or "test_database"
    cli = AsyncIOMotorClient(mongo_url)
    db = cli[db_name]
    docs = await db.auctions.find({}, {"_id": 0}).to_list(None)
    logger.info("Scanning %d auctions in db=%s", len(docs), db_name)
    results = []
    for d in docs:
        try:
            r = await _migrate_doc(db, d)
            results.append(r)
        except Exception as e:  # noqa: BLE001
            logger.exception("Migration failed for %s: %s", d.get("id"), e)
            results.append({"id": d.get("id"), "changed": False, "error": str(e)})
    changed = sum(1 for r in results if r.get("changed"))
    logger.info("DONE — migrated %d / %d auctions", changed, len(results))


if __name__ == "__main__":
    asyncio.run(main())
