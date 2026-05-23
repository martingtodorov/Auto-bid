"""
SEO / social sharing routes — XML sitemaps + OG-rich share pages for crawlers.
Extracted from server.py to keep auction/bidding logic focused.
"""
import os
import re
import json as _json
import json
from datetime import datetime, timezone
from html import escape as _esc
from typing import Optional

from fastapi import APIRouter, HTTPException, Query, Request, Response
from fastapi.responses import PlainTextResponse, RedirectResponse

from deps import db
from services import og_image

router = APIRouter()


# Cyrillic → Latin transliteration for slug generation (Bulgarian alphabet).
# Mirrors the frontend table in `frontend/src/lib/auctionUrl.js` so sitemap
# URLs match the ones actually rendered in the SPA.
_CYR_MAP = str.maketrans({
    "а":"a","б":"b","в":"v","г":"g","д":"d","е":"e","ж":"zh","з":"z","и":"i","й":"y",
    "к":"k","л":"l","м":"m","н":"n","о":"o","п":"p","р":"r","с":"s","т":"t","у":"u",
    "ф":"f","х":"h","ц":"ts","ч":"ch","ш":"sh","щ":"sht","ъ":"a","ь":"y","ю":"yu","я":"ya",
    "А":"A","Б":"B","В":"V","Г":"G","Д":"D","Е":"E","Ж":"Zh","З":"Z","И":"I","Й":"Y",
    "К":"K","Л":"L","М":"M","Н":"N","О":"O","П":"P","Р":"R","С":"S","Т":"T","У":"U",
    "Ф":"F","Х":"H","Ц":"Ts","Ч":"Ch","Ш":"Sh","Щ":"Sht","Ъ":"A","Ь":"Y","Ю":"Yu","Я":"Ya",
})


def _auction_slug_url(auction: dict) -> str:
    """Build the SEO-friendly `/auctions/<slug>-<suffix>` path. The 8-char
    suffix is the first 8 hex chars of the UUID (dashes stripped) so it
    stays unique even across identical titles."""
    aid = str(auction.get("id") or "")
    if not aid:
        return "/auctions/"
    suffix = aid.replace("-", "")[:8]
    title = auction.get("title") or " ".join(
        str(auction.get(k) or "") for k in ("year", "make", "model")
    ).strip()
    if not title:
        return f"/auctions/{aid}"
    slug = title.translate(_CYR_MAP).lower()
    slug = re.sub(r"[^a-z0-9]+", "-", slug).strip("-")[:80]
    if not slug:
        return f"/auctions/{aid}"
    return f"/auctions/{slug}-{suffix}"


async def _deindex_enabled() -> bool:
    """True when admin has toggled pre-launch `deindex_mode`. Read directly
    from Mongo so any replica / worker sees fresh state without a cache bust.
    """
    doc = await db.site_settings.find_one({"id": "global"}, {"_id": 0, "deindex_mode": 1})
    return bool(doc and doc.get("deindex_mode"))


def _fb_app_id_tag() -> str:
    """Emit `<meta property="fb:app_id" content="...">` when the env
    variable is configured. Facebook's Sharing Debugger flags missing
    `fb:app_id` as a warning; setting it links our share previews to
    the Domain Insights dashboard for that app. Returns an empty string
    when unset so we never emit an empty tag (which FB also rejects).
    """
    fb_id = (os.environ.get("FB_APP_ID") or "").strip()
    if not fb_id:
        return ""
    return f'<meta property="fb:app_id" content="{_esc(fb_id)}">'


@router.get("/robots.txt", response_class=PlainTextResponse)
async def robots_txt(request: Request):
    """Dynamic robots.txt — flips to full Disallow when admin enables
    `deindex_mode` in /admin/settings. Nginx should proxy `/robots.txt`
    → this endpoint so crawlers see the live value."""
    # Explicit headers so intermediaries (notably Cloudflare AI Shield,
    # which otherwise injects `Content-Signal:` directives when it sees
    # HTML content type) don't rewrite the body. `no-transform` is the
    # documented opt-out for CF's "Content Signals" managed transform.
    _plain_headers = {
        "Content-Type": "text/plain; charset=utf-8",
        "Cache-Control": "public, max-age=3600, no-transform",
        "X-Robots-Tag": "noindex",  # the file itself is not indexed
    }
    frontend_base = _canonical_base_for_request(request)
    if await _deindex_enabled():
        body = (
            "# Site is in pre-launch deindex mode — search engines stay out.\n"
            "User-agent: *\n"
            "Disallow: /\n"
        )
        return PlainTextResponse(
            content=body,
            headers={**_plain_headers, "Cache-Control": "no-store, no-transform"},
        )
    body = (
        "User-agent: *\n"
        "Allow: /\n"
        "\n"
        "# Disallow internal/admin flows\n"
        "Disallow: /admin\n"
        "Disallow: /login\n"
        "Disallow: /register\n"
        "Disallow: /dashboard\n"
        "Disallow: /settings\n"
        "Disallow: /watchlist\n"
        "Disallow: /inbox\n"
        "Disallow: /verify-email\n"
        "Disallow: /reset-password\n"
        "\n"
        f"Sitemap: {frontend_base}/sitemap.xml\n"
        f"Sitemap: {frontend_base}/sitemap-images.xml\n"
    )
    return PlainTextResponse(content=body, headers=_plain_headers)


