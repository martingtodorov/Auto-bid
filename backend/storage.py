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
    choice = os.environ.get("STORAGE_BACKEND", "inline").lower()
    if choice == "s3":
        _backend = S3Storage()
    else:
        _backend = InlineStorage()
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
