"""
Auto-translation helper for auction descriptions (BG → RO / EN).

Hybrid provider selection so the same code works in the Emergent preview AND
on self-hosted production (Hetzner):

  1. If `GEMINI_API_KEY` is set → direct `google-generativeai` SDK (production).
  2. Else if `EMERGENT_LLM_KEY` is set → Emergent Universal Key via
     `emergentintegrations` (Emergent preview — not available on Hetzner).
  3. Else → return None (caller keeps the Bulgarian original).

Translations are cached on the auction document (`description_ro`,
`description_en`) by the caller, so this function is invoked at most once
per target language per description revision.
"""
from __future__ import annotations

import asyncio
import logging
import os
from typing import Optional

logger = logging.getLogger(__name__)

_LANG_NAMES = {"ro": "Romanian", "en": "English", "bg": "Bulgarian"}
_TRANSLATE_TIMEOUT_SEC = 30
# Gemini 2.5 Flash — fast, cheap, reliable quality for medium-length prose.
_MODEL_NAME = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")


def _prompt(target_name: str, text: str) -> str:
    return (
        f"You are a professional translator. Translate the following car-listing "
        f"description into {target_name}. Keep the tone neutral and journalistic, "
        f"preserve line breaks, do not add comments or metadata. If the input is "
        f"already in the target language, return it unchanged. Output only the "
        f"translation.\n\n--- TEXT ---\n{text[:8000]}"
    )


async def _translate_via_gemini(text: str, target_name: str, api_key: str) -> Optional[str]:
    """Direct Google Gemini SDK path — used on self-hosted production."""
    try:
        import google.generativeai as genai
    except Exception as e:  # pragma: no cover - import defensive
        logger.warning("google.generativeai unavailable: %s", e)
        return None

    def _call() -> Optional[str]:
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel(_MODEL_NAME)
        resp = model.generate_content(_prompt(target_name, text))
        out = getattr(resp, "text", None)
        return out.strip() if out else None

    try:
        return await asyncio.wait_for(asyncio.to_thread(_call), timeout=_TRANSLATE_TIMEOUT_SEC)
    except asyncio.TimeoutError:
        logger.warning("gemini timeout after %ss", _TRANSLATE_TIMEOUT_SEC)
        return None
    except Exception as e:
        logger.warning("gemini error: %s", e)
        return None


async def _translate_via_emergent(text: str, target_name: str, api_key: str) -> Optional[str]:
    """Emergent Universal Key path — used on the Emergent preview where
    `emergentintegrations` is pre-installed and the universal key handles
    routing across providers. Not available on Hetzner — hence the Gemini
    path above is the production default."""
    try:
        from emergentintegrations.llm.chat import LlmChat, UserMessage
    except Exception as e:
        logger.warning("emergentintegrations unavailable: %s", e)
        return None

    system = (
        f"You are a professional translator. Translate user-provided car-listing "
        f"text into {target_name}. Keep the tone neutral and journalistic, "
        f"preserve line breaks, do not add comments or metadata. If the input is "
        f"already in the target language, return it unchanged. Output only the "
        f"translation."
    )

    try:
        chat = LlmChat(
            api_key=api_key,
            session_id=f"translate-{target_name.lower()}",
            system_message=system,
        ).with_model("gemini", "gemini-2.5-flash")
        msg = UserMessage(text=text[:8000])
        response = await asyncio.wait_for(chat.send_message(msg), timeout=_TRANSLATE_TIMEOUT_SEC)
        if isinstance(response, str):
            return response.strip()
        return str(response).strip() if response else None
    except asyncio.TimeoutError:
        logger.warning("emergent translate timeout after %ss", _TRANSLATE_TIMEOUT_SEC)
        return None
    except Exception as e:
        logger.warning("emergent translate error: %s", e)
        return None


