"""
Multi-format / multi-size image variant generator.

For every uploaded image we produce a 12-cell matrix:

              200w (thumb)   600w (card)   1200w (gallery)   1920w (full)
    AVIF        ✓               ✓             ✓                 ✓
    WebP        ✓               ✓             ✓                 ✓
    JPG         ✓               ✓             ✓                 ✓

Files are content-addressed by the sha256 of the *source* bytes so that
re-uploading the same image is free (existing variants are reused) and
cache keys never collide. Layout on disk:

    <UPLOAD_DIR>/variants/<aa>/<bb>/<sha256>/<size>.{avif,webp,jpg}

where `<aa>` is `sha256[:2]` and `<bb>` is `sha256[2:4]` — keeps the
directory fan-out tractable even at millions of files.

Public URLs are emitted via `public_variant_url(sha, size, ext)` which
respects the optional `IMAGE_CDN_BASE` env var (e.g.
`https://img.autoandbid.com`) so the platform can graduate to a true CDN
subdomain without touching any application code.

Strong compression knobs (AVIF q50 / WebP q75 / JPG q82) were tuned on
representative car listing photos (BMW M2, Porsche 911, AMG GT). The
visual delta vs the source JPEG is imperceptible at viewing distances
typical of car-card and gallery contexts; payload drops 60-75%.
"""
from __future__ import annotations

import hashlib
import io
import logging
import os
from typing import Optional

from PIL import Image, ImageOps

logger = logging.getLogger(__name__)

# Register pillow_heif so PIL.Image.open() accepts HEIC/HEIF uploads
# straight from iOS users. Optional dependency — log and continue if
# the wheel didn't install (e.g. on a minimal Alpine image).
try:
    import pillow_heif  # type: ignore
    pillow_heif.register_heif_opener()
except Exception:  # pragma: no cover
    logger.info("pillow_heif unavailable — HEIC uploads will be rejected")

# Pillow ≥ 11 has built-in AVIF support; no plugin required.
SIZE_THUMB = 200
SIZE_CARD = 600
SIZE_GALLERY = 1200
SIZE_FULL = 1920

# Order matters — smaller-first so a quick LCP request can return without
# blocking on the largest variant.
SIZES: list[tuple[str, int]] = [
    ("thumb", SIZE_THUMB),
    ("card", SIZE_CARD),
    ("gallery", SIZE_GALLERY),
    ("full", SIZE_FULL),
]

# Quality knobs — see module docstring for tuning rationale.
AVIF_QUALITY = 50
WEBP_QUALITY = 75
JPG_QUALITY = 82
JPG_PROGRESSIVE = True


# ---------------------------------------------------------------------------
# Storage layout
# ---------------------------------------------------------------------------

def _uploads_root() -> str:
    """Mirror of `storage._UPLOAD_DIR` (kept local to avoid a circular import)."""
    return os.environ.get("UPLOAD_DIR") or "/opt/autobids/uploads"


def _variant_dir(sha: str) -> str:
    return os.path.join(_uploads_root(), "variants", sha[:2], sha[2:4], sha)


def _variant_path(sha: str, size_name: str, ext: str) -> str:
    return os.path.join(_variant_dir(sha), f"{size_name}.{ext}")


def public_variant_url(sha: str, size_name: str, ext: str) -> str:
    """Public URL for a variant.

    Resolution delegates to `storage.public_uploads_base()` so all uploaded
    media (auction photos, OG images, variants) share a single env var
    (`CDN_BASE_URL`, e.g. `https://img.autoandbid.bg`). The returned URL is
    always of shape `<base>/variants/<sha2>/<sha2>/<sha>/<size>.<ext>` —
    nginx on the CDN subdomain serves it from `alias /opt/autobids/uploads/`.
    """
    from storage import public_uploads_base
    rel = f"variants/{sha[:2]}/{sha[2:4]}/{sha}/{size_name}.{ext}"
    return f"{public_uploads_base()}/{rel}"


# ---------------------------------------------------------------------------
# Generation
# ---------------------------------------------------------------------------

def _open_normalised(src_bytes: bytes) -> Image.Image:
    """Open + auto-rotate via EXIF + convert to a colour space that all
    three encoders accept (RGB for JPG, RGBA for AVIF/WebP transparency).

    The EXIF rotate step (`ImageOps.exif_transpose`) is critical for
    phone uploads — iPhones store images in landscape with an EXIF flag
    flipping them to portrait. Without this step the variants come out
    sideways even though the original viewer shows them upright.
    """
    img = Image.open(io.BytesIO(src_bytes))
    img = ImageOps.exif_transpose(img) or img
    # Some sources (PNG with palette, BMP) need a mode bump.
    if img.mode in ("P", "L"):
        img = img.convert("RGB")
    elif img.mode in ("CMYK", "I", "F"):
        img = img.convert("RGB")
    return img


