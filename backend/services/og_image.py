"""
Dynamic Open Graph (social sharing) image generator.

Mimics the site's AuctionCard design so shares look "native":
  • Upper 70 %: full-width cover photo
  • Pill overlays (top-left, backdrop-blurred): live / ending time + optional
    featured / VAT, using the same palette as the app CSS variables.
  • Lower 30 %: clean white card body — title + current bid big number, with
    the Auto&Bid wordmark (Manrope Bold, black `A`/`B`, emerald `&`) top-right.

Cache key = sha1(id + current_bid + ends_at_minute) so every bid + each
passing minute naturally produces a fresh PNG without overwhelming disk.
"""

from __future__ import annotations

import asyncio
import hashlib
import io
import logging
import os
import time
from datetime import datetime, timezone
from typing import Optional

import httpx
from PIL import Image, ImageDraw, ImageFilter, ImageFont

logger = logging.getLogger(__name__)

_CACHE_DIR = "/tmp/og_cache"
os.makedirs(_CACHE_DIR, exist_ok=True)
_CACHE_TTL_SEC = 24 * 3600

# Canvas — Facebook / Twitter recommend 1200×630 (1.91:1).
_W, _H = 1200, 630
_PHOTO_H = 420        # top image band
_FOOTER_H = _H - _PHOTO_H   # 210 px body
_PAD = 44

# Palette — hand-converted from the :root CSS variables in `index.css`
# (`--ink`, `--ink-muted`, `--accent`, `--line`, `--surface`, `--danger`).
_BG = (255, 255, 255)
_INK = (21, 26, 36)             # --ink (near-black)
_INK_MUTED = (107, 114, 128)
_ACCENT = (30, 106, 80)         # --accent (emerald)
_ACCENT_SOFT = (228, 243, 235)  # --accent-soft
_LINE = (229, 231, 235)         # --line
_SURFACE = (247, 248, 250)      # --surface
_DANGER = (197, 48, 56)         # --danger
_DANGER_SOFT = (254, 234, 234)

# Match the site's brand mark: black `A` + emerald `&` + black `B`
_AMP_GREEN = (16, 185, 129)  # same emerald as the favicon artefact
# Path to the Manrope TTFs shipped alongside this service
_FONT_DIR = os.path.join(os.path.dirname(__file__), "fonts")


def _font(name: str, size: int) -> ImageFont.FreeTypeFont:
    try:
        return ImageFont.truetype(os.path.join(_FONT_DIR, name), size)
    except Exception:
        return ImageFont.load_default()


async def _fetch_image(url: str, timeout: float = 8.0) -> Optional[bytes]:
    if not url:
        return None
    try:
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as c:
            r = await c.get(url)
            r.raise_for_status()
            return r.content
    except Exception as e:
        logger.warning("og: cover fetch failed %s: %s", url, e)
        return None


