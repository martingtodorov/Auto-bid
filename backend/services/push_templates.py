"""Localized push notification templates.

Each template defines `title`/`body` strings keyed by language code.
`send_template` resolves the recipient's preferred language from
`db.users.lang` (falling back to "bg") and dispatches the localized
payload via `push.send_to_user`.

Body strings use Python `.format(**fmt_args)` placeholders so call
sites remain ergonomic and language-agnostic.
"""
from __future__ import annotations
from typing import Optional

from deps import db
from services import push as push_svc


SUPPORTED_LANGS = ("bg", "en", "ro")
DEFAULT_LANG = "bg"


# Each entry: { "<lang>": {"title": str, "body": str (with {placeholders})} }
TEMPLATES: dict[str, dict[str, dict[str, str]]] = {
    # User got outbid
    "outbid": {
        "bg": {"title": "Надминати сте · {title}", "body": "Ново наддаване €{amount}. Все още можете да отговорите."},
        "en": {"title": "You've been outbid · {title}", "body": "New bid €{amount}. You can still place a counter-bid."},
        "ro": {"title": "Ați fost depășit · {title}", "body": "Ofertă nouă €{amount}. Mai puteți reveni cu o ofertă."},
    },
    # Seller — your car got a new bid
    "seller_new_bid": {
        "bg": {"title": "Нова наддавка · {title}", "body": "{bidder} наддаде €{amount}. Общо {count} наддавания."},
        "en": {"title": "New bid · {title}", "body": "{bidder} placed €{amount}. {count} bids in total."},
        "ro": {"title": "Ofertă nouă · {title}", "body": "{bidder} a oferit €{amount}. {count} oferte în total."},
    },
    # Saved-search match
    "saved_search_match": {
        "bg": {"title": "Нова обява · {name}", "body": "{title} · от €{price}"},
        "en": {"title": "New listing · {name}", "body": "{title} · from €{price}"},
        "ro": {"title": "Anunț nou · {name}", "body": "{title} · de la €{price}"},
    },
    # Chat — admin → user
    "chat_admin_message": {
        "bg": {"title": "Поддръжка ви пише", "body": "{preview}"},
        "en": {"title": "Support sent you a message", "body": "{preview}"},
        "ro": {"title": "Asistența v-a scris", "body": "{preview}"},
    },
    # Auction won (premium captured)
    "auction_won": {
        "bg": {"title": "Спечелихте търга · {title}", "body": "Сума: €{amount}. Очаквайте инструкции."},
        "en": {"title": "You won the auction · {title}", "body": "Amount: €{amount}. Instructions to follow."},
        "ro": {"title": "Ați câștigat licitația · {title}", "body": "Sumă: €{amount}. Urmează instrucțiuni."},
    },
    # Auction lost (hold released)
    "auction_lost": {
        "bg": {"title": "Търгът приключи · {title}", "body": "Не спечелихте този път. Депозитът е освободен."},
        "en": {"title": "Auction ended · {title}", "body": "You didn't win this time. Your hold has been released."},
        "ro": {"title": "Licitația s-a încheiat · {title}", "body": "Nu ați câștigat. Depozitul a fost eliberat."},
    },
    # Ending soon (≈1h before auction ends) — sent to watchers and active bidders
    "ending_soon": {
        "bg": {"title": "Изтича скоро · {title}", "body": "Около 1 час до края. Текуща оферта €{amount}."},
        "en": {"title": "Ending soon · {title}", "body": "About 1 hour left. Current bid €{amount}."},
        "ro": {"title": "Se încheie curând · {title}", "body": "Aprox. 1 oră rămasă. Ofertă curentă €{amount}."},
    },
    # Reserve met on the seller's own auction
    "reserve_met": {
        "bg": {"title": "Резервът е достигнат · {title}", "body": "Текущата оферта (€{amount}) надхвърля резервната цена."},
        "en": {"title": "Reserve met · {title}", "body": "Current bid (€{amount}) has met the reserve price."},
        "ro": {"title": "Prag atins · {title}", "body": "Oferta curentă (€{amount}) a atins prețul de rezervă."},
    },
}


def normalize_lang(value: Optional[str]) -> str:
    v = (value or "").strip().lower()[:2]
    return v if v in SUPPORTED_LANGS else DEFAULT_LANG


async def get_user_lang(user_id: str) -> str:
    """Read the user's preferred UI language from Mongo (defaults to bg)."""
    u = await db.users.find_one({"id": user_id}, {"_id": 0, "lang": 1})
    return normalize_lang((u or {}).get("lang"))


async def send_template(
    user_id: str,
    template_id: str,
    *,
    fmt_args: Optional[dict] = None,
    url: str = "/",
    tag: Optional[str] = None,
    icon: Optional[str] = None,
) -> int:
    """Dispatch a localized push using the recipient's preferred language."""
    tmpl = TEMPLATES.get(template_id)
    if not tmpl:
        return 0
    lang = await get_user_lang(user_id)
    payload = tmpl.get(lang) or tmpl.get(DEFAULT_LANG)
    if not payload:
        return 0
    fmt = fmt_args or {}
    try:
        title = payload["title"].format(**fmt)
        body = payload["body"].format(**fmt)
    except (KeyError, IndexError):
        # Missing placeholder — render raw template instead of crashing.
        title = payload["title"]
        body = payload["body"]
    return await push_svc.send_to_user(
        user_id, title=title, body=body, url=url, tag=tag, icon=icon
    )
