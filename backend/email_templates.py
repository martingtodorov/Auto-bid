"""
Editable email template registry.

WHY this exists
---------------
Previously, every transactional email's subject + HTML body was hard-coded
in `emails.py` / `routers/auth.py`. Admins could not edit them, and the
admin "Email templates" tab was effectively decorative — it accepted user-
defined slugs but the system bypassed them entirely.

This module makes ALL system emails admin-editable while preserving safe
defaults baked into the codebase. The flow is:

  1. `SYSTEM_TEMPLATES` (below) is the source of truth for defaults — one
     entry per system email. Slug, subject pattern, HTML body, declared
     placeholder list, human description, and language code.
  2. `_render(slug, vars)` looks up `site_settings.email_templates[slug]`
     in MongoDB; if missing/blank it falls back to the system default.
     `{{var}}` placeholders are substituted using mustache-lite (no
     conditionals — admins can't accidentally execute code).
  3. Each `email_*` helper in `emails.py` is now a thin wrapper around
     `_render() → send_email()`.
  4. `seed_defaults_on_startup(db)` writes any missing system templates
     to MongoDB on first startup, so the admin UI lists them with the
     correct factory text from day one.

Adding a NEW system email
-------------------------
Append an entry to `SYSTEM_TEMPLATES`. The startup seeder will pick it up
on next deploy. No DB migration needed.

Multi-language
--------------
A few templates (verify_email) ship in BG/EN/RO. They use compound slugs
`<base>_<lang>` (e.g. `verify_email_bg`, `verify_email_ro`). The caller
picks the slug based on the user's `lang` preference; missing locales
fall back to the BG version.
"""
from __future__ import annotations

import logging
import re
from typing import Any, Optional

logger = logging.getLogger(__name__)


# --- Mustache-lite substitution -------------------------------------------
# Intentionally NOT a full templating engine — admins should never execute
# code via email bodies. Only `{{name}}` style variable substitution and a
# bare-bones `{{var | default}}` fallback are supported.

_PLACEHOLDER_RE = re.compile(r"\{\{\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*(?:\|\s*([^}]*?))?\s*\}\}")


def _substitute(text: str, variables: dict[str, Any]) -> str:
    """Replace `{{var}}` and `{{var | default}}` with values from `variables`.

    Missing variables are replaced with an empty string (or the literal
    `default` if one was provided after the `|`). HTML-escaping is the
    caller's responsibility — most variables we pass are already
    sanitised (e.g. car titles are stored after Pydantic validation).
    """
    if not text:
        return ""

    def repl(m: re.Match) -> str:
        key = m.group(1)
        default = (m.group(2) or "").strip()
        val = variables.get(key)
        if val is None or val == "":
            return default
        return str(val)

    return _PLACEHOLDER_RE.sub(repl, text)


# --- System template registry --------------------------------------------

# Each system template entry has:
#   subject:      str  — subject line with {{var}} placeholders
#   header:       str  — title rendered inside the email body (above content)
#   body_html:    str  — inner HTML (gets wrapped by `_shell` at send time)
#   placeholders: list[str]  — variables consumed (admin UI shows these as hints)
#   description:  str  — human note shown in admin UI
#   lang:         str  — primary language ("bg", "en", "ro")
#   system:       True — marks the template as protected (admins can edit
#                        subject + body but can't delete the slug)
#
# CTAs reused across templates — keep visual consistency.
_BTN_PRIMARY = (
    'background:#1B4D3E;color:#ffffff;padding:12px 22px;border-radius:10px;'
    'text-decoration:none;font-weight:600;display:inline-block;'
)
_BTN_DARK = (
    'background:#111827;color:#ffffff;padding:12px 22px;border-radius:999px;'
    'text-decoration:none;font-weight:600;display:inline-block;'
)


