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


def _shell(title: str, body_html: str, to: str = "", lang: str = "bg") -> str:
    """Branded transactional email envelope (auto&bid design system).

    Layout:
      - Top brand bar: "Auto&Bid" with the ampersand rendered in the brand green.
      - White card with template content (eyebrow + H1 inside body_html).
      - Footer disclaimer + Unsubscribe link (per recipient).
    """
    # Localized labels (footer + unsubscribe)
    lang_norm = (lang or "bg").lower()[:2]
    if lang_norm == "en":
        footer_note = "This is an automated message related to your account on autoandbid.com."
        unsub_label = "Unsubscribe"
        prefs_label = "Notification preferences"
    elif lang_norm == "ro":
        footer_note = "Acesta este un mesaj automat legat de contul tău pe autoandbid.com."
        unsub_label = "Dezabonare"
        prefs_label = "Preferințe notificări"
    else:
        footer_note = "Това е автоматично съобщение, свързано с акаунта ви в autoandbid.com."
        unsub_label = "Отпиши се"
        prefs_label = "Настройки за известия"
    # Per-recipient unsubscribe link (token-less: backend validates by email
    # against the recipient's account). The /unsubscribe route disables all
    # marketing/notification emails for that address and returns a confirmation
    # page. We URL-encode the email defensively.
    try:
        from urllib.parse import quote as _quote
        to_q = _quote((to or "").strip(), safe="@.")
    except Exception:
        to_q = ""
    unsub_url = f"{APP_URL}/api/unsubscribe?email={to_q}" if to_q else f"{APP_URL}/account/notifications"
    prefs_url = f"{APP_URL}/account/notifications"
    return (
        "<!doctype html>"
        '<html><head><meta charset="utf-8">'
        "<style>"
        "body{margin:0;padding:0;background:#f6f7f8;"
        "font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Manrope,Inter,Roboto,sans-serif;"
        "color:#111827;-webkit-font-smoothing:antialiased;}"
        "p{margin:0 0 14px 0;line-height:1.55;font-size:15px;}"
        "p:last-child{margin-bottom:0;}"
        ".brandbar{max-width:560px;margin:32px auto 0 auto;padding:0 36px;text-align:center;}"
        ".brand{display:inline-block;font-size:22px;font-weight:700;letter-spacing:-0.01em;"
        "color:#0b0f1a;text-decoration:none;}"
        ".brand .amp{color:#1B4D3E;font-weight:800;}"
        ".wrap{max-width:560px;margin:18px auto 0 auto;background:#ffffff;"
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
        ".disclaimer{max-width:560px;margin:14px auto 8px auto;text-align:center;"
        "color:#9ca3af;font-size:12px;padding:0 16px;line-height:1.5;}"
        ".unsub{max-width:560px;margin:0 auto 32px auto;text-align:center;"
        "color:#9ca3af;font-size:12px;padding:0 16px;}"
        ".unsub a{color:#6b7280;text-decoration:underline;}"
        "code.mono{font-family:ui-monospace,'IBM Plex Mono',monospace;"
        "letter-spacing:4px;font-size:22px;font-weight:600;}"
        "</style></head>"
        '<body><div class="brandbar"><span class="brand">Auto<span class="amp">&amp;</span>Bid</span></div>'
        '<div class="wrap">'
        + body_html +
        "</div>"
        f'<div class="disclaimer">{footer_note}</div>'
        f'<div class="unsub"><a href="{unsub_url}">{unsub_label}</a>'
        f' &nbsp;·&nbsp; <a href="{prefs_url}">{prefs_label}</a></div>'
        "</body></html>"
    )


async def email_outbid(to: str, name: str, auction_title: str, auction_id: str, new_bid: float, lang: str = "bg"):
    subject, header, body = render_localized("outbid", lang, {
        "name": name, "auction_title": auction_title, "auction_id": auction_id,
        "new_bid": f"{int(new_bid):,}", "app_url": APP_URL,
    })
    await send_email(to, subject, _shell(header, body, to=to, lang=lang))


async def email_won(to: str, name: str, auction_title: str, auction_id: str, price: float, lang: str = "bg",
                    seller_name: str = "", seller_email: str = "", seller_phone: str = ""):
    """Buyer wins — uses the rich `auction_won_buyer` template that includes
    seller contact details + the insurance/notary helper note.
    """
    vars_ = {
        "name": name, "auction_title": auction_title, "auction_id": auction_id,
        "price": f"{int(price):,}", "app_url": APP_URL,
        "seller_name": seller_name or "—",
        "seller_email": seller_email or "—",
        "seller_phone": seller_phone or "—",
    }
    subject, header, body = render_localized("auction_won_buyer", lang, vars_)
    await send_email(to, subject, _shell(header, body, to=to, lang=lang))


async def email_auction_won_seller(to: str, name: str, auction_title: str, auction_id: str, price: float,
                                    buyer_name: str, buyer_email: str, buyer_phone: str, lang: str = "bg"):
    """Seller notification: their car was won. Includes buyer contact details."""
    subject, header, body = render_localized("auction_won_seller", lang, {
        "name": name, "auction_title": auction_title, "auction_id": auction_id,
        "price": f"{int(price):,}", "app_url": APP_URL,
        "buyer_name": buyer_name or "—",
        "buyer_email": buyer_email or "—",
        "buyer_phone": buyer_phone or "—",
    })
    await send_email(to, subject, _shell(header, body, to=to, lang=lang))