def _json_ld_vehicle(a: dict, url: str) -> str:
    """Build schema.org Vehicle structured data for a listing.

    Includes rich-result Offer data (price, currency, availability, priceValidUntil,
    itemCondition, seller) so Google can render Rich Snippets (price/availability).
    """
    # Availability mapping across auction lifecycle
    status = a.get("status")
    availability = "https://schema.org/InStock"
    if status in ("ended", "sold"):
        availability = "https://schema.org/SoldOut"
    elif status in ("cancelled", "archived"):
        availability = "https://schema.org/Discontinued"
    elif status in ("scheduled", "upcoming"):
        availability = "https://schema.org/PreOrder"

    # Price: prefer current bid, fall back to starting bid
    price_value = a.get("current_bid_eur") or a.get("starting_bid_eur") or 0
    try:
        price_value = float(price_value)
    except (TypeError, ValueError):
        price_value = 0.0

    site_origin = url.split("/auctions/")[0] if "/auctions/" in url else url
    seller = (
        {"@type": "Person", "name": a.get("seller_name")}
        if a.get("seller_name")
        else {"@type": "Organization", "name": "Auto&Bid", "url": site_origin}
    )

    offers = {
        "@type": "Offer",
        "priceCurrency": "EUR",
        "price": price_value,
        "url": url,
        "availability": availability,
        "itemCondition": "https://schema.org/UsedCondition",
        "seller": seller,
        # Shipping: marketplace doesn't ship — buyer collects from seller's
        # city. Surface as `0 EUR` shipping covering the listing country so
        # the Google Merchant rich card shows "Free pickup" instead of a
        # missing-shipping warning.
        "shippingDetails": {
            "@type": "OfferShippingDetails",
            "shippingRate": {
                "@type": "MonetaryAmount",
                "value": 0,
                "currency": "EUR",
            },
            "shippingDestination": {
                "@type": "DefinedRegion",
                "addressCountry": (a.get("country_code") or "BG").upper()[:2],
            },
            "deliveryTime": {
                "@type": "ShippingDeliveryTime",
                "handlingTime": {"@type": "QuantitativeValue", "minValue": 0, "maxValue": 3, "unitCode": "DAY"},
                "transitTime": {"@type": "QuantitativeValue", "minValue": 1, "maxValue": 14, "unitCode": "DAY"},
            },
        },
        # Return policy: auction sales are final under EU consumer law
        # (private-party + auction = no 14-day distance-selling right).
        # Declaring this explicitly avoids the Search Console
        # "missing return policy" rich-result warning.
        "hasMerchantReturnPolicy": {
            "@type": "MerchantReturnPolicy",
            "applicableCountry": (a.get("country_code") or "BG").upper()[:2],
            "returnPolicyCategory": "https://schema.org/MerchantReturnNotPermitted",
        },
    }
    # priceValidUntil:
    #  - LIVE auction → `ends_at` (when bidding closes)
    #  - SOLD / ENDED → finalized_at + 30 days (post-sale snippet stays
    #    fresh in Google's cache instead of going stale on the close timestamp)
    #  - SCHEDULED / OTHER → fall back to ends_at if present
    if status in ("sold", "ended", "reserve_not_met") and a.get("finalized_at"):
        try:
            from datetime import datetime, timedelta
            fin = a["finalized_at"]
            if isinstance(fin, str):
                fin_dt = datetime.fromisoformat(fin.replace("Z", "+00:00"))
            else:
                fin_dt = fin
            offers["priceValidUntil"] = (fin_dt + timedelta(days=30)).isoformat()
        except Exception:  # noqa: BLE001
            if a.get("ends_at"):
                offers["priceValidUntil"] = a.get("ends_at")
    elif a.get("ends_at"):
        offers["priceValidUntil"] = a.get("ends_at")

    data = {
        "@context": "https://schema.org",
        "@type": "Vehicle",
        "name": a.get("title", ""),
        "brand": {"@type": "Brand", "name": a.get("make", "")} if a.get("make") else None,
        "manufacturer": {"@type": "Organization", "name": a.get("make")} if a.get("make") else None,
        "model": a.get("model", ""),
        "vehicleModelDate": a.get("year"),
        "modelDate": a.get("year"),
        "productionDate": str(a.get("year")) if a.get("year") else None,
        "bodyType": _schema_enum("body_type", a.get("body_type")),
        "fuelType": _schema_enum("fuel", a.get("fuel")),
        "vehicleTransmission": _schema_enum("transmission", a.get("transmission")),
        "color": _schema_enum("color", a.get("color")),
        "mileageFromOdometer": {
            "@type": "QuantitativeValue", "value": a.get("mileage_km"), "unitCode": "KMT",
        } if a.get("mileage_km") else None,
        "vehicleEngine": {
            "@type": "EngineSpecification",
            "engineDisplacement": {"@type": "QuantitativeValue", "value": a.get("engine_cc"), "unitCode": "CMQ"},
            "enginePower": {"@type": "QuantitativeValue", "value": a.get("power_hp"), "unitCode": "BHP"},
        } if a.get("engine_cc") else None,
        "image": [img for img in (a.get("images") or []) if img and not img.startswith("data:")][:6] or None,
        "description": (a.get("description") or "")[:600],
        "url": url,
        "offers": offers,
    }
    clean = {k: v for k, v in data.items() if v is not None}
    return _json.dumps(clean, ensure_ascii=False)


def _frontend_base(request: Request) -> str:
    return (
        os.environ.get("APP_URL")
        or request.headers.get("origin")
        or str(request.base_url).rstrip("/")
    ).rstrip("/")


# --- Canonical-per-language domain mapping ------------------------------------
# Production canonical URLs are pinned to the three TLDs regardless of which
# host actually answers the request (preview, staging, *.emergentagent.com).
# When the request *is* on one of the canonical TLDs we respect the language
# implied by the host (e.g. autoandbid.bg → bg sitemap); otherwise we default
# to the English `.com` canonical so dev/preview environments never leak into
# Google's index.
_LANG_TLD = {"bg": "autoandbid.bg", "en": "autoandbid.com", "ro": "autoandbid.ro"}


def _lang_from_host(host: str) -> str:
    h = (host or "").lower().split(":")[0]
    if h.endswith("autoandbid.bg"):
        return "bg"
    if h.endswith("autoandbid.ro"):
        return "ro"
    if h.endswith("autoandbid.com"):
        return "en"
    return "en"  # preview / staging / unknown → default English


def _canonical_base_for_lang(lang: str) -> str:
    return f"https://{_LANG_TLD.get(lang, _LANG_TLD['en'])}"


def _canonical_base_for_request(request: Request) -> str:
    """Always returns one of the three production TLDs — never the preview
    domain. Picks the TLD that matches the inbound `Host:` header; falls
    back to `autoandbid.com` (English canonical) otherwise."""
    host = request.headers.get("host", "")
    return _canonical_base_for_lang(_lang_from_host(host))