SYSTEM_TEMPLATES: dict[str, dict] = {
    # ── Auth ────────────────────────────────────────────────────────────
    "verify_email_bg": {
        "system": True, "lang": "bg",
        "description": "Изпраща се при регистрация — потвърждаване на имейл (BG).",
        "placeholders": ["name", "link"],
        "subject": "Потвърдете имейл адреса си",
        "header": "Потвърдете имейл адреса си",
        "body_html": (
            "<p>Здравейте, {{name}},</p>"
            "<p>Благодарим, че се регистрирахте в autoandbid.com. Моля, потвърдете "
            "имейл адреса си, като натиснете бутона по-долу:</p>"
            f'<p><a href="{{{{link}}}}" style="{_BTN_PRIMARY}">Потвърди имейл</a></p>'
            '<p style="color:#6b7280;font-size:13px;">Линкът е валиден 48 часа. '
            "Ако не сте инициирали това действие, можете да игнорирате имейла.</p>"
        ),
    },
    "verify_email_en": {
        "system": True, "lang": "en",
        "description": "Sent on registration — email verification (EN).",
        "placeholders": ["name", "link"],
        "subject": "Verify your email address",
        "header": "Verify your email address",
        "body_html": (
            "<p>Hi {{name}},</p>"
            "<p>Thanks for signing up on autoandbid.com. Please confirm your "
            "email address by clicking the button below:</p>"
            f'<p><a href="{{{{link}}}}" style="{_BTN_PRIMARY}">Verify email</a></p>'
            '<p style="color:#6b7280;font-size:13px;">This link is valid for 48 hours. '
            "If you did not request this, you can safely ignore this email.</p>"
        ),
    },
    "verify_email_ro": {
        "system": True, "lang": "ro",
        "description": "Trimis la înregistrare — confirmare email (RO).",
        "placeholders": ["name", "link"],
        "subject": "Confirmă-ți adresa de email",
        "header": "Confirmă-ți adresa de email",
        "body_html": (
            "<p>Bună, {{name}},</p>"
            "<p>Mulțumim că te-ai înregistrat pe autoandbid.com. Te rugăm să-ți "
            "confirmi adresa de email apăsând butonul de mai jos:</p>"
            f'<p><a href="{{{{link}}}}" style="{_BTN_PRIMARY}">Confirmă email</a></p>'
            '<p style="color:#6b7280;font-size:13px;">Linkul este valabil 48 de ore. '
            "Dacă nu ai inițiat această cerere, poți ignora acest mesaj.</p>"
        ),
    },
    "password_reset_bg": {
        "system": True, "lang": "bg",
        "description": "Код за нулиране на парола (6-цифрен OTP).",
        "placeholders": ["name", "code", "ttl_min"],
        "subject": "autoandbid.com — Код за нулиране на парола",
        "header": "Нулиране на парола",
        "body_html": (
            '<p style="margin:0 0 16px 0;">Здравейте {{name}},</p>'
            '<p style="margin:0 0 16px 0;">Получихме заявка за нулиране на паролата '
            "за вашия autoandbid.com акаунт.</p>"
            '<p style="margin:0 0 8px 0;">Вашият код за потвърждение (валиден '
            "{{ttl_min}} минути):</p>"
            '<div style="font-family:\'Courier New\',monospace;font-size:32px;'
            "letter-spacing:8px;background:#f6f7f8;padding:18px;text-align:center;"
            'border-radius:10px;border:1px solid #e5e7eb;margin:16px 0;">'
            "<strong>{{code}}</strong></div>"
            '<p style="color:#6b7280;font-size:13px;margin:24px 0 0 0;">'
            "Ако не сте правили такава заявка, можете спокойно да игнорирате това "
            "съобщение — паролата ви няма да бъде променена.</p>"
        ),
    },

    # ── Bidding lifecycle ───────────────────────────────────────────────
    "outbid": {
        "system": True, "lang": "bg",
        "description": "Изпреварен сте — изпраща се на участник при по-висока оферта.",
        "placeholders": ["name", "auction_title", "auction_id", "new_bid", "app_url"],
        "subject": "Изпреварени сте · {{auction_title}}",
        "header": "Имате нова оферта срещу вас",
        "body_html": (
            "<p>Здравейте, {{name}},</p>"
            "<p>Някой направи по-високо наддаване за <strong>{{auction_title}}</strong>.</p>"
            '<p style="font-size:20px;margin:20px 0;">Ново текущо наддаване: '
            "<strong>€{{new_bid}}</strong></p>"
            "<p>Вашата pre-authorization е автоматично освободена.</p>"
            f'<p><a href="{{{{app_url}}}}/auctions/{{{{auction_id}}}}" style="{_BTN_DARK}">Върни се в търга</a></p>'
        ),
    },
    "won": {
        "system": True, "lang": "bg",
        "description": "Поздравителен имейл при спечелен търг.",
        "placeholders": ["name", "auction_title", "auction_id", "price", "app_url"],
        "subject": "🏁 Спечелихте · {{auction_title}}",
        "header": "Вашето наддаване беше печелившото",
        "body_html": (
            "<p>Поздравления, {{name}}!</p>"
            "<p>Спечелихте търга за <strong>{{auction_title}}</strong>.</p>"
            '<p style="font-size:20px;margin:20px 0;">Крайна цена: <strong>€{{price}}</strong></p>'
            "<p>Нашият екип ще се свърже с вас за финализирането в рамките на 24 часа. "
            "Вашата pre-authorization остава задържана до приключване на сделката.</p>"
            f'<p><a href="{{{{app_url}}}}/auctions/{{{{auction_id}}}}" style="{_BTN_PRIMARY}">Виж търга</a></p>'
        ),
    },
    "approved": {
        "system": True, "lang": "bg",
        "description": "Обявата е одобрена от модератор и е публикувана.",
        "placeholders": ["name", "auction_title", "auction_id", "app_url"],
        "subject": "Одобрена обява · {{auction_title}}",
        "header": "Обявата ви е одобрена",
        "body_html": (
            "<p>Здравейте, {{name}},</p>"
            "<p>Вашата обява за <strong>{{auction_title}}</strong> е одобрена и вече е активна.</p>"
            f'<p><a href="{{{{app_url}}}}/auctions/{{{{auction_id}}}}" style="{_BTN_DARK}">Виж обявата</a></p>'
        ),
    },
    "rejected": {
        "system": True, "lang": "bg",
        "description": "Обявата изисква корекции — изпраща се с бележка от модератора.",
        "placeholders": ["name", "auction_title", "reason"],
        "subject": "Необходими корекции · {{auction_title}}",
        "header": "Обявата изисква корекции",
        "body_html": (
            "<p>Здравейте, {{name}},</p>"
            "<p>След преглед вашата обява за <strong>{{auction_title}}</strong> "
            "не беше одобрена.</p>"
            '<p style="background:#fafafa;border:1px solid #e5e7eb;padding:14px;border-radius:8px;">'
            "<strong>Забележка от екипа:</strong><br/>{{reason | —}}</p>"
            "<p>Може да редактирате и подадете отново.</p>"
        ),
    },
    "vin_delivery": {
        "system": True, "lang": "bg",
        "description": "VIN номер — изпраща се на печелившия купувач.",
        "placeholders": ["name", "auction_title", "auction_id", "vin", "app_url"],
        "subject": "VIN номер · {{auction_title}}",
        "header": "Пълен VIN номер",
        "body_html": (
            "<p>Здравейте, {{name}},</p>"
            "<p>Ето пълния VIN номер за <strong>{{auction_title}}</strong>:</p>"
            '<div style="margin:22px 0;padding:18px;background:#fafafa;border:1px solid #e5e7eb;'
            'border-radius:10px;text-align:center;">'
            '<div style="font-family:ui-monospace,\'IBM Plex Mono\',monospace;font-size:22px;'
            'letter-spacing:4px;font-weight:600;">{{vin}}</div></div>'
            "<p>Можете да направите VIN проверка чрез избран от вас сервиз.</p>"
            f'<p><a href="{{{{app_url}}}}/auctions/{{{{auction_id}}}}" style="{_BTN_PRIMARY}">Върни се в търга</a></p>'
            '<p style="color:#6b7280;font-size:12px;margin-top:20px;">VIN номерът се предоставя '
            "информативно за вземане на информирано решение при наддаване.</p>"
        ),
    },
    "seller_new_bid": {
        "system": True, "lang": "bg",
        "description": "Ново наддаване — уведомява продавача в реално време.",
        "placeholders": ["name", "auction_title", "auction_id", "bidder_name", "amount", "bid_count", "app_url"],
        "subject": "Ново наддаване €{{amount}} · {{auction_title}}",
        "header": "Ново наддаване в търга ви",
        "body_html": (
            "<p>Здравейте, {{name}},</p>"
            "<p>Ново наддаване за <strong>{{auction_title}}</strong>.</p>"
            '<div style="margin:20px 0;padding:16px;background:#fafafa;border:1px solid #e5e7eb;border-radius:10px;">'
            '<div style="font-size:12px;color:#6b7280;text-transform:uppercase;letter-spacing:0.1em;">Нова текуща</div>'
            '<div style="font-size:26px;font-weight:700;margin-top:4px;">€{{amount}}</div>'
            '<div style="font-size:13px;color:#6b7280;margin-top:6px;">от {{bidder_name}} · общо {{bid_count}} наддавания</div>'
            "</div>"
            f'<p><a href="{{{{app_url}}}}/auctions/{{{{auction_id}}}}" style="{_BTN_PRIMARY}">Следи търга</a></p>'
        ),
    },
    "seller_new_comment": {
        "system": True, "lang": "bg",
        "description": "Нов коментар под обявата — уведомява продавача.",
        "placeholders": ["name", "auction_title", "auction_id", "commenter_name", "snippet", "app_url"],
        "subject": "Нов коментар · {{auction_title}}",
        "header": "Нов коментар в обявата ви",
        "body_html": (
            "<p>Здравейте, {{name}},</p>"
            "<p><strong>{{commenter_name}}</strong> остави коментар в обявата "
            "<strong>{{auction_title}}</strong>.</p>"
            '<blockquote style="margin:20px 0;padding:14px 18px;background:#fafafa;'
            'border-left:3px solid #1B4D3E;color:#111827;font-style:italic;">{{snippet}}</blockquote>'
            f'<p><a href="{{{{app_url}}}}/auctions/{{{{auction_id}}}}" style="{_BTN_DARK}">Отговори</a></p>'
        ),
    },
    "ending_soon_watcher": {
        "system": True, "lang": "bg",
        "description": "Любим търг изтича скоро — изпраща се ~1 час преди край.",
        "placeholders": ["name", "auction_title", "auction_id", "current_bid", "app_url"],
        "subject": "⏰ Изтича скоро · {{auction_title}}",
        "header": "Любим търг изтича скоро",
        "body_html": (
            "<p>Здравейте, {{name}},</p>"
            "<p>До края на търга <strong>{{auction_title}}</strong> остава около 1 час.</p>"
            '<div style="margin:18px 0;padding:14px 16px;background:#fafafa;border:1px solid #e5e7eb;border-radius:10px;">'
            '<div style="font-size:12px;color:#6b7280;text-transform:uppercase;letter-spacing:0.08em;">Текуща оферта</div>'
            '<div style="font-size:24px;font-weight:700;margin-top:4px;">€{{current_bid}}</div></div>'
            f'<p><a href="{{{{app_url}}}}/auctions/{{{{auction_id}}}}" style="{_BTN_PRIMARY}">Отвори търга</a></p>'
        ),
    },
    "ending_soon_bidder": {
        "system": True, "lang": "bg",
        "description": "Търг с ваше наддаване изтича скоро — изпраща се ~1 час преди край.",
        "placeholders": ["name", "auction_title", "auction_id", "current_bid", "app_url"],
        "subject": "⏰ Изтича скоро · {{auction_title}}",
        "header": "Търг с ваше наддаване изтича скоро",
        "body_html": (
            "<p>Здравейте, {{name}},</p>"
            "<p>До края на търга <strong>{{auction_title}}</strong> остава около 1 час.</p>"
            '<div style="margin:18px 0;padding:14px 16px;background:#fafafa;border:1px solid #e5e7eb;border-radius:10px;">'
            '<div style="font-size:12px;color:#6b7280;text-transform:uppercase;letter-spacing:0.08em;">Текуща оферта</div>'
            '<div style="font-size:24px;font-weight:700;margin-top:4px;">€{{current_bid}}</div></div>'
            f'<p><a href="{{{{app_url}}}}/auctions/{{{{auction_id}}}}" style="{_BTN_PRIMARY}">Отвори търга</a></p>'
        ),
    },
    "reserve_met": {
        "system": True, "lang": "bg",
        "description": "Резервната цена е достигната — поздравителен имейл за продавача.",
        "placeholders": ["name", "auction_title", "auction_id", "current_bid", "reserve", "app_url"],
        "subject": "🎯 Резервът е достигнат · {{auction_title}}",
        "header": "Резервната цена е достигната",
        "body_html": (
            "<p>Поздравления, {{name}}!</p>"
            "<p>Резервната цена на вашата обява <strong>{{auction_title}}</strong> беше достигната.</p>"
            '<div style="margin:18px 0;padding:14px 16px;background:#fafafa;border:1px solid #e5e7eb;border-radius:10px;">'
            '<div style="font-size:12px;color:#6b7280;text-transform:uppercase;letter-spacing:0.08em;">Резерв · Текуща</div>'
            '<div style="font-size:22px;font-weight:700;margin-top:4px;">€{{reserve}} → '
            '<span style="color:#1B4D3E;">€{{current_bid}}</span></div></div>'
            "<p>Търгът вече е гарантирано продаваем при текущата или по-висока оферта.</p>"
            f'<p><a href="{{{{app_url}}}}/auctions/{{{{auction_id}}}}" style="{_BTN_PRIMARY}">Виж търга</a></p>'
        ),
    },
}


