"""
Shared business-logic helpers for AutoBid.bg backend.
Pure / near-pure functions with no FastAPI or Mongo side effects —
safe to import from any router module.
"""
from datetime import datetime, timezone


# ---------- Bid increments (BaT-style) ----------
def bid_step(current_price: float) -> float:
    """Variable bid increment based on current bid price.
    €1,000-€2,500 → €100; €2,500-€5,000 → €150; €5,000-€10,000 → €250;
    €10,000-€20,000 → €500; €20,000-€50,000 → €1,000;
    €50,000-€100,000 → €2,000; above €100,000 → €2,500.
    Below €1,000 we use €50.
    """
    p = float(current_price or 0)
    if p < 1000:   return 50.0
    if p < 2500:   return 100.0
    if p < 5000:   return 150.0
    if p < 10000:  return 250.0
    if p < 20000:  return 500.0
    if p < 50000:  return 1000.0
    if p < 100000: return 2000.0
    return 2500.0


def buyer_fee(amount_eur: float, pct: float, fmin: float, fmax: float) -> float:
    """Buyer's premium — configurable via Settings. pct is a percentage (e.g. 2.0 for 2%)."""
    fee = round(float(amount_eur or 0) * (float(pct) / 100.0), 2)
    if fee < float(fmin): fee = float(fmin)
    if fee > float(fmax): fee = float(fmax)
    return fee


# ---------- Auction status (computed from ends_at + stored status) ----------
_STICKY_STATUSES = ("sold", "rejected", "pending", "withdrawn", "reserve_not_met", "ended", "removed")


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
