"""
Auto-translation helper for auction descriptions (BG → RO / EN).

Uses the direct `google.generativeai` SDK (Gemini) so it works on any
self-hosted server. `GEMINI_API_KEY` is read from env (see
`/app/deploy/hetzner/env-templates/backend.env.example`). Get one free at
https://aistudio.google.com/apikey.

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


def _build_prompt(target_name: str, text: str) -> str:
    return (
        f"You are a professional translator. Translate the following car-listing "
        f"description into {target_name}. Keep the tone neutral and journalistic, "
        f"preserve line breaks, do not add comments or metadata. If the input is "
        f"already in the target language, return it unchanged. Output only the "
        f"translation.\n\n--- TEXT ---\n{text[:8000]}"
    )


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

    api_key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not api_key:
        logger.warning("translate_text: GEMINI_API_KEY missing — skipping translation")
        return None

    # Lazy import so server boot doesn't depend on the SDK being installed.
    try:
        import google.generativeai as genai
    except Exception as e:  # pragma: no cover - import defensive
        logger.warning("google.generativeai unavailable: %s", e)
        return None

    target_name = _LANG_NAMES[target]
    prompt = _build_prompt(target_name, text)

    def _call() -> Optional[str]:
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel(_MODEL_NAME)
        resp = model.generate_content(prompt)
        out = getattr(resp, "text", None)
        return out.strip() if out else None

    try:
        # SDK is sync — run in default thread pool so we don't block the loop.
        translated = await asyncio.wait_for(
            asyncio.to_thread(_call), timeout=_TRANSLATE_TIMEOUT_SEC
        )
        return translated
    except asyncio.TimeoutError:
        logger.warning("translate_text timeout after %ss (lang=%s)", _TRANSLATE_TIMEOUT_SEC, target)
        return None
    except Exception as e:
        logger.warning("translate_text error (lang=%s): %s", target, e)
        return None
