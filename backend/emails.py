"""Resend-based email helper with graceful fallback when API key is missing.

All transactional helpers (`email_outbid`, `email_won`, ...) render their
subject + body from the admin-editable `site_settings.email_templates`
collection via `email_templates.render()`. The factory defaults live in
`email_templates.SYSTEM_TEMPLATES`. Adding a new system email = adding
an entry to that registry; no migration needed.
"""
import os
import asyncio
import logging
import resend

from email_templates import render as render_template
from email_templates import localized_render as render_localized

logger = logging.getLogger(__name__)

RESEND_API_KEY = os.environ.get("RESEND_API_KEY", "").strip()
SENDER_EMAIL = os.environ.get("SENDER_EMAIL", "autoandbid.com <onboarding@resend.dev>")
APP_URL = os.environ.get("APP_URL", "https://auction-drive-bg.preview.emergentagent.com")

if RESEND_API_KEY:
    resend.api_key = RESEND_API_KEY


async def send_email(to: str, subject: str, html: str) -> bool:
    """Send an email via Resend. Logs to notification_log. Returns True on success."""
    from datetime import datetime, timezone
    import uuid as _uuid
    try:
        from deps import db
    except Exception:
        db = None
    ok = False
    error = None
    if not RESEND_API_KEY:
        logger.info("[EMAIL:mock] to=%s subject=%s", to, subject)
    else:
        try:
            params = {"from": SENDER_EMAIL, "to": [to], "subject": subject, "html": html}
            result = await asyncio.to_thread(resend.Emails.send, params)
            logger.info("[EMAIL:sent] id=%s to=%s", result.get("id"), to)
            ok = True
        except Exception as e:
            logger.error("[EMAIL:error] %s", e)
            error = str(e)[:300]
    # Notification log (non-blocking)
    if db is not None:
        try:
            await db.notification_log.insert_one({
                "id": str(_uuid.uuid4()),
                "channel": "email",
                "to": to,
                "subject": subject,
                "status": "sent" if ok else ("mock" if not RESEND_API_KEY else "error"),
                "error": error,
                "at": datetime.now(timezone.utc).isoformat(),
            })
        except Exception as e:
            logger.error("[notification_log insert failed] %s", e)
    return ok


def _shell(title: str, body_html: str) -> str:
    """Pass-through wrapper with a minimal CSS reset.

    Per user request (2026-05-16) no chrome is added — no logo header,
    no footer, no font-family override. The single style block zeroes
    out the default browser margin on `<p>` so paragraph-to-paragraph
    spacing looks like Gmail compose (which wraps lines in `<div>`
    instead of `<p>`). Without this reset, every `<p>` rendered ~16px
    top + 16px bottom margin = visible empty line between paragraphs.
    """
    return (
        "<!doctype html><html><head>"
        "<style>p{margin:0;padding:0}p+p{margin-top:4px}</style>"
        "</head><body>" + body_html + "</body></html>"
    )


async def email_outbid(to: str, name: str, auction_title: str, auction_id: str, new_bid: float, lang: str = "bg"):
    subject, header, body = render_localized("outbid", lang, {
        "name": name, "auction_title": auction_title, "auction_id": auction_id,
        "new_bid": f"{int(new_bid):,}", "app_url": APP_URL,
    })
    await send_email(to, subject, _shell(header, body))


async def email_won(to: str, name: str, auction_title: str, auction_id: str, price: float, lang: str = "bg"):
    subject, header, body = render_localized("won", lang, {
        "name": name, "auction_title": auction_title, "auction_id": auction_id,
        "price": f"{int(price):,}", "app_url": APP_URL,
    })
    await send_email(to, subject, _shell(header, body))


async def email_approved(to: str, name: str, auction_title: str, auction_id: str, lang: str = "bg"):
    subject, header, body = render_localized("approved", lang, {
        "name": name, "auction_title": auction_title, "auction_id": auction_id,
        "app_url": APP_URL,
    })
    await send_email(to, subject, _shell(header, body))


async def email_rejected(to: str, name: str, auction_title: str, reason: str, lang: str = "bg"):
    subject, header, body = render_localized("rejected", lang, {
        "name": name, "auction_title": auction_title, "reason": reason or "—",
    })
    await send_email(to, subject, _shell(header, body))


async def email_vin_delivery(to: str, name: str, auction_title: str, auction_id: str, vin: str, lang: str = "bg"):
    subject, header, body = render_localized("vin_delivery", lang, {
        "name": name, "auction_title": auction_title, "auction_id": auction_id,
        "vin": vin, "app_url": APP_URL,
    })
    await send_email(to, subject, _shell(header, body))


async def email_seller_new_bid(to: str, name: str, auction_title: str, auction_id: str, bidder_name: str, amount: float, bid_count: int, lang: str = "bg"):
    subject, header, body = render_localized("seller_new_bid", lang, {
        "name": name, "auction_title": auction_title, "auction_id": auction_id,
        "bidder_name": bidder_name, "amount": f"{int(amount):,}",
        "bid_count": bid_count, "app_url": APP_URL,
    })
    await send_email(to, subject, _shell(header, body))


async def email_seller_new_comment(to: str, name: str, auction_title: str, auction_id: str, commenter_name: str, snippet: str, lang: str = "bg"):
    subject, header, body = render_localized("seller_new_comment", lang, {
        "name": name, "auction_title": auction_title, "auction_id": auction_id,
        "commenter_name": commenter_name, "snippet": snippet, "app_url": APP_URL,
    })
    await send_email(to, subject, _shell(header, body))


async def email_ending_soon(to: str, name: str, auction_title: str, auction_id: str, current_bid: float, role: str = "watcher", lang: str = "bg"):
    """role: 'watcher' (favourited) or 'bidder' (currently leading or active in bidding)."""
    base = "ending_soon_bidder" if role == "bidder" else "ending_soon_watcher"
    subject, header, body = render_localized(base, lang, {
        "name": name, "auction_title": auction_title, "auction_id": auction_id,
        "current_bid": f"{int(current_bid):,}", "app_url": APP_URL,
    })
    await send_email(to, subject, _shell(header, body))


async def email_reserve_met(to: str, name: str, auction_title: str, auction_id: str, current_bid: float, reserve: float, lang: str = "bg"):
    subject, header, body = render_localized("reserve_met", lang, {
        "name": name, "auction_title": auction_title, "auction_id": auction_id,
        "current_bid": f"{int(current_bid):,}", "reserve": f"{int(reserve):,}",
        "app_url": APP_URL,
    })
    await send_email(to, subject, _shell(header, body))
