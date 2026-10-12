from __future__ import annotations

import re

_HALLUCINATION_PATTERNS = (
    re.compile(r"thanks for watching[.!\s]*", re.IGNORECASE),
    re.compile(r"thank you for watching[.!\s]*", re.IGNORECASE),
    re.compile(r"thanks for listening[.!\s]*", re.IGNORECASE),
    re.compile(r"please subscribe[.!\s]*", re.IGNORECASE),
    re.compile(r"like and subscribe[.!\s]*", re.IGNORECASE),
    re.compile(r"subtitles by the amara\.org community[.!\s]*", re.IGNORECASE),
    re.compile(r"subtitles by[.!\s]*", re.IGNORECASE),
    re.compile(r"amara\.org[.!\s]*", re.IGNORECASE),
    re.compile(r"www\.amara\.org[.!\s]*", re.IGNORECASE),
    re.compile(r"\[(music|applause|silence|blank audio)\][.!\s]*", re.IGNORECASE),
    re.compile(r"\((music|applause|silence)\)[.!\s]*", re.IGNORECASE),
    re.compile(r"(music playing|blank audio|silence)[.!\s]*", re.IGNORECASE),
)


def is_hallucination(text: str, no_speech_prob: float | None, threshold: float) -> bool:
    if no_speech_prob is not None and no_speech_prob >= threshold:
        return True
    cleaned = " ".join((text or "").strip().split())
    if not cleaned:
        return True
    if re.fullmatch(r"[\W_]+", cleaned, flags=re.UNICODE):
        return True
    return any(pattern.fullmatch(cleaned) for pattern in _HALLUCINATION_PATTERNS)


def format_timestamp(seconds: float) -> str:
    whole = max(0, int(seconds))
    hours, remainder = divmod(whole, 3600)
    minutes, secs = divmod(remainder, 60)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}"


def strip_model_wrapping(text: str) -> str:
    cleaned = (text or "").strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```[a-zA-Z]*\s*", "", cleaned)
        cleaned = re.sub(r"\s*```$", "", cleaned)
        cleaned = cleaned.strip()
    if len(cleaned) >= 2 and cleaned[0] == cleaned[-1] and cleaned[0] in {'"', "'"}:
        cleaned = cleaned[1:-1].strip()
    return cleaned
