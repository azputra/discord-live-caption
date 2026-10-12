from __future__ import annotations

from abc import ABC, abstractmethod

import numpy as np

from app.models import SttResult


class SpeechToText(ABC):
    @abstractmethod
    def transcribe(
        self,
        audio: np.ndarray,
        sample_rate: int,
        language: str | None = None,
    ) -> SttResult:
        """Transcribe mono audio. language is None or auto to detect."""
