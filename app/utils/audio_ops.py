from __future__ import annotations

import io
import wave

import numpy as np


def to_mono(samples: np.ndarray) -> np.ndarray:
    array = np.asarray(samples, dtype=np.float32)
    if array.ndim == 2 and array.shape[1] > 1:
        array = array.mean(axis=1)
    elif array.ndim == 2:
        array = array[:, 0]
    return np.ascontiguousarray(array.reshape(-1), dtype=np.float32)


def resample_linear(samples: np.ndarray, orig_sr: int, target_sr: int) -> np.ndarray:
    samples = np.asarray(samples, dtype=np.float32).reshape(-1)
    if len(samples) == 0 or orig_sr == target_sr:
        return samples
    if orig_sr <= 0 or target_sr <= 0:
        raise ValueError("sample rate must be positive")
    target_len = int(round(len(samples) * float(target_sr) / float(orig_sr)))
    if target_len <= 0:
        return np.zeros(0, dtype=np.float32)
    if len(samples) == 1 or target_len == 1:
        return np.full(target_len, samples[0], dtype=np.float32)
    old_x = np.linspace(0.0, 1.0, num=len(samples), endpoint=False)
    new_x = np.linspace(0.0, 1.0, num=target_len, endpoint=False)
    return np.interp(new_x, old_x, samples).astype(np.float32)


def rms(samples: np.ndarray) -> float:
    if len(samples) == 0:
        return 0.0
    return float(np.sqrt(np.mean(np.square(samples, dtype=np.float64))))


def wav_bytes(samples: np.ndarray, sample_rate: int) -> bytes:
    clipped = np.clip(np.asarray(samples, dtype=np.float32), -1.0, 1.0)
    pcm = (clipped * 32767.0).astype(np.int16)
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(sample_rate)
        handle.writeframes(pcm.tobytes())
    return buffer.getvalue()