def _resize_max_edge(img: Image.Image, max_edge: int) -> Image.Image:
    """Downscale so the long edge ≤ `max_edge`. Never upscales —
    a 400×300 source asked for the 1920 variant stays at 400×300 (we'd
    only waste pixels and add encode noise upscaling)."""
    w, h = img.size
    if max(w, h) <= max_edge:
        return img
    img.thumbnail((max_edge, max_edge), Image.LANCZOS)
    return img


def _encode(img: Image.Image, fmt: str, quality: int) -> bytes:
    buf = io.BytesIO()
    save_kwargs: dict = {"format": fmt}
    if fmt == "AVIF":
        save_kwargs.update(quality=quality, speed=6)
    elif fmt == "WEBP":
        save_kwargs.update(quality=quality, method=4)
    elif fmt == "JPEG":
        # Convert RGBA→RGB on a white matte; JPEG has no alpha channel.
        if img.mode == "RGBA":
            bg = Image.new("RGB", img.size, (255, 255, 255))
            bg.paste(img, mask=img.split()[3])
            img = bg
        elif img.mode != "RGB":
            img = img.convert("RGB")
        save_kwargs.update(
            quality=quality, optimize=True, progressive=JPG_PROGRESSIVE,
        )
    img.save(buf, **save_kwargs)
    return buf.getvalue()


def generate_variants(src_bytes: bytes, *, sha: Optional[str] = None) -> dict:
    """Materialise all 12 variants on disk for the given source bytes.

    Returns a dict:
        {
          "sha": "<sha256>",
          "width": int,    # original (post EXIF-rotate)
          "height": int,
          "variants": {
            "thumb":   {"avif": "<url>", "webp": "<url>", "jpg": "<url>"},
            "card":    {...},
            "gallery": {...},
            "full":    {...},
          },
          "primary": "<jpg url for the largest variant — used as <img src>>"
        }

    Idempotent: existing files are not re-encoded. Caller-supplied `sha`
    is trusted (saves a hash pass when the caller already has it).
    """
    if not src_bytes:
        raise ValueError("Empty source bytes")
    sha = sha or hashlib.sha256(src_bytes).hexdigest()

    out_dir = _variant_dir(sha)
    os.makedirs(out_dir, exist_ok=True)

    base = _open_normalised(src_bytes)
    orig_w, orig_h = base.size

    out: dict = {"sha": sha, "width": orig_w, "height": orig_h, "variants": {}}

    for size_name, max_edge in SIZES:
        size_out: dict[str, str] = {}
        # Resize once per size — re-use across encoders.
        resized = _resize_max_edge(base.copy(), max_edge)
        for ext, fmt, quality in (
            ("avif", "AVIF", AVIF_QUALITY),
            ("webp", "WEBP", WEBP_QUALITY),
            ("jpg", "JPEG", JPG_QUALITY),
        ):
            path = _variant_path(sha, size_name, ext)
            if not os.path.exists(path):
                try:
                    data = _encode(resized, fmt, quality)
                    tmp = path + ".tmp"
                    with open(tmp, "wb") as f:
                        f.write(data)
                    os.replace(tmp, path)
                except Exception as e:  # noqa: BLE001
                    logger.warning("variant encode %s/%s failed: %s", size_name, ext, e)
                    continue
            size_out[ext] = public_variant_url(sha, size_name, ext)
        out["variants"][size_name] = size_out

    # Default `<img src>` — JPG at gallery size is the safest universal
    # fallback (any browser, any pre-AVIF crawler, e.g. Facebook).
    out["primary"] = out["variants"].get("gallery", {}).get("jpg") or \
                     out["variants"].get("full", {}).get("jpg")
    return out


def variant_manifest_for(src_bytes: bytes) -> dict:
    """Public-facing facade: ensure variants exist + return the manifest
    block to embed on the auction document (`images_variants[N]`)."""
    return generate_variants(src_bytes)


# ---------------------------------------------------------------------------
# Data-URL convenience
# ---------------------------------------------------------------------------

def _decode_data_url(data_url: str) -> Optional[bytes]:
    """Strip a `data:image/...;base64,<body>` URL down to raw bytes.

    Returns None if the URL is not a data URL — caller is responsible
    for falling back (e.g. fetch the http URL first via
    `storage.fetch_remote_images_as_data_urls`).
    """
    if not data_url or not data_url.startswith("data:"):
        return None
    _, _, body = data_url.partition("base64,")
    if not body:
        return None
    try:
        import base64
        return base64.b64decode(body)
    except Exception:
        return None


def variants_from_data_url(data_url: str) -> Optional[dict]:
    """Decode a data URL, generate all variants, return the manifest.

    Returns None if the input is unusable (not a data URL, corrupt body,
    or Pillow refuses to decode). Caller should keep the legacy single
    JPG path as a fallback in that case.
    """
    raw = _decode_data_url(data_url)
    if not raw:
        return None
    try:
        return generate_variants(raw)
    except Exception as e:  # noqa: BLE001
        logger.warning("variants_from_data_url failed: %s", e)
        return None