def _english_time_left(ends_at_iso: Optional[str]) -> tuple[str, bool]:
    """Returns (label, urgent). `urgent` = <24 h remaining → red pill."""
    if not ends_at_iso:
        return "LIVE", False
    try:
        iso = ends_at_iso.replace("Z", "+00:00")
        end = datetime.fromisoformat(iso)
    except Exception:
        return "LIVE", False
    now = datetime.now(timezone.utc)
    delta = (end - now).total_seconds()
    if delta <= 0:
        return "ENDED", False
    days = int(delta // 86400)
    hours = int((delta % 86400) // 3600)
    minutes = int((delta % 3600) // 60)
    if days > 0:
        return f"{days}D {hours}H", False
    if hours > 0:
        return f"{hours}H {minutes}M", hours < 2
    return f"{minutes}M", True


# ---------------------------------------------------------------------------
# Primitives
# ---------------------------------------------------------------------------
def _round_rect_mask(size: tuple[int, int], radius: int) -> Image.Image:
    m = Image.new("L", size, 0)
    ImageDraw.Draw(m).rounded_rectangle([0, 0, size[0] - 1, size[1] - 1], radius=radius, fill=255)
    return m


def _pill(
    draw: ImageDraw.ImageDraw,
    canvas: Image.Image,
    xy: tuple[int, int],
    text: str,
    *,
    fg: tuple[int, int, int],
    bg: tuple[int, int, int, int],
    border: tuple[int, int, int, int],
    font: ImageFont.FreeTypeFont,
    icon_dot: Optional[tuple[int, int, int]] = None,
) -> int:
    """Draw a card-style pill (rounded, semi-translucent bg). Returns x-offset
    of the pill's right edge for laying out subsequent pills."""
    text = text.upper()
    pad_x, pad_y = 18, 10
    tw = int(draw.textlength(text, font=font))
    th = font.size
    dot_w = 10 + 8 if icon_dot else 0
    pill_w = pad_x * 2 + dot_w + tw
    pill_h = pad_y * 2 + th

    x, y = xy
    # Per-pill translucent layer so we keep true alpha over the photo
    layer = Image.new("RGBA", (pill_w, pill_h), (0, 0, 0, 0))
    ld = ImageDraw.Draw(layer)
    ld.rounded_rectangle([0, 0, pill_w - 1, pill_h - 1], radius=pill_h // 2, fill=bg, outline=border, width=1)

    text_x = pad_x
    if icon_dot:
        cy = pill_h // 2
        dot_r = 4
        ld.ellipse([pad_x, cy - dot_r, pad_x + dot_r * 2, cy + dot_r], fill=icon_dot)
        text_x = pad_x + dot_r * 2 + 8
    # Baseline tweak: slightly lift text so it looks optically centred
    ld.text((text_x, pad_y - 2), text, font=font, fill=fg)

    canvas.alpha_composite(layer, dest=(x, y))
    return x + pill_w


def _compose_image(
    cover_bytes: Optional[bytes],
    title: str,
    time_label: str,
    time_urgent: bool,
    featured: bool,
    bid_label: Optional[str],
    bid_sub_label: Optional[str],
) -> bytes:
    canvas = Image.new("RGBA", (_W, _H), _BG + (255,))

    # --- Top: photo -----------------------------------------------------
    photo_box = (0, 0, _W, _PHOTO_H)
    if cover_bytes:
        try:
            src = Image.open(io.BytesIO(cover_bytes)).convert("RGB")
            # Cover-crop at _W × _PHOTO_H
            src_ratio = src.width / src.height
            tgt_ratio = _W / _PHOTO_H
            if src_ratio > tgt_ratio:
                new_h = _PHOTO_H
                new_w = int(_PHOTO_H * src_ratio)
            else:
                new_w = _W
                new_h = int(_W / src_ratio)
            src = src.resize((new_w, new_h), Image.LANCZOS)
            left = (new_w - _W) // 2
            top = (new_h - _PHOTO_H) // 2
            cropped = src.crop((left, top, left + _W, top + _PHOTO_H)).convert("RGBA")
            canvas.paste(cropped, (0, 0))
        except Exception as e:
            logger.warning("og: cover decode failed: %s", e)
            canvas.paste(Image.new("RGBA", (_W, _PHOTO_H), _INK_MUTED + (255,)), (0, 0))
    else:
        canvas.paste(Image.new("RGBA", (_W, _PHOTO_H), _INK_MUTED + (255,)), (0, 0))

    # Subtle bottom gradient so the divider line reads cleanly
    grad = Image.new("RGBA", (_W, 80), (0, 0, 0, 0))
    gd = ImageDraw.Draw(grad)
    for i in range(80):
        a = int(i / 80 * 55)
        gd.rectangle([0, i, _W, i + 1], fill=(0, 0, 0, a))
    canvas.alpha_composite(grad, dest=(0, _PHOTO_H - 80))

    draw = ImageDraw.Draw(canvas)

    # --- Pill overlays (top-left) --------------------------------------
    pill_font = _font("Manrope-Bold.ttf", 20)
    px, py = _PAD - 12, _PAD - 12
    # Time pill — match AuctionCard .pill-live / .pill-ending styling
    if time_urgent or time_label == "ENDED":
        time_fg = _DANGER
        time_bg = _DANGER_SOFT + (235,)
        time_border = _DANGER + (100,)
        dot = _DANGER
    else:
        time_fg = _ACCENT
        time_bg = _ACCENT_SOFT + (235,)
        time_border = _ACCENT + (100,)
        dot = _ACCENT
    px = _pill(
        draw, canvas, (px, py),
        time_label,
        fg=time_fg, bg=time_bg, border=time_border,
        font=pill_font, icon_dot=dot,
    ) + 10
    if featured:
        # Featured — neutral white glass pill like the site default
        _pill(
            draw, canvas, (px, py),
            "FEATURED",
            fg=_INK,
            bg=(255, 255, 255, 235),
            border=_LINE + (255,),
            font=pill_font,
        )

    # --- Divider ------------------------------------------------------
    draw.rectangle([0, _PHOTO_H, _W, _PHOTO_H + 1], fill=_LINE + (255,))

    # --- Bottom: card body ---------------------------------------------
    body_top = _PHOTO_H
    body_y = body_top + _PAD - 8
    # Left column — title + subline
    title_font = _font("Manrope-Bold.ttf", 42)
    # Wrap to max 1 line + ellipsis (we only have 210 px vertical for body
    # so keep it tight and let the image do the heavy lifting).
    title_max_w = _W - _PAD * 2 - 320  # reserve space on the right for the wordmark + bid
    title_line = _fit_single_line(draw, title, title_font, title_max_w)
    draw.text((_PAD, body_y), title_line, font=title_font, fill=_INK)

    # Subline under title: current bid label
    sub_font = _font("Manrope-SemiBold.ttf", 22)
    muted_font = _font("Manrope-Regular.ttf", 18)
    sub_y = body_y + 58
    if bid_label:
        draw.text((_PAD, sub_y), "CURRENT BID", font=muted_font, fill=_INK_MUTED)
        bid_font = _font("Manrope-Bold.ttf", 44)
        draw.text((_PAD, sub_y + 24), bid_label, font=bid_font, fill=_INK)
        if bid_sub_label:
            draw.text(
                (_PAD + int(draw.textlength(bid_label, font=bid_font)) + 14, sub_y + 40),
                bid_sub_label,
                font=sub_font, fill=_INK_MUTED,
            )
    else:
        draw.text((_PAD, sub_y), "Live auction · No bids yet", font=sub_font, fill=_INK_MUTED)

    # Right column — wordmark (top) + sparse details (bottom)
    # Wordmark "A&B" lockup — same as the new favicon: black A, emerald &, black B.
    # We render "Auto&Bid" for horizontal displays since we have the room.
    logo_font = _font("Manrope-Bold.ttf", 38)
    left_text = "Auto"
    amp_text = "&"
    right_text = "Bid"
    lw = draw.textlength(left_text, font=logo_font)
    aw = draw.textlength(amp_text, font=logo_font)
    rw = draw.textlength(right_text, font=logo_font)
    total_logo_w = lw + aw + rw
    logo_x = _W - _PAD - int(total_logo_w)
    logo_y = body_top + _PAD - 6
    draw.text((logo_x, logo_y), left_text, font=logo_font, fill=_INK)
    draw.text((logo_x + lw, logo_y), amp_text, font=logo_font, fill=_AMP_GREEN)
    draw.text((logo_x + lw + aw, logo_y), right_text, font=logo_font, fill=_INK)

    # Domain hint under the wordmark — tiny, muted
    domain_font = _font("Manrope-SemiBold.ttf", 16)
    domain_text = "autoandbid.com"
    dw = draw.textlength(domain_text, font=domain_font)
    draw.text((_W - _PAD - int(dw), logo_y + 48), domain_text, font=domain_font, fill=_INK_MUTED)

    buf = io.BytesIO()
    canvas.convert("RGB").save(buf, "PNG", optimize=True)
    return buf.getvalue()


def _fit_single_line(draw, text, font, max_width):
    text = (text or "").strip()
    if draw.textlength(text, font=font) <= max_width:
        return text
    # Binary-trim and append an ellipsis
    lo, hi = 0, len(text)
    while lo < hi:
        mid = (lo + hi + 1) // 2
        if draw.textlength(text[:mid] + "…", font=font) <= max_width:
            lo = mid
        else:
            hi = mid - 1
    return text[:lo].rstrip() + "…"


def _cache_key(auction_id: str, current_bid: float, ends_at_iso: Optional[str]) -> str:
    minute_bucket = ""
    if ends_at_iso:
        try:
            end = datetime.fromisoformat(ends_at_iso.replace("Z", "+00:00"))
            minute_bucket = end.strftime("%Y%m%d%H%M")
        except Exception:
            minute_bucket = ends_at_iso
    raw = f"{auction_id}:{int(current_bid or 0)}:{minute_bucket}:v2"
    return hashlib.sha1(raw.encode()).hexdigest()[:16]


async def build_or_cache(auction: dict) -> bytes:
    aid = str(auction.get("id") or "")
    current_bid = float(auction.get("current_bid_eur") or auction.get("starting_bid_eur") or 0)
    ends_at = auction.get("ends_at")
    key = _cache_key(aid, current_bid, ends_at)
    cache_path = os.path.join(_CACHE_DIR, f"{key}.png")
    if os.path.exists(cache_path) and (time.time() - os.path.getmtime(cache_path) < _CACHE_TTL_SEC):
        try:
            with open(cache_path, "rb") as f:
                return f.read()
        except Exception:
            pass

    cover_url = (auction.get("thumbnails") or auction.get("images") or [None])[0]
    cover_bytes = await _fetch_image(cover_url) if cover_url else None

    title = auction.get("title") or " ".join(
        str(auction.get(k) or "") for k in ("year", "make", "model")
    ).strip() or "Auto&Bid auction"
    time_label, time_urgent = _english_time_left(ends_at)
    featured = bool(auction.get("featured"))
    bid_label = f"€{int(current_bid):,}".replace(",", "\u202f") if current_bid > 0 else None
    bid_count = int(auction.get("bid_count") or 0)
    bid_sub = f"· {bid_count} bids" if bid_count and bid_label else None

    png = await asyncio.to_thread(
        _compose_image,
        cover_bytes, title, time_label, time_urgent, featured, bid_label, bid_sub,
    )
    try:
        with open(cache_path, "wb") as f:
            f.write(png)
    except Exception as e:
        logger.debug("og: cache write failed: %s", e)
    return png
