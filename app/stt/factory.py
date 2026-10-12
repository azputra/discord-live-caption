from __future__ import annotations

from app.config import AppConfig
from app.stt.base import SpeechToText
from app.stt.cloud_provider import CloudSttProvider
from app.stt.faster_whisper_provider import FasterWhisperProvider
from app.stt.mock_provider import MockSttProvider


def create_stt(config: AppConfig) -> SpeechToText:
    provider = (config.stt.provider or "faster-whisper").strip().lower()
    if provider == "mock":
        return MockSttProvider()
    if provider in {"openai", "cloud"}:
        return CloudSttProvider()
    return FasterWhisperProvider(
        model_size=config.stt.model_size or "small",
        device=config.stt.device,
        compute_type=config.stt.compute_type,
    )


def create_local_fallback(config: AppConfig) -> FasterWhisperProvider:
    return FasterWhisperProvider(
        model_size=config.stt.model_size or "small",
        device="auto",
        compute_type="auto",
    )