# --- Schema.org enum mapping (Cyrillic → canonical English) -------------------
# Google's Rich Results validator rejects Cyrillic enum strings for the
# Vehicle properties below, so we transliterate them into the canonical
# English values it expects. Unknown values fall through unchanged.
_SCHEMA_ENUM = {
    "body_type": {
        "Седан": "Sedan", "Хечбек": "Hatchback", "Хетчбек": "Hatchback",
        "Купе": "Coupe", "Кабрио": "Convertible", "Кабриолет": "Convertible",
        "Комби": "Estate", "Джип": "SUV", "SUV": "SUV", "Офроуд": "Off-road",
        "Ван": "Van", "Миниван": "Minivan", "Пикап": "Pickup",
        "Лимузина": "Limousine", "Родстер": "Roadster",
    },
    "fuel": {
        "Бензин": "Petrol", "Дизел": "Diesel", "Хибрид": "Hybrid",
        "Хибриден": "Hybrid", "Plug-in хибрид": "Plug-in hybrid",
        "Електричество": "Electric", "Електрически": "Electric",
        "Газ/Бензин": "LPG/Petrol", "LPG": "LPG", "Метан": "CNG",
        "Водороден": "Hydrogen",
    },
    "transmission": {
        "Автоматик": "Automatic", "Автоматична": "Automatic",
        "Ръчна": "Manual", "Полуавтоматична": "Semi-automatic",
        "Tiptronic": "Tiptronic", "Робот": "Automated", "Вариатор": "CVT",
    },
    "color": {
        "Бял": "White", "Черен": "Black", "Сив": "Grey", "Сребрист": "Silver",
        "Червен": "Red", "Син": "Blue", "Зелен": "Green", "Жълт": "Yellow",
        "Оранжев": "Orange", "Кафяв": "Brown", "Бежов": "Beige",
        "Златист": "Gold", "Графит": "Graphite",
        "Тъмно син": "Dark blue", "Тъмно сив": "Dark grey",
    },
}


def _schema_enum(kind: str, value):
    if not value or not isinstance(value, str):
        return value
    return _SCHEMA_ENUM.get(kind, {}).get(value, value)


def _collect_imgs(a: dict, max_count: int) -> list:
    """Return up to `max_count` unique image URLs for an auction.

    Dedupes by *normalized* path: `…/big1/front.jpg` and `…/front.jpg`
    collapse to the same logical image so Google sees one URL per shot
    instead of ~2× duplicates (originals + size variants). Earlier
    entries win — i.e. the order in `images_exterior` is preserved.
    """
    import re

    imgs_all = (
        (a.get("images_exterior") or [])
        + (a.get("images_interior") or [])
        + (a.get("images_wheels") or [])
        + (a.get("images_bumper") or [])
        + (a.get("images") or [])
    )
    # Strip variant/size segments: /big1/, /big2/, /thumb/, /md/, /lg/, /sm/.
    _variant_re = re.compile(r"/(big\d+|thumb|sm|md|lg|xl|original)/", re.I)
    seen = set()
    clean = []
    for img in imgs_all:
        if not img or not isinstance(img, str) or img.startswith("data:"):
            continue
        normalized = _variant_re.sub("/", img)
        if normalized in seen:
            continue
        seen.add(normalized)
        clean.append(img)
        if len(clean) >= max_count:
            break
    return clean


@router.get("/sitemap.xml", response_class=Response)
async def sitemap_xml(request: Request):
    """Dynamic XML sitemap (with Google Image Sitemap namespace)."""
    if await _deindex_enabled():
        # Pre-launch deindex — pretend we never had one.
        raise HTTPException(status_code=404, detail="Not found")
    frontend_base = _canonical_base_for_request(request)
    pages = [
        ("", "daily", "1.0"),
        ("/auctions", "hourly", "0.9"),
        ("/how-it-works", "monthly", "0.7"),
        ("/faq", "monthly", "0.6"),
        ("/fees", "monthly", "0.6"),
        ("/contacts", "monthly", "0.5"),
        ("/terms", "yearly", "0.3"),
    ]
    cursor = db.auctions.find(
        {
            "status": {"$in": ["live", "sold", "ended", "reserve_not_met"]},
            "is_archived": {"$ne": True},
        },
        {
            "_id": 0, "id": 1, "title": 1, "make": 1, "model": 1,
            "updated_at": 1, "finalized_at": 1, "created_at": 1, "status": 1,
            "images": 1, "images_exterior": 1, "images_interior": 1,
            "images_wheels": 1, "images_bumper": 1,
        },
    ).sort("created_at", -1).limit(5000)
    auctions = await cursor.to_list(5000)

    xml_parts = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"',
        '        xmlns:image="http://www.google.com/schemas/sitemap-image/1.1"',
        '        xmlns:xhtml="http://www.w3.org/1999/xhtml">',
    ]
    # Hreflang map — every auction URL is the same path under three TLDs.
    tld_map = {"bg": "https://autoandbid.bg", "en": "https://autoandbid.com", "ro": "https://autoandbid.ro"}
    for path, freq, pr in pages:
        alts = "".join(
            f'<xhtml:link rel="alternate" hreflang="{code}" href="{base}{path}"/>'
            for code, base in tld_map.items()
        )
        alts += f'<xhtml:link rel="alternate" hreflang="x-default" href="{tld_map["en"]}{path}"/>'
        xml_parts.append(
            f"<url><loc>{frontend_base}{path}</loc>"
            + alts
            + f"<changefreq>{freq}</changefreq><priority>{pr}</priority></url>"
        )
    for a in auctions:
        last = a.get("finalized_at") or a.get("updated_at") or a.get("created_at") or ""
        lastmod = f"<lastmod>{last[:10]}</lastmod>" if last else ""
        freq = "hourly" if a.get("status") == "live" else "monthly"
        pr = "0.9" if a.get("status") == "live" else "0.5"
        clean_imgs = _collect_imgs(a, 20)
        caption = _esc((a.get("title") or "").strip()[:160])
        image_blocks = []
        for img in clean_imgs:
            image_blocks.append(
                f"<image:image><image:loc>{_esc(img)}</image:loc>"
                + (f"<image:caption>{caption}</image:caption>" if caption else "")
                + f"<image:title>{caption}</image:title></image:image>"
            )
        slug_path = _auction_slug_url(a)
        alts = "".join(
            f'<xhtml:link rel="alternate" hreflang="{code}" href="{base}{slug_path}"/>'
            for code, base in tld_map.items()
        )
        alts += f'<xhtml:link rel="alternate" hreflang="x-default" href="{tld_map["en"]}{slug_path}"/>'
        xml_parts.append(
            f"<url><loc>{frontend_base}{slug_path}</loc>"
            + lastmod
            + alts
            + f"<changefreq>{freq}</changefreq><priority>{pr}</priority>"
            + "".join(image_blocks)
            + "</url>"
        )
    xml_parts.append("</urlset>")
    return Response(content="\n".join(xml_parts), media_type="application/xml; charset=utf-8")


