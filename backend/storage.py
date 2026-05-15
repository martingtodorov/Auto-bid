"""
Pluggable image storage backend.

- STORAGE_BACKEND=inline (default): base64 data URLs are kept inline in MongoDB.
  Simple, zero-ops, ideal for staging or small deployments.
- STORAGE_BACKEND=s3: data URLs are decoded, uploaded to an S3-compatible
  bucket (AWS S3, Cloudflare R2, DigitalOcean Spaces, MinIO, Backblaze B2) and
  the public URL is stored in MongoDB instead. Dramatically reduces DB size
  and CDN cost.

Public `store_image(data_url)` accepts a data URL or an https URL. The
function is idempotent — https URLs pass through untouched so re-saving
existing documents doesn't re-upload.

All network IO is synchronous (boto3) but is called from within
`await asyncio.to_thread(...)` by the server to keep the event loop free.
"""
from __future__ import annotations

import base64
import hashlib
import logging
import os
import re
from typing import Optional

# Re-export `ImageProcessingError` from the sibling image service so the
# disk backend can raise the same error type as the image optimizer.
# Keeping a single exception class means route handlers can map both
# "bad input" and "filesystem not writable" to 400s with one `except`.
from services.image_processing import ImageProcessingError

logger = logging.getLogger("storage")

_DATA_URL_RE = re.compile(r"^data:image/(?P<ext>[a-z0-9+.-]+);base64,(?P<body>.+)$", re.IGNORECASE)
_EXT_ALIASES = {"jpeg": "jpg", "svg+xml": "svg"}


def _extract_data_url(url: str) -> Optional[tuple[str, bytes]]:
    m = _DATA_URL_RE.match(url.strip())
    if not m:
        return None
    ext = m.group("ext").lower()
    ext = _EXT_ALIASES.get(ext, ext)
    try:
        body = base64.b64decode(m.group("body"), validate=False)
    except Exception:
        return None
    return ext, body


class InlineStorage:
    """No-op backend: return the data URL as-is."""
    name = "inline"

    def store(self, data_url: str) -> str:
        return data_url


class DiskStorage:
    """Local filesystem backend: write data URLs to disk, return public URL.

    Files are content-addressed (sha256 of bytes) so the same image
    uploaded twice gets stored once. The directory layout matches S3:

        <UPLOAD_DIR>/auctions/<aa>/<full-sha>.<ext>

    Public URL is built from `PUBLIC_UPLOAD_BASE` (e.g. `/uploads`) so a
    reverse proxy (nginx) or FastAPI's StaticFiles can serve the path
    without further routing logic.
    """
    name = "disk"

    def __init__(self) -> None:
        # Persistent storage root. Production VPS has `/app` mounted
        # read-only, so we default to `/opt/autobids/uploads` which is
        # owned by the `www-data` service user (see Ansible backend role).
        # Preview/containerised environments can override this via the
        # `UPLOAD_DIR` env var to keep files co-located with the code.
        self.root = os.path.abspath(os.environ.get("UPLOAD_DIR", "/opt/autobids/uploads"))
        # Default `/api/uploads` is the only path the k8s preview ingress
        # routes to the backend. On a Hetzner box nginx can short-circuit
        # the same path via `alias`, so the public URL is identical
        # everywhere.
        self.public_base = os.environ.get("PUBLIC_UPLOAD_BASE", "/api/uploads").rstrip("/")
        # Soft-create the directory. If the filesystem is read-only (e.g.
        # /app on the production VPS) we don't crash the process here —
        # `store()` will raise a clear ImageProcessingError per upload so
        # unrelated endpoints keep working and only the Sell flow surfaces
        # the misconfiguration.
        try:
            os.makedirs(self.root, exist_ok=True)
        except OSError:
            # Logged at mount time in server.py; don't spam on every init.
            pass

    def store(self, data_url: str) -> str:
        if not data_url:
            return data_url
        # Already a URL — passthrough
        if data_url.startswith(("http://", "https://", "/uploads/", "/api/uploads/")):
            return data_url
        if data_url.startswith(self.public_base + "/"):
            return data_url
        parsed = _extract_data_url(data_url)
        if not parsed:
            return data_url
        ext, body = parsed
        digest = hashlib.sha256(body).hexdigest()
        sub = digest[:2]
        rel = f"auctions/{sub}/{digest}.{ext}"
        abs_path = os.path.join(self.root, rel)
        if not os.path.exists(abs_path):
            try:
                os.makedirs(os.path.dirname(abs_path), exist_ok=True)
                tmp = abs_path + ".tmp"
                with open(tmp, "wb") as f:
                    f.write(body)
                os.replace(tmp, abs_path)  # atomic
            except OSError as e:
                # Most common: `/app` is read-only on prod, `UPLOAD_DIR`
                # not set in systemd env, or /opt/autobids/uploads not
                # yet created by Ansible. Surface a clear 400 instead of
                # a noisy 500 traceback.
                raise ImageProcessingError(
                    f"Image storage is not writable at {self.root!r} "
                    f"({e.strerror}). Проверете UPLOAD_DIR и правата на директорията."
                ) from e
        return f"{self.public_base}/{rel}"


