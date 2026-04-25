"""
Web Push notifications via VAPID (W3C Push API).

Works on:
  • Android Chrome / Edge / Firefox / Samsung Internet
  • iOS 16.4+ — only when the site is installed as a PWA (Add to Home Screen)
  • Desktop Chrome / Edge / Firefox / Safari

Subscriptions are stored in MongoDB collection `push_subscriptions`:
  { id, user_id, endpoint (unique), keys: {p256dh, auth}, user_agent, created_at }

Send happens via pywebpush; failures with status 404/410 mean the
subscription is gone and we prune it.
"""
from __future__ import annotations

import os
import json as _json
import logging
import asyncio
from datetime import datetime, timezone
from typing import Optional

from pywebpush import webpush, WebPushException

from deps import db

logger = logging.getLogger(__name__)


def vapid_public_key() -> str:
    return os.environ.get("VAPID_PUBLIC_KEY", "")


def _vapid_claims() -> dict:
    return {"sub": os.environ.get("VAPID_CONTACT_EMAIL", "mailto:admin@example.com")}


async def save_subscription(user_id: str, subscription: dict, user_agent: Optional[str] = None) -> str:
    """Idempotent — keyed on (user_id, endpoint)."""
    endpoint = subscription.get("endpoint")
    keys = subscription.get("keys") or {}
    if not endpoint or not keys.get("p256dh") or not keys.get("auth"):
        raise ValueError("Невалидна push subscription")

    existing = await db.push_subscriptions.find_one({"endpoint": endpoint}, {"_id": 0, "id": 1})
    if existing:
        await db.push_subscriptions.update_one(
            {"endpoint": endpoint},
            {"$set": {
                "user_id": user_id,
                "keys": keys,
                "user_agent": user_agent or "",
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }},
        )
        return existing["id"]

    import uuid as _uuid
    sub_id = str(_uuid.uuid4())
    await db.push_subscriptions.insert_one({
        "id": sub_id,
        "user_id": user_id,
        "endpoint": endpoint,
        "keys": keys,
        "user_agent": user_agent or "",
        "created_at": datetime.now(timezone.utc).isoformat(),
    })
    return sub_id


async def delete_subscription(user_id: str, endpoint: str) -> int:
    res = await db.push_subscriptions.delete_one({"user_id": user_id, "endpoint": endpoint})
    return res.deleted_count


def _send_one(subscription_info: dict, payload: str) -> tuple[bool, Optional[int]]:
    """Synchronous push send. Returns (success, http_status_or_None)."""
    private_pem = os.environ.get("VAPID_PRIVATE_KEY", "")
    if not private_pem:
        return False, None
    try:
        webpush(
            subscription_info=subscription_info,
            data=payload,
            vapid_private_key=private_pem,
            vapid_claims=_vapid_claims(),
            ttl=60 * 60 * 24,  # keep for 24h if device offline
        )
        return True, 201
    except WebPushException as e:
        status = e.response.status_code if e.response is not None else None
        return False, status


async def send_to_user(user_id: str, *, title: str, body: str, url: str = "/", tag: Optional[str] = None, icon: Optional[str] = None) -> int:
    """Fan-out push to all of a user's active subscriptions. Returns count delivered.
    Auto-prunes 404/410 (gone) endpoints."""
    if not os.environ.get("VAPID_PRIVATE_KEY"):
        logger.debug("Push skipped — VAPID_PRIVATE_KEY not configured")
        return 0

    subs = await db.push_subscriptions.find({"user_id": user_id}, {"_id": 0}).to_list(50)
    if not subs:
        return 0

    payload = _json.dumps({
        "title": title,
        "body": body,
        "url": url,
        "tag": tag or f"u-{user_id}",
        "icon": icon or "/icons/push-icon-192.png",
        "badge": "/icons/push-badge-72.png",
        "ts": datetime.now(timezone.utc).isoformat(),
    }, ensure_ascii=False)

    delivered = 0
    gone_endpoints: list[str] = []

    loop = asyncio.get_event_loop()
    for s in subs:
        info = {"endpoint": s["endpoint"], "keys": s["keys"]}
        # pywebpush is sync — run in default thread pool
        ok, status = await loop.run_in_executor(None, _send_one, info, payload)
        if ok:
            delivered += 1
        elif status in (404, 410):
            gone_endpoints.append(s["endpoint"])
        else:
            logger.warning("push send failed: status=%s endpoint=%s", status, s["endpoint"][:60])

    if gone_endpoints:
        await db.push_subscriptions.delete_many({"endpoint": {"$in": gone_endpoints}})
        logger.info("Pruned %d expired push subscriptions", len(gone_endpoints))

    return delivered
