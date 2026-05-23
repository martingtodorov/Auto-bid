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
    # Local URLs (`/api/uploads/...`) are stored on disk — short-circuit
    # the HTTP fetch and just read the file. Saves a round-trip through
    # the public ingress AND works inside the cluster even when the
    # public hostname isn't routable from this pod.
    if url.startswith("/"):
        try:
            uploads_prefix = "/api/uploads/"
            if url.startswith(uploads_prefix):
                rel = url[len(uploads_prefix):]
                fs_path = os.path.join(_uploads_root(), rel)
                if os.path.exists(fs_path):
                    with open(fs_path, "rb") as f:
                        return f.read()
        except Exception as e:
            logger.debug("og: local cover read failed %s: %s", url, e)
        # Fallback: try the in-cluster backend on localhost so we still
        # cover variant-served paths or future routes that don't map 1:1
        # to a file on disk.
        url = f"http://127.0.0.1:8001{url}"
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

    # --- Pill overlay on the photo (top-left, BIG) ---------------------
    # Countdown removed intentionally — a time pill forces every-minute
    # regeneration of the PNG, which the social crawler cache never
    # respects anyway. We now refresh the share card only when the user
    # sees a materially different number (new bid, new title, cover
    # swap). FEATURED still shows when the admin flags the listing.
    if featured:
        pill_font = _font("Manrope-Bold.ttf", 32)
        _pill(
            draw, canvas, (_PAD - 8, _PAD - 8),
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
    cur_y += 84

    # Subtle horizontal rule under the wordmark
    draw.rectangle(
        [panel_x + inner_pad, cur_y, panel_x + _PANEL_W - inner_pad, cur_y + 1],
        fill=_LINE + (255,),
    )
    cur_y += 36

    # Title (Manrope Bold 42, up to 3 lines, ellipsis) — the primary
    # content of the share card. Sized so a typical "BMW M2 Competition
    # 2020" fits on one or two lines and stays readable in WhatsApp /
    # Telegram previews at 80 % scale.
    title_font = _font("Manrope-Bold.ttf", 42)
    line_h = 52
    title_max_w = _PANEL_W - inner_pad * 2
    title_lines = _wrap(draw, title, title_font, title_max_w, max_lines=3)
    for line in title_lines:
        draw.text((panel_x + inner_pad, cur_y), line, font=title_font, fill=_INK)
        cur_y += line_h

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


def _cache_key(auction_id: str, current_bid: float, title: str = "", cover_url: str = "") -> str:
    """Cache key includes everything that visually affects the rendered PNG.

    By including `title` + `cover_url` (not just bid), we invalidate the cache
    when the auction's headline changes — e.g. seller renames the listing or
    re-orders the photos. Without this, the cached PNG would silently lag the
    real auction state and social shares would show a stale title.
    """
    raw = f"{auction_id}:{int(current_bid or 0)}:{title}:{cover_url}:v8"
    return hashlib.sha1(raw.encode()).hexdigest()[:16]


async def build_or_cache(auction: dict) -> bytes:
    aid = str(auction.get("id") or "")
    # Apply VAT if the listing is `vat_inclusive`. The rest of the app
    # displays gross prices globally (per the 2026-02 "prices WITH VAT"
    # policy) and the share card must match — otherwise a buyer sees a
    # suspiciously-low bid in WhatsApp preview and a higher one after
    # clicking through.
    raw_bid = float(auction.get("current_bid_eur") or auction.get("starting_bid_eur") or 0)
    if auction.get("vat_status") == "vat_inclusive":
        try:
            rate = float(auction.get("vat_rate_pct") or 0)
            current_bid = round(raw_bid * (1 + rate / 100.0), 2)
        except Exception:
            current_bid = raw_bid
    else:
        current_bid = raw_bid

    title = auction.get("title") or " ".join(
        str(auction.get(k) or "") for k in ("year", "make", "model")
    ).strip() or "Auto&Bid auction"
    cover_url = (auction.get("thumbnails") or auction.get("images") or [None])[0] or ""
    key = _cache_key(aid, current_bid, title, cover_url)
    cache_path = os.path.join(_CACHE_DIR, f"{key}.png")
    if os.path.exists(cache_path) and (time.time() - os.path.getmtime(cache_path) < _CACHE_TTL_SEC):
        try:
            with open(cache_path, "rb") as f:
                return f.read()
        except Exception:
            pass

    cover_bytes = await _fetch_image(cover_url) if cover_url else None

    featured = bool(auction.get("featured"))
    bid_label = f"€{int(current_bid):,}".replace(",", "\u202f") if current_bid > 0 else None
    bid_count = int(auction.get("bid_count") or 0)
    bid_sub = f"· {bid_count} bids" if bid_count and bid_label else None

    png = await asyncio.to_thread(
        _compose_image,
        cover_bytes, title, featured, bid_label, bid_sub,
    )
    try:
        with open(cache_path, "wb") as f:
            f.write(png)
    except Exception as e:
        logger.debug("og: cache write failed: %s", e)
    return png


# ---------------------------------------------------------------------------
# Eager generation — called at publish time so the file exists before any
# social crawler hits the listing. Writes to the shared uploads directory
# (so nginx serves the PNG directly) and returns the public URL that gets
# persisted on the auction document as `og_image_url`.
# ---------------------------------------------------------------------------
def _uploads_root() -> str:
    return os.path.abspath(os.environ.get("UPLOAD_DIR", "/opt/autobids/uploads"))


def _uploads_public_base() -> str:
    from storage import public_uploads_base
    return public_uploads_base()


def headline_image_url(auction: dict) -> str:
    """Return the auction's headline (first available) image URL.
    Used as a graceful fallback for the OG share image when our
    template generator fails — far better UX than the homepage's
    static `/og-default.jpg`, which gives no signal about *which*
    listing was shared."""
    for bucket in ("thumbnails", "images"):
        items = auction.get(bucket) or []
        for c in items:
            if c and isinstance(c, str):
                return c
    return ""


async def build_and_persist(auction: dict) -> str:
    """Generate the per-auction social-share PNG and persist it under
    `<UPLOAD_DIR>/og/{id}.png` so Nginx can serve it directly as a static
    asset (no FastAPI hit per share-preview crawl).

    Returns the public URL of the freshly-written PNG. The caller is
    expected to persist this URL on the auction document as
    `og_image_url` — the SSR `/share/auction/{id}` route then emits it
    as the `og:image` meta without re-rendering.

    Cache behaviour:
      • Filename is content-addressed via `_cache_key(...)`. A new bid
        OR title change OR cover swap produces a different sha1 hash,
        so old files become orphaned but the new one is regenerated.
      • Existing fresh files (≤ `_CACHE_TTL_SEC` old) are returned
        without re-rendering — keeps the call idempotent during high-
        frequency bid storms.
      • On any error we gracefully fall back to the headline photo URL,
        so the share preview is never broken — at worst it shows the
        unbranded car photo.
    """
    aid = str(auction.get("id") or "")
    if not aid:
        return headline_image_url(auction) or "/og-default.jpg"

    # Replicate the VAT-aware bid resolution from `build_or_cache` so
    # the persisted file matches the on-demand one and the same cache
    # key resolves to the same hash on both code paths.
    raw_bid = float(auction.get("current_bid_eur") or auction.get("starting_bid_eur") or 0)
    if auction.get("vat_status") == "vat_inclusive":
        try:
            rate = float(auction.get("vat_rate_pct") or 0)
            current_bid = round(raw_bid * (1 + rate / 100.0), 2)
        except Exception:
            current_bid = raw_bid
    else:
        current_bid = raw_bid
    title = auction.get("title") or " ".join(
        str(auction.get(k) or "") for k in ("year", "make", "model")
    ).strip() or "Auto&Bid auction"
    cover_url = (auction.get("thumbnails") or auction.get("images") or [None])[0] or ""
    key = _cache_key(aid, current_bid, title, cover_url)

    uploads_root = _uploads_root()
    og_dir = os.path.join(uploads_root, "og")
    try:
        os.makedirs(og_dir, exist_ok=True)
    except Exception as e:
        logger.warning("og: cannot create %s: %s — falling back to headline", og_dir, e)
        return headline_image_url(auction) or "/og-default.jpg"

    # Per-auction stable filename — embeds the cache key so the URL
    # changes when the content changes (busts FB/Twitter caches without
    # us having to call their refresh APIs).
    fname = f"{aid}_{key}.png"
    fpath = os.path.join(og_dir, fname)
    public_url = f"{_uploads_public_base().rstrip('/')}/og/{fname}"

    if os.path.exists(fpath) and (time.time() - os.path.getmtime(fpath) < _CACHE_TTL_SEC):
        return public_url

    try:
        png = await build_or_cache(auction)
        with open(fpath, "wb") as f:
            f.write(png)
        # Best-effort cleanup of older PNGs for this same auction — we
        # only keep the latest cache-keyed file, so leftovers from
        # previous bids accumulate otherwise.
        try:
            prefix = f"{aid}_"
            for entry in os.listdir(og_dir):
                if entry.startswith(prefix) and entry != fname:
                    try:
                        os.remove(os.path.join(og_dir, entry))
                    except Exception:
                        pass
        except Exception:
            pass
        return public_url
    except Exception as e:
        logger.warning("og: persist failed for %s: %s", aid, e)
        return headline_image_url(auction) or auction.get("og_image_url") or "/og-default.jpg"
