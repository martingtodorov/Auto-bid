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