async def email_digest_3day(to: str, name: str, new_html: str, ending_html: str, lang: str = "bg"):
    """3-day digest of new listings + auctions ending soon. The two HTML chunks
    are pre-rendered lists from the digest worker (one row per auction).
    """
    subject, header, body = render_localized("digest_3day", lang, {
        "name": name, "new_html": new_html, "ending_html": ending_html,
        "app_url": APP_URL,
    })
    await send_email(to, subject, _shell(header, body, to=to, lang=lang))


async def email_approved(to: str, name: str, auction_title: str, auction_id: str, lang: str = "bg"):
    subject, header, body = render_localized("approved", lang, {
        "name": name, "auction_title": auction_title, "auction_id": auction_id,
        "app_url": APP_URL,
    })
    await send_email(to, subject, _shell(header, body, to=to, lang=lang))


async def email_rejected(to: str, name: str, auction_title: str, reason: str, lang: str = "bg"):
    subject, header, body = render_localized("rejected", lang, {
        "name": name, "auction_title": auction_title, "reason": reason or "—",
    })
    await send_email(to, subject, _shell(header, body, to=to, lang=lang))


async def email_vin_delivery(to: str, name: str, auction_title: str, auction_id: str, vin: str, lang: str = "bg"):
    subject, header, body = render_localized("vin_delivery", lang, {
        "name": name, "auction_title": auction_title, "auction_id": auction_id,
        "vin": vin, "app_url": APP_URL,
    })
    await send_email(to, subject, _shell(header, body, to=to, lang=lang))


async def email_seller_new_bid(to: str, name: str, auction_title: str, auction_id: str, bidder_name: str, amount: float, bid_count: int, lang: str = "bg"):
    subject, header, body = render_localized("seller_new_bid", lang, {
        "name": name, "auction_title": auction_title, "auction_id": auction_id,
        "bidder_name": bidder_name, "amount": f"{int(amount):,}",
        "bid_count": bid_count, "app_url": APP_URL,
    })
    await send_email(to, subject, _shell(header, body, to=to, lang=lang))


async def email_seller_new_comment(to: str, name: str, auction_title: str, auction_id: str, commenter_name: str, snippet: str, lang: str = "bg"):
    subject, header, body = render_localized("seller_new_comment", lang, {
        "name": name, "auction_title": auction_title, "auction_id": auction_id,
        "commenter_name": commenter_name, "snippet": snippet, "app_url": APP_URL,
    })
    await send_email(to, subject, _shell(header, body, to=to, lang=lang))


async def email_ending_soon(to: str, name: str, auction_title: str, auction_id: str, current_bid: float, role: str = "watcher", lang: str = "bg"):
    """role: 'watcher' (favourited) or 'bidder' (currently leading or active in bidding)."""
    base = "ending_soon_bidder" if role == "bidder" else "ending_soon_watcher"
    subject, header, body = render_localized(base, lang, {
        "name": name, "auction_title": auction_title, "auction_id": auction_id,
        "current_bid": f"{int(current_bid):,}", "app_url": APP_URL,
    })
    await send_email(to, subject, _shell(header, body, to=to, lang=lang))


async def email_reserve_met(to: str, name: str, auction_title: str, auction_id: str, current_bid: float, reserve: float, lang: str = "bg"):
    subject, header, body = render_localized("reserve_met", lang, {
        "name": name, "auction_title": auction_title, "auction_id": auction_id,
        "current_bid": f"{int(current_bid):,}", "reserve": f"{int(reserve):,}",
        "app_url": APP_URL,
    })
    await send_email(to, subject, _shell(header, body, to=to, lang=lang))


async def notify_auction_finalized(db, auction: dict) -> None:
    """Centralised post-finalization notification: emails the buyer (with seller
    contact) AND the seller (with buyer contact). Best-effort — every failure is
    logged but never raised, so the auction state stays consistent.

    Idempotent: relies on the caller having already moved the auction to "sold".
    Safe to invoke multiple times only when at-most-once semantics are not
    required (current call sites guard with finalised_at).
    """
    winner_id = auction.get("high_bidder_id")
    seller_id = auction.get("seller_id") or auction.get("owner_id")
    title = auction.get("title") or ""
    auction_id = auction.get("id") or ""
    price = float(auction.get("current_bid_eur") or 0)
    winner = await db.users.find_one({"id": winner_id}, {"_id": 0}) if winner_id else None
    seller = await db.users.find_one({"id": seller_id}, {"_id": 0}) if seller_id else None
    # Buyer email (rich version with seller contacts)
    if winner and winner.get("email"):
        try:
            await email_won(
                winner["email"], winner.get("name") or "",
                title, auction_id, price,
                lang=(winner.get("lang") or "bg"),
                seller_name=(seller or {}).get("name", ""),
                seller_email=(seller or {}).get("email", ""),
                seller_phone=(seller or {}).get("phone", ""),
            )
        except Exception as e:
            logger.error("email_won (buyer) failed: %s", e)
    # Seller email (buyer contacts attached)
    if seller and seller.get("email") and winner:
        try:
            await email_auction_won_seller(
                seller["email"], seller.get("name") or "",
                title, auction_id, price,
                buyer_name=winner.get("name") or "",
                buyer_email=winner.get("email") or "",
                buyer_phone=winner.get("phone") or "",
                lang=(seller.get("lang") or "bg"),
            )
        except Exception as e:
            logger.error("email_auction_won_seller failed: %s", e)
