from __future__ import annotations

import threading
import wave
from pathlib import Path

import numpy as np


class WavWriter:
    """Append mono float32 audio to a 16 kHz WAV file."""

    def __init__(self, path: Path, sample_rate: int = 16000) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._handle = wave.open(str(self.path), "wb")
        self._handle.setnchannels(1)
        self._handle.setsampwidth(2)
        self._handle.setframerate(sample_rate)
        self._closed = False

    def write(self, samples: np.ndarray) -> None:
        clipped = np.clip(np.asarray(samples, dtype=np.float32), -1.0, 1.0)
        pcm = (clipped * 32767.0).astype(np.int16).tobytes()
        with self._lock:
            if not self._closed:
                self._handle.writeframes(pcm)

    def close(self) -> None:
        with self._lock:
            if not self._closed:
                self._handle.close()
                self._closed = True
