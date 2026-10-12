import time

import numpy as np

from app.audio.vad import StreamingVad
from app.models import AudioChunk, SttResult
from app.pipeline import Pipeline
from app.storage.db import Database
from app.stt.mock_provider import MockSttProvider
from app.translate.mock_provider import MockTranslator


def _vad() -> StreamingVad:
    def is_speech(frame: np.ndarray) -> bool:
        if len(frame) == 0:
            return False
        return float(np.sqrt(np.mean(np.square(frame)))) >= 0.02

    return StreamingVad(
        is_speech,
        min_speech_ms=80,
        min_silence_ms=150,
        speech_pad_ms=40,
        partial_interval_s=30,
    )


def _pipeline(tmp_path, stt, translator, **kwargs) -> tuple[Pipeline, Database]:
    database = Database(tmp_path / "sessions.sqlite3")
    pipeline = Pipeline(
        stt=stt,
        translator=translator,
        database=database,
        vad_factory=_vad,
        retry_sleep=lambda _delay: None,
        **kwargs,
    )
    pipeline.open_session()
    return pipeline, database


def _speak(pipeline: Pipeline, source: str = "others") -> None:
    sample_rate = 16000
    times = np.arange(int(sample_rate * 0.45))
    tone = (0.25 * np.sin(2 * np.pi * 220 * times / sample_rate)).astype(np.float32)
    silence = np.zeros(int(sample_rate * 0.7), dtype=np.float32)
    pipeline.handle_audio(AudioChunk(source, tone, sample_rate, 0.0))
    pipeline.handle_audio(AudioChunk(source, silence, sample_rate, 0.45))
    pipeline.finish_audio()
    pipeline.drain_translations()


def test_swap_translates_english_to_indonesian(tmp_path):
    translator = MockTranslator()
    pipeline, database = _pipeline(
        tmp_path,
        MockSttProvider([SttResult("Hello team", "en", 0.05)]),
        translator,
        translation_mode="swap",
    )
    _speak(pipeline)
    rows = database.list_segments(pipeline.session_id)
    assert len(rows) == 1
    assert rows[0].language == "en"
    assert rows[0].text == "Hello team"
    assert rows[0].target_language == "id"
    assert rows[0].translated_text == "[id] Hello team"
    assert translator.calls[0][1:] == ("en", "id", ())
    pipeline.close_session()


def test_fixed_target_skips_same_language(tmp_path):
    translator = MockTranslator()
    pipeline, database = _pipeline(
        tmp_path,
        MockSttProvider([SttResult("Hello team", "en", 0.05)]),
        translator,
        translation_mode="fixed",
        fixed_target="en",
    )
    _speak(pipeline)
    rows = database.list_segments(pipeline.session_id)
    assert rows[0].translation_status == "skipped"
    assert rows[0].translated_text is None
    assert translator.calls == []
    pipeline.close_session()


def test_manual_language_overrides_detection(tmp_path):
    translator = MockTranslator()
    pipeline, database = _pipeline(
        tmp_path,
        MockSttProvider([SttResult("Hello team", "en", 0.05)]),
        translator,
        translation_mode="swap",
        forced_language="id",
    )
    _speak(pipeline)
    rows = database.list_segments(pipeline.session_id)
    assert rows[0].language == "id"
    assert rows[0].translated_text == "[en] Hello team"
    pipeline.close_session()


def test_hallucination_is_not_stored(tmp_path):
    pipeline, database = _pipeline(
        tmp_path,
        MockSttProvider([SttResult("Thanks for watching!", "en", 0.1)]),
        MockTranslator(),
    )
    _speak(pipeline)
    assert database.list_segments(pipeline.session_id) == []
    pipeline.close_session()


def test_translation_failure_keeps_the_segment(tmp_path):
    pipeline, database = _pipeline(
        tmp_path,
        MockSttProvider([SttResult("Hello team", "en", 0.05)]),
        MockTranslator(fail_times=5),
        retry_attempts=2,
    )
    _speak(pipeline)
    rows = database.list_segments(pipeline.session_id)
    assert rows[0].text == "Hello team"
    assert rows[0].translation_status == "error"
    assert rows[0].translated_text is None
    pipeline.close_session()


def test_context_includes_the_previous_segment(tmp_path):
    translator = MockTranslator()
    pipeline, _database = _pipeline(
        tmp_path,
        MockSttProvider(
            [
                SttResult("Halo tim", "id", 0.05),
                SttResult("Please review", "en", 0.05),
            ]
        ),
        translator,
        translation_mode="swap",
    )
    _speak(pipeline)
    _speak(pipeline, source="me")
    assert len(translator.calls) == 2
    assert translator.calls[1][2] == "id"
    assert "Halo tim" in translator.calls[1][3][0]
    pipeline.close_session()


def test_workers_finish_a_caption(tmp_path):
    database = Database(tmp_path / "sessions.sqlite3")
    pipeline = Pipeline(
        stt=MockSttProvider([SttResult("Hello team", "en", 0.02)]),
        translator=MockTranslator(),
        database=database,
        vad_factory=_vad,
        retry_sleep=lambda _delay: None,
        translation_mode="swap",
    )
    pipeline.open_session()
    pipeline.start_workers()
    sample_rate = 16000
    times = np.arange(int(sample_rate * 0.45))
    tone = (0.25 * np.sin(2 * np.pi * 220 * times / sample_rate)).astype(np.float32)
    silence = np.zeros(int(sample_rate * 0.7), dtype=np.float32)
    pipeline.push_audio(AudioChunk("others", tone, sample_rate, 0.0))
    pipeline.push_audio(AudioChunk("others", silence, sample_rate, 0.45))
    deadline = time.time() + 4
    rows = []
    while time.time() < deadline:
        rows = database.list_segments(pipeline.session_id)
        if rows and rows[0].translation_status == "done":
            break
        time.sleep(0.02)
    pipeline.shutdown(timeout=3)
    assert rows and rows[0].translated_text == "[id] Hello team"
    assert database.get_session(pipeline.session_id).ended_at is not None
