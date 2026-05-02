"""
Dynamic Open Graph (social sharing) image generator.

Builds a 1200×630 PNG per auction:
  • Left ~65 %: cropped cover photo
  • Right ~35 %: black panel with the Auto&Bid wordmark (green "&"),
    the English time-remaining, and the current bid if space allows.

Cache is keyed by (auction_id, current_bid_eur, ends_at_minute) so that
FB/Twitter crawlers get a fresh image whenever the visible numbers
change, without regenerating on every hit.
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
from PIL import Image, ImageDraw, ImageFont

logger = logging.getLogger(__name__)

_CACHE_DIR = "/tmp/og_cache"
os.makedirs(_CACHE_DIR, exist_ok=True)

# Keep generated images around for 24 h — we regenerate on bid changes
# via the cache key anyway, so TTL is just a safety net.
_CACHE_TTL_SEC = 24 * 3600

# Canvas
_W, _H = 1200, 630
_PHOTO_W = 780          # left photo column
_PANEL_W = _W - _PHOTO_W  # right black panel (420 px)
_PAD = 40

# Palette — matches the app CSS variables
_BG = (255, 255, 255)
_INK = (15, 23, 42)             # slate-900 like
_INK_MUTED = (100, 116, 139)
_ACCENT = (27, 77, 62)          # --accent (hsl 166 48% 20%)
_PANEL_BG = (11, 18, 32)        # near-black with a hint of navy
_PANEL_INK = (255, 255, 255)
_PANEL_MUTED = (156, 175, 200)
_AMPERSAND_GREEN = (52, 211, 153)  # bright emerald — pops against black

# Font discovery — Liberation is installed by default in our container.
_FONT_DIR = "/usr/share/fonts/truetype/liberation"
_FALLBACK_FONT_DIR = "/usr/share/fonts/truetype"


def _font(name: str, size: int) -> ImageFont.FreeTypeFont:
    """Return a truetype font; fall back to PIL default on any failure."""
    try:
        path = os.path.join(_FONT_DIR, name)
        if os.path.exists(path):
            return ImageFont.truetype(path, size)
        # Try anywhere under /usr/share/fonts/truetype
        for root, _dirs, files in os.walk(_FALLBACK_FONT_DIR):
            if name in files:
                return ImageFont.truetype(os.path.join(root, name), size)
    except Exception:
        pass
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


def _english_time_left(ends_at_iso: Optional[str]) -> str:
    """Plain English compact label: `Ends in 4d 12h`, `Ends in 2h 15m`,
    `Ends in 8m`, or `Ended`."""
    if not ends_at_iso:
        return "Live auction"
    try:
        iso = ends_at_iso.replace("Z", "+00:00")
        end = datetime.fromisoformat(iso)
    except Exception:
        return "Live auction"
    now = datetime.now(timezone.utc)
    delta = (end - now).total_seconds()
    if delta <= 0:
        return "Ended"
    days = int(delta // 86400)
    hours = int((delta % 86400) // 3600)
    minutes = int((delta % 3600) // 60)
    if days > 0:
        return f"Ends in {days}d {hours}h"
    if hours > 0:
        return f"Ends in {hours}h {minutes}m"
    return f"Ends in {minutes}m"


def _compose_image(
    cover_bytes: Optional[bytes],
    title: str,
    time_label: str,
    bid_label: Optional[str],
) -> bytes:
    canvas = Image.new("RGB", (_W, _H), _BG)

    # --- Left: photo ---------------------------------------------------
    if cover_bytes:
        try:
            src = Image.open(io.BytesIO(cover_bytes)).convert("RGB")
            # Cover crop at _PHOTO_W × _H
            src_ratio = src.width / src.height
            tgt_ratio = _PHOTO_W / _H
            if src_ratio > tgt_ratio:
                new_h = _H
                new_w = int(_H * src_ratio)
            else:
                new_w = _PHOTO_W
                new_h = int(_PHOTO_W / src_ratio)
            src = src.resize((new_w, new_h), Image.LANCZOS)
            left = (new_w - _PHOTO_W) // 2
            top = (new_h - _H) // 2
            canvas.paste(src.crop((left, top, left + _PHOTO_W, top + _H)), (0, 0))
        except Exception as e:
            logger.warning("og: cover decode failed: %s", e)
            canvas.paste(Image.new("RGB", (_PHOTO_W, _H), _INK_MUTED), (0, 0))
    else:
        # No cover → solid mid-grey so the panel still reads
        canvas.paste(Image.new("RGB", (_PHOTO_W, _H), _INK_MUTED), (0, 0))

    draw = ImageDraw.Draw(canvas)

    # --- Right: black panel --------------------------------------------
    draw.rectangle([_PHOTO_W, 0, _W, _H], fill=_PANEL_BG)

    # Wordmark "Auto&Bid" with green ampersand
    # Manually composite: render "Auto" + "&" + "Bid" with 3 draw calls
    # so the ampersand can be emerald while the rest stays white.
    logo_bold = _font("LiberationSans-Bold.ttf", 56)
    left_text = "Auto"
    amp_text = "&"
    right_text = "Bid"
    # measure
    lw = draw.textlength(left_text, font=logo_bold)
    aw = draw.textlength(amp_text, font=logo_bold)
    rw = draw.textlength(right_text, font=logo_bold)
    total = lw + aw + rw
    logo_x = _PHOTO_W + (_PANEL_W - total) / 2
    logo_y = _PAD + 8
    draw.text((logo_x, logo_y), left_text, font=logo_bold, fill=_PANEL_INK)
    draw.text((logo_x + lw, logo_y), amp_text, font=logo_bold, fill=_AMPERSAND_GREEN)
    draw.text((logo_x + lw + aw, logo_y), right_text, font=logo_bold, fill=_PANEL_INK)

    # Divider rule under wordmark
    rule_y = logo_y + 80
    draw.rectangle(
        [_PHOTO_W + _PAD, rule_y, _W - _PAD, rule_y + 1],
        fill=(60, 80, 105),
    )

    # Title — wrap to 2 lines max
    title_font = _font("LiberationSerif-Regular.ttf", 30)
    title_lines = _wrap(draw, title, title_font, _PANEL_W - 2 * _PAD, max_lines=3)
    ty = rule_y + 28
    for line in title_lines:
        draw.text((_PHOTO_W + _PAD, ty), line, font=title_font, fill=_PANEL_INK)
        ty += 38

    # Time + bid stacked at the bottom of the panel
    small_label = _font("LiberationSans-Regular.ttf", 18)
    big_number = _font("LiberationSans-Bold.ttf", 44)

    # Current bid first (eye-catching number)
    bottom_y = _H - _PAD - 6
    if bid_label:
        bid_lbl_txt = "CURRENT BID"
        draw.text(
            (_PHOTO_W + _PAD, bottom_y - 90),
            bid_lbl_txt,
            font=small_label,
            fill=_PANEL_MUTED,
        )
        draw.text(
            (_PHOTO_W + _PAD, bottom_y - 68),
            bid_label,
            font=big_number,
            fill=_PANEL_INK,
        )
        # Time remaining on the row above the bid (smaller)
        time_font = _font("LiberationSans-Bold.ttf", 22)
        time_w = draw.textlength(time_label, font=time_font)
        draw.text(
            (_W - _PAD - time_w, bottom_y - 20),
            time_label,
            font=time_font,
            fill=_AMPERSAND_GREEN,
        )
    else:
        # No bid yet — make the time label the hero piece at the bottom
        draw.text(
            (_PHOTO_W + _PAD, bottom_y - 60),
            time_label,
            font=big_number,
            fill=_AMPERSAND_GREEN,
        )

    buf = io.BytesIO()
    canvas.save(buf, "PNG", optimize=True)
    return buf.getvalue()


def _wrap(draw, text, font, max_width, max_lines=2):
    words = (text or "").split()
    lines: list[str] = []
    cur = ""
    for w in words:
        test = f"{cur} {w}".strip()
        if draw.textlength(test, font=font) <= max_width:
            cur = test
        else:
            if cur:
                lines.append(cur)
            cur = w
            if len(lines) == max_lines - 1:
                # Truncate last line with ellipsis if needed
                while cur and draw.textlength(cur + "…", font=font) > max_width:
                    cur = cur[:-1]
                if cur:
                    lines.append(cur + "…")
                return lines
    if cur and len(lines) < max_lines:
        lines.append(cur)
    return lines


def _cache_key(auction_id: str, current_bid: float, ends_at_iso: Optional[str]) -> str:
    # Quantize `ends_at` to the minute so 60s of cache life exists per rev
    minute_bucket = ""
    if ends_at_iso:
        try:
            end = datetime.fromisoformat(ends_at_iso.replace("Z", "+00:00"))
            minute_bucket = end.strftime("%Y%m%d%H%M")
        except Exception:
            minute_bucket = ends_at_iso
    raw = f"{auction_id}:{int(current_bid or 0)}:{minute_bucket}"
    return hashlib.sha1(raw.encode()).hexdigest()[:16]


async def build_or_cache(auction: dict) -> bytes:
    """Return PNG bytes for the auction, reading from disk when possible."""
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

    # Pick the cover image: prefer thumbnail (cheaper + already cached
    # at our CDN edge). Full-res still works if we only have that.
    cover_url = (auction.get("thumbnails") or auction.get("images") or [None])[0]
    cover_bytes = await _fetch_image(cover_url) if cover_url else None

    # Compose in a threadpool — PIL is CPU-bound and blocks the loop.
    title = auction.get("title") or " ".join(
        str(auction.get(k) or "") for k in ("year", "make", "model")
    ).strip() or "Auto&Bid auction"
    time_label = _english_time_left(ends_at)
    bid_label = f"€{int(current_bid):,}".replace(",", "\u202f") if current_bid > 0 else None

    png = await asyncio.to_thread(
        _compose_image, cover_bytes, title, time_label, bid_label
    )
    try:
        with open(cache_path, "wb") as f:
            f.write(png)
    except Exception as e:
        logger.debug("og: cache write failed: %s", e)
    return png
