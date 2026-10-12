from __future__ import annotations

import logging
from collections.abc import Callable

import numpy as np

from app.audio.devices import exclude_loopback_mics, prefer_host_api
from app.models import AudioChunk, AudioDevice
from app.utils.audio_ops import resample_linear, to_mono

logger = logging.getLogger(__name__)


def list_input_devices() -> list[AudioDevice]:
    try:
        import sounddevice as sd
    except Exception as exc:
        logger.warning("sounddevice is unavailable: %s", exc)
        return []
    try:
        devices = sd.query_devices()
        hostapis = sd.query_hostapis()
        default_input = sd.default.device[0]
    except Exception as exc:
        logger.warning("Could not query audio devices: %s", exc)
        return []
    listed: list[AudioDevice] = []
    for index, device in enumerate(devices):
        if int(device["max_input_channels"]) < 1:
            continue
        host_index = int(device["hostapi"])
        host_name = ""
        if 0 <= host_index < len(hostapis):
            host_name = str(hostapis[host_index]["name"])
        listed.append(
            AudioDevice(
                id=str(index),
                name=str(device["name"]),
                channels=int(device["max_input_channels"]),
                sample_rate=int(device["default_samplerate"]),
                kind="input",
                is_default=index == default_input,
                host_api=host_name,
            )
        )
    return listed


def probe_input(device_id: str) -> tuple[int, int, int]:
    import sounddevice as sd

    index = int(device_id)
    info = sd.query_devices(index)
    max_channels = int(info["max_input_channels"])
    if max_channels < 1:
        raise RuntimeError(f"Device '{info['name']}' has no input channels")
    channels = 1 if max_channels == 1 else 2
    rate = int(info["default_samplerate"])
    stream = sd.InputStream(
        device=index,
        channels=channels,
        samplerate=rate,
        dtype="float32",
    )
    try:
        stream.start()
    finally:
        stream.close()
    return index, channels, rate


def read_loop(
    *,
    device_index: int,
    channels: int,
    sample_rate: int,
    source: str,
    should_run: Callable[[], bool],
    on_chunk: Callable[[AudioChunk], None],
    on_level: Callable[[str, np.ndarray], None],
    clock: Callable[[], float],
) -> None:
    import sounddevice as sd

    block = max(1, int(sample_rate * 0.03))
    stream = sd.InputStream(
        device=device_index,
        channels=channels,
        samplerate=sample_rate,
        dtype="float32",
        blocksize=block,
    )
    stream.start()
    try:
        while should_run():
            data, _overflowed = stream.read(block)
            samples = resample_linear(to_mono(data), sample_rate, 16000)
            on_level(source, samples)
            on_chunk(
                AudioChunk(
                    source=source,
                    samples=samples,
                    sample_rate=16000,
                    timestamp=float(clock()),
                )
            )
    finally:
        try:
            stream.stop()
        except Exception:
            logger.debug("stream stop failed", exc_info=True)
        stream.close()


def windows_mic_devices() -> list[AudioDevice]:
    return exclude_loopback_mics(prefer_host_api(list_input_devices(), "WASAPI"))
