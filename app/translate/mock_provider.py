from __future__ import annotations

from app.translate.base import Translator


class MockTranslator(Translator):
    """Deterministic translator for tests and offline UI runs."""

    def __init__(self, fail_times: int = 0) -> None:
        self.fail_times = fail_times
        self.calls: list[tuple[str, str, str, tuple[str, ...]]] = []

    def translate(self, text: str, source_lang: str, target_lang: str, context: list[str]) -> str:
        self.calls.append((text, source_lang, target_lang, tuple(context)))
        if self.fail_times > 0:
            self.fail_times -= 1
            raise RuntimeError("mock translation failure")
        return f"[{target_lang}] {text}"

    def summarize(self, transcript: str) -> str:
        preview = transcript.strip()
        if len(preview) > 400:
            preview = preview[:400]
        return "Summary:\n" + preview