@router.get("/sitemap-images.xml", response_class=Response)
async def sitemap_images_xml(request: Request):
    """Dedicated image-only sitemap."""
    if await _deindex_enabled():
        raise HTTPException(status_code=404, detail="Not found")
    frontend_base = _canonical_base_for_request(request)
    cursor = db.auctions.find(
        {
            "status": {"$in": ["live", "sold", "ended", "reserve_not_met"]},
            "is_archived": {"$ne": True},
        },
        {
            "_id": 0, "id": 1, "title": 1,
            "images": 1, "images_exterior": 1, "images_interior": 1,
            "images_wheels": 1, "images_bumper": 1,
        },
    ).sort("created_at", -1).limit(5000)
    auctions = await cursor.to_list(5000)

    xml = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"',
        '        xmlns:image="http://www.google.com/schemas/sitemap-image/1.1">',
    ]
    for a in auctions:
        clean = _collect_imgs(a, 50)
        if not clean:
            continue
        caption = _esc((a.get("title") or "").strip()[:160])
        parts = [f"<url><loc>{frontend_base}{_auction_slug_url(a)}</loc>"]
        for img in clean:
            parts.append(
                f"<image:image><image:loc>{_esc(img)}</image:loc>"
                + (f"<image:caption>{caption}</image:caption>" if caption else "")
                + f"<image:title>{caption}</image:title></image:image>"
            )
        parts.append("</url>")
        xml.append("".join(parts))
    xml.append("</urlset>")
    return Response(content="\n".join(xml), media_type="application/xml; charset=utf-8")


@router.get("/og/home.png")
@router.get("/og/home.jpg")
async def og_home_image():
    """Homepage OG share card (1200×630 JPEG).

    Redirects to the persisted, content-addressed file under
    `/api/uploads/og/home_{hash}.jpg`. The persisted file is served by
    Nginx directly as a static asset — much faster than re-rendering on
    every crawl, and the URL changes whenever the featured/active
    rotation changes so social platforms naturally refresh their cache
    (same pattern as per-auction `og_image_url` on detail pages).

    If persistence fails, we fall back to rendering inline so the
    preview is never broken.
    """
    try:
        persisted_url = await og_image.build_and_persist_home()
        if persisted_url and persisted_url.startswith("/"):
            # Relative path — issue a 302 so the social crawler follows
            # it and caches the persisted URL as the canonical og:image.
            return RedirectResponse(url=persisted_url, status_code=302)
        # Absolute URL (rare path: storage backend in S3/CDN mode)
        if persisted_url and persisted_url.startswith("http"):
            return RedirectResponse(url=persisted_url, status_code=302)
    except Exception as e:
        import logging
        logging.getLogger(__name__).warning("og:home persist failed, falling back to inline render: %s", e)

    # Fallback: render and serve inline so the preview is never broken.
    try:
        img = await og_image.build_home_card(force=False)
        return Response(
            content=img,
            media_type="image/jpeg",
            headers={
                "Cache-Control": "public, max-age=3600",
                "Content-Disposition": 'inline; filename="auto-and-bid-home.jpg"',
            },
        )
    except Exception as e:
        import logging
        logging.getLogger(__name__).warning("og:home inline render failed: %s", e)
        raise HTTPException(status_code=500, detail="OG home image render failed")



@router.get("/og/auction/{auction_id}.png")
@router.get("/og/auction/{auction_id}.jpg")
async def og_auction_image(auction_id: str, request: Request):
    """Per-auction OG share image (1200×630 JPEG).

    Returns the freshly-rendered social card directly. The image is
    content-addressed cached in `<UPLOAD_DIR>/og/{id}_{hash}.jpg` so
    subsequent crawls of the same auction hit a static file (Nginx
    serves it directly via the `/uploads/og/...` location). Crawlers
    that hit this endpoint instead of the static URL still get an
    immediate fresh render — we re-call `build_and_persist` to ensure
    the disk cache is warm for the next request.

    Accepts EITHER:
      • a full UUID (canonical internal identifier), or
      • a SEO slug ending in a `-XXXXXXXX` hex suffix (6-12 chars).
    The slug form lets the front-end inline script pass the user-
    visible `/auctions/bmw-m240i-...-ff615975` URL straight through
    without an extra resolution call.
    """
    # Resolve slug suffix → canonical UUID. Mirrors the lookup used by
    # /api/share/auction/{slug} so the same URL works for both meta and
    # image rendering.
    import re as _re
    _UUID = _re.compile(r"^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}$", _re.IGNORECASE)
    a = None
    if _UUID.match(auction_id):
        a = await db.auctions.find_one({"id": auction_id}, {"_id": 0})
    else:
        parts = auction_id.rsplit("-", 1)
        if len(parts) == 2 and _re.fullmatch(r"[a-f0-9]{6,12}", parts[1], _re.IGNORECASE):
            suffix = parts[1].lower()
            a = await db.auctions.find_one(
                {"id": {"$regex": f"^{_re.escape(suffix)}"}},
                {"_id": 0},
            )
    if not a:
        raise HTTPException(status_code=404, detail="Auction not found")
    # Same pattern as `/api/og/home.jpg` — return a 302 to the persisted,
    # content-addressed file so social crawlers cache the right URL. The
    # persisted file has a hash-suffix that automatically busts the cache
    # when the bid / title / cover changes.
    try:
        persisted_url = await og_image.build_and_persist(a)
        if persisted_url and persisted_url.startswith("/"):
            return RedirectResponse(url=persisted_url, status_code=302)
        if persisted_url and persisted_url.startswith("http"):
            return RedirectResponse(url=persisted_url, status_code=302)
    except Exception as e:
        import logging
        logging.getLogger(__name__).warning("og:auction persist failed, falling back: %s", e)
    try:
        png = await og_image.build_or_cache(a)
        return Response(
            content=png,
            media_type="image/jpeg",
            headers={
                "Cache-Control": "public, max-age=86400, immutable",
                "Content-Disposition": f'inline; filename="{auction_id}.jpg"',
            },
        )
    except Exception as e:
        # Graceful fallback: if rendering blows up, redirect to the
        # auction's headline photo so the share preview still resolves.
        import logging
        logging.getLogger(__name__).warning("og render failed for %s: %s", auction_id, e)
        headline = og_image.headline_image_url(a)
        if not headline:
            raise HTTPException(status_code=500, detail="OG image render failed")
        if not headline.startswith("http"):
            proto = request.headers.get("x-forwarded-proto", "https")
            host = request.headers.get("host") or request.url.hostname or ""
            if host:
                headline = f"{proto}://{host}{headline}"
        return RedirectResponse(url=headline, status_code=302)


