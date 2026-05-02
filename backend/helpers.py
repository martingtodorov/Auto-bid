"""
Shared business-logic helpers for autoandbid.com backend.
Pure / near-pure functions with no FastAPI or Mongo side effects —
safe to import from any router module.
"""
from datetime import datetime, timezone


# ---------- Bid increments (BaT-style) ----------
def bid_step(current_price: float) -> float:
    """Variable bid increment based on current bid price.
    Halved brackets compared to BaT:
    €0-1k → €25; 1k-5k → €50; 5k-10k → €125; 10k-25k → €250; 25k-50k → €400;
    50k-100k → €500; 100k-200k → €1,000; 200k-500k → €2,500;
    500k-1M → €5,000; above €1M → €10,000.
    """
    p = float(current_price or 0)
    if p < 1000:     return 25.0
    if p < 5000:     return 50.0
    if p < 10000:    return 125.0
    if p < 25000:    return 250.0
    if p < 50000:    return 400.0
    if p < 100000:   return 500.0
    if p < 200000:   return 1000.0
    if p < 500000:   return 2500.0
    if p < 1000000:  return 5000.0
    return 10000.0


def buyer_fee(amount_eur: float, pct: float, fmin: float, fmax: float) -> float:
    """Buyer's premium — configurable via Settings. pct is a percentage (e.g. 2.0 for 2%)."""
    fee = round(float(amount_eur or 0) * (float(pct) / 100.0), 2)
    if fee < float(fmin): fee = float(fmin)
    if fee > float(fmax): fee = float(fmax)
    return fee


# ---------- Auction status (computed from ends_at + stored status) ----------
_STICKY_STATUSES = ("sold", "rejected", "pending", "withdrawn", "reserve_not_met", "ended", "removed", "archived", "cancelled")


def auction_status(a: dict) -> str:
    stored = a.get("status")
    if stored in _STICKY_STATUSES:
        return stored
    try:
        end = datetime.fromisoformat(a["ends_at"])
    except Exception:
        return stored or "live"
    if datetime.now(timezone.utc) >= end:
        reserve = a.get("reserve_eur")
        if reserve and float(a.get("current_bid_eur", 0)) < float(reserve):
            return "reserve_not_met"
        return "ended"
    return "live"


# ---------- VIN masking ----------
def mask_vin(vin: str) -> str:
    if not vin:
        return ""
    v = vin.strip().upper()
    if len(v) <= 7:
        return "*" * len(v)
    return v[:3] + "*" * (len(v) - 7) + v[-4:]



# ---------- Audit log ----------
import uuid as _uuid
import logging as _logging
_audit_logger = _logging.getLogger("audit")


async def audit_log(db, *, actor_id: str, actor_email: str = "", actor_role: str = "",
                    action: str, target_type: str = "", target_id: str = "",
                    details: dict = None, ip: str = "", user_agent: str = ""):
    """Append an immutable audit entry. Never raises — audit failures must not break flows."""
    try:
        doc = {
            "id": str(_uuid.uuid4()),
            "at": datetime.now(timezone.utc).isoformat(),
            "actor_id": actor_id or "",
            "actor_email": actor_email or "",
            "actor_role": actor_role or "",
            "action": action,
            "target_type": target_type or "",
            "target_id": target_id or "",
            "details": details or {},
            "ip": ip or "",
            "user_agent": user_agent or "",
        }
        await db.audit_log.insert_one(doc)
    except Exception as e:
        _audit_logger.error("audit_log failed: %s", e)


# ---------- Stripe runtime config (selects test/live key from saved settings) ----------
def stripe_public_config(settings: dict) -> dict:
    """What's safe to expose to the frontend."""
    mode = settings.get("stripe_mode") or "test"
    pk = settings.get(f"stripe_publishable_key_{mode}") or ""
    return {
        "mode": mode,
        "publishable_key": pk,
        "enabled": bool(settings.get("stripe_enabled") and pk),
    }


def stripe_runtime_config(settings: dict) -> dict:
    """Server-only: returns the secret + webhook secret for the active mode."""
    mode = settings.get("stripe_mode") or "test"
    return {
        "mode": mode,
        "publishable_key": settings.get(f"stripe_publishable_key_{mode}") or "",
        "secret_key": settings.get(f"stripe_secret_key_{mode}") or "",
        "webhook_secret": settings.get(f"stripe_webhook_secret_{mode}") or "",
        "enabled": bool(settings.get("stripe_enabled")),
    }


def mask_secret(s: str) -> str:
    if not s:
        return ""
    s = str(s)
    if len(s) <= 8:
        return "••••"
    return f"{s[:4]}…{s[-4:]}"
