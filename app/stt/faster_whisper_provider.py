from __future__ import annotations

import logging

import numpy as np

from app.models import SttResult
from app.stt.base import SpeechToText
from app.utils.lang import normalize_lang

logger = logging.getLogger(__name__)


def cuda_available() -> bool:
    try:
        import ctranslate2

        return int(ctranslate2.get_cuda_device_count()) > 0
    except Exception:
        return False


def resolve_whisper_device(device: str, compute_type: str) -> tuple[str, str]:
    """Pick CUDA float16 when a GPU is present, otherwise CPU int8.

    Apple Silicon has no CUDA device, so it stays on CPU int8.
    """
    requested = (device or "auto").strip().lower()
    compute = (compute_type or "auto").strip().lower()
    has_cuda = requested in {"auto", "cuda"} and cuda_available()
    if has_cuda:
        resolved = compute if compute != "auto" else "float16"
        return "cuda", resolved
    resolved = compute if compute != "auto" else "int8"
    return "cpu", resolved


class FasterWhisperProvider(SpeechToText):
    def __init__(
        self,
        model_size: str = "small",
        device: str = "auto",
        compute_type: str = "auto",
    ) -> None:
        self.model_size = model_size or "small"
        self.device_pref = device or "auto"
        self.compute_pref = compute_type or "auto"
        self._model = None

    def _ensure(self):
        if self._model is not None:
            return self._model
        from faster_whisper import WhisperModel

        device, compute = resolve_whisper_device(self.device_pref, self.compute_pref)
        logger.info(
            "Loading faster-whisper model %s on %s (%s)",
            self.model_size,
            device,
            compute,
        )
        self._model = WhisperModel(self.model_size, device=device, compute_type=compute)
        return self._model

    def transcribe(self, audio, sample_rate, language=None) -> SttResult:
        del sample_rate
        model = self._ensure()
        forced = normalize_lang(language)
        whisper_language = None if forced in {None, "auto"} else forced
        segments, info = model.transcribe(
            np.asarray(audio, dtype=np.float32),
            language=whisper_language,
            task="transcribe",
            vad_filter=False,
            beam_size=1,
            temperature=0.0,
            condition_on_previous_text=False,
            without_timestamps=True,
        )
        parts: list[str] = []
        probabilities: list[float] = []
        for segment in segments:
            parts.append((segment.text or "").strip())
            probabilities.append(float(getattr(segment, "no_speech_prob", 0.0) or 0.0))
        text = " ".join(part for part in parts if part).strip()
        detected = normalize_lang(getattr(info, "language", None)) or whisper_language or "en"
        if whisper_language:
            detected = whisper_language
        no_speech = max(probabilities) if probabilities else 1.0
        if detected in {None, "auto"}:
            detected = "en"
        return SttResult(text=text, language=detected, no_speech_prob=no_speech)
