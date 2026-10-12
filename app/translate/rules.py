from __future__ import annotations

from app.utils.lang import SUPPORTED_LANGUAGES, normalize_lang


def desired_target(mode: str, detected: str | None, fixed_target: str | None) -> str | None:
    """Return the language to translate into, or None when no call is needed.

    Swap turns Indonesian into English and English into Indonesian.
    Fixed target translates only when the segment is not already in that language.
    Same-language pairs (id->id, en->en) never produce a target.
    Languages outside Indonesian and English are left unchanged.
    """
    language = normalize_lang(detected)
    if language not in SUPPORTED_LANGUAGES:
        return None
    normalized_mode = (mode or "").strip().lower()
    if normalized_mode == "swap":
        return "en" if language == "id" else "id"
    if normalized_mode == "fixed":
        target = normalize_lang(fixed_target)
        if target not in SUPPORTED_LANGUAGES or target == language:
            return None
        return target
    return None