@router.get("/share/auction/{auction_id}", response_class=PlainTextResponse)
async def share_auction(
    auction_id: str,
    request: Request,
    lang: Optional[str] = Query(None, regex="^(bg|en|ro)$"),
):
    """Locale-aware OG share HTML.

    Locale resolution (first match wins):
      1. `?lang=bg|en|ro` query param — used by the in-app share button
         to pin the preview to the current UI language.
      2. Host suffix: `.bg` → bg, `.ro` → ro, `.com` → en.
      3. `Accept-Language` header — first listed code.
      4. Default `bg`.

    Behaviour: emits the right `og:locale`, sets `<html lang>`, plus
    `<link rel="alternate" hreflang>` tuples to the same listing on the
    other two TLDs so Google treats them as proper geo-variants and not
    duplicate content.
    """
    # Resolve slug-suffix → canonical UUID when the caller passes a
    # SEO-friendly URL (e.g. nginx rewrites `/auctions/bmw-m240i-...-ff615975`
    # → `/api/share/auction/bmw-m240i-...-ff615975`). Without this step
    # `find_one({"id": slug})` finds nothing and we silently fall back to
    # the static `/og-default.jpg`, which is exactly what users hit when
    # the SPA's integrated Share button forwards a slug URL to WhatsApp.
    import re as _re
    _UUID = _re.compile(r"^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}$", _re.IGNORECASE)
    resolved_id = auction_id
    a = None
    if _UUID.match(auction_id):
        a = await db.auctions.find_one({"id": auction_id}, {"_id": 0})
    else:
        # Split once on the final dash to isolate the 6-12 hex suffix.
        parts = auction_id.rsplit("-", 1)
        if len(parts) == 2 and _re.fullmatch(r"[a-f0-9]{6,12}", parts[1], _re.IGNORECASE):
            suffix = parts[1].lower()
            a = await db.auctions.find_one(
                {"id": {"$regex": f"^{_re.escape(suffix)}"}},
                {"_id": 0},
            )
            if a:
                resolved_id = a["id"]
    # Build the public-facing origin from the `Host` header (what the
    # crawler actually typed), NOT `request.base_url` — the latter
    # returns the internal cluster host when we sit behind the ingress
    # and social crawlers would then be served a URL they can't resolve.
    origin_hdr = request.headers.get("origin")
    if origin_hdr:
        frontend_base = origin_hdr.rstrip("/")
        host_for_lang = re.sub(r"^https?://", "", frontend_base)
    else:
        proto = request.headers.get("x-forwarded-proto", "https")
        host_for_lang = request.headers.get("host") or request.url.hostname or "autoandbid.com"
        frontend_base = f"{proto}://{host_for_lang}"
    # ---- Locale resolution ------------------------------------------
    # Order: explicit `?lang=` > host TLD > Accept-Language header > bg.
    def _lang_from_host_local(h: str) -> Optional[str]:
        h = (h or "").lower()
        if h.endswith(".bg"):
            return "bg"
        if h.endswith(".ro"):
            return "ro"
        if h.endswith(".com") or h.endswith(".org") or h.endswith(".net"):
            return "en"
        return None

    def _lang_from_accept(header: str) -> Optional[str]:
        # Take the first language code from `Accept-Language: bg-BG;q=0.9, en;q=0.8`.
        first = (header or "").split(",")[0].strip().lower().split("-")[0]
        return first if first in ("bg", "en", "ro") else None

    resolved_lang = (
        lang
        or _lang_from_host_local(host_for_lang)
        or _lang_from_accept(request.headers.get("accept-language", ""))
        or "bg"
    )
    html_lang = resolved_lang
    og_locale = {"bg": "bg_BG", "en": "en_US", "ro": "ro_RO"}[resolved_lang]
    # Canonical target URL — ALWAYS pinned to the production TLD that
    # matches `resolved_lang` (autoandbid.bg / .ro / .com). This way
    # preview/staging hosts never leak into Google's index when crawlers
    # follow a share preview link.
    base_path = _auction_slug_url(a) if a else f"/auctions/{resolved_id}"
    canonical_base = _canonical_base_for_lang(resolved_lang)
    target = f"{canonical_base}{base_path}"
    # Cross-domain alternates for the same listing — Google, Bing and
    # Facebook all honour these as long as the URLs resolve.
    tld_map = {"bg": "autoandbid.bg", "en": "autoandbid.com", "ro": "autoandbid.ro"}
    alt_links: list[tuple[str, str]] = []
    for code, domain in tld_map.items():
        alt_links.append((code, f"https://{domain}{base_path}"))
    # `x-default` should point to the canonical (English) edition.
    alt_links.append(("x-default", f"https://{tld_map['en']}{base_path}"))

    if not a:
        title_fallback = {
            "bg": "autoandbid.bg — Търг", "en": "autoandbid.com — Auction", "ro": "autoandbid.ro — Licitație",
        }[resolved_lang]
        desc_fallback = {
            "bg": "Търгът не е намерен.", "en": "Auction not found.", "ro": "Licitația nu a fost găsită.",
        }[resolved_lang]
        title = title_fallback
        description = desc_fallback
        image = f"{canonical_base}/og-default.jpg"
        json_ld = ""
    else:
        # Title: locale-specific cache if present, otherwise raw `title`
        # (which is the seller-entered string — usually already a Latin
        # make/model line so it's safe across locales).
        title_localized = a.get(f"title_{resolved_lang}") or a.get("title") or ""
        brand = {"bg": "autoandbid.bg", "en": "autoandbid.com", "ro": "autoandbid.ro"}[resolved_lang]
        prefix = {"bg": "Търг", "en": "Auction", "ro": "Licitație"}[resolved_lang]
        title = f"{prefix} {title_localized} — {brand}"
        # Description: prefer the short SEO snippet (cached as
        # `seo_description_<lang>` at approve time, ≤280 chars).
        # Fallback chain: full localised description → full BG
        # description → empty.
        description = (
            a.get(f"seo_description_{resolved_lang}")
            or (a.get(f"description_{resolved_lang}") or "")[:280]
            or (a.get("description") or "")[:280]
        )
        # OG image priority chain:
        #   1. `og_image_url` — the pre-generated 1200×630 share PNG
        #      written at publish-time / bid-time by `build_and_persist`.
        #      This is the BRANDED card with title + current bid + logo.
        #   2. Auction's headline photo — unbranded but always exists.
        #   3. Static `/og-default.jpg` fallback.
        og_branded = a.get("og_image_url") or ""
        if og_branded:
            cover = og_branded
        else:
            cover = og_image.headline_image_url(a)
        if cover:
            image = cover if cover.startswith("http") else f"{canonical_base}{cover}"
        else:
            image = f"{canonical_base}/og-default.jpg"
        # Append a content-hash query string so Facebook + Viber cannot
        # reuse a stale cached preview when the auction's title / bid /
        # cover changes. The hash lives in the filename already, so this
        # extra `?v=` is belt-and-suspenders for platforms that compute
        # their cache key from the og:image URL string verbatim.
        if "?" not in image:
            cache_token = (a.get("og_image_updated_at") or a.get("last_bid_at") or a.get("updated_at") or "")
            if cache_token:
                # Use first 10 chars of ISO timestamp (sec resolution) as
                # the cache buster — short enough to keep the URL clean,
                # specific enough to change on every meaningful update.
                import hashlib as _hashlib
                token = _hashlib.sha1(str(cache_token).encode()).hexdigest()[:10]
                image = f"{image}?v={token}"
        json_ld = f'<script type="application/ld+json">{_json_ld_vehicle(a, target)}</script>'

    # Compose hreflang link tags.
    hreflang_html = "\n".join(
        f'<link rel="alternate" hreflang="{code}" href="{_esc(href)}">'
        for code, href in alt_links
    )

    # `og:updated_time` is the dominant signal that tells Facebook +
    # Viber + LinkedIn to refetch a previously-cached URL. We set it to
    # the auction's most recent mutation (last bid > publish time > now)
    # so any state change (new bid, title edit, cover swap, OG rebuild)
    # automatically invalidates their server-side cache without us
    # having to hit each platform's Sharing Debugger by hand.
    if a:
        updated_time = (
            a.get("og_image_updated_at")
            or a.get("last_bid_at")
            or a.get("published_at")
            or a.get("updated_at")
            or datetime.now(timezone.utc).isoformat()
        )
    else:
        updated_time = datetime.now(timezone.utc).isoformat()

    # Build og:url + canonical from the REQUEST host, not the hard-coded
    # production canonical. Reason: when Facebook scrapes a preview /
    # staging URL, our previous code returned production-host og:url —
    # so FB would follow the implied redirect to the production host
    # and re-scrape there, where (if the deployment hasn't landed yet)
    # it picked up the OLD homepage canonical from the static SPA HTML.
    # By mirroring the actual fetched host, FB sees one consistent URL
    # and never follows itself off our SSR endpoint.
    #
    # CRITICAL: when the auction lookup failed (a is None), we MUST
    # still point og:url + canonical at the AUCTION URL the crawler
    # fetched — not the homepage root. Returning canonical="/" causes
    # Facebook to treat every share as a homepage share and overwrite
    # the per-auction preview with the brand card.
    proto = request.headers.get("x-forwarded-proto", "https")
    host = request.headers.get("host") or request.url.hostname or ""
    if host:
        req_origin = f"{proto}://{host}"
        if a:
            # Reconstruct the SEO-friendly slug URL on the request host.
            target_path = _auction_slug_url(a)
        else:
            # Auction not found in DB — preserve the original requested
            # path so FB / Twitter still treat this as the canonical
            # URL for the auction, not the homepage.
            target_path = f"/auctions/{auction_id}"
        target = f"{req_origin}{target_path}"

    html = f"""<!DOCTYPE html>
<html lang="{html_lang}">
<head>
<meta charset="UTF-8">
<title>{_esc(title)}</title>
<meta name="description" content="{_esc(description)}">
<meta property="og:type" content="article">
<meta property="og:site_name" content="autoandbid">
<meta property="og:title" content="{_esc(title)}">
<meta property="og:description" content="{_esc(description)}">
<meta property="og:image" content="{_esc(image)}">
<meta property="og:image:secure_url" content="{_esc(image)}">
<meta property="og:image:type" content="image/jpeg">
<meta property="og:image:width" content="1200">
<meta property="og:image:height" content="630">
<meta property="og:image:alt" content="{_esc(title)}">
<meta property="og:url" content="{_esc(target)}">
<meta property="og:locale" content="{og_locale}">
<meta property="og:locale:alternate" content="bg_BG">
<meta property="og:locale:alternate" content="en_US">
<meta property="og:locale:alternate" content="ro_RO">
<meta property="og:updated_time" content="{_esc(updated_time)}">
<meta property="article:modified_time" content="{_esc(updated_time)}">
{_fb_app_id_tag()}
<meta name="twitter:card" content="summary_large_image">
<meta name="twitter:title" content="{_esc(title)}">
<meta name="twitter:description" content="{_esc(description)}">
<meta name="twitter:image" content="{_esc(image)}">
<link rel="canonical" href="{_esc(target)}">
{hreflang_html}
{json_ld}
</head>
<body>
<h1>{_esc(title)}</h1>
<p>{_esc(description)}</p>
<p><a href="{_esc(target)}">{_esc(target)}</a></p>
</body>
</html>"""
    # Cache-control: tell social-platform scrapers to revalidate on
    # every fetch (max-age=0) while still letting their edge accept a
    # cached copy for the brief moment between scrapes (s-maxage=60).
    # Without this, FB/Viber/LinkedIn happily reuse a stale copy for
    # weeks even after `og:updated_time` advances.
    return Response(
        content=html,
        media_type="text/html; charset=utf-8",
        headers={
            "Cache-Control": "public, max-age=0, must-revalidate, s-maxage=60",
            "X-Robots-Tag": "noindex",
        },
    )