async def translate_text(text: str, target_lang: str) -> Optional[str]:
    """Translate `text` into `target_lang` ('ro' | 'en' | 'bg').

    Returns the translated string on success, or None on any failure
    (missing API key, network, quota, malformed response). Caller decides
    fallback behaviour (usually: return the original Bulgarian text).
    """
    if not text or not text.strip():
        return ""
    target = (target_lang or "").lower()
    if target not in _LANG_NAMES:
        return None
    if target == "bg":
        # No-op: our canonical source language.
        return text
    target_name = _LANG_NAMES[target]

    gemini_key = os.environ.get("GEMINI_API_KEY", "").strip()
    if gemini_key:
        return await _translate_via_gemini(text, target_name, gemini_key)

    emergent_key = os.environ.get("EMERGENT_LLM_KEY", "").strip()
    if emergent_key:
        return await _translate_via_emergent(text, target_name, emergent_key)

    logger.warning(
        "translate_text: no provider key set (GEMINI_API_KEY or EMERGENT_LLM_KEY) — skipping"
    )
    return None



# ---------------------------------------------------------------------------
# City / place name transliteration
# ---------------------------------------------------------------------------
#
# Mobile.bg (and every Bulgarian classifieds portal) publishes city names in
# Cyrillic. Our frontend stores cities as Latin strings so they render nicely
# across .bg / .ro / .com tenants and line up with existing facet filters.
# Gemini (or the Emergent universal key fallback) is the fastest way to get a
# correct transliteration + translation in one shot — it handles special cases
# like "Велико Търново" → "Veliko Tarnovo" that a naive char-map gets wrong.
#
# Static fallback: if no LLM provider is reachable we fall back to the
# official Bulgarian-state transliteration scheme (ISO 9, Law № 4 / 2009).

_BG_TO_LATIN_MAP = {
    "а": "a", "б": "b", "в": "v", "г": "g", "д": "d", "е": "e", "ж": "zh",
    "з": "z", "и": "i", "й": "y", "к": "k", "л": "l", "м": "m", "н": "n",
    "о": "o", "п": "p", "р": "r", "с": "s", "т": "t", "у": "u", "ф": "f",
    "х": "h", "ц": "ts", "ч": "ch", "ш": "sh", "щ": "sht", "ъ": "a",
    "ь": "y", "ю": "yu", "я": "ya",
}

# Curated overrides for the ~40 biggest Bulgarian cities — the official
# street-sign spelling is not always the same as the ISO 9 transliteration
# (e.g. "София" is officially "Sofia", not "Sofiya"). We keep the LLM path
# as a fallback for obscure places and typos.
_CITY_OVERRIDES = {
    "софия": "Sofia", "пловдив": "Plovdiv", "варна": "Varna",
    "бургас": "Burgas", "русе": "Ruse", "стара загора": "Stara Zagora",
    "плевен": "Pleven", "сливен": "Sliven", "добрич": "Dobrich",
    "шумен": "Shumen", "перник": "Pernik", "хасково": "Haskovo",
    "ямбол": "Yambol", "пазарджик": "Pazardzhik", "благоевград": "Blagoevgrad",
    "велико търново": "Veliko Tarnovo", "враца": "Vratsa", "габрово": "Gabrovo",
    "асеновград": "Asenovgrad", "видин": "Vidin", "казанлък": "Kazanlak",
    "кърджали": "Kardzhali", "кюстендил": "Kyustendil", "монтана": "Montana",
    "силистра": "Silistra", "търговище": "Targovishte", "разград": "Razgrad",
    "ловеч": "Lovech", "смолян": "Smolyan", "дупница": "Dupnitsa",
    "свищов": "Svishtov", "червен бряг": "Cherven Bryag", "димитровград": "Dimitrovgrad",
    "гоце делчев": "Gotse Delchev", "петрич": "Petrich", "сандански": "Sandanski",
    "лом": "Lom", "попово": "Popovo", "айтос": "Aytos", "несебър": "Nesebar",
    "созопол": "Sozopol", "поморие": "Pomorie", "свиленград": "Svilengrad",
    "банско": "Bansko", "самоков": "Samokov", "елин пелин": "Elin Pelin",
    "ботевград": "Botevgrad", "берковица": "Berkovitsa",
}


