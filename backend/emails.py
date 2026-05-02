"""Resend-based email helper with graceful fallback when API key is missing."""
import os
import asyncio
import logging
import resend

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
    return f"""
<!doctype html>
<html><body style="margin:0;background:#f6f7f8;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Manrope,Roboto,sans-serif;color:#111827;">
<table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="background:#f6f7f8;padding:32px 0;">
  <tr><td align="center">
    <table role="presentation" width="560" cellspacing="0" cellpadding="0" style="background:#ffffff;border:1px solid #e5e7eb;border-radius:14px;overflow:hidden;">
      <tr><td style="padding:28px 32px;border-bottom:1px solid #e5e7eb;">
        <div style="font-weight:700;font-size:22px;letter-spacing:-0.03em;">autoandbid<span style="color:#1B4D3E">.bg</span></div>
      </td></tr>
      <tr><td style="padding:32px;">
        <h1 style="margin:0 0 16px 0;font-size:24px;letter-spacing:-0.02em;">{title}</h1>
        {body_html}
      </td></tr>
      <tr><td style="padding:20px 32px;background:#fafafa;border-top:1px solid #e5e7eb;color:#6b7280;font-size:12px;">
        autoandbid.com · Редакционна платформа за автомобилни търгове · София
      </td></tr>
    </table>
  </td></tr>
</table></body></html>
"""


async def email_outbid(to: str, name: str, auction_title: str, auction_id: str, new_bid: float):
    body = f"""
      <p>Здравейте, {name},</p>
      <p>Някой направи по-високо наддаване за <strong>{auction_title}</strong>.</p>
      <p style="font-size:20px;margin:20px 0;">Ново текущо наддаване: <strong>€{int(new_bid):,}</strong></p>
      <p>Вашата pre-authorization е автоматично освободена.</p>
      <p><a href="{APP_URL}/auctions/{auction_id}" style="display:inline-block;background:#111827;color:#fff;padding:12px 22px;border-radius:999px;text-decoration:none;font-weight:600;">Върни се в търга</a></p>
    """
    await send_email(to, f"Изпреварени сте · {auction_title}", _shell("Имате нова оферта срещу вас", body))


async def email_won(to: str, name: str, auction_title: str, auction_id: str, price: float):
    body = f"""
      <p>Поздравления, {name}!</p>
      <p>Спечелихте търга за <strong>{auction_title}</strong>.</p>
      <p style="font-size:20px;margin:20px 0;">Крайна цена: <strong>€{int(price):,}</strong></p>
      <p>Нашият екип ще се свърже с вас за финализирането в рамките на 24 часа. Вашата pre-authorization остава задържана до приключване на сделката.</p>
      <p><a href="{APP_URL}/auctions/{auction_id}" style="display:inline-block;background:#1B4D3E;color:#fff;padding:12px 22px;border-radius:999px;text-decoration:none;font-weight:600;">Виж търга</a></p>
    """
    await send_email(to, f"🏁 Спечелихте · {auction_title}", _shell("Вашето наддаване беше печелившото", body))


async def email_approved(to: str, name: str, auction_title: str, auction_id: str):
    body = f"""
      <p>Здравейте, {name},</p>
      <p>Вашата обява за <strong>{auction_title}</strong> е одобрена и вече е активна.</p>
      <p><a href="{APP_URL}/auctions/{auction_id}" style="display:inline-block;background:#111827;color:#fff;padding:12px 22px;border-radius:999px;text-decoration:none;font-weight:600;">Виж обявата</a></p>
    """
    await send_email(to, f"Одобрена обява · {auction_title}", _shell("Обявата ви е одобрена", body))


async def email_rejected(to: str, name: str, auction_title: str, reason: str):
    body = f"""
      <p>Здравейте, {name},</p>
      <p>След преглед вашата обява за <strong>{auction_title}</strong> не беше одобрена.</p>
      <p style="background:#fafafa;border:1px solid #e5e7eb;padding:14px;border-radius:8px;"><strong>Забележка от екипа:</strong><br/>{reason or '—'}</p>
      <p>Може да редактирате и подадете отново.</p>
    """
    await send_email(to, f"Необходими корекции · {auction_title}", _shell("Обявата изисква корекции", body))


async def email_vin_delivery(to: str, name: str, auction_title: str, auction_id: str, vin: str):
    body = f"""
      <p>Здравейте, {name},</p>
      <p>Ето пълния VIN номер за <strong>{auction_title}</strong>:</p>
      <div style="margin:22px 0;padding:18px;background:#fafafa;border:1px solid #e5e7eb;border-radius:10px;text-align:center;">
        <div style="font-family:ui-monospace,'IBM Plex Mono',monospace;font-size:22px;letter-spacing:4px;font-weight:600;">{vin}</div>
      </div>
      <p>Можете да направите VIN проверка чрез избран от вас сервиз.</p>
      <p><a href="{APP_URL}/auctions/{auction_id}" style="display:inline-block;background:#1B4D3E;color:#fff;padding:12px 22px;border-radius:999px;text-decoration:none;font-weight:600;">Върни се в търга</a></p>
      <p style="color:#6b7280;font-size:12px;margin-top:20px;">VIN номерът се предоставя информативно за вземане на информирано решение при наддаване.</p>
    """
    await send_email(to, f"VIN номер · {auction_title}", _shell("Пълен VIN номер", body))