# ============================================================================
# Listing-page SSR (for non-JS crawlers — Bing, Facebook, Twitter, Apple News)
# ============================================================================
# Google JS-renders these listings fine on its own, but Bing / Facebook /
# Twitter / smaller crawlers still need a static HTML snapshot. Nginx
# rewrites `/(auctions|sales|leaderboard)` → `/api/share/$1` when the
# UA matches `$is_social_bot`; the response is a fully populated meta
# page that immediately client-redirects browsers back to the SPA route.

# Static i18n payload — title, description, schema.org type per route.
# Keep it inline (no DB lookup) so the response is fast and crawlable
# even if Mongo is unreachable.
_LISTING_META = {
    "home": {
        "bg": ("Auto&Bid — Онлайн търгове за автомобили",
               "Подбрани автомобили. Прозрачно наддаване. Открийте подбрани автомобили с подробна документация, качествени снимки и ясни условия за участие в търга."),
        "en": ("Auto&Bid — Online car auctions",
               "Curated cars. Transparent bidding. Browse curated cars with detailed documentation, quality photos and clear auction terms."),
        "ro": ("Auto&Bid — Licitații online pentru mașini",
               "Mașini selectate. Licitare transparentă. Descoperă mașini selectate cu documentație detaliată, fotografii de calitate și condiții clare de licitare."),
    },
    "auctions": {
        "bg": ("Активни автомобилни търгове · Auto&Bid",
               "Разгледайте всички активни автомобилни търгове в България — филтрирайте по марка, година, гориво и цена. Уникални оферти всеки ден."),
        "en": ("Live car auctions · Auto&Bid",
               "Browse all active car auctions — filter by make, year, fuel and price. New cars added daily across Bulgaria, Romania and EU."),
        "ro": ("Licitații auto active · Auto&Bid",
               "Răsfoiește toate licitațiile auto active — filtrează după marcă, an, combustibil și preț. Mașini noi zilnic în România și UE."),
    },
    "sales": {
        "bg": ("Продадени автомобили · Auto&Bid",
               "Архив на скорошните продажби — реални финални цени, спецификации и снимки от приключилите търгове. Прозрачно ценообразуване."),
        "en": ("Sold cars archive · Auto&Bid",
               "Archive of recently sold vehicles — real final prices, specs and photos from closed auctions. Transparent pricing data."),
        "ro": ("Arhivă mașini vândute · Auto&Bid",
               "Arhivă cu mașini vândute recent — prețuri finale reale, specificații și fotografii de la licitații încheiate. Date transparente."),
    },
    "leaderboard": {
        "bg": ("Класация на участниците · Auto&Bid",
               "Топ купувачи и продавачи в Auto&Bid платформата — спечелени търгове, обем сделки, успеваемост. Социално доказателство в действие."),
        "en": ("Buyer & seller leaderboard · Auto&Bid",
               "Top performing buyers and sellers on Auto&Bid — won auctions, transaction volume and success rate. Social proof for serious traders."),
        "ro": ("Clasament cumpărători & vânzători · Auto&Bid",
               "Cei mai performanți cumpărători și vânzători de pe Auto&Bid — licitații câștigate, volum de tranzacții și rata de succes."),
    },
}


