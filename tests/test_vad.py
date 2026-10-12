import numpy as np

from app.audio.vad import StreamingVad, create_vad
from app.config import AppConfig
from app.utils.audio_ops import resample_linear, to_mono
from app.utils.text import is_hallucination


def _detector(frame: np.ndarray) -> bool:
    if len(frame) == 0:
        return False
    value = float(np.sqrt(np.mean(np.square(frame))))
    return value >= 0.02


def _vad() -> StreamingVad:
    return StreamingVad(
        _detector,
        min_speech_ms=80,
        min_silence_ms=150,
        speech_pad_ms=40,
        partial_interval_s=30,
        name="energy",
    )


def test_vad_emits_one_segment_after_silence():
    vad = _vad()
    sample_rate = 16000
    times = np.arange(int(sample_rate * 0.5))
    tone = (0.25 * np.sin(2 * np.pi * 220 * times / sample_rate)).astype(np.float32)
    silence = np.zeros(int(sample_rate * 0.6), dtype=np.float32)
    first = vad.feed(tone, 0.0)
    second = vad.feed(silence, 0.5)
    finished = first.finished + second.finished
    assert len(finished) == 1
    assert finished[0].samples.size > int(sample_rate * 0.2)
    assert finished[0].start_time < 0.2


def test_vad_flush_keeps_trailing_speech():
    vad = _vad()
    sample_rate = 16000
    times = np.arange(int(sample_rate * 0.4))
    tone = (0.25 * np.sin(2 * np.pi * 220 * times / sample_rate)).astype(np.float32)
    assert vad.feed(tone, 0.0).finished == []
    flushed = vad.flush()
    assert len(flushed) == 1


def test_energy_provider_and_fallback(monkeypatch):
    config = AppConfig()
    config.vad.provider = "energy"
    assert create_vad(config).name == "energy"

    import app.audio.vad as vad_module

    def boom(_threshold):
        raise RuntimeError("unavailable")

    monkeypatch.setattr(vad_module, "_silero_detector", boom)
    monkeypatch.setattr(vad_module, "_webrtc_detector", boom)
    config.vad.provider = "silero"
    assert create_vad(config).name == "energy"


def test_resample_and_downmix():
    stereo = np.ones((4, 2), dtype=np.float32)
    stereo[:, 1] = 3
    mono = to_mono(stereo)
    assert mono.shape == (4,)
    assert float(mono[0]) == 2.0
    source = np.linspace(-1, 1, 4800, dtype=np.float32)
    converted = resample_linear(source, 48000, 16000)
    assert abs(len(converted) - 1600) <= 1


def test_hallucination_filters():
    assert is_hallucination("Thanks for watching!", 0.1, 0.6)
    assert is_hallucination("  Subtitles by the Amara.org community ", 0.0, 0.6)
    assert is_hallucination("Halo tim", 0.9, 0.6)
    assert not is_hallucination("Halo tim", 0.1, 0.6)
    assert not is_hallucination("Thanks for watching this demo", 0.1, 0.6)
    assert is_hallucination("   ", 0.0, 0.6)
