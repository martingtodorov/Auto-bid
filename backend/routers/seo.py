"""
SEO / social sharing routes — XML sitemaps + OG-rich share pages for crawlers.
Extracted from server.py to keep auction/bidding logic focused.
"""
import os
import re
import json as _json
from html import escape as _esc

from fastapi import APIRouter, HTTPException, Request, Response
from fastapi.responses import PlainTextResponse

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
    frontend_base = _frontend_base(request)
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
    }
    if a.get("ends_at"):
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
        "bodyType": a.get("body_type"),
        "fuelType": a.get("fuel"),
        "vehicleTransmission": a.get("transmission"),
        "color": a.get("color"),
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


def _collect_imgs(a: dict, max_count: int) -> list:
    imgs_all = (
        (a.get("images_exterior") or [])
        + (a.get("images_interior") or [])
        + (a.get("images_wheels") or [])
        + (a.get("images_bumper") or [])
        + (a.get("images") or [])
    )
    seen = set()
    clean = []
    for img in imgs_all:
        if not img or not isinstance(img, str) or img.startswith("data:") or img in seen:
            continue
        seen.add(img)
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
    frontend_base = _frontend_base(request)
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
        '        xmlns:image="http://www.google.com/schemas/sitemap-image/1.1">',
    ]
    for path, freq, pr in pages:
        xml_parts.append(
            f"<url><loc>{frontend_base}{path}</loc><changefreq>{freq}</changefreq><priority>{pr}</priority></url>"
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
        xml_parts.append(
            f"<url><loc>{frontend_base}{_auction_slug_url(a)}</loc>"
            + lastmod
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
    frontend_base = _frontend_base(request)
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


@router.get("/og/auction/{auction_id}.png")
async def og_auction_image(auction_id: str):
    """Dynamic Open Graph PNG for a single auction. English text only.

    URL is shaped as `.png` so social crawlers don't second-guess the
    Content-Type (some cache the URL extension). Cached in memory +
    on-disk by (id, current_bid, ends_at_minute) so every new bid
    produces a fresh image the next time the share link is scraped.
    """
    a = await db.auctions.find_one({"id": auction_id}, {"_id": 0})
    if not a:
        raise HTTPException(status_code=404, detail="Auction not found")
    png = await og_image.build_or_cache(a)
    # Long edge cache is safe — the cache key already embeds the bid +
    # ends_at minute, so new versions get a new URL-less file behind
    # the scenes but the public URL stays the same. We give Cloudflare
    # 5 min to absorb traffic spikes during viral shares, then
    # revalidate.
    return Response(
        content=png,
        media_type="image/png",
        headers={"Cache-Control": "public, max-age=60, s-maxage=300, stale-while-revalidate=600"},
    )


@router.get("/share/auction/{auction_id}", response_class=PlainTextResponse)
async def share_auction(auction_id: str, request: Request):
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
    else:
        proto = request.headers.get("x-forwarded-proto", "https")
        host = request.headers.get("host") or request.url.hostname or "autoandbid.com"
        frontend_base = f"{proto}://{host}"
    # Redirect crawlers to the SEO-friendly slug URL.
    target = f"{frontend_base}{_auction_slug_url(a) if a else f'/auctions/{resolved_id}'}"

    if not a:
        title = "autoandbid.com — Търг"
        description = "Търгът не е намерен."
        image = f"{frontend_base}/og-default.jpg"
        json_ld = ""
    else:
        title = f"{a.get('title','')} — autoandbid.com"
        description = (a.get("description") or "")[:280]
        # Prefer the eagerly-generated OG image stored on the auction doc
        # (populated at publish time — see `admin_approve` in server.py).
        # This guarantees Facebook / WhatsApp / Telegram see the custom
        # car-card image on the *first* share, not after 3-4 attempts
        # while the lazy generator warmed up. Fall back to the live
        # generator endpoint only if the stored URL is missing.
        stored_og = a.get("og_image_url")
        if stored_og:
            # Stored URL may be absolute (S3) or relative (/api/uploads/...).
            image = stored_og if stored_og.startswith("http") else f"{frontend_base}{stored_og}"
        else:
            image = f"{frontend_base}/api/og/auction/{resolved_id}.png"
        json_ld = f'<script type="application/ld+json">{_json_ld_vehicle(a, target)}</script>'

    html = f"""<!DOCTYPE html>
<html lang="bg">
<head>
<meta charset="UTF-8">
<title>{_esc(title)}</title>
<meta name="description" content="{_esc(description)}">
<meta property="og:type" content="article">
<meta property="og:site_name" content="autoandbid.com">
<meta property="og:title" content="{_esc(title)}">
<meta property="og:description" content="{_esc(description)}">
<meta property="og:image" content="{_esc(image)}">
<meta property="og:image:width" content="1200">
<meta property="og:image:height" content="630">
<meta property="og:image:type" content="image/png">
<meta property="og:url" content="{_esc(target)}">
<meta property="og:locale" content="bg_BG">
<meta name="twitter:card" content="summary_large_image">
<meta name="twitter:title" content="{_esc(title)}">
<meta name="twitter:description" content="{_esc(description)}">
<meta name="twitter:image" content="{_esc(image)}">
<link rel="canonical" href="{_esc(target)}">
{json_ld}
<meta http-equiv="refresh" content="0; url={_esc(target)}">
</head>
<body>
<script>window.location.replace({repr(target)});</script>
<p>Пренасочване към <a href="{_esc(target)}">{_esc(target)}</a>…</p>
</body>
</html>"""
    return Response(content=html, media_type="text/html; charset=utf-8")
