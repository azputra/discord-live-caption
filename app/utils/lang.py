from __future__ import annotations

SUPPORTED_LANGUAGES = ("id", "en")

_INDONESIAN = {"id", "ind", "indonesian", "bahasa"}
_ENGLISH = {"en", "eng", "english"}


def normalize_lang(code: str | None) -> str | None:
    """Map common language names to id/en. Unknown codes are kept as-is."""
    if code is None:
        return None
    cleaned = code.strip().lower()
    if cleaned == "":
        return None
    if cleaned in {"auto", "detect"}:
        return "auto"
    if cleaned in _INDONESIAN:
        return "id"
    if cleaned in _ENGLISH:
        return "en"
    return cleaned