def _listing_lang_from_request(request: Request, override: Optional[str]) -> str:
    """Same locale resolution chain as the auction-share endpoint."""
    if override in ("bg", "en", "ro"):
        return override
    host = (request.headers.get("host") or "").lower()
    if host.endswith(".bg"):
        return "bg"
    if host.endswith(".ro"):
        return "ro"
    if host.endswith(".com") or host.endswith(".org") or host.endswith(".net"):
        return "en"
    first = (request.headers.get("accept-language") or "").split(",")[0].strip().lower().split("-")[0]
    if first in ("bg", "en", "ro"):
        return first
    return "bg"


async def _build_listing_ssr(
    request: Request,
    page_key: str,
    page_path: str,
    lang: Optional[str] = None,
    json_ld_extra: Optional[str] = None,
) -> Response:
    """Compose a fully-populated meta HTML for one of the listing pages.

    The body contains the title/description + a `meta refresh` to the
    real SPA URL so a curious human who actually loads it is redirected
    immediately. Crawlers only read `<head>` so they see the metadata.
    """
    resolved_lang = _listing_lang_from_request(request, lang)
    title, description = _LISTING_META[page_key][resolved_lang]
    og_locale = {"bg": "bg_BG", "en": "en_US", "ro": "ro_RO"}[resolved_lang]
    canonical_base = _canonical_base_for_lang(resolved_lang)
    target = f"{canonical_base}{page_path}"
    # OG image: for the home + auctions index we use the PERSISTED home
    # share card (same pattern as per-auction images on detail pages —
    # `og_image_url` points to `/api/uploads/og/{id}_{hash}.jpg`, a
    # content-addressed file served as a static asset by Nginx). The
    # hash changes whenever the featured/active rotation changes, so
    # social platforms detect new content and refresh their cache
    # automatically — exactly how it works for bidding updates on
    # auction detail pages. Listings pages without their own ItemList
    # fall back to the static `/og-default.jpg` as a last resort.
    image = None
    if page_key in {"home", "auctions"}:
        try:
            persisted_url = await og_image.build_and_persist_home()
            # `persisted_url` is a relative path (e.g. /api/uploads/og/home_xxx.jpg).
            # Convert to absolute so Facebook + LinkedIn + WhatsApp don't reject it.
            if persisted_url.startswith("http"):
                image = persisted_url
            elif persisted_url.startswith("/"):
                image = f"{canonical_base}{persisted_url}"
        except Exception as e:
            import logging
            logging.getLogger(__name__).warning("og:home persist failed during SSR: %s", e)
    if not image:
        image = f"{canonical_base}/og-default.jpg"
    tld_map = {"bg": "autoandbid.bg", "en": "autoandbid.com", "ro": "autoandbid.ro"}
    alt_links = [(code, f"https://{domain}{page_path}") for code, domain in tld_map.items()]
    alt_links.append(("x-default", f"https://{tld_map['en']}{page_path}"))
    hreflang_html = "\n".join(
        f'<link rel="alternate" hreflang="{code}" href="{_esc(href)}">'
        for code, href in alt_links
    )

    # Default JSON-LD: WebPage + BreadcrumbList; routes can append
    # ItemList via `json_ld_extra`.
    base_jsonld = {
        "@context": "https://schema.org",
        "@graph": [
            {
                "@type": "WebPage",
                "name": title,
                "description": description,
                "url": target,
                "inLanguage": resolved_lang,
            },
            {
                "@type": "BreadcrumbList",
                "itemListElement": [
                    {"@type": "ListItem", "position": 1, "name": "Auto&Bid", "item": canonical_base},
                    {"@type": "ListItem", "position": 2, "name": title, "item": target},
                ],
            },
        ],
    }
    json_ld_html = f'<script type="application/ld+json">{json.dumps(base_jsonld, ensure_ascii=False)}</script>'
    if json_ld_extra:
        json_ld_html += f'\n<script type="application/ld+json">{json_ld_extra}</script>'

    # Cache-busting og:updated_time for FB/Viber/LinkedIn — bumped to
    # the current minute so any rescrape after a cached preview sees a
    # fresher signal and refetches. Homepage and listing pages don't
    # have a stable per-auction mutation timestamp, so we tick this
    # every minute (FB rescrapes at most every 30 minutes anyway).
    listing_updated = datetime.now(timezone.utc).replace(second=0, microsecond=0).isoformat()

    # Mirror the request host (same reasoning as the per-auction SSR —
    # see comment there). When Facebook scrapes a preview / staging
    # host, og:url + canonical must point at the SAME host so FB's
    # canonical-follower never lands on a stale production deployment.
    proto = request.headers.get("x-forwarded-proto", "https")
    host = request.headers.get("host") or request.url.hostname or ""
    if host:
        target = f"{proto}://{host}{page_path}"

    html = f"""<!DOCTYPE html>
<html lang="{resolved_lang}">
<head>
<meta charset="UTF-8">
<title>{_esc(title)}</title>
<meta name="description" content="{_esc(description)}">
<meta property="og:type" content="website">
<meta property="og:site_name" content="autoandbid">
<meta property="og:title" content="{_esc(title)}">
<meta property="og:description" content="{_esc(description)}">
<meta property="og:image" content="{_esc(image)}">
<meta property="og:image:secure_url" content="{_esc(image)}">
<meta property="og:image:type" content="image/jpeg">
<meta property="og:image:width" content="1200">
<meta property="og:image:height" content="630">
<meta property="og:image:alt" content="{_esc(title)}">
<meta property="og:url" content="{_esc(target)}">
<meta property="og:locale" content="{og_locale}">
<meta property="og:locale:alternate" content="bg_BG">
<meta property="og:locale:alternate" content="en_US">
<meta property="og:locale:alternate" content="ro_RO">
<meta property="og:updated_time" content="{_esc(listing_updated)}">
{_fb_app_id_tag()}
<meta name="twitter:card" content="summary_large_image">
<meta name="twitter:title" content="{_esc(title)}">
<meta name="twitter:description" content="{_esc(description)}">
<meta name="twitter:image" content="{_esc(image)}">
<link rel="canonical" href="{_esc(target)}">
{hreflang_html}
{json_ld_html}
</head>
<body>
<h1>{_esc(title)}</h1>
<p>{_esc(description)}</p>
<p><a href="{_esc(target)}">{_esc(target)}</a></p>
</body>
</html>"""
    return Response(
        content=html,
        media_type="text/html; charset=utf-8",
        headers={
            "Cache-Control": "public, max-age=0, must-revalidate, s-maxage=60",
            "X-Robots-Tag": "noindex",
        },
    )


