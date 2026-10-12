from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np


@dataclass
class AudioDevice:
    id: str
    name: str
    channels: int
    sample_rate: int
    kind: str
    is_default: bool = False
    host_api: str = ""


@dataclass
class AudioChunk:
    source: str
    samples: np.ndarray
    sample_rate: int
    timestamp: float


@dataclass
class SpeechSegment:
    samples: np.ndarray
    start_time: float
    end_time: float


@dataclass
class SttResult:
    text: str
    language: str
    no_speech_prob: float = 0.0


@dataclass
class TranscriptSegment:
    id: str
    session_id: str
    source: str
    start_time: float
    end_time: float
    text: str
    language: str
    created_at: str
    is_partial: bool = False
    translated_text: str | None = None
    target_language: str | None = None
    translation_status: str = "pending"


@dataclass
class SessionRecord:
    id: str
    title: str
    started_at: str
    ended_at: str | None = None
    segment_count: int = 0


@dataclass
class StartResult:
    system_started: bool
    mic_started: bool
    errors: list[str] = field(default_factory=list)