def _static_transliterate_bg(text: str) -> str:
    """Deterministic fallback used when no LLM provider is available.
    Lossy but close enough for rare production corner-cases."""
    out: list[str] = []
    for ch in text:
        lower = ch.lower()
        if lower in _BG_TO_LATIN_MAP:
            mapped = _BG_TO_LATIN_MAP[lower]
            out.append(mapped.capitalize() if ch.isupper() else mapped)
        else:
            out.append(ch)
    return "".join(out)


def _has_cyrillic(text: str) -> bool:
    return any("\u0400" <= ch <= "\u04FF" for ch in text or "")


async def transliterate_city_to_latin(name: str) -> str:
    """Return the Latin-script form of a Bulgarian (Cyrillic) city/place.
    If `name` is already Latin or empty, returns it unchanged. On LLM
    failure, falls back to the deterministic char-map so the caller
    always gets a usable Latin string.
    """
    name = (name or "").strip()
    if not name or not _has_cyrillic(name):
        return name

    # Fast-path: well-known city — avoid an LLM round-trip entirely.
    key = name.lower().strip()
    if key in _CITY_OVERRIDES:
        return _CITY_OVERRIDES[key]

    prompt = (
        "Transliterate the following Bulgarian city or place name into standard "
        "Latin script used on English maps (e.g. 'София' → 'Sofia', "
        "'Велико Търново' → 'Veliko Tarnovo', 'Пловдив' → 'Plovdiv'). Return "
        "ONLY the Latin form, no quotes, no commentary.\n\nInput: " + name
    )

    gemini_key = os.environ.get("GEMINI_API_KEY", "").strip()
    if gemini_key:
        try:
            import google.generativeai as genai

            def _call() -> Optional[str]:
                genai.configure(api_key=gemini_key)
                model = genai.GenerativeModel(_MODEL_NAME)
                resp = model.generate_content(prompt)
                out = getattr(resp, "text", None)
                return out.strip() if out else None

            out = await asyncio.wait_for(asyncio.to_thread(_call), timeout=8)
            if out:
                return out.splitlines()[0].strip().strip('"').strip("'")
        except Exception as e:
            logger.warning("gemini city transliteration error: %s", e)

    emergent_key = os.environ.get("EMERGENT_LLM_KEY", "").strip()
    if emergent_key:
        try:
            from emergentintegrations.llm.chat import LlmChat, UserMessage
            chat = LlmChat(
                api_key=emergent_key,
                session_id="transliterate-city",
                system_message="You transliterate Bulgarian place names into "
                               "standard Latin script. Return only the Latin form.",
            ).with_model("gemini", "gemini-2.5-flash")
            msg = UserMessage(text=prompt)
            response = await asyncio.wait_for(chat.send_message(msg), timeout=8)
            text_out = response if isinstance(response, str) else str(response or "")
            text_out = text_out.strip().splitlines()[0].strip().strip('"').strip("'")
            if text_out:
                return text_out
        except Exception as e:
            logger.warning("emergent city transliteration error: %s", e)

    # Final fallback
    return _static_transliterate_bg(name)


# ---------------------------------------------------------------------------
# Country resolver (based on the request's tenant domain)
# ---------------------------------------------------------------------------
#
# Each TLD maps to a canonical Latin country name that matches the enum in
# `carTranslations.js`. The frontend i18n layer re-translates the label.

_DOMAIN_TO_COUNTRY = {
    "bg": "Bulgaria",
    "ro": "Romania",
    "com": "Bulgaria",  # default tenant — .com serves Bulgaria listings
}


def country_from_host(host: str) -> str:
    """Extract the TLD from a request host and return the canonical
    Latin-script country name for it. Defaults to Bulgaria for unknown
    TLDs so imports never land without a country."""
    h = (host or "").strip().lower()
    if not h:
        return _DOMAIN_TO_COUNTRY["com"]
    # Drop port if present
    h = h.split(":", 1)[0]
    tld = h.rsplit(".", 1)[-1]
    return _DOMAIN_TO_COUNTRY.get(tld, _DOMAIN_TO_COUNTRY["com"])
