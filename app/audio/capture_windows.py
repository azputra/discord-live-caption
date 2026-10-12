from __future__ import annotations

import logging
from collections.abc import Callable

import numpy as np

from app.audio.capture import CaptureController
from app.audio.streams import probe_input, read_loop, windows_mic_devices
from app.models import AudioChunk, AudioDevice, StartResult
from app.utils.audio_ops import resample_linear, to_mono

logger = logging.getLogger(__name__)


def _pyaudio():
    import pyaudiowpatch as pyaudio

    return pyaudio


def list_wasapi_loopbacks() -> list[AudioDevice]:
    pyaudio = _pyaudio()
    audio = pyaudio.PyAudio()
    try:
        devices: list[AudioDevice] = []
        for info in audio.get_loopback_device_info_generator():
            devices.append(
                AudioDevice(
                    id=str(info["index"]),
                    name=str(info["name"]),
                    channels=int(info["maxInputChannels"]),
                    sample_rate=int(info["defaultSampleRate"]),
                    kind="loopback",
                    is_default=False,
                    host_api="WASAPI",
                )
            )
        return devices
    finally:
        audio.terminate()


def default_wasapi_output_name() -> str | None:
    pyaudio = _pyaudio()
    audio = pyaudio.PyAudio()
    try:
        host = audio.get_host_api_info_by_type(pyaudio.paWASAPI)
        info = audio.get_device_info_by_index(int(host["defaultOutputDevice"]))
        return str(info["name"])
    except Exception:
        logger.debug("Default WASAPI output is unavailable", exc_info=True)
        return None
    finally:
        audio.terminate()


def probe_loopback(device_id: str) -> tuple[int, int, int]:
    pyaudio = _pyaudio()
    audio = pyaudio.PyAudio()
    try:
        info = audio.get_device_info_by_index(int(device_id))
        channels = max(1, int(info["maxInputChannels"]))
        rate = int(info["defaultSampleRate"])
        stream = audio.open(
            format=pyaudio.paInt16,
            channels=channels,
            rate=rate,
            input=True,
            input_device_index=int(device_id),
            frames_per_buffer=max(1, int(rate * 0.03)),
        )
        stream.close()
        return int(device_id), channels, rate
    finally:
        audio.terminate()


class WindowsAudioCapture:
    """WASAPI loopback for meeting audio, sounddevice for the microphone."""

    platform_name = "windows"

    def __init__(self) -> None:
        self._controller = CaptureController()
        self.last_error: str | None = None
        self.default_output_name: str | None = None

    def list_system_devices(self) -> list[AudioDevice]:
        try:
            self.default_output_name = default_wasapi_output_name()
            devices = list_wasapi_loopbacks()
            self.last_error = None
            return devices
        except Exception as exc:
            self.last_error = (
                "WASAPI loopback is unavailable. Install pyaudiowpatch and pick "
                f"the loopback device for the speakers Discord is using. ({exc})"
            )
            logger.warning("WASAPI loopback listing failed: %s", exc)
            return []

    def list_mic_devices(self) -> list[AudioDevice]:
        try:
            devices = windows_mic_devices()
            for device in devices:
                device.kind = "mic"
            return devices
        except Exception as exc:
            self.last_error = str(exc)
            logger.warning("Microphone listing failed: %s", exc)
            return []

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
                index, channels, rate = probe_loopback(system_device)
            except Exception as exc:
                errors.append(f"System audio: {exc}")
            else:
                self._launch_loopback(
                    index, channels, rate, generation, on_chunk, on_error, clock
                )
                system_started = True
        else:
            errors.append("System audio device is not selected")

        if mic_device:
            try:
                index, channels, rate = probe_input(mic_device)
            except Exception as exc:
                errors.append(f"Microphone: {exc}")
            else:
                self._launch_mic(index, channels, rate, generation, on_chunk, on_error, clock)
                mic_started = True
        else:
            errors.append("Microphone is not selected")

        if not system_started and not mic_started:
            self._controller.end()
        return StartResult(system_started, mic_started, errors)

    def _launch_loopback(
        self,
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
                self._loopback_loop(index, channels, rate, generation, on_chunk, clock)
            except Exception as exc:
                logger.exception("WASAPI loopback failed")
                on_error("others", str(exc))

        self._controller.add_thread(run, "capture-others")

    def _launch_mic(
        self,
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
                    source="me",
                    should_run=lambda: self._controller.should_run(generation),
                    on_chunk=on_chunk,
                    on_level=self._controller.set_level,
                    clock=clock,
                )
            except Exception as exc:
                logger.exception("Microphone capture failed")
                on_error("me", str(exc))

        self._controller.add_thread(run, "capture-me")

    def _loopback_loop(
        self,
        index: int,
        channels: int,
        rate: int,
        generation: int,
        on_chunk: Callable,
        clock: Callable[[], float],
    ) -> None:
        pyaudio = _pyaudio()
        audio = pyaudio.PyAudio()
        frames = max(1, int(rate * 0.03))
        stream = audio.open(
            format=pyaudio.paInt16,
            channels=channels,
            rate=rate,
            input=True,
            input_device_index=index,
            frames_per_buffer=frames,
        )
        try:
            while self._controller.should_run(generation):
                raw = stream.read(frames, exception_on_overflow=False)
                pcm = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
                if channels > 1:
                    usable = pcm[: len(pcm) - (len(pcm) % channels)]
                    pcm = usable.reshape(-1, channels)
                samples = resample_linear(to_mono(pcm), rate, 16000)
                self._controller.set_level("others", samples)
                on_chunk(
                    AudioChunk(
                        source="others",
                        samples=samples,
                        sample_rate=16000,
                        timestamp=float(clock()),
                    )
                )
        finally:
            try:
                stream.close()
            except Exception:
                logger.debug("loopback close failed", exc_info=True)
            audio.terminate()
