from __future__ import annotations

import logging
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass

import numpy as np

from app.models import SpeechSegment

logger = logging.getLogger(__name__)


@dataclass
class VadResult:
    finished: list[SpeechSegment]
    partial: SpeechSegment | None = None


class StreamingVad:
    """Frame VAD that emits finished utterances and occasional partials."""

    def __init__(
        self,
        is_speech_frame: Callable[[np.ndarray], bool],
        *,
        sample_rate: int = 16000,
        frame_samples: int = 320,
        min_speech_ms: int = 250,
        min_silence_ms: int = 500,
        speech_pad_ms: int = 200,
        max_segment_s: float = 20,
        partial_interval_s: float = 2.5,
        name: str = "vad",
    ) -> None:
        self._is_speech_frame = is_speech_frame
        self.sample_rate = sample_rate
        self.frame_samples = frame_samples
        self.min_speech = max(frame_samples, int(sample_rate * min_speech_ms / 1000))
        self.min_silence = max(frame_samples, int(sample_rate * min_silence_ms / 1000))
        self.pad = max(0, int(sample_rate * speech_pad_ms / 1000))
        self.max_segment = max(self.min_speech, int(sample_rate * max_segment_s))
        self.partial_interval = max(frame_samples, int(sample_rate * partial_interval_s))
        self.name = name
        self._remainder = np.zeros(0, dtype=np.float32)
        self.reset()

    def reset(self) -> None:
        self._ring: deque[np.ndarray] = deque()
        self._ring_samples = 0
        self._ring_limit = max(self.pad, self.min_speech)
        self._triggered = False
        self._speech_run = 0
        self._silence_run = 0
        self._collected: list[np.ndarray] = []
        self._collected_samples = 0
        self._cursor = 0
        self._started = False
        self._speech_start = 0
        self._since_partial = 0

    def feed(self, samples: np.ndarray, timestamp: float | None = None) -> VadResult:
        incoming = np.asarray(samples, dtype=np.float32).reshape(-1)
        self._align(timestamp, len(incoming))
        data = np.concatenate([self._remainder, incoming]) if len(self._remainder) else incoming
        offset = 0
        finished: list[SpeechSegment] = []
        partial: SpeechSegment | None = None
        frame = self.frame_samples
        while offset + frame <= len(data):
            piece = data[offset : offset + frame]
            offset += frame
            self._cursor += frame
            is_speech = bool(self._is_speech_frame(piece))
            if not self._triggered:
                self._push_ring(piece)
                if is_speech:
                    self._speech_run += frame
                    if self._speech_run >= self.min_speech:
                        self._trigger()
                else:
                    self._speech_run = 0
                continue
            self._collected.append(piece)
            self._collected_samples += frame
            self._since_partial += frame
            if is_speech:
                self._silence_run = 0
            else:
                self._silence_run += frame
            reached_cap = self._collected_samples >= self.max_segment
            if self._silence_run >= self.min_silence or reached_cap:
                finished.append(self._finish(trim_silence=not reached_cap))
                partial = None
            elif self._since_partial >= self.partial_interval:
                partial = self._partial()
                self._since_partial = 0
        self._remainder = np.asarray(data[offset:], dtype=np.float32)
        return VadResult(finished, partial)

    def flush(self) -> list[SpeechSegment]:
        if len(self._remainder) and self._triggered:
            self._collected.append(self._remainder)
            self._collected_samples += len(self._remainder)
            self._cursor += len(self._remainder)
        self._remainder = np.zeros(0, dtype=np.float32)
        if not self._triggered or self._collected_samples < self.min_speech:
            self._clear_utterance()
            return []
        segment = self._finish(trim_silence=True)
        return [segment]

    def _align(self, timestamp: float | None, count: int) -> None:
        del count
        if timestamp is None:
            return
        incoming = max(0, int(timestamp * self.sample_rate))
        if not self._started:
            self._cursor = incoming
            self._started = True
            return
        if incoming > self._cursor + self.sample_rate:
            self._cursor = incoming

    def _push_ring(self, frame: np.ndarray) -> None:
        self._ring.append(frame)
        self._ring_samples += len(frame)
        while self._ring_samples > self._ring_limit and len(self._ring) > 1:
            removed = self._ring.popleft()
            self._ring_samples -= len(removed)

    def _trigger(self) -> None:
        self._triggered = True
        self._silence_run = 0
        self._collected = list(self._ring)
        self._collected_samples = self._ring_samples
        self._speech_start = self._cursor - self._ring_samples
        self._since_partial = 0
        self._ring.clear()
        self._ring_samples = 0
        self._speech_run = 0

    def _audio(self, trim_silence: bool) -> np.ndarray:
        audio = np.concatenate(self._collected) if self._collected else np.zeros(0, dtype=np.float32)
        if trim_silence and self._silence_run > 0:
            keep = min(self._silence_run, self.pad)
            trim = self._silence_run - keep
            if 0 < trim < len(audio):
                audio = audio[:-trim]
        return audio

    def _segment_from(self, audio: np.ndarray) -> SpeechSegment:
        start = max(0, self._speech_start) / self.sample_rate
        end = start + (len(audio) / self.sample_rate)
        return SpeechSegment(samples=audio, start_time=start, end_time=end)

    def _partial(self) -> SpeechSegment:
        audio = np.concatenate(self._collected) if self._collected else np.zeros(0, dtype=np.float32)
        return self._segment_from(audio)

    def _finish(self, trim_silence: bool) -> SpeechSegment:
        audio = self._audio(trim_silence)
        segment = self._segment_from(audio)
        self._clear_utterance()
        return segment

    def _clear_utterance(self) -> None:
        self._triggered = False
        self._speech_run = 0
        self._silence_run = 0
        self._collected = []
        self._collected_samples = 0
        self._since_partial = 0
        self._ring.clear()
        self._ring_samples = 0


