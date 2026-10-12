from __future__ import annotations

import logging
import os

from app.translate.base import Translator
from app.utils.retry import retry
from app.utils.text import strip_model_wrapping

logger = logging.getLogger(__name__)

TRANSLATE_SYSTEM = (
    "You translate live meeting captions between Indonesian (id) and English (en). "
    "Keep the translation faithful to what was said. Preserve names, numbers, and "
    "technical terms. Do not add commentary, labels, quotes, or explanations. "
    "Output only the translated text."
)

SUMMARY_SYSTEM = (
    "You are a meeting assistant. Follow the user's instruction exactly and "
    "base the summary only on the transcript."
)


def build_translation_prompt(
    text: str,
    source_lang: str,
    target_lang: str,
    context: list[str],
) -> str:
    names = {"id": "Indonesian", "en": "English"}
    lines: list[str] = []
    if context:
        lines.append("Recent captions for context. Do not translate them again:")
        lines.extend(f"- {line}" for line in context[-5:])
        lines.append("")
    source_name = names.get(source_lang, source_lang)
    target_name = names.get(target_lang, target_lang)
    lines.append(f"Translate this caption from {source_name} to {target_name}.")
    lines.append("Caption:")
    lines.append(text)
    return "\n".join(lines)


class LlmTranslator(Translator):
    def __init__(self, vendor: str, model: str) -> None:
        self.vendor = "anthropic" if vendor == "anthropic" else "openai"
        self.model = model

    def translate(self, text, source_lang, target_lang, context) -> str:
        prompt = build_translation_prompt(text, source_lang, target_lang, context)
        return self._complete(TRANSLATE_SYSTEM, prompt, max_tokens=800, attempts=1)

    def summarize(self, transcript: str) -> str:
        return self._complete(SUMMARY_SYSTEM, transcript, max_tokens=2000, attempts=3)

    def _complete(self, system: str, user: str, max_tokens: int, attempts: int) -> str:
        self._require_key()

        def attempt() -> str:
            if self.vendor == "anthropic":
                return self._anthropic(system, user, max_tokens)
            return self._openai(system, user, max_tokens)

        raw = retry(attempt, attempts=attempts, base_delay=0.5)
        return strip_model_wrapping(raw)

    def _require_key(self) -> None:
        if self.vendor == "anthropic":
            if not os.environ.get("ANTHROPIC_API_KEY", "").strip():
                raise RuntimeError("ANTHROPIC_API_KEY is not set")
            return
        if not os.environ.get("OPENAI_API_KEY", "").strip():
            raise RuntimeError("OPENAI_API_KEY is not set")

    def _openai(self, system: str, user: str, max_tokens: int) -> str:
        from openai import OpenAI

        response = OpenAI().chat.completions.create(
            model=self.model,
            temperature=0,
            max_tokens=max_tokens,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        )
        return (response.choices[0].message.content or "").strip()

    def _anthropic(self, system: str, user: str, max_tokens: int) -> str:
        from anthropic import Anthropic

        response = Anthropic().messages.create(
            model=self.model,
            max_tokens=max_tokens,
            temperature=0,
            system=system,
            messages=[{"role": "user", "content": user}],
        )
        parts: list[str] = []
        for block in response.content:
            text = getattr(block, "text", None)
            if text:
                parts.append(text)
        return "\n".join(parts).strip()