# --- DB-backed rendering --------------------------------------------------

def _fetch_override(slug: str) -> Optional[dict]:
    """Read admin override for `slug` from cached site settings.

    Returns None if the admin hasn't set a custom override (or the cache
    isn't ready yet — defensive against startup-order issues).
    """
    try:
        # Late import to avoid circular dep with server.py at module load.
        from server import get_settings_cached
        s = get_settings_cached() or {}
    except Exception:
        return None
    tpl = (s.get("email_templates") or {}).get(slug)
    if not isinstance(tpl, dict):
        return None
    if not tpl.get("subject") and not tpl.get("body") and not tpl.get("body_html"):
        return None
    return tpl


def render(slug: str, variables: Optional[dict[str, Any]] = None) -> tuple[str, str, str]:
    """Resolve `slug` → `(subject, header, inner_body_html)` with variables substituted.

    Admin overrides win over system defaults. Missing slugs raise KeyError
    so callers can't silently fail with an empty email.

    Returns:
        subject: rendered subject line (no chrome)
        header:  rendered title for the email body
        inner:   rendered inner HTML body (NOT yet wrapped by `_shell`)
    """
    default = SYSTEM_TEMPLATES.get(slug)
    if not default:
        raise KeyError(f"Unknown email template slug: {slug!r}")

    override = _fetch_override(slug) or {}
    vars_ = variables or {}

    subject_tpl = override.get("subject") or default["subject"]
    # Admin UI stores `body` (single field); system defaults split into
    # `body_html`. Accept either, with override > default.
    body_tpl = (
        override.get("body_html")
        or override.get("body")
        or default["body_html"]
    )
    header_tpl = override.get("header") or default.get("header") or subject_tpl

    return (
        _substitute(subject_tpl, vars_),
        _substitute(header_tpl, vars_),
        _substitute(body_tpl, vars_),
    )


