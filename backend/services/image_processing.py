"""Server-side image optimization for auction listings.

Why server-side?
  • Browsers may upload files compressed on the client side, but adversaries
    can bypass the client. Re-encoding on the server gives us a single source
    of truth for size, dimensions, format and EXIF stripping (privacy).
  • A consistent JPEG (q=85, max 1920px long edge) keeps storage and CDN
    bandwidth predictable.
  • Generated thumbnails (400px long edge) speed up grid views.

API:
  optimize_data_url(data_url) -> (full_data_url, thumb_data_url)
      Decodes a `data:image/...;base64,...` URL, re-encodes to JPEG with
      EXIF stripped, returns a (web-optimized, thumbnail) tuple — both as
      data URLs ready to be passed to `storage.store_image`.

Limits:
  IMAGE_MAX_RAW_BYTES (10 MB) — per-image raw bytes after base64 decode.
  Payload-level totals are enforced by the caller (see server.py).
"""
from __future__ import annotations

import base64
import io
import logging
import re
from typing import Optional

from PIL import Image, ImageOps

logger = logging.getLogger("img_processing")

IMAGE_MAX_RAW_BYTES = 10 * 1024 * 1024   # 10 MB per image (raw, post-decode)
WEB_MAX_DIM = 1920                       # long edge of the optimized version
THUMB_MAX_DIM = 400                      # long edge of the thumbnail
JPEG_QUALITY = 85                        # ~85 is the visual sweet-spot for cars

_DATA_URL_RE = re.compile(r"^data:image/(?P<ext>[a-z0-9+.-]+);base64,(?P<body>.+)$", re.IGNORECASE)

# Allowed source formats — anything else is rejected to prevent SVG/script
# injection or unusual formats poisoning the pipeline.
_ALLOWED_FORMATS = {"jpeg", "jpg", "png", "webp", "heic", "heif"}


class ImageProcessingError(Exception):
    """Raised when a single image fails validation or decoding."""


def derive_external_thumbnail(url: str) -> str:
    """Map an external (already-hosted) image URL to its small CDN variant.

    We never download remote images; we only know that several CDNs serve
    multiple sizes under predictable URL patterns. When we recognise one of
    those patterns we rewrite the URL to point at the small variant so the
    gallery thumbnail strip uses ~16 KB previews instead of the 250+ KB
    full-resolution source.

    Currently handled:
      • mobile.bg (`mobistatic*.focus.bg/.../big1/<name>.webp`) → drop the
        `/big1/` segment to get the ~120 px preview the CDN already serves.

    Falls back to the original URL when no rule matches — caller is free
    to use the same URL for both web and thumb fields in that case.
    """
    if not url or not isinstance(url, str):
        return url
    lower = url.lower()
    # mobile.bg / focus.bg CDN: stripping `/big1/` resolves to a ~16 KB
    # preview that's still hosted on the same origin.
    if ("focus.bg" in lower or "mobile.bg" in lower) and "/big1/" in url:
        return url.replace("/big1/", "/", 1)
    return url


def _decode_data_url(url: str) -> tuple[str, bytes]:
    m = _DATA_URL_RE.match(url.strip())
    if not m:
        raise ImageProcessingError("not a data URL")
    ext = m.group("ext").lower().split("+")[0]
    if ext not in _ALLOWED_FORMATS:
        raise ImageProcessingError(f"unsupported image format: {ext}")
    try:
        body = base64.b64decode(m.group("body"), validate=False)
    except Exception:
        raise ImageProcessingError("invalid base64 payload")
    return ext, body


def _to_data_url(buf: bytes, mime: str = "image/jpeg") -> str:
    return f"data:{mime};base64,{base64.b64encode(buf).decode('ascii')}"


def _open_and_normalise(raw: bytes) -> Image.Image:
    """Open via PIL, apply EXIF orientation, drop alpha, return RGB image."""
    try:
        img = Image.open(io.BytesIO(raw))
        img.load()
    except Exception as e:
        raise ImageProcessingError(f"PIL cannot decode: {e}")
    # Honour EXIF orientation tag — without this iPhone shots come out sideways.
    img = ImageOps.exif_transpose(img)
    # Flatten alpha onto white so JPEG doesn't end up with black backgrounds.
    if img.mode in ("RGBA", "LA", "P"):
        bg = Image.new("RGB", img.size, (255, 255, 255))
        if img.mode == "P":
            img = img.convert("RGBA")
        bg.paste(img, mask=img.split()[-1] if img.mode in ("RGBA", "LA") else None)
        img = bg
    elif img.mode != "RGB":
        img = img.convert("RGB")
    return img


def _resize_keeping_aspect(img: Image.Image, max_dim: int) -> Image.Image:
    w, h = img.size
    if w <= max_dim and h <= max_dim:
        return img
    if w >= h:
        new_w = max_dim
        new_h = max(1, round(h * max_dim / w))
    else:
        new_h = max_dim
        new_w = max(1, round(w * max_dim / h))
    return img.resize((new_w, new_h), Image.LANCZOS)


