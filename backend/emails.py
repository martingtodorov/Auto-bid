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
    """Wrap an inner HTML body in the brand chrome (header + footer).

    The `title` parameter is kept for backwards-compatibility with the
    template renderer (`render_localized` returns subject/header/body)
    but is INTENTIONALLY no longer rendered as an `<h1>` inside the
    email — per user request the brand label "Auto&Bid" is the only
    title shown, in the brand green (`#1B4D3E`) without any underline /
    hyperlink styling. Individual templates can include their own
    heading inside `body_html` if needed.
    """
    return f"""
<!doctype html>
<html><body style="margin:0;background:#f6f7f8;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Manrope,Roboto,sans-serif;color:#111827;">
<table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="background:#f6f7f8;padding:32px 0;">
  <tr><td align="center">
    <table role="presentation" width="560" cellspacing="0" cellpadding="0" style="background:#ffffff;">
      <tr><td style="padding:28px 32px 12px 32px;text-align:left;">
        <span style="font-weight:800;font-size:22px;letter-spacing:-0.02em;color:#1B4D3E;text-decoration:none;">Auto&amp;Bid</span>
      </td></tr>
      <tr><td style="padding:8px 32px 32px 32px;">
        {body_html}
      </td></tr>
      <tr><td style="padding:20px 32px;background:#fafafa;color:#6b7280;font-size:12px;">
        autoandbid.com · Редакционна платформа за автомобилни търгове · София
      </td></tr>
    </table>
  </td></tr>
</table></body></html>
"""


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
