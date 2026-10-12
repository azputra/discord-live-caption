from __future__ import annotations

import logging
from collections.abc import Callable

from app.audio.capture import CaptureController
from app.audio.devices import split_macos_devices
from app.audio.streams import list_input_devices, probe_input, read_loop
from app.models import AudioDevice, StartResult

logger = logging.getLogger(__name__)


class MacAudioCapture:
    """System audio through a virtual loopback (BlackHole) and the default mic."""

    platform_name = "macos"

    def __init__(self) -> None:
        self._controller = CaptureController()
        self.last_error: str | None = None

    def list_input_devices(self) -> list[AudioDevice]:
        try:
            self.last_error = None
            return list_input_devices()
        except Exception as exc:
            self.last_error = str(exc)
            logger.warning("macOS device listing failed: %s", exc)
            return []

    def list_system_devices(self) -> list[AudioDevice]:
        system, _mics = split_macos_devices(self.list_input_devices())
        for device in system:
            device.kind = "loopback"
        return system

    def list_mic_devices(self) -> list[AudioDevice]:
        _system, mics = split_macos_devices(self.list_input_devices())
        for device in mics:
            device.kind = "mic"
        return mics

    def levels(self) -> dict[str, float]:
        return self._controller.levels()

    def stop(self) -> None:
        self._controller.end()

    def start(
        self,
        system_device: str | None,
        mic_device: str | None,
        on_chunk: Callable,
        on_error: Callable[[str, str], None],
        clock: Callable[[], float],
    ) -> StartResult:
        generation = self._controller.begin()
        errors: list[str] = []
        system_started = False
        mic_started = False

        if system_device:
            try:
                index, channels, rate = probe_input(system_device)
            except Exception as exc:
                errors.append(f"System audio: {exc}")
            else:
                self._launch("others", index, channels, rate, generation, on_chunk, on_error, clock)
                system_started = True
        else:
            errors.append("System audio device is not selected")

        if mic_device:
            try:
                index, channels, rate = probe_input(mic_device)
            except Exception as exc:
                errors.append(f"Microphone: {exc}")
            else:
                self._launch("me", index, channels, rate, generation, on_chunk, on_error, clock)
                mic_started = True
        else:
            errors.append("Microphone is not selected")

        if not system_started and not mic_started:
            self._controller.end()
        return StartResult(system_started, mic_started, errors)

    def _launch(
        self,
        source: str,
        index: int,
        channels: int,
        rate: int,
        generation: int,
        on_chunk: Callable,
        on_error: Callable[[str, str], None],
        clock: Callable[[], float],
    ) -> None:
        def run() -> None:
            try:
                read_loop(
                    device_index=index,
                    channels=channels,
                    sample_rate=rate,
                    source=source,
                    should_run=lambda: self._controller.should_run(generation),
                    on_chunk=on_chunk,
                    on_level=self._controller.set_level,
                    clock=clock,
                )
            except Exception as exc:
                logger.exception("macOS capture failed for %s", source)
                on_error(source, str(exc))

        self._controller.add_thread(run, f"capture-{source}")
