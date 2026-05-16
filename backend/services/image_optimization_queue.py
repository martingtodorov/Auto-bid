"""
Single-worker async queue for image AVIF/WebP/JPG variant generation.

WHY this exists (architectural rationale):
==========================================

The legacy upload pipeline did all image work synchronously during the
HTTP request:

    user clicks Submit → upload → optimize → variants → store → return URL

That meant:
  • 25-photo car listings spent 30-90 s in `optimize_many` before the
    request completed → frequent uploader timeouts on mobile/4G.
  • Pillow encoding pinned a CPU core during the request, starving
    bidding-loop responsiveness during the auction prime time when
    sellers tend to add new listings.
  • A single bad image (corrupt EXIF, unsupported HEIC variant) failed
    the whole submission rather than persisting the rest.

New flow:

    user clicks Submit
      → upload bytes
      → store ORIGINAL on disk (cheap, ~10 ms each)
      → record status=`original_uploaded`
      → enqueue background variant generation
      → return URLs immediately (using the original as `primary`)

Variant generation runs in the background with:

  • `MAX_CONCURRENCY=1` — one Pillow encode at a time (CPU-bound;
    parallelism just trashes the cache and hurts throughput).
  • Retry on transient failures with exponential backoff (3 attempts).
  • The original is NEVER deleted until variants are successfully
    written → if encoding fails, the user still sees a working image
    (just unoptimized — bigger payload, no AVIF).

Per-auction status is tracked in `auction.image_optimization` so the
admin UI can show pending/failed counts and offer a retry button.

Queue is in-process (no Redis). Survives restarts via `_resume_pending`
on startup which scans the DB for `optimization_pending` rows.
"""
from __future__ import annotations

import asyncio
import logging
import os
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

log = logging.getLogger(__name__)

# CPU-bound work: 1 concurrent encode is optimal on a single-box deployment.
# Increase only if the host has many cores AND we're not seeing the API
# loop starve under encode load.
MAX_CONCURRENCY = 1

# Per-image retry policy. Backoff schedule (seconds) is intentionally
# short — encode failures are usually deterministic (corrupt source).
MAX_ATTEMPTS = 3
RETRY_BACKOFF_SECONDS = (5, 30, 120)

# Per-image hard timeout. Even a high-res 12MP shot finishes well under
# 30 s on the modest 2-core Hetzner box; anything longer means a Pillow
# bug or runaway memory.
ENCODE_TIMEOUT_SECONDS = 60


@dataclass
class _Job:
    sha: str
    src_path: str          # path on disk to the ORIGINAL file
    auction_id: Optional[str]
    image_idx: Optional[int]
    attempt: int
    enqueued_at: float


_queue: "asyncio.Queue[_Job]" = asyncio.Queue()
_in_flight: set[str] = set()        # `sha` strings currently queued or running
_worker_started = False
_lock = asyncio.Lock()
_db = None  # set by `init(db)` at startup


# --- Status field helpers ---------------------------------------------------
# We store optimization status per image inside the auction document:
#
#   auction.image_optimization = {
#     "<sha>": {
#       "status":   "original_uploaded" | "optimizing" | "optimized" | "failed",
#       "attempts": int,
#       "last_error": str | None,
#       "updated_at": isoformat,
#     }
#   }
#
# Aggregate counts (used by the admin dashboard) are derived from this map
# via a single aggregation query — no separate collection needed.

async def _set_status(
    auction_id: Optional[str], sha: str, status: str,
    *, attempts: Optional[int] = None, error: Optional[str] = None,
):
    if not auction_id or _db is None:
        return
    payload: dict = {
        f"image_optimization.{sha}.status": status,
        f"image_optimization.{sha}.updated_at": datetime.now(timezone.utc).isoformat(),
    }
    if attempts is not None:
        payload[f"image_optimization.{sha}.attempts"] = attempts
    if error is not None:
        # Trim to keep the doc small — full traceback already in logs.
        payload[f"image_optimization.{sha}.last_error"] = error[:300]
    try:
        await _db.auctions.update_one({"id": auction_id}, {"$set": payload})
    except Exception:  # noqa: BLE001
        log.exception("failed to set optimization status sha=%s status=%s", sha[:10], status)


