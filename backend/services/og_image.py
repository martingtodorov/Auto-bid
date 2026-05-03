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
_PHOTO_W = 720        # left photo column (full height)
_PANEL_W = _W - _PHOTO_W  # 480 px white card on the right
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
    pad_x, pad_y = 24, 14
    tw = int(draw.textlength(text, font=font))
    th = font.size
    dot_r = 6
    dot_w = (dot_r * 2 + 12) if icon_dot else 0
    pill_w = pad_x * 2 + dot_w + tw
    pill_h = pad_y * 2 + th

    x, y = xy
    layer = Image.new("RGBA", (pill_w, pill_h), (0, 0, 0, 0))
    ld = ImageDraw.Draw(layer)
    ld.rounded_rectangle([0, 0, pill_w - 1, pill_h - 1], radius=pill_h // 2, fill=bg, outline=border, width=2)

    text_x = pad_x
    if icon_dot:
        cy = pill_h // 2
        ld.ellipse([pad_x, cy - dot_r, pad_x + dot_r * 2, cy + dot_r], fill=icon_dot)
        text_x = pad_x + dot_r * 2 + 12
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

    # --- LEFT: photo (full height) -------------------------------------
    if cover_bytes:
        try:
            src = Image.open(io.BytesIO(cover_bytes)).convert("RGB")
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
            cropped = src.crop((left, top, left + _PHOTO_W, top + _H)).convert("RGBA")
            canvas.paste(cropped, (0, 0))
        except Exception as e:
            logger.warning("og: cover decode failed: %s", e)
            canvas.paste(Image.new("RGBA", (_PHOTO_W, _H), _INK_MUTED + (255,)), (0, 0))
    else:
        canvas.paste(Image.new("RGBA", (_PHOTO_W, _H), _INK_MUTED + (255,)), (0, 0))

    # White card divider — vertical 1px line where photo meets panel
    draw = ImageDraw.Draw(canvas)
    draw.rectangle([_PHOTO_W, 0, _PHOTO_W + 1, _H], fill=_LINE + (255,))

    # --- Pill overlays on the photo (top-left, BIG) --------------------
    pill_font = _font("Manrope-Bold.ttf", 32)
    px, py = _PAD - 8, _PAD - 8
    if time_urgent or time_label == "ENDED":
        time_fg = _DANGER
        time_bg = _DANGER_SOFT + (235,)
        time_border = _DANGER + (110,)
        dot = _DANGER
    else:
        time_fg = _ACCENT
        time_bg = _ACCENT_SOFT + (235,)
        time_border = _ACCENT + (110,)
        dot = _ACCENT
    px = _pill(
        draw, canvas, (px, py),
        time_label,
        fg=time_fg, bg=time_bg, border=time_border,
        font=pill_font, icon_dot=dot,
    ) + 12
    if featured:
        _pill(
            draw, canvas, (px, py),
            "FEATURED",
            fg=_INK,
            bg=(255, 255, 255, 235),
            border=_LINE + (255,),
            font=pill_font,
        )

    # --- RIGHT: white card panel ---------------------------------------
    panel_x = _PHOTO_W + 1
    inner_pad = 36
    cur_y = _PAD - 4

    # Auto&Bid wordmark — TOP of the panel, BIG (Manrope Bold 64)
    logo_font = _font("Manrope-Bold.ttf", 64)
    left_text, amp_text, right_text = "Auto", "&", "Bid"
    lw = draw.textlength(left_text, font=logo_font)
    aw = draw.textlength(amp_text, font=logo_font)
    rw = draw.textlength(right_text, font=logo_font)
    total_logo_w = lw + aw + rw
    logo_x = panel_x + (_PANEL_W - int(total_logo_w)) // 2
    draw.text((logo_x, cur_y), left_text, font=logo_font, fill=_INK)
    draw.text((logo_x + lw, cur_y), amp_text, font=logo_font, fill=_AMP_GREEN)
    draw.text((logo_x + lw + aw, cur_y), right_text, font=logo_font, fill=_INK)
    cur_y += 78

    # Domain hint, centered
    domain_font = _font("Manrope-SemiBold.ttf", 18)
    domain_text = "autoandbid.com"
    dw = draw.textlength(domain_text, font=domain_font)
    draw.text(
        (panel_x + (_PANEL_W - int(dw)) // 2, cur_y),
        domain_text,
        font=domain_font, fill=_INK_MUTED,
    )
    cur_y += 50

    # Subtle horizontal rule under the wordmark block
    draw.rectangle(
        [panel_x + inner_pad, cur_y, panel_x + _PANEL_W - inner_pad, cur_y + 1],
        fill=_LINE + (255,),
    )
    cur_y += 32

    # Title (Manrope Bold 30, up to 3 lines, ellipsis)
    title_font = _font("Manrope-Bold.ttf", 30)
    title_max_w = _PANEL_W - inner_pad * 2
    title_lines = _wrap(draw, title, title_font, title_max_w, max_lines=3)
    for line in title_lines:
        draw.text((panel_x + inner_pad, cur_y), line, font=title_font, fill=_INK)
        cur_y += 38

    # --- Bottom: BIG current bid block ---------------------------------
    bottom_y = _H - _PAD - 4
    if bid_label:
        muted_font = _font("Manrope-SemiBold.ttf", 20)
        bid_font = _font("Manrope-Bold.ttf", 80)
        sub_font = _font("Manrope-SemiBold.ttf", 22)
        # "CURRENT BID" tiny label — draw word-by-word so the space is
        # visually correct (Manrope SemiBold collapses ASCII space too tight)
        draw.text(
            (panel_x + inner_pad, bottom_y - 130),
            "CURRENT",
            font=muted_font, fill=_INK_MUTED,
        )
        cur_w = draw.textlength("CURRENT", font=muted_font)
        draw.text(
            (panel_x + inner_pad + int(cur_w) + 8, bottom_y - 130),
            "BID",
            font=muted_font, fill=_INK_MUTED,
        )
        # The big number
        draw.text(
            (panel_x + inner_pad, bottom_y - 100),
            bid_label,
            font=bid_font, fill=_INK,
        )
        if bid_sub_label:
            draw.text(
                (panel_x + inner_pad, bottom_y - 12),
                bid_sub_label,
                font=sub_font, fill=_INK_MUTED,
            )
    else:
        no_bid_font = _font("Manrope-Bold.ttf", 36)
        draw.text(
            (panel_x + inner_pad, bottom_y - 60),
            "No bids yet",
            font=no_bid_font, fill=_ACCENT,
        )

    buf = io.BytesIO()
    canvas.convert("RGB").save(buf, "PNG", optimize=True)
    return buf.getvalue()


def _wrap(draw, text, font, max_width, max_lines=3):
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
                while cur and draw.textlength(cur + "…", font=font) > max_width:
                    cur = cur[:-1]
                if cur:
                    lines.append(cur + "…")
                return lines
    if cur and len(lines) < max_lines:
        lines.append(cur)
    return lines


def _cache_key(auction_id: str, current_bid: float, ends_at_iso: Optional[str]) -> str:
    minute_bucket = ""
    if ends_at_iso:
        try:
            end = datetime.fromisoformat(ends_at_iso.replace("Z", "+00:00"))
            minute_bucket = end.strftime("%Y%m%d%H%M")
        except Exception:
            minute_bucket = ends_at_iso
    raw = f"{auction_id}:{int(current_bid or 0)}:{minute_bucket}:v4"
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