class S3Storage:
    """S3-compatible bucket backend."""
    name = "s3"

    def __init__(self) -> None:
        import boto3  # lazily imported so inline mode has zero cost
        endpoint = os.environ.get("S3_ENDPOINT_URL") or None  # omit for AWS S3
        region = os.environ.get("S3_REGION", "us-east-1")
        self.bucket = os.environ["S3_BUCKET"]
        self.public_base = os.environ.get("S3_PUBLIC_BASE_URL", "").rstrip("/")
        self.acl = os.environ.get("S3_ACL", "public-read")
        self._client = boto3.client(
            "s3",
            endpoint_url=endpoint,
            region_name=region,
            aws_access_key_id=os.environ.get("S3_ACCESS_KEY_ID"),
            aws_secret_access_key=os.environ.get("S3_SECRET_ACCESS_KEY"),
        )

    def store(self, data_url: str) -> str:
        # Passthrough: already a URL
        if data_url.startswith(("http://", "https://")):
            return data_url
        parsed = _extract_data_url(data_url)
        if not parsed:
            return data_url  # unknown scheme — leave as-is, server-side validation will catch it
        ext, body = parsed
        # Content-addressed filename — deduplicates identical images for free
        digest = hashlib.sha256(body).hexdigest()
        key = f"auctions/{digest[:2]}/{digest}.{ext}"
        content_type = f"image/{'jpeg' if ext == 'jpg' else ext}"
        try:
            self._client.put_object(
                Bucket=self.bucket,
                Key=key,
                Body=body,
                ContentType=content_type,
                ACL=self.acl,
                CacheControl="public, max-age=31536000, immutable",
            )
        except Exception as e:
            logger.exception("S3 upload failed for key=%s: %s", key, e)
            # Fall back to inline so the request does not fail outright
            return data_url
        if self.public_base:
            return f"{self.public_base}/{key}"
        # Default virtual-hosted-style URL (works for AWS + most providers)
        if os.environ.get("S3_ENDPOINT_URL"):
            endpoint = os.environ["S3_ENDPOINT_URL"].rstrip("/")
            return f"{endpoint}/{self.bucket}/{key}"
        return f"https://{self.bucket}.s3.{os.environ.get('S3_REGION', 'us-east-1')}.amazonaws.com/{key}"


_backend: Optional[object] = None


def _get_backend():
    global _backend
    if _backend is not None:
        return _backend
    choice = os.environ.get("STORAGE_BACKEND", "disk").lower()
    if choice == "s3":
        _backend = S3Storage()
    elif choice == "inline":
        _backend = InlineStorage()
    else:
        _backend = DiskStorage()
    logger.info("Storage backend initialised: %s", _backend.name)
    return _backend


def store_image(data_url: str) -> str:
    """Store a single image (data URL or https URL) and return its reference."""
    if not data_url:
        return data_url
    return _get_backend().store(data_url)


def store_images(urls: list[str]) -> list[str]:
    """Bulk convenience — maintains order, filters empties."""
    return [store_image(u) for u in (urls or []) if u]


# ---------------------------------------------------------------------------
# Remote image rehosting
# ---------------------------------------------------------------------------
# When the source of an auction is a third-party listing (e.g. mobile.bg
# importer), the scraper hands us a list of external image URLs that point
# at a CDN we don't control (focus.bg). To take ownership of the visuals —
# watermarking, compression, link rot, GDPR — we download the bytes once
# at import time and feed them through the standard data-URL → optimize →
# store_image pipeline so they end up under `/api/uploads/...`.
#
# Kept here (not in image_processing) because the responsibility is
# storage-side: "give me a stable URL on our infra". Image processing is a
# *separate* concern run later by `optimize_many` once the data URL exists.
# ---------------------------------------------------------------------------
import asyncio  # noqa: E402  (used by async fetcher below)