async def seed_defaults_on_startup(db) -> int:
    """Write any missing system templates into `site_settings.email_templates`.

    Idempotent: existing admin overrides are preserved. Returns the number
    of new entries seeded so the startup log can show what happened.
    """
    from datetime import datetime, timezone
    s = await db.site_settings.find_one({"id": "global"}, {"_id": 0, "email_templates": 1}) or {}
    existing = s.get("email_templates") or {}
    additions: dict[str, dict] = {}
    for slug, tpl in SYSTEM_TEMPLATES.items():
        if slug in existing:
            continue
        additions[slug] = {
            "subject": tpl["subject"],
            "body": tpl["body_html"],
            "header": tpl.get("header") or tpl["subject"],
            "system": True,
            "lang": tpl.get("lang", "bg"),
            "description": tpl.get("description", ""),
            "placeholders": tpl.get("placeholders", []),
        }
    if not additions:
        return 0
    merged = {**existing, **additions}
    await db.site_settings.update_one(
        {"id": "global"},
        {"$set": {
            "email_templates": merged,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }, "$setOnInsert": {"id": "global"}},
        upsert=True,
    )
    logger.info("email_templates: seeded %d system defaults", len(additions))
    return len(additions)


def system_template_metadata() -> dict[str, dict]:
    """Return slug → {description, placeholders, lang, system: True} map
    for the admin UI to render. Body / subject are read separately via
    the standard `GET /admin/email-templates` endpoint.
    """
    return {
        slug: {
            "description": tpl.get("description", ""),
            "placeholders": tpl.get("placeholders", []),
            "lang": tpl.get("lang", "bg"),
            "system": True,
        }
        for slug, tpl in SYSTEM_TEMPLATES.items()
    }