def init(db) -> None:
    """Bind the MongoDB handle. Called once from `server.py` startup."""
    global _db
    _db = db


# --- Core worker ------------------------------------------------------------

async def _encode_one(job: _Job) -> tuple[bool, Optional[str]]:
    """Synchronously encode all variants for a single source file.

    Returns `(ok, error_message)`. Runs the Pillow work in a thread so the
    event loop stays responsive (Pillow releases the GIL during JPEG/AVIF
    encoding, so this gives us real parallelism with the API loop).
    """
    from services.image_variants import generate_variants

    try:
        with open(job.src_path, "rb") as f:
            src_bytes = f.read()
    except OSError as e:
        return False, f"read failed: {e}"

    def _do():
        return generate_variants(src_bytes, sha=job.sha)

    try:
        manifest = await asyncio.wait_for(
            asyncio.to_thread(_do), timeout=ENCODE_TIMEOUT_SECONDS,
        )
    except asyncio.TimeoutError:
        return False, f"encode timed out after {ENCODE_TIMEOUT_SECONDS}s"
    except Exception as e:  # noqa: BLE001
        return False, f"{type(e).__name__}: {e}"

    # Sanity check: the largest size must exist as JPG for `primary`.
    if not manifest.get("primary"):
        return False, "manifest missing primary JPG"

    # Persist the manifest back onto the auction document so the frontend
    # can pick up the AVIF/WebP variants on next load.
    if job.auction_id and _db is not None:
        try:
            await _db.auctions.update_one(
                {"id": job.auction_id, "image_optimization." + job.sha + ".status": {"$in": ["optimizing", "original_uploaded"]}},
                {"$set": {
                    f"image_optimization.{job.sha}.manifest": manifest,
                }},
            )
        except Exception:  # noqa: BLE001
            log.exception("failed to persist manifest for sha=%s", job.sha[:10])
    return True, None


async def _run_one(job: _Job):
    started = time.time()
    log.info(
        "img-queue: starting sha=%s auction=%s attempt=%s/%s queue_wait=%.1fs",
        job.sha[:10], job.auction_id, job.attempt, MAX_ATTEMPTS,
        started - job.enqueued_at,
    )
    await _set_status(
        job.auction_id, job.sha, "optimizing", attempts=job.attempt,
    )
    ok, err = await _encode_one(job)
    elapsed = time.time() - started
    if ok:
        log.info("img-queue: finished sha=%s ok=True in %.1fs", job.sha[:10], elapsed)
        await _set_status(job.auction_id, job.sha, "optimized", attempts=job.attempt)
        return

    log.warning(
        "img-queue: encode failed sha=%s attempt=%s/%s err=%s",
        job.sha[:10], job.attempt, MAX_ATTEMPTS, err,
    )
    if job.attempt < MAX_ATTEMPTS:
        # Schedule a retry. Backoff slot indexes from 0.
        backoff = RETRY_BACKOFF_SECONDS[min(job.attempt - 1, len(RETRY_BACKOFF_SECONDS) - 1)]
        await _set_status(
            job.auction_id, job.sha, "optimizing",
            attempts=job.attempt, error=err,
        )

        async def _resched():
            await asyncio.sleep(backoff)
            retry_job = _Job(
                sha=job.sha, src_path=job.src_path,
                auction_id=job.auction_id, image_idx=job.image_idx,
                attempt=job.attempt + 1, enqueued_at=time.time(),
            )
            await _queue.put(retry_job)

        asyncio.create_task(_resched())
    else:
        await _set_status(
            job.auction_id, job.sha, "failed",
            attempts=job.attempt, error=err,
        )


