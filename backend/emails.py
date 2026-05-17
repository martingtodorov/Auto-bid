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
    """Branded transactional email envelope (auto&bid design system).

    Per user reference (2026-05-17 screenshots): no top logo bar, content
    starts directly with the template's own eyebrow + H1. We provide a
    centered card on a subtle grey background with rounded corners + a
    minimal centered disclaimer at the bottom. Everything else (headings,
    cards, CTA buttons) lives inside the template body.
    """
    return (
        "<!doctype html>"
        '<html><head><meta charset="utf-8">'
        "<style>"
        "body{margin:0;padding:0;background:#f6f7f8;"
        "font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Manrope,Inter,Roboto,sans-serif;"
        "color:#111827;-webkit-font-smoothing:antialiased;}"
        "p{margin:0 0 14px 0;line-height:1.55;font-size:15px;}"
        "p:last-child{margin-bottom:0;}"
        ".wrap{max-width:560px;margin:32px auto;background:#ffffff;"
        "border-radius:18px;padding:40px 36px;}"
        ".eyebrow{font-size:11px;letter-spacing:0.14em;text-transform:uppercase;"
        "color:#6b7280;margin:0 0 10px 0;font-weight:600;}"
        ".h1{font-size:30px;line-height:1.2;font-weight:700;letter-spacing:-0.02em;"
        "margin:0 0 24px 0;color:#0b0f1a;}"
        ".card{border:1px solid #e5e7eb;border-radius:14px;padding:18px 20px;"
        "margin:22px 0;}"
        ".card .eyebrow{margin:0 0 6px 0;}"
        ".card-title{font-size:16px;font-weight:700;color:#0b0f1a;margin:0;}"
        ".cta{display:inline-block;background:#1B4D3E;color:#ffffff!important;"
        "padding:13px 26px;border-radius:999px;text-decoration:none;font-weight:600;"
        "font-size:15px;}"
        ".disclaimer{max-width:560px;margin:14px auto 32px auto;text-align:center;"
        "color:#9ca3af;font-size:12px;padding:0 16px;}"
        "code.mono{font-family:ui-monospace,'IBM Plex Mono',monospace;"
        "letter-spacing:4px;font-size:22px;font-weight:600;}"
        "</style></head>"
        '<body><div class="wrap">'
        + body_html +
        "</div>"
        '<div class="disclaimer">Това е автоматично съобщение, свързано с акаунта ви в autoandbid.com.</div>'
        "</body></html>"
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
