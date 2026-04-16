"""Twilio SMS helper with graceful fallback when credentials are missing."""
import os
import asyncio
import logging

logger = logging.getLogger(__name__)

SID = os.environ.get("TWILIO_ACCOUNT_SID", "").strip()
TOKEN = os.environ.get("TWILIO_AUTH_TOKEN", "").strip()
FROM = os.environ.get("TWILIO_FROM_NUMBER", "").strip()

_client = None
if SID and TOKEN and FROM:
    try:
        from twilio.rest import Client
        _client = Client(SID, TOKEN)
    except Exception as e:
        logger.error("twilio client init failed: %s", e)


async def send_sms(to: str, body: str) -> bool:
    """Send SMS. Returns True on success, False when missing config or failure."""
    if not _client:
        logger.info("[SMS:mock] to=%s body=%s", to, body[:120])
        return False
    if not to or not to.startswith("+"):
        logger.warning("[SMS:skip] invalid to=%s", to)
        return False
    try:
        def _send():
            return _client.messages.create(body=body, from_=FROM, to=to)
        msg = await asyncio.to_thread(_send)
        logger.info("[SMS:sent] sid=%s to=%s", msg.sid, to)
        return True
    except Exception as e:
        logger.error("[SMS:error] to=%s err=%s", to, e)
        return False
