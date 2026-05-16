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


def public_uploads_base() -> str:
    """Single source of truth for the public base URL of uploaded media.

    Resolution order (first non-empty wins):
        1. `CDN_BASE_URL` — canonical env var (e.g. `https://img.autoandbid.bg`).
           When set, uploaded asset URLs become `<CDN_BASE_URL>/uploads/...`
           (no `/api` prefix) — nginx on the CDN subdomain serves them
           directly from disk via `alias /opt/autobids/uploads/`.
        2. `IMAGE_BASE_URL` — legacy alias kept for previously deployed envs.
        3. `PUBLIC_UPLOAD_BASE` — pre-CDN-era setting, typically `/api/uploads`
           which is what the k8s preview ingress routes to the backend.
        4. Fallback `/api/uploads` for dev / containerised environments where
           the image subdomain isn't set up yet.

    A trailing `/uploads` segment is auto-appended when `CDN_BASE_URL` or
    `IMAGE_BASE_URL` is set without it, so the public URL layout is always
    `<base>/uploads/auctions/<sha2>/<sha>.<ext>` — consistent regardless of
    which env var the operator chose.
    """
    cdn = (os.environ.get("CDN_BASE_URL") or os.environ.get("IMAGE_BASE_URL") or "").rstrip("/")
    if cdn:
        # If the operator pointed CDN_BASE_URL at the host root, append
        # `/uploads`. If they already included a path segment (legacy
        # `https://img.x/uploads`), respect it.
        if cdn.endswith("/uploads") or "/uploads/" in cdn:
            return cdn
        return cdn + "/uploads"
    return (os.environ.get("PUBLIC_UPLOAD_BASE") or "/api/uploads").rstrip("/")


class DiskStorage:
    """Local filesystem backend: write data URLs to disk, return public URL.

    Files are content-addressed (sha256 of bytes) so the same image
    uploaded twice gets stored once. The directory layout matches S3:

        <UPLOAD_DIR>/auctions/<aa>/<full-sha>.<ext>

    Public URL is built from `public_uploads_base()` so the same on-disk
    layout is served from either the CDN subdomain (production) or the
    backend itself (dev / preview).
    """
    name = "disk"

    def __init__(self) -> None:
        # Persistent storage root. Production VPS has `/app` mounted
        # read-only, so we default to `/opt/autobids/uploads` which is
        # owned by the `www-data` service user (see Ansible backend role).
        # Preview/containerised environments can override this via the
        # `UPLOAD_DIR` env var to keep files co-located with the code.
        self.root = os.path.abspath(os.environ.get("UPLOAD_DIR", "/opt/autobids/uploads"))
        self.public_base = public_uploads_base()
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


def _sniff_image_type(head: bytes) -> Optional[str]:
    """Return the canonical image extension based on magic bytes.

    Trusts the file's content, not the Content-Type header — focus.bg
    and other scraping sources occasionally serve HTML error pages with
    `image/jpeg` headers (login walls, anti-bot 200s), so we never let
    those reach the storage pipeline. Returns None when the bytes are
    not a recognised image format.
    """
    if not head or len(head) < 12:
        return None
    # JPEG: FF D8 FF
    if head[:3] == b"\xff\xd8\xff":
        return "jpeg"
    # PNG: 89 50 4E 47 0D 0A 1A 0A
    if head[:8] == b"\x89PNG\r\n\x1a\n":
        return "png"
    # WebP: "RIFF" .... "WEBP"
    if head[:4] == b"RIFF" and head[8:12] == b"WEBP":
        return "webp"
    # GIF
    if head[:6] in (b"GIF87a", b"GIF89a"):
        return "gif"
    # AVIF / HEIF — ISO BMFF box; brand starts at offset 4 ("ftyp" + brand)
    if head[4:8] == b"ftyp" and head[8:12] in (b"avif", b"avis", b"heic", b"heix", b"mif1"):
        return "avif" if head[8:12].startswith(b"avi") else "heif"
    return None


