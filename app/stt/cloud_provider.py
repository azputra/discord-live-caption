from __future__ import annotations

import io
import os

from app.models import SttResult
from app.stt.base import SpeechToText
from app.utils.audio_ops import wav_bytes
from app.utils.lang import normalize_lang


class CloudSttProvider(SpeechToText):
    """OpenAI transcription API. The pipeline retries and can fall back locally."""

    def __init__(self, model: str = "whisper-1") -> None:
        self.model = model or "whisper-1"

    def transcribe(self, audio, sample_rate, language=None) -> SttResult:
        if not os.environ.get("OPENAI_API_KEY", "").strip():
            raise RuntimeError("OPENAI_API_KEY is not set")
        from openai import OpenAI

        payload = io.BytesIO(wav_bytes(audio, sample_rate))
        payload.name = "segment.wav"
        forced = normalize_lang(language)
        kwargs: dict = {
            "model": self.model,
            "file": payload,
            "response_format": "verbose_json",
        }
        if forced and forced != "auto":
            kwargs["language"] = forced
        response = OpenAI().audio.transcriptions.create(**kwargs)
        text = (getattr(response, "text", "") or "").strip()
        detected = normalize_lang(getattr(response, "language", None)) or forced or "en"
        if forced and forced != "auto":
            detected = forced
        if detected in {None, "auto"}:
            detected = "en"
        return SttResult(text=text, language=detected, no_speech_prob=0.0)