async def _worker():
    """Single consumer — pulls jobs sequentially, never in parallel."""
    while True:
        job = await _queue.get()
        try:
            await _run_one(job)
        except Exception:  # noqa: BLE001
            log.exception("img-queue: worker loop error sha=%s", job.sha[:10])
        finally:
            _in_flight.discard(job.sha)
            _queue.task_done()


# --- Public API -------------------------------------------------------------

async def enqueue(
    *, sha: str, src_path: str,
    auction_id: Optional[str] = None,
    image_idx: Optional[int] = None,
) -> bool:
    """Submit a variant-generation job. Idempotent: the same `sha` cannot
    be queued twice concurrently. Returns True if a new job was enqueued,
    False if a duplicate was suppressed.
    """
    global _worker_started

    async with _lock:
        if sha in _in_flight:
            return False
        _in_flight.add(sha)
        if not _worker_started:
            _worker_started = True
            for _ in range(MAX_CONCURRENCY):
                asyncio.create_task(_worker())

    # Mark status before enqueueing so the admin UI shows "pending"
    # immediately, even before the worker picks the job up.
    await _set_status(auction_id, sha, "optimizing", attempts=1)
    await _queue.put(_Job(
        sha=sha, src_path=src_path,
        auction_id=auction_id, image_idx=image_idx,
        attempt=1, enqueued_at=time.time(),
    ))
    return True


async def enqueue_for_stored_urls(
    urls: list[str],
    *,
    auction_id: Optional[str] = None,
    categories: Optional[list[str]] = None,
) -> int:
    """Enqueue variant generation for images already persisted to disk.

    Called by `/auctions` submit + `/auctions/import-mobile-bg` so the
    HTTP response returns AS SOON AS the optimized JPGs are stored —
    AVIF/WebP variants for the responsive `<Picture>` element generate
    in the background, not on the submit request thread.

    `urls` are public URLs as returned by `storage.store_image()` —
    they end in `<sha>.<ext>` because the disk backend is
    content-addressed. We extract sha + extension from the URL, locate
    the file on disk, and submit one queue job per image.

    Returns the number of jobs successfully enqueued.
    """
    if not urls:
        return 0
    upload_root = os.environ.get("UPLOAD_DIR", "/opt/autobids/uploads")
    enqueued = 0
    for idx, url in enumerate(urls):
        if not isinstance(url, str) or not url:
            continue
        # URL forms accepted:
        #   /api/uploads/auctions/<aa>/<sha>.<ext>
        #   https://img.autoandbid.bg/uploads/auctions/<aa>/<sha>.<ext>
        #   /uploads/auctions/<aa>/<sha>.<ext>
        marker = "/uploads/"
        if marker not in url:
            continue
        rel = url.split(marker, 1)[1]
        abs_path = os.path.join(upload_root, rel)
        if not os.path.isfile(abs_path):
            log.warning("ioq.enqueue_for_stored_urls: file missing %s", abs_path)
            continue
        sha = os.path.splitext(os.path.basename(abs_path))[0]
        # Sanity: storage layer should always produce a 64-char hex sha.
        # If the URL isn't sha-addressed (e.g. legacy import) hash the
        # file bytes — slow but correct.
        if len(sha) != 64 or any(c not in "0123456789abcdef" for c in sha):
            import hashlib
            with open(abs_path, "rb") as f:
                sha = hashlib.sha256(f.read()).hexdigest()
        if await enqueue(
            sha=sha, src_path=abs_path,
            auction_id=auction_id, image_idx=idx,
        ):
            enqueued += 1
    return enqueued


async def retry_failed(*, sha: str, src_path: str, auction_id: str) -> bool:
    """Admin-triggered retry of a previously-failed image. Resets the
    status to `optimizing` and re-enqueues the job from attempt 1.
    """
    return await enqueue(sha=sha, src_path=src_path, auction_id=auction_id)