async def email_seller_new_bid(to: str, name: str, auction_title: str, auction_id: str, bidder_name: str, amount: float, bid_count: int):
    body = f"""
      <p>Здравейте, {name},</p>
      <p>Ново наддаване за <strong>{auction_title}</strong>.</p>
      <div style="margin:20px 0;padding:16px;background:#fafafa;border:1px solid #e5e7eb;border-radius:10px;">
        <div style="font-size:12px;color:#6b7280;text-transform:uppercase;letter-spacing:0.1em;">Нова текуща</div>
        <div style="font-size:26px;font-weight:700;margin-top:4px;">€{int(amount):,}</div>
        <div style="font-size:13px;color:#6b7280;margin-top:6px;">от {bidder_name} · общо {bid_count} наддавания</div>
      </div>
      <p><a href="{APP_URL}/auctions/{auction_id}" style="display:inline-block;background:#1B4D3E;color:#fff;padding:12px 22px;border-radius:999px;text-decoration:none;font-weight:600;">Следи търга</a></p>
    """
    await send_email(to, f"Ново наддаване €{int(amount):,} · {auction_title}", _shell("Ново наддаване в търга ви", body))


async def email_seller_new_comment(to: str, name: str, auction_title: str, auction_id: str, commenter_name: str, snippet: str):
    body = f"""
      <p>Здравейте, {name},</p>
      <p><strong>{commenter_name}</strong> остави коментар в обявата <strong>{auction_title}</strong>.</p>
      <blockquote style="margin:20px 0;padding:14px 18px;background:#fafafa;border-left:3px solid #1B4D3E;color:#111827;font-style:italic;">{snippet}</blockquote>
      <p><a href="{APP_URL}/auctions/{auction_id}" style="display:inline-block;background:#111827;color:#fff;padding:12px 22px;border-radius:999px;text-decoration:none;font-weight:600;">Отговори</a></p>
    """
    await send_email(to, f"Нов коментар · {auction_title}", _shell("Нов коментар в обявата ви", body))



async def email_ending_soon(to: str, name: str, auction_title: str, auction_id: str, current_bid: float, role: str = "watcher"):
    """role: 'watcher' (favourited) or 'bidder' (currently leading or active in bidding)."""
    headline = "Любим търг изтича скоро" if role == "watcher" else "Търг с ваше наддаване изтича скоро"
    body = f"""
      <p>Здравейте, {name},</p>
      <p>До края на търга <strong>{auction_title}</strong> остава около 1 час.</p>
      <div style="margin:18px 0;padding:14px 16px;background:#fafafa;border:1px solid #e5e7eb;border-radius:10px;">
        <div style="font-size:12px;color:#6b7280;text-transform:uppercase;letter-spacing:0.08em;">Текуща оферта</div>
        <div style="font-size:24px;font-weight:700;margin-top:4px;">€{int(current_bid):,}</div>
      </div>
      <p><a href="{APP_URL}/auctions/{auction_id}" style="display:inline-block;background:#1B4D3E;color:#fff;padding:12px 22px;border-radius:999px;text-decoration:none;font-weight:600;">Отвори търга</a></p>
    """
    await send_email(to, f"⏰ Изтича скоро · {auction_title}", _shell(headline, body))


async def email_reserve_met(to: str, name: str, auction_title: str, auction_id: str, current_bid: float, reserve: float):
    body = f"""
      <p>Поздравления, {name}!</p>
      <p>Резервната цена на вашата обява <strong>{auction_title}</strong> беше достигната.</p>
      <div style="margin:18px 0;padding:14px 16px;background:#fafafa;border:1px solid #e5e7eb;border-radius:10px;">
        <div style="font-size:12px;color:#6b7280;text-transform:uppercase;letter-spacing:0.08em;">Резерв · Текуща</div>
        <div style="font-size:22px;font-weight:700;margin-top:4px;">€{int(reserve):,} → <span style="color:#1B4D3E;">€{int(current_bid):,}</span></div>
      </div>
      <p>Търгът вече е гарантирано продаваем при текущата или по-висока оферта.</p>
      <p><a href="{APP_URL}/auctions/{auction_id}" style="display:inline-block;background:#1B4D3E;color:#fff;padding:12px 22px;border-radius:999px;text-decoration:none;font-weight:600;">Виж търга</a></p>
    """
    await send_email(to, f"🎯 Резервът е достигнат · {auction_title}", _shell("Резервната цена е достигната", body))