async def _fetch_one(client, url: str) -> Optional[str]:
    """Download a single URL and return it as a base64 data URL.

    Validation layers (all must pass — defence in depth against
    anti-bot pages, login walls, and content-type spoofing):
      1. HTTP status must be 2xx
      2. Content-Type header must not be `text/html` (anti-bot page)
      3. Payload size must be ≤ REMOTE_FETCH_MAX_BYTES
      4. First 12 bytes must match a known image magic signature
         (JPEG / PNG / WebP / GIF / AVIF / HEIF) — this catches HTML
         pages that lie about their Content-Type and prevents the
         "image URL fetches HTML, browser later ORB-blocks" failure
         we hit with focus.bg's bot challenges.

    On any failure we log the source URL, final redirected URL, HTTP
    status, and Content-Type so operators can debug from the prod
    log without re-running the import.
    """
    try:
        # Stream the response so we can abort early if it exceeds the
        # byte cap — mobile.bg images are usually 200-500 KB but a
        # rogue source could try to wedge us with a huge payload.
        async with client.stream("GET", url, timeout=REMOTE_FETCH_TIMEOUT, follow_redirects=True) as r:
            # `r.url` is the FINAL URL after redirects — log it on
            # failure so we can distinguish "404 from origin" vs
            # "redirected to a login page".
            final_url = str(r.url)
            ct_full = (r.headers.get("content-type") or "").strip()
            ct = ct_full.lower().split(";")[0].strip()

            if r.status_code >= 400:
                logger.warning(
                    "remote fetch %s → HTTP %s (final=%s ct=%s)",
                    url, r.status_code, final_url, ct_full,
                )
                return None

            # Hard reject HTML pages early — saves bandwidth + skips
            # downloading megabytes of anti-bot challenge HTML before
            # the magic-byte check would catch it.
            if ct.startswith("text/") or ct in ("application/xhtml+xml",):
                logger.warning(
                    "remote fetch %s rejected: HTML/text content-type (status=%s ct=%s final=%s)",
                    url, r.status_code, ct_full, final_url,
                )
                return None

            chunks = bytearray()
            async for chunk in r.aiter_bytes(chunk_size=64 * 1024):
                chunks.extend(chunk)
                if len(chunks) > REMOTE_FETCH_MAX_BYTES:
                    logger.warning(
                        "remote fetch %s → oversize abort (>%d B, final=%s)",
                        url, REMOTE_FETCH_MAX_BYTES, final_url,
                    )
                    return None
            if not chunks:
                logger.warning(
                    "remote fetch %s → empty body (status=%s ct=%s final=%s)",
                    url, r.status_code, ct_full, final_url,
                )
                return None

            # ── Magic byte verification ────────────────────────────────
            # Trust the bytes, not the header. focus.bg/mobile.bg
            # occasionally serves `<!DOCTYPE html>` anti-bot challenges
            # with image/jpeg Content-Type. The browser's ORB pipeline
            # will reject those downstream, so we must too.
            sniffed = _sniff_image_type(bytes(chunks[:12]))
            if not sniffed:
                # Most common reason this fires: bytes are HTML/XML.
                # Show a small preview so the prod log diagnoses cleanly.
                preview = bytes(chunks[:64]).decode("ascii", "replace")
                logger.warning(
                    "remote fetch %s rejected: bytes are not a valid image "
                    "(status=%s ct=%s final=%s preview=%r)",
                    url, r.status_code, ct_full, final_url, preview,
                )
                return None

            # Use the sniffed type — it's authoritative. Content-Type
            # header takes second place; URL extension is only a hint
            # we no longer trust because mobile.bg .jpg URLs sometimes
            # actually serve PNG.
            ext = sniffed
            ext = _EXT_ALIASES.get(ext, ext)
            b64 = base64.b64encode(bytes(chunks)).decode("ascii")
            return f"data:image/{ext};base64,{b64}"
    except Exception as e:  # noqa: BLE001 — log & continue, do not break the import
        logger.warning("remote fetch %s failed: %s", url, e)
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
            # mobile.bg/focus.bg blocks default Python User-Agents. Use a
            # current Chrome UA + Accept-Language + Sec-Fetch-* hints so
            # the request looks indistinguishable from a real browser
            # session — they enforce these specifically for image hot-
            # linking detection.
            "User-Agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/127.0.0.0 Safari/537.36"
            ),
            "Accept": "image/avif,image/webp,image/apng,image/*,*/*;q=0.8",
            "Accept-Language": "bg-BG,bg;q=0.9,en-US;q=0.8,en;q=0.7",
            "Referer": "https://www.mobile.bg/",
            "Sec-Fetch-Dest": "image",
            "Sec-Fetch-Mode": "no-cors",
            "Sec-Fetch-Site": "cross-site",
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
