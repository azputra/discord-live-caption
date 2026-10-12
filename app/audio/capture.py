from __future__ import annotations

import logging
import threading
from collections.abc import Callable

import numpy as np

from app.utils.audio_ops import rms

logger = logging.getLogger(__name__)


class CaptureController:
    """Shared start/stop and level-meter state for both OS backends."""

    def __init__(self) -> None:
        self._stop = threading.Event()
        self._threads: list[threading.Thread] = []
        self._generation = 0
        self._levels = {"me": 0.0, "others": 0.0}
        self._lock = threading.Lock()

    def begin(self) -> int:
        self.end()
        self._generation += 1
        self._stop.clear()
        return self._generation

    def end(self) -> None:
        self._stop.set()
        threads = self._threads
        self._threads = []
        self._generation += 1
        for thread in threads:
            thread.join(timeout=1.5)
        self._stop.clear()
        with self._lock:
            self._levels = {"me": 0.0, "others": 0.0}

    def should_run(self, generation: int) -> bool:
        return (not self._stop.is_set()) and generation == self._generation

    def add_thread(self, target: Callable[[], None], name: str) -> None:
        thread = threading.Thread(target=target, name=name, daemon=True)
        self._threads.append(thread)
        thread.start()

    def set_level(self, source: str, samples: np.ndarray) -> None:
        level = min(1.0, rms(samples) * 5.0)
        with self._lock:
            previous = self._levels.get(source, 0.0)
            self._levels[source] = previous * 0.65 + level * 0.35

    def levels(self) -> dict[str, float]:
        with self._lock:
            return dict(self._levels)


class UnsupportedPlatform(RuntimeError):
    pass


def backend_for_platform(platform: str) -> str:
    if platform == "win32" or platform.startswith("win"):
        return "windows"
    if platform == "darwin":
        return "macos"
    raise UnsupportedPlatform(
        f"Unsupported platform '{platform}'. This app runs on Windows and macOS."
    )


def create_capture(platform: str | None = None):
    import sys

    name = backend_for_platform(platform or sys.platform)
    if name == "windows":
        from app.audio.capture_windows import WindowsAudioCapture

        return WindowsAudioCapture()
    from app.audio.capture_macos import MacAudioCapture

    return MacAudioCapture()