REMOTE_FETCH_MAX_BYTES = 12 * 1024 * 1024  # 12 MB hard cap per remote image
REMOTE_FETCH_TIMEOUT = 15.0                # seconds per image
REMOTE_FETCH_CONCURRENCY = 6               # parallel downloads per batch


async def _fetch_one(client, url: str) -> Optional[str]:
    """Download a single URL and return it as a base64 data URL.

    Returns None on failure (timeout, non-2xx, oversized, unknown content-
    type) so the caller can keep the original URL as a graceful fallback.
    """
    try:
        # Stream the response so we can abort early if it exceeds the
        # byte cap — mobile.bg images are usually 200-500 KB but a
        # rogue source could try to wedge us with a huge payload.
        async with client.stream("GET", url, timeout=REMOTE_FETCH_TIMEOUT, follow_redirects=True) as r:
            if r.status_code >= 400:
                logger.info("remote fetch %s → HTTP %s", url, r.status_code)
                return None
            ct = (r.headers.get("content-type") or "").lower().split(";")[0].strip()
            # Trust either an image/* content-type or fall back to the
            # URL extension. focus.bg sometimes serves `application/
            # octet-stream` for .webp so we can't be strict here.
            if ct and ct.startswith("image/"):
                ext = ct.split("/", 1)[1].split("+")[0]
            else:
                tail = url.lower().rsplit("?", 1)[0].rsplit(".", 1)
                ext = tail[1] if len(tail) == 2 and len(tail[1]) <= 5 else "jpeg"
            ext = _EXT_ALIASES.get(ext, ext)
            chunks = bytearray()
            async for chunk in r.aiter_bytes(chunk_size=64 * 1024):
                chunks.extend(chunk)
                if len(chunks) > REMOTE_FETCH_MAX_BYTES:
                    logger.info("remote fetch %s → oversize abort (>%d B)", url, REMOTE_FETCH_MAX_BYTES)
                    return None
            if not chunks:
                return None
            b64 = base64.b64encode(bytes(chunks)).decode("ascii")
            return f"data:image/{ext};base64,{b64}"
    except Exception as e:  # noqa: BLE001 — log & continue, do not break the import
        logger.info("remote fetch %s failed: %s", url, e)
        return None


async def fetch_remote_images_as_data_urls(urls: list[str], *, strict: bool = False) -> list[str]:
    """Download a list of remote image URLs and return them as base64
    data URLs ready to feed into `optimize_many` + `store_image`.

    Concurrency is capped at `REMOTE_FETCH_CONCURRENCY` so a 24-image
    listing doesn't fan out into 24 simultaneous sockets.

    By default each failed download keeps the original https URL in the
    returned list (so the user still sees the image even if our copy is
    missing). Pass `strict=True` to return an empty string in that
    position instead — caller can then filter for unfetchable URLs and
    refuse to persist them as external (which would leave us dependent
    on the third-party CDN).
    """
    try:
        import httpx
    except ImportError:  # pragma: no cover — pinned in requirements.txt
        logger.warning("httpx not installed; remote rehost disabled")
        return list(urls or [])

    if not urls:
        return []

    # Pass-through anything that isn't an external image already (data:
    # URLs, our own /api/uploads paths, empty strings).
    def _needs_fetch(u: str) -> bool:
        if not u or not isinstance(u, str):
            return False
        if u.startswith(("data:image/", "/api/uploads/", "/uploads/")):
            return False
        return u.startswith(("http://", "https://"))

    sem = asyncio.Semaphore(REMOTE_FETCH_CONCURRENCY)
    async with httpx.AsyncClient(
        headers={
            # Some CDNs (focus.bg included) refuse to serve images without
            # a referer that matches the originating listing host. Set a
            # generic one — the actual content is public.
            "User-Agent": "Mozilla/5.0 (compatible; AutoBidImporter/1.0)",
            "Referer": "https://www.mobile.bg/",
            "Accept": "image/avif,image/webp,image/*,*/*;q=0.8",
        },
    ) as client:
        async def _guarded(u: str) -> str:
            if not _needs_fetch(u):
                return u
            async with sem:
                fetched = await _fetch_one(client, u)
            if fetched is None:
                return "" if strict else u  # strict drops failures
            return fetched

        return list(await asyncio.gather(*[_guarded(u) for u in urls]))