@router.get("/share/home", response_class=PlainTextResponse)
@router.get("/share/", response_class=PlainTextResponse)
async def share_home(request: Request, lang: Optional[str] = Query(None, regex="^(bg|en|ro)$")):
    """SSR snapshot of the homepage.

    Hit by social-bot middleware when a crawler scrapes the bare apex
    domain (`https://autoandbid.bg/`). Returns the full OG meta block
    with absolute URLs (relative `/api/og/home.jpg` is rejected by
    Facebook + most messenger previewers), plus an Organization +
    WebSite JSON-LD graph and the dynamic 4-car brand card as
    `og:image`.
    """
    return await _build_listing_ssr(request, "home", "/", lang=lang)


@router.get("/share/auctions", response_class=PlainTextResponse)
async def share_auctions_listing(request: Request, lang: Optional[str] = Query(None, regex="^(bg|en|ro)$")):
    """SSR snapshot of the live-auctions listing.

    Adds an ItemList JSON-LD with the top 12 live auctions so Google /
    Bing can build a rich preview ("X car auctions, starting from …").
    Crawlers without JS rendering still get all the listing data they
    need to decide if the page is worth indexing.
    """
    cursor = db.auctions.find(
        {"status": "live", "is_archived": {"$ne": True}},
        {
            "_id": 0, "id": 1, "title": 1, "current_bid_eur": 1,
            "starting_bid_eur": 1, "year": 1, "make": 1, "model": 1,
        },
    ).sort("ends_at", 1).limit(12)
    auctions = await cursor.to_list(12)
    resolved_lang = _listing_lang_from_request(request, lang)
    canonical_base = _canonical_base_for_lang(resolved_lang)
    item_list = {
        "@context": "https://schema.org",
        "@type": "ItemList",
        "numberOfItems": len(auctions),
        "itemListElement": [
            {
                "@type": "ListItem",
                "position": i + 1,
                "url": f"{canonical_base}{_auction_slug_url(a)}",
                "name": a.get("title") or f"{a.get('make','')} {a.get('model','')}".strip(),
            }
            for i, a in enumerate(auctions)
        ],
    }
    return await _build_listing_ssr(
        request, "auctions", "/auctions", lang=lang,
        json_ld_extra=json.dumps(item_list, ensure_ascii=False),
    )


@router.get("/share/sales", response_class=PlainTextResponse)
async def share_sales_listing(request: Request, lang: Optional[str] = Query(None, regex="^(bg|en|ro)$")):
    """SSR snapshot of the sold-cars archive.

    Same treatment as `/share/auctions` — emits an ItemList with the 12
    most-recently-sold listings so crawlers building rich previews see
    real prices/titles instead of just the page chrome.
    """
    cursor = db.auctions.find(
        {"status": "sold"},
        {
            "_id": 0, "id": 1, "title": 1, "current_bid_eur": 1,
            "starting_bid_eur": 1, "year": 1, "make": 1, "model": 1,
        },
    ).sort("finalized_at", -1).limit(12)
    auctions = await cursor.to_list(12)
    resolved_lang = _listing_lang_from_request(request, lang)
    canonical_base = _canonical_base_for_lang(resolved_lang)
    item_list = {
        "@context": "https://schema.org",
        "@type": "ItemList",
        "numberOfItems": len(auctions),
        "itemListElement": [
            {
                "@type": "ListItem",
                "position": i + 1,
                "url": f"{canonical_base}{_auction_slug_url(a)}",
                "name": a.get("title") or f"{a.get('make','')} {a.get('model','')}".strip(),
            }
            for i, a in enumerate(auctions)
        ],
    }
    return await _build_listing_ssr(
        request, "sales", "/sales", lang=lang,
        json_ld_extra=json.dumps(item_list, ensure_ascii=False) if auctions else None,
    )


@router.get("/share/leaderboard", response_class=PlainTextResponse)
async def share_leaderboard(request: Request, lang: Optional[str] = Query(None, regex="^(bg|en|ro)$")):
    """SSR snapshot of the buyer/seller leaderboard."""
    return await _build_listing_ssr(request, "leaderboard", "/leaderboard", lang=lang)
