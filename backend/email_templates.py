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

    # ── EN translations ────────────────────────────────────────────────
    "password_reset_en": {
        "system": True, "lang": "en",
        "description": "Password reset code (6-digit OTP).",
        "placeholders": ["name", "code", "ttl_min"],
        "subject": "autoandbid.com — Password reset code",
        "header": "Password reset",
        "body_html": (
            '<p style="margin:0 0 16px 0;">Hi {{name}},</p>'
            '<p style="margin:0 0 16px 0;">We received a request to reset the password '
            "for your autoandbid.com account.</p>"
            '<p style="margin:0 0 8px 0;">Your verification code (valid {{ttl_min}} minutes):</p>'
            '<div style="font-family:\'Courier New\',monospace;font-size:32px;'
            "letter-spacing:8px;background:#f6f7f8;padding:18px;text-align:center;"
            'border-radius:10px;border:1px solid #e5e7eb;margin:16px 0;">'
            "<strong>{{code}}</strong></div>"
            '<p style="color:#6b7280;font-size:13px;margin:24px 0 0 0;">'
            "If you did not request this, you can safely ignore this email — "
            "your password will not be changed.</p>"
        ),
    },
    "outbid_en": {
        "system": True, "lang": "en",
        "description": "You've been outbid — sent to bidders when a higher offer arrives.",
        "placeholders": ["name", "auction_title", "auction_id", "new_bid", "app_url"],
        "subject": "You've been outbid · {{auction_title}}",
        "header": "A new bid is ahead of yours",
        "body_html": (
            "<p>Hi {{name}},</p>"
            "<p>Someone placed a higher bid on <strong>{{auction_title}}</strong>.</p>"
            '<p style="font-size:20px;margin:20px 0;">New current bid: <strong>€{{new_bid}}</strong></p>'
            "<p>Your pre-authorization has been automatically released.</p>"
            f'<p><a href="{{{{app_url}}}}/auctions/{{{{auction_id}}}}" style="{_BTN_DARK}">Back to auction</a></p>'
        ),
    },
    "approved_en": {
        "system": True, "lang": "en",
        "description": "Listing approved by moderator and published.",
        "placeholders": ["name", "auction_title", "auction_id", "app_url"],
        "subject": "Listing approved · {{auction_title}}",
        "header": "Your listing has been approved",
        "body_html": (
            "<p>Hi {{name}},</p>"
            "<p>Your listing for <strong>{{auction_title}}</strong> has been approved and is now live.</p>"
            f'<p><a href="{{{{app_url}}}}/auctions/{{{{auction_id}}}}" style="{_BTN_DARK}">View listing</a></p>'
        ),
    },
    "rejected_en": {
        "system": True, "lang": "en",
        "description": "Listing requires changes — sent with a moderator's note.",
        "placeholders": ["name", "auction_title", "reason"],
        "subject": "Changes required · {{auction_title}}",
        "header": "Your listing needs changes",
        "body_html": (
            "<p>Hi {{name}},</p>"
            "<p>After review, your listing for <strong>{{auction_title}}</strong> was not approved.</p>"
            '<p style="background:#fafafa;border:1px solid #e5e7eb;padding:14px;border-radius:8px;">'
            "<strong>Note from the team:</strong><br/>{{reason | —}}</p>"
            "<p>You can edit and resubmit.</p>"
        ),
    },
    "vin_delivery_en": {
        "system": True, "lang": "en",
        "description": "VIN number — sent to the winning bidder.",
        "placeholders": ["name", "auction_title", "auction_id", "vin", "app_url"],
        "subject": "VIN number · {{auction_title}}",
        "header": "Full VIN number",
        "body_html": (
            "<p>Hi {{name}},</p>"
            "<p>Here is the full VIN for <strong>{{auction_title}}</strong>:</p>"
            '<div style="margin:22px 0;padding:18px;background:#fafafa;border:1px solid #e5e7eb;'
            'border-radius:10px;text-align:center;">'
            '<div style="font-family:ui-monospace,\'IBM Plex Mono\',monospace;font-size:22px;'
            'letter-spacing:4px;font-weight:600;">{{vin}}</div></div>'
            "<p>You can run a VIN check via a workshop of your choice.</p>"
            f'<p><a href="{{{{app_url}}}}/auctions/{{{{auction_id}}}}" style="{_BTN_PRIMARY}">Back to auction</a></p>'
            '<p style="color:#6b7280;font-size:12px;margin-top:20px;">The VIN is provided as '
            "information to help you make an informed bidding decision.</p>"
        ),
    },
    "seller_new_bid_en": {
        "system": True, "lang": "en",
        "description": "New bid — notifies the seller in real time.",
        "placeholders": ["name", "auction_title", "auction_id", "bidder_name", "amount", "bid_count", "app_url"],
        "subject": "New bid €{{amount}} · {{auction_title}}",
        "header": "New bid on your auction",
        "body_html": (
            "<p>Hi {{name}},</p>"
            "<p>A new bid was placed on <strong>{{auction_title}}</strong>.</p>"
            '<div style="margin:20px 0;padding:16px;background:#fafafa;border:1px solid #e5e7eb;border-radius:10px;">'
            '<div style="font-size:12px;color:#6b7280;text-transform:uppercase;letter-spacing:0.1em;">New current</div>'
            '<div style="font-size:26px;font-weight:700;margin-top:4px;">€{{amount}}</div>'
            '<div style="font-size:13px;color:#6b7280;margin-top:6px;">from {{bidder_name}} · {{bid_count}} bids total</div>'
            "</div>"
            f'<p><a href="{{{{app_url}}}}/auctions/{{{{auction_id}}}}" style="{_BTN_PRIMARY}">Follow auction</a></p>'
        ),
    },
    "seller_new_comment_en": {
        "system": True, "lang": "en",
        "description": "New comment on the listing — notifies the seller.",
        "placeholders": ["name", "auction_title", "auction_id", "commenter_name", "snippet", "app_url"],
        "subject": "New comment · {{auction_title}}",
        "header": "New comment on your listing",
        "body_html": (
            "<p>Hi {{name}},</p>"
            "<p><strong>{{commenter_name}}</strong> left a comment on the listing "
            "<strong>{{auction_title}}</strong>.</p>"
            '<blockquote style="margin:20px 0;padding:14px 18px;background:#fafafa;'
            'border-left:3px solid #1B4D3E;color:#111827;font-style:italic;">{{snippet}}</blockquote>'
            f'<p><a href="{{{{app_url}}}}/auctions/{{{{auction_id}}}}" style="{_BTN_DARK}">Reply</a></p>'
        ),
    },
    "ending_soon_watcher_en": {
        "system": True, "lang": "en",
        "description": "Favourited auction ending soon — sent ~1 hour before end.",
        "placeholders": ["name", "auction_title", "auction_id", "current_bid", "app_url"],
        "subject": "⏰ Ending soon · {{auction_title}}",
        "header": "Favourited auction ending soon",
        "body_html": (
            "<p>Hi {{name}},</p>"
            "<p>About 1 hour remains until the end of <strong>{{auction_title}}</strong>.</p>"
            '<div style="margin:18px 0;padding:14px 16px;background:#fafafa;border:1px solid #e5e7eb;border-radius:10px;">'
            '<div style="font-size:12px;color:#6b7280;text-transform:uppercase;letter-spacing:0.08em;">Current bid</div>'
            '<div style="font-size:24px;font-weight:700;margin-top:4px;">€{{current_bid}}</div></div>'
            f'<p><a href="{{{{app_url}}}}/auctions/{{{{auction_id}}}}" style="{_BTN_PRIMARY}">Open auction</a></p>'
        ),
    },
    "ending_soon_bidder_en": {
        "system": True, "lang": "en",
        "description": "Auction with your bid ending soon — sent ~1 hour before end.",
        "placeholders": ["name", "auction_title", "auction_id", "current_bid", "app_url"],
        "subject": "⏰ Ending soon · {{auction_title}}",
        "header": "Auction with your bid ending soon",
        "body_html": (
            "<p>Hi {{name}},</p>"
            "<p>About 1 hour remains until the end of <strong>{{auction_title}}</strong>.</p>"
            '<div style="margin:18px 0;padding:14px 16px;background:#fafafa;border:1px solid #e5e7eb;border-radius:10px;">'
            '<div style="font-size:12px;color:#6b7280;text-transform:uppercase;letter-spacing:0.08em;">Current bid</div>'
            '<div style="font-size:24px;font-weight:700;margin-top:4px;">€{{current_bid}}</div></div>'
            f'<p><a href="{{{{app_url}}}}/auctions/{{{{auction_id}}}}" style="{_BTN_PRIMARY}">Open auction</a></p>'
        ),
    },
    "reserve_met_en": {
        "system": True, "lang": "en",
        "description": "Reserve price reached — congratulations email for the seller.",
        "placeholders": ["name", "auction_title", "auction_id", "current_bid", "reserve", "app_url"],
        "subject": "🎯 Reserve met · {{auction_title}}",
        "header": "Reserve price reached",
        "body_html": (
            "<p>Congratulations, {{name}}!</p>"
            "<p>The reserve price on your listing <strong>{{auction_title}}</strong> has been reached.</p>"
            '<div style="margin:18px 0;padding:14px 16px;background:#fafafa;border:1px solid #e5e7eb;border-radius:10px;">'
            '<div style="font-size:12px;color:#6b7280;text-transform:uppercase;letter-spacing:0.08em;">Reserve · Current</div>'
            '<div style="font-size:22px;font-weight:700;margin-top:4px;">€{{reserve}} → '
            '<span style="color:#1B4D3E;">€{{current_bid}}</span></div></div>'
            "<p>The auction is now guaranteed to sell at the current or a higher bid.</p>"
            f'<p><a href="{{{{app_url}}}}/auctions/{{{{auction_id}}}}" style="{_BTN_PRIMARY}">View auction</a></p>'
        ),
    },

    # ── RO translations ────────────────────────────────────────────────
    "password_reset_ro": {
        "system": True, "lang": "ro",
        "description": "Cod de resetare a parolei (OTP din 6 cifre).",
        "placeholders": ["name", "code", "ttl_min"],
        "subject": "autoandbid.com — Cod de resetare a parolei",
        "header": "Resetare parolă",
        "body_html": (
            '<p style="margin:0 0 16px 0;">Bună {{name}},</p>'
            '<p style="margin:0 0 16px 0;">Am primit o cerere de resetare a parolei '
            "pentru contul tău autoandbid.com.</p>"
            '<p style="margin:0 0 8px 0;">Codul tău de verificare (valabil {{ttl_min}} minute):</p>'
            '<div style="font-family:\'Courier New\',monospace;font-size:32px;'
            "letter-spacing:8px;background:#f6f7f8;padding:18px;text-align:center;"
            'border-radius:10px;border:1px solid #e5e7eb;margin:16px 0;">'
            "<strong>{{code}}</strong></div>"
            '<p style="color:#6b7280;font-size:13px;margin:24px 0 0 0;">'
            "Dacă nu ai inițiat această cerere, poți ignora în siguranță acest mesaj — "
            "parola ta nu va fi schimbată.</p>"
        ),
    },
    "outbid_ro": {
        "system": True, "lang": "ro",
        "description": "Ai fost depășit — se trimite ofertanților la apariția unei oferte mai mari.",
        "placeholders": ["name", "auction_title", "auction_id", "new_bid", "app_url"],
        "subject": "Ai fost depășit · {{auction_title}}",
        "header": "O nouă ofertă este înaintea ta",
        "body_html": (
            "<p>Bună, {{name}},</p>"
            "<p>Cineva a plasat o ofertă mai mare pentru <strong>{{auction_title}}</strong>.</p>"
            '<p style="font-size:20px;margin:20px 0;">Noua ofertă curentă: <strong>€{{new_bid}}</strong></p>'
            "<p>Pre-autorizarea ta a fost eliberată automat.</p>"
            f'<p><a href="{{{{app_url}}}}/auctions/{{{{auction_id}}}}" style="{_BTN_DARK}">Înapoi la licitație</a></p>'
        ),
    },
    "approved_ro": {
        "system": True, "lang": "ro",
        "description": "Anunțul a fost aprobat de moderator și este publicat.",
        "placeholders": ["name", "auction_title", "auction_id", "app_url"],
        "subject": "Anunț aprobat · {{auction_title}}",
        "header": "Anunțul tău a fost aprobat",
        "body_html": (
            "<p>Bună, {{name}},</p>"
            "<p>Anunțul tău pentru <strong>{{auction_title}}</strong> a fost aprobat și este activ.</p>"
            f'<p><a href="{{{{app_url}}}}/auctions/{{{{auction_id}}}}" style="{_BTN_DARK}">Vezi anunțul</a></p>'
        ),
    },
    "rejected_ro": {
        "system": True, "lang": "ro",
        "description": "Anunțul necesită modificări — trimis cu nota moderatorului.",
        "placeholders": ["name", "auction_title", "reason"],
        "subject": "Modificări necesare · {{auction_title}}",
        "header": "Anunțul necesită modificări",
        "body_html": (
            "<p>Bună, {{name}},</p>"
            "<p>După analiză, anunțul tău pentru <strong>{{auction_title}}</strong> nu a fost aprobat.</p>"
            '<p style="background:#fafafa;border:1px solid #e5e7eb;padding:14px;border-radius:8px;">'
            "<strong>Notă de la echipă:</strong><br/>{{reason | —}}</p>"
            "<p>Poți edita și trimite din nou.</p>"
        ),
    },
    "vin_delivery_ro": {
        "system": True, "lang": "ro",
        "description": "Număr VIN — trimis ofertantului câștigător.",
        "placeholders": ["name", "auction_title", "auction_id", "vin", "app_url"],
        "subject": "Număr VIN · {{auction_title}}",
        "header": "Număr VIN complet",
        "body_html": (
            "<p>Bună, {{name}},</p>"
            "<p>Iată VIN-ul complet pentru <strong>{{auction_title}}</strong>:</p>"
            '<div style="margin:22px 0;padding:18px;background:#fafafa;border:1px solid #e5e7eb;'
            'border-radius:10px;text-align:center;">'
            '<div style="font-family:ui-monospace,\'IBM Plex Mono\',monospace;font-size:22px;'
            'letter-spacing:4px;font-weight:600;">{{vin}}</div></div>'
            "<p>Poți efectua o verificare VIN printr-un service la alegere.</p>"
            f'<p><a href="{{{{app_url}}}}/auctions/{{{{auction_id}}}}" style="{_BTN_PRIMARY}">Înapoi la licitație</a></p>'
            '<p style="color:#6b7280;font-size:12px;margin-top:20px;">VIN-ul este furnizat '
            "informativ pentru a lua o decizie informată la licitație.</p>"
        ),
    },
    "seller_new_bid_ro": {
        "system": True, "lang": "ro",
        "description": "Ofertă nouă — anunță vânzătorul în timp real.",
        "placeholders": ["name", "auction_title", "auction_id", "bidder_name", "amount", "bid_count", "app_url"],
        "subject": "Ofertă nouă €{{amount}} · {{auction_title}}",
        "header": "Ofertă nouă în licitația ta",
        "body_html": (
            "<p>Bună, {{name}},</p>"
            "<p>Ofertă nouă pentru <strong>{{auction_title}}</strong>.</p>"
            '<div style="margin:20px 0;padding:16px;background:#fafafa;border:1px solid #e5e7eb;border-radius:10px;">'
            '<div style="font-size:12px;color:#6b7280;text-transform:uppercase;letter-spacing:0.1em;">Ofertă curentă</div>'
            '<div style="font-size:26px;font-weight:700;margin-top:4px;">€{{amount}}</div>'
            '<div style="font-size:13px;color:#6b7280;margin-top:6px;">de la {{bidder_name}} · total {{bid_count}} oferte</div>'
            "</div>"
            f'<p><a href="{{{{app_url}}}}/auctions/{{{{auction_id}}}}" style="{_BTN_PRIMARY}">Urmărește licitația</a></p>'
        ),
    },
    "seller_new_comment_ro": {
        "system": True, "lang": "ro",
        "description": "Comentariu nou la anunț — anunță vânzătorul.",
        "placeholders": ["name", "auction_title", "auction_id", "commenter_name", "snippet", "app_url"],
        "subject": "Comentariu nou · {{auction_title}}",
        "header": "Comentariu nou la anunțul tău",
        "body_html": (
            "<p>Bună, {{name}},</p>"
            "<p><strong>{{commenter_name}}</strong> a lăsat un comentariu la anunțul "
            "<strong>{{auction_title}}</strong>.</p>"
            '<blockquote style="margin:20px 0;padding:14px 18px;background:#fafafa;'
            'border-left:3px solid #1B4D3E;color:#111827;font-style:italic;">{{snippet}}</blockquote>'
            f'<p><a href="{{{{app_url}}}}/auctions/{{{{auction_id}}}}" style="{_BTN_DARK}">Răspunde</a></p>'
        ),
    },
    "ending_soon_watcher_ro": {
        "system": True, "lang": "ro",
        "description": "Licitație favorită se încheie curând — trimis cu ~1 oră înainte de final.",
        "placeholders": ["name", "auction_title", "auction_id", "current_bid", "app_url"],
        "subject": "⏰ Se încheie curând · {{auction_title}}",
        "header": "Licitație favorită se încheie curând",
        "body_html": (
            "<p>Bună, {{name}},</p>"
            "<p>Mai este aproximativ 1 oră până la finalul licitației <strong>{{auction_title}}</strong>.</p>"
            '<div style="margin:18px 0;padding:14px 16px;background:#fafafa;border:1px solid #e5e7eb;border-radius:10px;">'
            '<div style="font-size:12px;color:#6b7280;text-transform:uppercase;letter-spacing:0.08em;">Ofertă curentă</div>'
            '<div style="font-size:24px;font-weight:700;margin-top:4px;">€{{current_bid}}</div></div>'
            f'<p><a href="{{{{app_url}}}}/auctions/{{{{auction_id}}}}" style="{_BTN_PRIMARY}">Deschide licitația</a></p>'
        ),
    },
    "ending_soon_bidder_ro": {
        "system": True, "lang": "ro",
        "description": "Licitație cu oferta ta se încheie curând — trimis cu ~1 oră înainte de final.",
        "placeholders": ["name", "auction_title", "auction_id", "current_bid", "app_url"],
        "subject": "⏰ Se încheie curând · {{auction_title}}",
        "header": "Licitație cu oferta ta se încheie curând",
        "body_html": (
            "<p>Bună, {{name}},</p>"
            "<p>Mai este aproximativ 1 oră până la finalul licitației <strong>{{auction_title}}</strong>.</p>"
            '<div style="margin:18px 0;padding:14px 16px;background:#fafafa;border:1px solid #e5e7eb;border-radius:10px;">'
            '<div style="font-size:12px;color:#6b7280;text-transform:uppercase;letter-spacing:0.08em;">Ofertă curentă</div>'
            '<div style="font-size:24px;font-weight:700;margin-top:4px;">€{{current_bid}}</div></div>'
            f'<p><a href="{{{{app_url}}}}/auctions/{{{{auction_id}}}}" style="{_BTN_PRIMARY}">Deschide licitația</a></p>'
        ),
    },
    "reserve_met_ro": {
        "system": True, "lang": "ro",
        "description": "Prețul de rezervă a fost atins — email de felicitări pentru vânzător.",
        "placeholders": ["name", "auction_title", "auction_id", "current_bid", "reserve", "app_url"],
        "subject": "🎯 Rezerva atinsă · {{auction_title}}",
        "header": "Prețul de rezervă a fost atins",
        "body_html": (
            "<p>Felicitări, {{name}}!</p>"
            "<p>Prețul de rezervă al anunțului tău <strong>{{auction_title}}</strong> a fost atins.</p>"
            '<div style="margin:18px 0;padding:14px 16px;background:#fafafa;border:1px solid #e5e7eb;border-radius:10px;">'
            '<div style="font-size:12px;color:#6b7280;text-transform:uppercase;letter-spacing:0.08em;">Rezervă · Curent</div>'
            '<div style="font-size:22px;font-weight:700;margin-top:4px;">€{{reserve}} → '
            '<span style="color:#1B4D3E;">€{{current_bid}}</span></div></div>'
            "<p>Licitația este acum garantat vandabilă la oferta curentă sau una mai mare.</p>"
            f'<p><a href="{{{{app_url}}}}/auctions/{{{{auction_id}}}}" style="{_BTN_PRIMARY}">Vezi licitația</a></p>'
        ),
    },

    # ── Auction won — Buyer (rich version with seller contacts + helper note) ──
    "auction_won_buyer_bg": {
        "system": True, "lang": "bg",
        "description": "Купувачът печели търга — съдържа контакти на продавача и бележка за застраховка/нотариус.",
        "placeholders": ["name", "auction_title", "auction_id", "price", "seller_name", "seller_email", "seller_phone", "app_url"],
        "subject": "🏁 Поздравления — спечелихте · {{auction_title}}",
        "header": "Поздравления — спечелихте търга",
        "body_html": (
            "<p>Здравейте, {{name}},</p>"
            "<p>Вие сте печелившият купувач за <strong>{{auction_title}}</strong>.</p>"
            '<p style="font-size:20px;margin:20px 0;">Крайна цена: <strong>€{{price}}</strong></p>'
            '<div style="margin:22px 0;padding:18px 20px;border:1px solid #e5e7eb;border-radius:14px;">'
            '<div style="font-size:11px;letter-spacing:0.14em;text-transform:uppercase;color:#6b7280;font-weight:600;margin-bottom:8px;">Контакти на продавача</div>'
            '<div style="font-size:15px;font-weight:600;color:#0b0f1a;">{{seller_name}}</div>'
            '<div style="font-size:14px;margin-top:6px;"><a href="mailto:{{seller_email}}" style="color:#1B4D3E;">{{seller_email}}</a></div>'
            '<div style="font-size:14px;margin-top:4px;"><a href="tel:{{seller_phone}}" style="color:#1B4D3E;">{{seller_phone}}</a></div>'
            "</div>"
            '<div style="margin:22px 0;padding:18px 20px;background:#f0fdf4;border:1px solid #bbf7d0;border-radius:14px;">'
            '<div style="font-size:11px;letter-spacing:0.14em;text-transform:uppercase;color:#166534;font-weight:600;margin-bottom:6px;">Помощ от Auto&amp;Bid</div>'
            "<p style=\"margin:0;\">За <strong>застрахователна оценка</strong> при прехвърлянето или за "
            "<strong>препоръка за нотариус</strong>, можете да се обърнете към нашия екип — ще ви свържем "
            "с проверени партньори.</p></div>"
            f'<p><a href="{{{{app_url}}}}/auctions/{{{{auction_id}}}}" style="{_BTN_PRIMARY}">Виж търга</a></p>'
        ),
    },
    "auction_won_buyer_en": {
        "system": True, "lang": "en",
        "description": "Buyer wins the auction — contains seller contacts + insurance/notary helper note.",
        "placeholders": ["name", "auction_title", "auction_id", "price", "seller_name", "seller_email", "seller_phone", "app_url"],
        "subject": "🏁 Congratulations — you won · {{auction_title}}",
        "header": "Congratulations — you won the auction",
        "body_html": (
            "<p>Hi {{name}},</p>"
            "<p>You are the winning buyer for <strong>{{auction_title}}</strong>.</p>"
            '<p style="font-size:20px;margin:20px 0;">Final price: <strong>€{{price}}</strong></p>'
            '<div style="margin:22px 0;padding:18px 20px;border:1px solid #e5e7eb;border-radius:14px;">'
            '<div style="font-size:11px;letter-spacing:0.14em;text-transform:uppercase;color:#6b7280;font-weight:600;margin-bottom:8px;">Seller contact</div>'
            '<div style="font-size:15px;font-weight:600;color:#0b0f1a;">{{seller_name}}</div>'
            '<div style="font-size:14px;margin-top:6px;"><a href="mailto:{{seller_email}}" style="color:#1B4D3E;">{{seller_email}}</a></div>'
            '<div style="font-size:14px;margin-top:4px;"><a href="tel:{{seller_phone}}" style="color:#1B4D3E;">{{seller_phone}}</a></div>'
            "</div>"
            '<div style="margin:22px 0;padding:18px 20px;background:#f0fdf4;border:1px solid #bbf7d0;border-radius:14px;">'
            '<div style="font-size:11px;letter-spacing:0.14em;text-transform:uppercase;color:#166534;font-weight:600;margin-bottom:6px;">Help from Auto&amp;Bid</div>'
            "<p style=\"margin:0;\">For an <strong>insurance valuation</strong> during transfer or a "
            "<strong>notary recommendation</strong>, you can reach out to our team — we'll connect you with vetted partners.</p></div>"
            f'<p><a href="{{{{app_url}}}}/auctions/{{{{auction_id}}}}" style="{_BTN_PRIMARY}">View auction</a></p>'
        ),
    },
    "auction_won_buyer_ro": {
        "system": True, "lang": "ro",
        "description": "Cumpărătorul câștigă licitația — conține contactele vânzătorului + notă despre asigurare/notar.",
        "placeholders": ["name", "auction_title", "auction_id", "price", "seller_name", "seller_email", "seller_phone", "app_url"],
        "subject": "🏁 Felicitări — ai câștigat · {{auction_title}}",
        "header": "Felicitări — ai câștigat licitația",
        "body_html": (
            "<p>Bună, {{name}},</p>"
            "<p>Ești cumpărătorul câștigător pentru <strong>{{auction_title}}</strong>.</p>"
            '<p style="font-size:20px;margin:20px 0;">Preț final: <strong>€{{price}}</strong></p>'
            '<div style="margin:22px 0;padding:18px 20px;border:1px solid #e5e7eb;border-radius:14px;">'
            '<div style="font-size:11px;letter-spacing:0.14em;text-transform:uppercase;color:#6b7280;font-weight:600;margin-bottom:8px;">Contact vânzător</div>'
            '<div style="font-size:15px;font-weight:600;color:#0b0f1a;">{{seller_name}}</div>'
            '<div style="font-size:14px;margin-top:6px;"><a href="mailto:{{seller_email}}" style="color:#1B4D3E;">{{seller_email}}</a></div>'
            '<div style="font-size:14px;margin-top:4px;"><a href="tel:{{seller_phone}}" style="color:#1B4D3E;">{{seller_phone}}</a></div>'
            "</div>"
            '<div style="margin:22px 0;padding:18px 20px;background:#f0fdf4;border:1px solid #bbf7d0;border-radius:14px;">'
            '<div style="font-size:11px;letter-spacing:0.14em;text-transform:uppercase;color:#166534;font-weight:600;margin-bottom:6px;">Ajutor de la Auto&amp;Bid</div>'
            "<p style=\"margin:0;\">Pentru o <strong>evaluare de asigurare</strong> la transfer sau o "
            "<strong>recomandare de notar</strong>, ne poți contacta — te punem în legătură cu parteneri verificați.</p></div>"
            f'<p><a href="{{{{app_url}}}}/auctions/{{{{auction_id}}}}" style="{_BTN_PRIMARY}">Vezi licitația</a></p>'
        ),
    },

    # ── Auction won — Seller (notifies seller; includes buyer contacts) ─────
    "auction_won_seller_bg": {
        "system": True, "lang": "bg",
        "description": "Уведомява продавача, че колата му е спечелена; съдържа имейл и телефон на купувача.",
        "placeholders": ["name", "auction_title", "auction_id", "price", "buyer_name", "buyer_email", "buyer_phone", "app_url"],
        "subject": "🎉 Продадена — {{auction_title}}",
        "header": "Вашата кола е продадена",
        "body_html": (
            "<p>Поздравления, {{name}}!</p>"
            "<p>Търгът за <strong>{{auction_title}}</strong> приключи успешно — имате печеливш купувач.</p>"
            '<p style="font-size:20px;margin:20px 0;">Крайна цена: <strong>€{{price}}</strong></p>'
            '<div style="margin:22px 0;padding:18px 20px;border:1px solid #e5e7eb;border-radius:14px;">'
            '<div style="font-size:11px;letter-spacing:0.14em;text-transform:uppercase;color:#6b7280;font-weight:600;margin-bottom:8px;">Контакти на купувача</div>'
            '<div style="font-size:15px;font-weight:600;color:#0b0f1a;">{{buyer_name}}</div>'
            '<div style="font-size:14px;margin-top:6px;"><a href="mailto:{{buyer_email}}" style="color:#1B4D3E;">{{buyer_email}}</a></div>'
            '<div style="font-size:14px;margin-top:4px;"><a href="tel:{{buyer_phone}}" style="color:#1B4D3E;">{{buyer_phone}}</a></div>'
            "</div>"
            "<p>Свържете се с купувача в рамките на 48 часа, за да договорите детайлите по плащане и прехвърляне на собствеността. "
            "Екипът на Auto&amp;Bid е насреща с препоръки за нотариус и застрахователна оценка.</p>"
            f'<p><a href="{{{{app_url}}}}/auctions/{{{{auction_id}}}}" style="{_BTN_PRIMARY}">Виж обявата</a></p>'
        ),
    },
    "auction_won_seller_en": {
        "system": True, "lang": "en",
        "description": "Notifies the seller that their car was won; includes buyer's email and phone.",
        "placeholders": ["name", "auction_title", "auction_id", "price", "buyer_name", "buyer_email", "buyer_phone", "app_url"],
        "subject": "🎉 Sold — {{auction_title}}",
        "header": "Your car has been sold",
        "body_html": (
            "<p>Congratulations, {{name}}!</p>"
            "<p>The auction for <strong>{{auction_title}}</strong> ended successfully — you have a winning buyer.</p>"
            '<p style="font-size:20px;margin:20px 0;">Final price: <strong>€{{price}}</strong></p>'
            '<div style="margin:22px 0;padding:18px 20px;border:1px solid #e5e7eb;border-radius:14px;">'
            '<div style="font-size:11px;letter-spacing:0.14em;text-transform:uppercase;color:#6b7280;font-weight:600;margin-bottom:8px;">Buyer contact</div>'
            '<div style="font-size:15px;font-weight:600;color:#0b0f1a;">{{buyer_name}}</div>'
            '<div style="font-size:14px;margin-top:6px;"><a href="mailto:{{buyer_email}}" style="color:#1B4D3E;">{{buyer_email}}</a></div>'
            '<div style="font-size:14px;margin-top:4px;"><a href="tel:{{buyer_phone}}" style="color:#1B4D3E;">{{buyer_phone}}</a></div>'
            "</div>"
            "<p>Please reach out to the buyer within 48 hours to arrange payment and ownership transfer. "
            "The Auto&amp;Bid team is on hand with notary recommendations and insurance valuations.</p>"
            f'<p><a href="{{{{app_url}}}}/auctions/{{{{auction_id}}}}" style="{_BTN_PRIMARY}">View listing</a></p>'
        ),
    },
    "auction_won_seller_ro": {
        "system": True, "lang": "ro",
        "description": "Anunță vânzătorul că mașina sa a fost câștigată; conține emailul și telefonul cumpărătorului.",
        "placeholders": ["name", "auction_title", "auction_id", "price", "buyer_name", "buyer_email", "buyer_phone", "app_url"],
        "subject": "🎉 Vândut — {{auction_title}}",
        "header": "Mașina ta a fost vândută",
        "body_html": (
            "<p>Felicitări, {{name}}!</p>"
            "<p>Licitația pentru <strong>{{auction_title}}</strong> s-a încheiat cu succes — ai un cumpărător câștigător.</p>"
            '<p style="font-size:20px;margin:20px 0;">Preț final: <strong>€{{price}}</strong></p>'
            '<div style="margin:22px 0;padding:18px 20px;border:1px solid #e5e7eb;border-radius:14px;">'
            '<div style="font-size:11px;letter-spacing:0.14em;text-transform:uppercase;color:#6b7280;font-weight:600;margin-bottom:8px;">Contact cumpărător</div>'
            '<div style="font-size:15px;font-weight:600;color:#0b0f1a;">{{buyer_name}}</div>'
            '<div style="font-size:14px;margin-top:6px;"><a href="mailto:{{buyer_email}}" style="color:#1B4D3E;">{{buyer_email}}</a></div>'
            '<div style="font-size:14px;margin-top:4px;"><a href="tel:{{buyer_phone}}" style="color:#1B4D3E;">{{buyer_phone}}</a></div>'
            "</div>"
            "<p>Contactează cumpărătorul în maxim 48 de ore pentru a stabili plata și transferul proprietății. "
            "Echipa Auto&amp;Bid te ajută cu recomandări de notar și evaluări de asigurare.</p>"
            f'<p><a href="{{{{app_url}}}}/auctions/{{{{auction_id}}}}" style="{_BTN_PRIMARY}">Vezi anunțul</a></p>'
        ),
    },

    # ── 3-day digest (new listings + ending soon) ───────────────────────────
    "digest_3day_bg": {
        "system": True, "lang": "bg",
        "description": "Дайджест на всеки 3 дни: нови обяви и скоро изтичащи търгове.",
        "placeholders": ["name", "new_html", "ending_html", "app_url"],
        "subject": "Auto&Bid · Какво ново — нови обяви и скоро изтичащи",
        "header": "Какво ново в Auto&Bid",
        "body_html": (
            "<p>Здравейте, {{name}},</p>"
            "<p>Ето кратък преглед на новите обяви и търговете, които приключват скоро.</p>"
            '<div style="margin:24px 0 6px 0;font-size:11px;letter-spacing:0.14em;text-transform:uppercase;color:#1B4D3E;font-weight:600;">Нови обяви</div>'
            "{{new_html}}"
            '<div style="margin:28px 0 6px 0;font-size:11px;letter-spacing:0.14em;text-transform:uppercase;color:#9a3412;font-weight:600;">Скоро изтичат</div>'
            "{{ending_html}}"
            f'<p style="margin-top:24px;"><a href="{{{{app_url}}}}/auctions" style="{_BTN_PRIMARY}">Виж всички търгове</a></p>'
            '<p style="color:#6b7280;font-size:12px;margin-top:24px;">Получавате този дайджест на всеки 3 дни. Можете да го изключите от настройките за известия.</p>'
        ),
    },
    "digest_3day_en": {
        "system": True, "lang": "en",
        "description": "Every-3-day digest: new listings and auctions ending soon.",
        "placeholders": ["name", "new_html", "ending_html", "app_url"],
        "subject": "Auto&Bid · What's new — new listings and ending soon",
        "header": "What's new on Auto&Bid",
        "body_html": (
            "<p>Hi {{name}},</p>"
            "<p>Here's a quick look at the new listings and auctions ending soon.</p>"
            '<div style="margin:24px 0 6px 0;font-size:11px;letter-spacing:0.14em;text-transform:uppercase;color:#1B4D3E;font-weight:600;">New listings</div>'
            "{{new_html}}"
            '<div style="margin:28px 0 6px 0;font-size:11px;letter-spacing:0.14em;text-transform:uppercase;color:#9a3412;font-weight:600;">Ending soon</div>'
            "{{ending_html}}"
            f'<p style="margin-top:24px;"><a href="{{{{app_url}}}}/auctions" style="{_BTN_PRIMARY}">View all auctions</a></p>'
            '<p style="color:#6b7280;font-size:12px;margin-top:24px;">You receive this digest every 3 days. You can disable it in your notification preferences.</p>'
        ),
    },
    "digest_3day_ro": {
        "system": True, "lang": "ro",
        "description": "Newsletter la fiecare 3 zile: anunțuri noi și licitații care se încheie curând.",
        "placeholders": ["name", "new_html", "ending_html", "app_url"],
        "subject": "Auto&Bid · Ce e nou — anunțuri noi și care se încheie",
        "header": "Ce e nou pe Auto&Bid",
        "body_html": (
            "<p>Bună, {{name}},</p>"
            "<p>Iată un rezumat al anunțurilor noi și al licitațiilor care se încheie curând.</p>"
            '<div style="margin:24px 0 6px 0;font-size:11px;letter-spacing:0.14em;text-transform:uppercase;color:#1B4D3E;font-weight:600;">Anunțuri noi</div>'
            "{{new_html}}"
            '<div style="margin:28px 0 6px 0;font-size:11px;letter-spacing:0.14em;text-transform:uppercase;color:#9a3412;font-weight:600;">Se încheie curând</div>'
            "{{ending_html}}"
            f'<p style="margin-top:24px;"><a href="{{{{app_url}}}}/auctions" style="{_BTN_PRIMARY}">Vezi toate licitațiile</a></p>'
            '<p style="color:#6b7280;font-size:12px;margin-top:24px;">Primești acest rezumat la fiecare 3 zile. Îl poți dezactiva din preferințele de notificare.</p>'
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


def localized_render(
    base_slug: str,
    lang: Optional[str],
    variables: Optional[dict[str, Any]] = None,
) -> tuple[str, str, str]:
    """Same as `render`, but picks the right language variant.

    Resolution order for lang="ro":
      1. `<base>_ro`     — explicit Romanian translation
      2. `<base>_bg`     — Bulgarian (default site language)
      3. `<base>`        — un-suffixed (handles transitional registry state)

    Falls back gracefully so we never crash on a missing locale. Callers
    pass the user's stored `lang` preference; anonymous flows default to
    Bulgarian via the recipient_lookup before reaching here.
    """
    lang_norm = (lang or "bg").lower()[:2]
    for candidate in (f"{base_slug}_{lang_norm}", f"{base_slug}_bg", base_slug):
        if candidate in SYSTEM_TEMPLATES:
            return render(candidate, variables)
    # Nothing matched — let the caller see a clear error.
    raise KeyError(f"No template variant found for base {base_slug!r} (lang={lang_norm!r})")


async def seed_defaults_on_startup(db) -> int:
    """Write any missing system templates into `site_settings.email_templates`.

    DEPLOY SAFETY (per user request, 2026-05-16):
    Admin-edited templates are NEVER overwritten by a redeploy. The seeder
    skips every slug that already exists in the DB — even if the in-code
    registry default has been updated since the last deploy. This is by
    design: HTML edits made through the admin UI are the source of truth
    once written.

    Operationally:
      • First-ever deploy on a fresh DB → all system templates seeded.
      • Subsequent deploys → only NEW slugs (e.g. a freshly-added one in
        the registry) are seeded; everything else is left alone.
      • Deprecated slugs (listed in `_REMOVED_SLUGS`) are pruned from the
        DB so the admin UI no longer surfaces them.
      • To force-restore a specific template to its in-code default,
        the admin clicks "Reset" in the UI, which calls
        `POST /admin/email-templates/{slug}/reset`.

    Idempotent. Returns the number of new entries seeded so the startup
    log shows what happened.
    """
    from datetime import datetime, timezone
    s = await db.site_settings.find_one({"id": "global"}, {"_id": 0, "email_templates": 1}) or {}
    existing = s.get("email_templates") or {}
    # 1. Prune deprecated slugs (replaced by newer templates).
    pruned = await _prune_removed_slugs(db, existing)
    if pruned:
        # Re-read after the prune so subsequent merges don't resurrect them.
        s = await db.site_settings.find_one({"id": "global"}, {"_id": 0, "email_templates": 1}) or {}
        existing = s.get("email_templates") or {}
    # 2. Seed any new system slugs (additive only).
    additions: dict[str, dict] = {}
    skipped_existing = 0
    for slug, tpl in SYSTEM_TEMPLATES.items():
        if slug in existing:
            skipped_existing += 1
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
        logger.info(
            "email_templates: no new system defaults to seed (preserved %d existing entries — admin edits intact)",
            skipped_existing,
        )
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
    logger.info(
        "email_templates: seeded %d new system defaults (preserved %d existing — admin edits intact)",
        len(additions), skipped_existing,
    )
    return len(additions)


# Slugs we have explicitly retired. They are unset from
# `site_settings.email_templates` on every boot so the admin UI no longer
# lists them. Code paths that previously rendered them have been migrated
# to their replacements (see comments).
_REMOVED_SLUGS: tuple[str, ...] = (
    # 2026-05-17 — replaced by auction_won_buyer_<lang> which carries seller
    # contacts + insurance/notary helper note.
    "won", "won_en", "won_ro",
)


async def _prune_removed_slugs(db, existing: dict) -> list[str]:
    """Unset deprecated slugs from `site_settings.email_templates`.

    Returns the list of slugs actually removed. Safe on a fresh DB
    (Mongo `$unset` on a missing key is a no-op and we filter first).
    """
    from datetime import datetime, timezone
    to_remove = [s for s in _REMOVED_SLUGS if s in existing]
    if not to_remove:
        return []
    unset_ops = {f"email_templates.{s}": "" for s in to_remove}
    await db.site_settings.update_one(
        {"id": "global"},
        {"$unset": unset_ops,
         "$set": {"updated_at": datetime.now(timezone.utc).isoformat()}},
    )
    logger.info("email_templates: pruned %d deprecated slugs: %s",
                len(to_remove), ", ".join(to_remove))
    return to_remove


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
