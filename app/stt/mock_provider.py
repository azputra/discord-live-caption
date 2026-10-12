from __future__ import annotations

from app.models import SttResult
from app.stt.base import SpeechToText
from app.utils.lang import normalize_lang


class MockSttProvider(SpeechToText):
    """Scripted recognizer for tests and UI dry-runs. No audio hardware or API key."""

    def __init__(self, script: list[SttResult] | None = None) -> None:
        self.script = list(script or [SttResult("Hello", "en", 0.01)])
        self.calls = 0

    def transcribe(self, audio, sample_rate, language=None) -> SttResult:
        del audio, sample_rate
        result = self.script[self.calls % len(self.script)]
        self.calls += 1
        forced = normalize_lang(language)
        detected = result.language
        if forced and forced != "auto":
            detected = forced
        return SttResult(result.text, detected, result.no_speech_prob)
