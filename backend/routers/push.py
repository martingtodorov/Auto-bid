"""
Push subscription endpoints.

  GET  /api/push/public-key     — VAPID public key (for the frontend to subscribe)
  POST /api/push/subscribe      — register a new browser subscription
  POST /api/push/unsubscribe    — remove a subscription
  POST /api/push/test           — send a test push (auth required)
"""
from __future__ import annotations

from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Request

from services import push as push_svc

router = APIRouter()


def register_push_routes(get_current_user):
    @router.get("/push/public-key")
    async def get_public_key():
        return {"public_key": push_svc.vapid_public_key()}

    @router.post("/push/subscribe")
    async def subscribe(payload: dict, request: Request, user: dict = Depends(get_current_user)):
        sub = payload.get("subscription") or payload
        try:
            sub_id = await push_svc.save_subscription(
                user_id=user["id"],
                subscription=sub,
                user_agent=request.headers.get("user-agent", ""),
            )
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
        return {"ok": True, "id": sub_id}

    @router.post("/push/unsubscribe")
    async def unsubscribe(payload: dict, user: dict = Depends(get_current_user)):
        endpoint: Optional[str] = payload.get("endpoint")
        if not endpoint:
            raise HTTPException(status_code=400, detail="endpoint required")
        n = await push_svc.delete_subscription(user["id"], endpoint)
        return {"ok": True, "removed": n}

    @router.post("/push/test")
    async def test_push(user: dict = Depends(get_current_user)):
        n = await push_svc.send_to_user(
            user["id"],
            title="Auto&Bid · Тестова нотификация",
            body=f"Здравейте, {user.get('name','')}! Push известията работят 🎉",
            url="/dashboard",
            tag="test-push",
        )
        return {"ok": True, "delivered": n}

    return router