async def resume_pending() -> int:
    """Re-enqueue images still in `optimizing` status on startup. Called
    once from server.py during the lifespan startup hook. Returns the
    number of jobs re-enqueued.
    """
    if _db is None:
        return 0
    upload_root = os.environ.get("UPLOAD_DIR", "/opt/autobids/uploads")
    count = 0
    try:
        cursor = _db.auctions.find(
            {"image_optimization": {"$exists": True, "$ne": {}}},
            {"_id": 0, "id": 1, "image_optimization": 1},
        )
        async for doc in cursor:
            mp = doc.get("image_optimization") or {}
            for sha, st in mp.items():
                if (st or {}).get("status") != "optimizing":
                    continue
                # The original file lives under <UPLOAD_DIR>/auctions/<aa>/<sha>.<ext>.
                # We don't know the extension here, so glob the directory.
                sub = sha[:2]
                d = os.path.join(upload_root, "auctions", sub)
                src = None
                if os.path.isdir(d):
                    for name in os.listdir(d):
                        if name.startswith(sha + "."):
                            src = os.path.join(d, name)
                            break
                if not src:
                    log.warning("img-queue resume: no source on disk for sha=%s", sha[:10])
                    await _set_status(
                        doc["id"], sha, "failed",
                        error="source missing on disk during resume",
                    )
                    continue
                if await enqueue(sha=sha, src_path=src, auction_id=doc["id"]):
                    count += 1
    except Exception:  # noqa: BLE001
        log.exception("img-queue resume_pending crashed")
    log.info("img-queue: resume re-enqueued %d jobs", count)
    return count


def stats() -> dict:
    """In-process queue stats for `/admin/storage-health`."""
    return {
        "pending": _queue.qsize(),
        "in_flight": len(_in_flight),
        "max_concurrency": MAX_CONCURRENCY,
        "max_attempts": MAX_ATTEMPTS,
        "encode_timeout_seconds": ENCODE_TIMEOUT_SECONDS,
    }


async def db_stats() -> dict:
    """Persistent counts across the entire DB — used for the admin UI."""
    if _db is None:
        return {}
    pipeline = [
        {"$match": {"image_optimization": {"$exists": True, "$ne": {}}}},
        {"$project": {"_id": 0, "image_optimization": {"$objectToArray": "$image_optimization"}}},
        {"$unwind": "$image_optimization"},
        {"$group": {"_id": "$image_optimization.v.status", "n": {"$sum": 1}}},
    ]
    counts: dict[str, int] = {"optimized": 0, "optimizing": 0, "failed": 0, "original_uploaded": 0}
    try:
        async for row in _db.auctions.aggregate(pipeline):
            counts[row["_id"]] = row["n"]
    except Exception:  # noqa: BLE001
        log.exception("img-queue db_stats failed")
    return counts


async def failed_items(limit: int = 50) -> list[dict]:
    """List auctions that have at least one failed image. Used by the
    admin UI to show a clickable retry list."""
    if _db is None:
        return []
    out: list[dict] = []
    try:
        cursor = _db.auctions.find(
            {"image_optimization": {"$exists": True, "$ne": {}}},
            {"_id": 0, "id": 1, "title": 1, "image_optimization": 1, "status": 1},
        )
        async for doc in cursor:
            mp = doc.get("image_optimization") or {}
            failed = [
                {
                    "sha": sha,
                    "attempts": (st or {}).get("attempts"),
                    "last_error": (st or {}).get("last_error"),
                    "updated_at": (st or {}).get("updated_at"),
                }
                for sha, st in mp.items() if (st or {}).get("status") == "failed"
            ]
            if failed:
                out.append({
                    "auction_id": doc["id"],
                    "title": doc.get("title"),
                    "status": doc.get("status"),
                    "failed_images": failed,
                })
                if len(out) >= limit:
                    break
    except Exception:  # noqa: BLE001
        log.exception("img-queue failed_items failed")
    return out