def _energy_detector(threshold: float) -> Callable[[np.ndarray], bool]:
    def is_speech(frame: np.ndarray) -> bool:
        if len(frame) == 0:
            return False
        value = float(np.sqrt(np.mean(np.square(frame), dtype=np.float64)))
        return value >= threshold

    return is_speech


def _webrtc_detector(aggressiveness: int = 2) -> Callable[[np.ndarray], bool]:
    import webrtcvad

    vad = webrtcvad.Vad(aggressiveness)

    def is_speech(frame: np.ndarray) -> bool:
        pcm = (np.clip(frame, -1.0, 1.0) * 32767.0).astype(np.int16).tobytes()
        return bool(vad.is_speech(pcm, 16000))

    return is_speech


def _silero_detector(threshold: float) -> Callable[[np.ndarray], bool]:
    import torch
    from silero_vad import load_silero_vad

    model = load_silero_vad()
    model.reset_states()

    def is_speech(frame: np.ndarray) -> bool:
        tensor = torch.from_numpy(np.asarray(frame, dtype=np.float32))
        probability = float(model(tensor, 16000).detach().item())
        return probability >= threshold

    return is_speech


def _settings(config) -> dict:
    return dict(
        sample_rate=16000,
        min_speech_ms=int(config.vad.min_speech_ms),
        min_silence_ms=int(config.vad.min_silence_ms),
        speech_pad_ms=int(config.vad.speech_pad_ms),
        max_segment_s=float(config.vad.max_segment_s),
        partial_interval_s=float(config.vad.partial_interval_s),
    )


def create_vad(config) -> StreamingVad:
    provider = (config.vad.provider or "silero").lower()
    settings = _settings(config)
    errors: list[str] = []
    if provider == "energy":
        vad = StreamingVad(
            _energy_detector(float(config.vad.energy_threshold)),
            name="energy",
            **settings,
        )
        logger.info("Using energy VAD")
        return vad
    if provider == "silero":
        try:
            detector = _silero_detector(float(config.vad.threshold))
            detector(np.zeros(512, dtype=np.float32))
            vad = StreamingVad(
                detector,
                frame_samples=512,
                name="silero",
                **settings,
            )
            logger.info("Using Silero VAD")
            return vad
        except Exception as exc:
            errors.append(f"silero: {exc}")
    if provider in {"silero", "webrtc"}:
        try:
            detector = _webrtc_detector()
            detector(np.zeros(320, dtype=np.float32))
            vad = StreamingVad(
                detector,
                frame_samples=320,
                name="webrtc",
                **settings,
            )
            logger.info("Using webrtcvad")
            return vad
        except Exception as exc:
            errors.append(f"webrtc: {exc}")
    if errors:
        logger.warning("VAD fallback to energy (%s)", "; ".join(errors))
    else:
        logger.info("Using energy VAD")
    return StreamingVad(
        _energy_detector(float(config.vad.energy_threshold)),
        name="energy",
        **settings,
    )
