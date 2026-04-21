"""
Lightweight auto-translation helper backed by Emergent LLM universal key.
Used to translate auction descriptions (and other long-form seller text)
from the canonical Bulgarian into Romanian and English on demand.

Results are cached in the auction document (`description_ro`, `description_en`)
so we only pay for translation once per description revision.
"""
from __future__ import annotations

import asyncio
import logging
import os
from typing import Optional

logger = logging.getLogger(__name__)

_LANG_NAMES = {"ro": "Romanian", "en": "English", "bg": "Bulgarian"}
_TRANSLATE_TIMEOUT_SEC = 30


async def translate_text(text: str, target_lang: str) -> Optional[str]:
    """Translate `text` into target_lang ('ro' | 'en' | 'bg').

    Returns the translated string on success, or None on any failure
    (network, quota, malformed response). Caller decides fallback.
    """
    if not text or not text.strip():
        return ""
    target = (target_lang or "").lower()
    if target not in _LANG_NAMES:
        return None

    api_key = os.environ.get("EMERGENT_LLM_KEY")
    if not api_key:
        logger.warning("translate_text: EMERGENT_LLM_KEY missing")
        return None

    # Lazy import so the backend still starts even if emergentintegrations has issues.
    try:
        from emergentintegrations.llm.chat import LlmChat, UserMessage
    except Exception as e:  # pragma: no cover - import defensive
        logger.warning("emergentintegrations unavailable: %s", e)
        return None

    target_name = _LANG_NAMES[target]
    system = (
        f"You are a professional translator. Translate user-provided car-listing text into "
        f"{target_name}. Keep the tone neutral and journalistic, preserve line breaks, do not "
        f"add comments or metadata. If the input is already in the target language, return it "
        f"unchanged. Output only the translation."
    )

    try:
        chat = LlmChat(
            api_key=api_key,
            session_id=f"translate-{target}",
            system_message=system,
        ).with_model("gemini", "gemini-2.5-flash")
        msg = UserMessage(text=text[:8000])
        response = await asyncio.wait_for(
            chat.send_message(msg), timeout=_TRANSLATE_TIMEOUT_SEC
        )
        if isinstance(response, str):
            return response.strip()
        return str(response).strip() if response else None
    except asyncio.TimeoutError:
        logger.warning("translate_text timeout after %ss (lang=%s)", _TRANSLATE_TIMEOUT_SEC, target)
        return None
    except Exception as e:
        logger.warning("translate_text error (lang=%s): %s", target, e)
        return None
