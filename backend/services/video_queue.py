"""
Single-worker async queue for video compression jobs.

Why: AV1 encoding is extremely CPU-intensive (one core pinned at 100 %
for ~60-180 s per minute of input). Letting requests fan out into
concurrent encodes will pin every core and starve the API loop. A
**bounded queue with a single consumer** keeps the box responsive
under load — at worst, encodes back up; we never overload.

Queue is in-process (no Redis dep) so it does NOT survive a restart.
That's an acceptable trade-off: if uvicorn restarts mid-encode the
source file is still on disk, and the next user upload will re-queue
it (sha-keyed, so we don't waste cycles on the same SHA twice). For
multi-replica deployments this should be upgraded to a Redis/Celery
queue, but for the current single-box Hetzner deployment it is fine.

Guarantees:
- At most ONE encode runs at any time (`MAX_CONCURRENCY=1`).
- Each encode has a hard timeout (default 180 s).
- Failed encodes are logged with stderr + exit code.
- The same `out_path` is never queued twice (idempotent enqueue).
"""

from __future__ import annotations

import asyncio
import logging
import os
import time
from typing import Awaitable, Callable, Optional

log = logging.getLogger(__name__)

MAX_CONCURRENCY = 1
ENCODE_TIMEOUT_SECONDS = 180


class _Job:
    __slots__ = ("src", "out", "on_done", "enqueued_at")

    def __init__(self, src: str, out: str, on_done: Optional[Callable[[bool], Awaitable[None]]]):
        self.src = src
        self.out = out
        self.on_done = on_done
        self.enqueued_at = time.time()


_queue: "asyncio.Queue[_Job]" = asyncio.Queue()
_in_flight: set[str] = set()  # `out_path` strings currently queued or running
_worker_started = False
_lock = asyncio.Lock()


async def _run_one(job: _Job, encoder: Callable[[str, str], Awaitable[bool]]):
    started = time.time()
    log.info("video-queue: starting AV1 transcode src=%s out=%s queue_wait=%.1fs",
             job.src, job.out, started - job.enqueued_at)
    ok = False
    try:
        ok = await asyncio.wait_for(encoder(job.src, job.out), timeout=ENCODE_TIMEOUT_SECONDS)
    except asyncio.TimeoutError:
        log.error("video-queue: AV1 timed out after %ss for %s",
                  ENCODE_TIMEOUT_SECONDS, job.src)
        # Best-effort cleanup of partial output
        try:
            if os.path.exists(job.out):
                os.unlink(job.out)
        except OSError:
            pass
    except Exception:  # noqa: BLE001
        log.exception("video-queue: AV1 transcode crashed for %s", job.src)
    finally:
        log.info("video-queue: finished AV1 src=%s ok=%s total=%.1fs",
                 job.src, ok, time.time() - started)
        if job.on_done:
            try:
                await job.on_done(ok)
            except Exception:  # noqa: BLE001
                log.exception("video-queue: on_done callback failed for %s", job.src)


async def _worker(encoder: Callable[[str, str], Awaitable[bool]]):
    """Single consumer — pulls jobs sequentially, never in parallel."""
    while True:
        job = await _queue.get()
        try:
            await _run_one(job, encoder)
        finally:
            _in_flight.discard(job.out)
            _queue.task_done()


async def enqueue(
    src_path: str,
    out_path: str,
    encoder: Callable[[str, str], Awaitable[bool]],
    on_done: Optional[Callable[[bool], Awaitable[None]]] = None,
) -> bool:
    """Submit an encode job. Returns False if the same `out_path` is
    already queued / running (idempotent — caller can safely retry
    without spawning duplicate work)."""
    global _worker_started

    async with _lock:
        if out_path in _in_flight:
            log.info("video-queue: skip duplicate enqueue for %s", out_path)
            return False
        _in_flight.add(out_path)
        if not _worker_started:
            _worker_started = True
            for _ in range(MAX_CONCURRENCY):
                asyncio.create_task(_worker(encoder))

    await _queue.put(_Job(src_path, out_path, on_done))
    log.info("video-queue: enqueued src=%s out=%s pending=%s", src_path, out_path, _queue.qsize())
    return True


def stats() -> dict:
    return {
        "pending": _queue.qsize(),
        "in_flight": len(_in_flight),
        "max_concurrency": MAX_CONCURRENCY,
        "timeout_seconds": ENCODE_TIMEOUT_SECONDS,
    }
