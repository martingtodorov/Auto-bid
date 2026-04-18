"""
SEO / social sharing routes — XML sitemaps + OG-rich share pages for crawlers.
Extracted from server.py to keep auction/bidding logic focused.
"""
import os
import json as _json
from html import escape as _esc

from fastapi import APIRouter, Request, Response
from fastapi.responses import PlainTextResponse

from deps import db

router = APIRouter()


def _json_ld_vehicle(a: dict, url: str) -> str:
    """Build schema.org Vehicle structured data for a listing."""
    offers = {
        "@type": "Offer",
        "priceCurrency": "EUR",
        "price": float(a.get("current_bid_eur", 0)),
        "url": url,
        "availability": "https://schema.org/InStock" if a.get("status") == "live" else "https://schema.org/SoldOut",
    }
    data = {
        "@context": "https://schema.org",
        "@type": "Vehicle",
        "name": a.get("title", ""),
        "brand": {"@type": "Brand", "name": a.get("make", "")},
        "model": a.get("model", ""),
        "modelDate": a.get("year"),
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
        "image": (a.get("images") or [None])[0],
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
        {"status": {"$in": ["live", "sold", "ended", "reserve_not_met"]}},
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
            f"<url><loc>{frontend_base}/auctions/{a['id']}</loc>"
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
    frontend_base = _frontend_base(request)
    cursor = db.auctions.find(
        {"status": {"$in": ["live", "sold", "ended", "reserve_not_met"]}},
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
        parts = [f"<url><loc>{frontend_base}/auctions/{a['id']}</loc>"]
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


@router.get("/share/auction/{auction_id}", response_class=PlainTextResponse)
async def share_auction(auction_id: str, request: Request):
    a = await db.auctions.find_one({"id": auction_id}, {"_id": 0})
    frontend_base = request.headers.get("origin") or str(request.base_url).rstrip("/")
    target = f"{frontend_base}/auctions/{auction_id}"

    if not a:
        title = "AutoBid.bg — Търг"
        description = "Търгът не е намерен."
        image = f"{frontend_base}/og-default.jpg"
        json_ld = ""
    else:
        title = f"{a.get('title','')} — AutoBid.bg"
        description = (a.get("description") or "")[:280]
        image = (a.get("images") or [None])[0] or f"{frontend_base}/og-default.jpg"
        json_ld = f'<script type="application/ld+json">{_json_ld_vehicle(a, target)}</script>'

    html = f"""<!DOCTYPE html>
<html lang="bg">
<head>
<meta charset="UTF-8">
<title>{_esc(title)}</title>
<meta name="description" content="{_esc(description)}">
<meta property="og:type" content="article">
<meta property="og:site_name" content="AutoBid.bg">
<meta property="og:title" content="{_esc(title)}">
<meta property="og:description" content="{_esc(description)}">
<meta property="og:image" content="{_esc(image)}">
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