def _encode_jpeg(img: Image.Image, quality: int = JPEG_QUALITY) -> bytes:
    out = io.BytesIO()
    # `optimize=True` runs an extra Huffman pass; small file-size win for free.
    # `progressive=True` improves perceived load time on slow connections.
    img.save(out, format="JPEG", quality=quality, optimize=True, progressive=True)
    return out.getvalue()


def optimize_data_url(data_url: str) -> tuple[str, str]:
    """Re-encode an inbound data URL to web-optimized JPEG + 400px thumbnail.

    Raises `ImageProcessingError` if the file is too large, malformed,
    or in an unsupported format. Caller is expected to surface the
    error message back to the user.
    """
    if not data_url:
        raise ImageProcessingError("empty image")
    if not data_url.startswith("data:image/"):
        # Already a hosted URL — pass through for the full-resolution
        # `web` field. For the thumbnail field, try to derive a smaller
        # CDN variant when the host advertises one.
        return data_url, derive_external_thumbnail(data_url)

    _ext, raw = _decode_data_url(data_url)
    if len(raw) > IMAGE_MAX_RAW_BYTES:
        raise ImageProcessingError(
            f"image too large: {round(len(raw) / 1024 / 1024, 1)} MB "
            f"(max {IMAGE_MAX_RAW_BYTES // 1024 // 1024} MB)"
        )

    img = _open_and_normalise(raw)
    web = _encode_jpeg(_resize_keeping_aspect(img, WEB_MAX_DIM))
    thumb = _encode_jpeg(_resize_keeping_aspect(img, THUMB_MAX_DIM), quality=80)
    return _to_data_url(web), _to_data_url(thumb)


AVATAR_DIM = 256                         # square avatar size (px)
AVATAR_MAX_RAW_BYTES = 6 * 1024 * 1024   # 6 MB per upload


def _center_crop_square(img: Image.Image) -> Image.Image:
    w, h = img.size
    side = min(w, h)
    left = (w - side) // 2
    top = (h - side) // 2
    return img.crop((left, top, left + side, top + side))


def optimize_avatar_data_url(data_url: str) -> str:
    """Re-encode an inbound avatar data URL to a 256×256 square JPEG.

    Returns a single optimized data URL ready to be passed to
    `storage.store_image`. Raises `ImageProcessingError` on bad input.
    """
    if not data_url:
        raise ImageProcessingError("empty image")
    if not data_url.startswith("data:image/"):
        return data_url

    _ext, raw = _decode_data_url(data_url)
    if len(raw) > AVATAR_MAX_RAW_BYTES:
        raise ImageProcessingError(
            f"image too large: {round(len(raw) / 1024 / 1024, 1)} MB "
            f"(max {AVATAR_MAX_RAW_BYTES // 1024 // 1024} MB)"
        )

    img = _open_and_normalise(raw)
    img = _center_crop_square(img)
    img = img.resize((AVATAR_DIM, AVATAR_DIM), Image.LANCZOS)
    return _to_data_url(_encode_jpeg(img, quality=88))



def optimize_many(urls: list[str]) -> tuple[list[str], list[str], list[str]]:
    """Bulk optimize. Returns (web_urls, thumb_urls, error_messages).

    Items that fail processing keep their original URL in `web_urls` so a
    partial save still produces something usable. Caller decides whether
    to abort on errors.
    """
    web_out: list[str] = []
    thumb_out: list[str] = []
    errors: list[str] = []
    for i, u in enumerate(urls or []):
        if not u:
            continue
        try:
            web, thumb = optimize_data_url(u)
            web_out.append(web)
            thumb_out.append(thumb)
        except ImageProcessingError as e:
            errors.append(f"снимка #{i + 1}: {e}")
            web_out.append(u)
            thumb_out.append(u)
        except Exception as e:  # pragma: no cover — defensive
            logger.warning("optimize_data_url crashed: %s", e)
            errors.append(f"снимка #{i + 1}: вътрешна грешка")
            web_out.append(u)
            thumb_out.append(u)
    return web_out, thumb_out, errors


def total_raw_bytes(urls: list[str]) -> int:
    """Sum of decoded raw bytes for size-cap enforcement before optimization."""
    total = 0
    for u in urls or []:
        if not u or not u.startswith("data:image/"):
            continue
        # base64 ratio: each 4 chars encode 3 bytes, ignore padding.
        _h, _, body = u.partition(",")
        if not body:
            continue
        total += (len(body) * 3) // 4
    return total


def raw_bytes_of(url: str) -> int:
    if not url or not url.startswith("data:image/"):
        return 0
    _h, _, body = url.partition(",")
    if not body:
        return 0
    return (len(body) * 3) // 4
