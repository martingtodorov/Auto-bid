"""Per-user notification preferences.

Each user has a `notification_prefs` document of the shape:
    {
      "push":  {"outbid": bool, "seller_new_bid": bool, "saved_search": bool,
                "ending_soon": bool, "reserve_met": bool},
      "email": {"outbid": bool, "seller_new_bid": bool, "saved_search": bool,
                "ending_soon": bool, "reserve_met": bool},
    }

When the document is missing OR a specific key is missing, the channel/kind
defaults to **enabled** (True) — this keeps existing user behaviour identical
to what it was before granular toggles were introduced.
"""
from __future__ import annotations

NOTIF_KINDS = ("outbid", "seller_new_bid", "saved_search", "ending_soon", "reserve_met", "listing_approved")
NOTIF_CHANNELS = ("push", "email")


def default_prefs() -> dict:
    return {ch: {k: True for k in NOTIF_KINDS} for ch in NOTIF_CHANNELS}


def is_enabled(user: dict, channel: str, kind: str) -> bool:
    """Return True iff the user has not explicitly disabled this notification."""
    if channel not in NOTIF_CHANNELS or kind not in NOTIF_KINDS:
        return True
    prefs = (user or {}).get("notification_prefs") or {}
    chan_prefs = prefs.get(channel) or {}
    val = chan_prefs.get(kind, True)   # default-enabled
    return bool(val)


def normalize_input(payload: dict) -> dict:
    """Sanitise a `notification_prefs` blob coming from the client.

    Drops unknown keys, coerces values to bool, ensures the structure is
    valid before persisting in Mongo. Missing fields are NOT filled in
    (they will fall back to default-enabled at read time).
    """
    out: dict[str, dict[str, bool]] = {}
    if not isinstance(payload, dict):
        return out
    for ch in NOTIF_CHANNELS:
        chan = payload.get(ch)
        if not isinstance(chan, dict):
            continue
        clean = {}
        for k in NOTIF_KINDS:
            if k in chan:
                clean[k] = bool(chan[k])
        if clean:
            out[ch] = clean
    return out
