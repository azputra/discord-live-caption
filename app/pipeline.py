from __future__ import annotations

import logging
import queue
import threading
import time
import uuid
from collections.abc import Callable
from pathlib import Path

import numpy as np

from app.audio.recorder import WavWriter
from app.audio.vad import create_vad
from app.models import AudioChunk, SpeechSegment, TranscriptSegment
from app.storage.db import Database, utc_now
from app.translate.rules import desired_target
from app.utils.audio_ops import resample_linear, to_mono
from app.utils.lang import normalize_lang
from app.utils.retry import retry
from app.utils.text import is_hallucination, strip_model_wrapping

logger = logging.getLogger(__name__)


def format_context_line(segment: TranscriptSegment) -> str:
    speaker = "Me" if segment.source == "me" else "Others"
    if segment.translated_text and segment.target_language:
        return (
            f"{speaker} ({segment.language}): {segment.text} "
            f"=> ({segment.target_language}): {segment.translated_text}"
        )
    return f"{speaker} ({segment.language}): {segment.text}"


class Pipeline:
    """Audio to VAD to speech-to-text to translation, with one worker per stage."""

    def __init__(
        self,
        *,
        stt,
        translator,
        database: Database,
        vad_factory: Callable,
        translation_mode: str = "swap",
        fixed_target: str = "en",
        forced_language: str = "auto",
        no_speech_threshold: float = 0.6,
        context_segments: int = 5,
        save_audio_dir: Path | None = None,
        fallback_to_local: bool = False,
        local_fallback_factory: Callable | None = None,
        retry_attempts: int = 3,
        retry_sleep: Callable[[float], None] = time.sleep,
        on_segment: Callable[[TranscriptSegment], None] | None = None,
        on_partial: Callable[[TranscriptSegment], None] | None = None,
        on_translation: Callable[[TranscriptSegment], None] | None = None,
        on_status: Callable[[str], None] | None = None,
        on_warning: Callable[[str], None] | None = None,
    ) -> None:
        self.stt = stt
        self.translator = translator
        self.database = database
        self._vad_factory = vad_factory
        self.translation_mode = translation_mode
        self.fixed_target = fixed_target
        self.forced_language = forced_language
        self.no_speech_threshold = no_speech_threshold
        self.context_limit = max(1, int(context_segments))
        self.save_audio_dir = Path(save_audio_dir) if save_audio_dir else None
        self.fallback_to_local = fallback_to_local
        self._local_fallback_factory = local_fallback_factory
        self.retry_attempts = retry_attempts
        self.retry_sleep = retry_sleep
        self.on_segment = on_segment
        self.on_partial = on_partial
        self.on_translation = on_translation
        self.on_status = on_status
        self.on_warning = on_warning

        self.session_id: str | None = None
        self._t0: float | None = None
        self._running = False
        self._status = ""
        self._vads: dict = {}
        self._writers: dict[str, WavWriter] = {}
        self._audio_queues = {
            "me": queue.Queue(maxsize=400),
            "others": queue.Queue(maxsize=400),
        }
        self._translate_queue: queue.Queue = queue.Queue()
        self._context: list[str] = []
        self._context_lock = threading.Lock()
        self._inflight = 0
        self._inflight_lock = threading.Lock()
        self._stop_audio = threading.Event()
        self._stop_translate = threading.Event()
        self._audio_threads: list[threading.Thread] = []
        self._translate_thread: threading.Thread | None = None
        self._fallback_stt = None
        self._state_lock = threading.Lock()

    def clock(self) -> float:
        if self._t0 is None:
            return 0.0
        return time.monotonic() - self._t0

    def open_session(self) -> str:
        session = self.database.create_session()
        self.session_id = session.id
        self._t0 = time.monotonic()
        self._vads = {"me": self._vad_factory(), "others": self._vad_factory()}
        self._context = []
        self._running = True
        self._close_writers()
        if self.save_audio_dir is not None:
            self.save_audio_dir.mkdir(parents=True, exist_ok=True)
            for source in ("me", "others"):
                path = self.save_audio_dir / f"{session.id}-{source}.wav"
                self._writers[source] = WavWriter(path)
        self._emit_status("listening")
        logger.info("Session %s started", session.id)
        return session.id

    def close_session(self) -> None:
        session_id = self.session_id
        self._running = False
        self._close_writers()
        if session_id:
            self.database.end_session(session_id)
            logger.info("Session %s ended", session_id)

    def push_audio(self, chunk: AudioChunk) -> None:
        if not self._running or chunk.source not in self._audio_queues:
            return
        audio_queue = self._audio_queues[chunk.source]
        try:
            audio_queue.put_nowait(chunk)
        except queue.Full:
            try:
                audio_queue.get_nowait()
            except queue.Empty:
                pass
            try:
                audio_queue.put_nowait(chunk)
            except queue.Full:
                logger.warning("Dropping audio for %s because the queue is full", chunk.source)

    def handle_audio(self, chunk: AudioChunk) -> None:
        vad = self._vads.get(chunk.source)
        if vad is None:
            return
        samples = to_mono(chunk.samples)
        if chunk.sample_rate != 16000:
            samples = resample_linear(samples, chunk.sample_rate, 16000)
        writer = self._writers.get(chunk.source)
        if writer is not None and len(samples):
            writer.write(samples)
        result = vad.feed(samples, chunk.timestamp)
        for speech in result.finished:
            self._consume_speech(chunk.source, speech, partial=False)
        if result.partial is not None:
            self._consume_speech(chunk.source, result.partial, partial=True)

    def finish_audio(self) -> None:
        """Flush VAD state. Use this only when worker threads are not running."""
        for source, vad in self._vads.items():
            for speech in vad.flush():
                self._consume_speech(source, speech, partial=False)

    def drain_translations(self) -> None:
        while True:
            try:
                segment = self._translate_queue.get_nowait()
            except queue.Empty:
                break
            self._translate_segment(segment)

    def start_workers(self) -> None:
        if self._audio_threads or self._translate_thread is not None:
            return
        self._stop_audio.clear()
        self._stop_translate.clear()
        self._audio_threads = []
        for source in ("me", "others"):
            thread = threading.Thread(
                target=self._audio_loop,
                args=(source,),
                name=f"stt-{source}",
                daemon=True,
            )
            self._audio_threads.append(thread)
            thread.start()
        self._translate_thread = threading.Thread(
            target=self._translate_loop,
            name="translate",
            daemon=True,
        )
        self._translate_thread.start()

    def shutdown(self, timeout: float = 30) -> None:
        self._stop_audio.set()
        for thread in self._audio_threads:
            thread.join(timeout=timeout)
        self._audio_threads.clear()
        self._stop_translate.set()
        if self._translate_thread is not None:
            self._translate_thread.join(timeout=timeout)
            self._translate_thread = None
        self.drain_translations()
        self.close_session()
        self._emit_status("idle")

    def _audio_loop(self, source: str) -> None:
        audio_queue = self._audio_queues[source]
        while not self._stop_audio.is_set():
            try:
                chunk = audio_queue.get(timeout=0.1)
            except queue.Empty:
                continue
            try:
                self.handle_audio(chunk)
            except Exception:
                logger.exception("Audio worker failed for %s", source)
        while True:
            try:
                chunk = audio_queue.get_nowait()
            except queue.Empty:
                break
            try:
                self.handle_audio(chunk)
            except Exception:
                logger.exception("Audio drain failed for %s", source)
        vad = self._vads.get(source)
        if vad is None:
            return
        try:
            for speech in vad.flush():
                self._consume_speech(source, speech, partial=False)
        except Exception:
            logger.exception("VAD flush failed for %s", source)

    def _translate_loop(self) -> None:
        while not self._stop_translate.is_set() or not self._translate_queue.empty():
            try:
                segment = self._translate_queue.get(timeout=0.1)
            except queue.Empty:
                continue
            try:
                self._translate_segment(segment)
            except Exception:
                logger.exception("Translation worker failed")

    def _consume_speech(self, source: str, speech: SpeechSegment, *, partial: bool) -> None:
        if speech.samples.size == 0:
            return
        self._bump(1)
        try:
            audio = np.asarray(speech.samples, dtype=np.float32)
            if partial and len(audio) > 16000 * 5:
                audio = audio[-16000 * 5 :]
            forced = normalize_lang(self.forced_language)
            lang_arg = None if forced in {None, "auto"} else forced
            try:
                result = self._transcribe_audio(audio, lang_arg)
            except Exception as exc:
                logger.exception("Transcription failed")
                self._warn(f"Transcription failed: {exc}")
                return
            text = (result.text or "").strip()
            language = normalize_lang(result.language) or ""
            if lang_arg:
                language = lang_arg
            if language in {"", "auto", None}:
                language = "en"
            if is_hallucination(text, result.no_speech_prob, self.no_speech_threshold):
                logger.info("Dropped non-speech caption: %r", text)
                return
            segment = TranscriptSegment(
                id=uuid.uuid4().hex,
                session_id=self.session_id or "",
                source=source,
                start_time=speech.start_time,
                end_time=speech.end_time,
                text=text,
                language=language,
                created_at=utc_now(),
                is_partial=partial,
            )
            if partial:
                self._safe(self.on_partial, segment)
                return
            target = desired_target(self.translation_mode, language, self.fixed_target)
            if target is None:
                segment.translation_status = "skipped"
            self.database.insert_segment(segment)
            self._safe(self.on_segment, segment)
            if target is None:
                self._remember(segment)
                self._safe(self.on_translation, segment)
            else:
                self._translate_queue.put(segment)
        finally:
            self._bump(-1)

    def _transcribe_audio(self, audio: np.ndarray, language: str | None):
        def attempt():
            return self.stt.transcribe(audio, 16000, language)

        try:
            return retry(
                attempt,
                attempts=self.retry_attempts,
                base_delay=0.4,
                sleep=self.retry_sleep,
            )
        except Exception as exc:
            if not self.fallback_to_local or self._local_fallback_factory is None:
                raise
            logger.warning("Primary STT failed, using local faster-whisper: %s", exc)
            self._warn(f"Cloud transcription failed, using the local model. {exc}")
            if self._fallback_stt is None:
                self._fallback_stt = self._local_fallback_factory()
            return self._fallback_stt.transcribe(audio, 16000, language)

    def _translate_segment(self, segment: TranscriptSegment) -> None:
        target = desired_target(self.translation_mode, segment.language, self.fixed_target)
        if target is None:
            segment.translation_status = "skipped"
            segment.translated_text = None
            segment.target_language = None
            self.database.update_translation(segment.id, None, None, "skipped")
            self._remember(segment)
            self._safe(self.on_translation, segment)
            return
        context = self._context_lines()
        self._bump(1)
        try:
            def attempt() -> str:
                return self.translator.translate(segment.text, segment.language, target, context)

            translated = retry(
                attempt,
                attempts=self.retry_attempts,
                base_delay=0.4,
                sleep=self.retry_sleep,
            )
            segment.translated_text = strip_model_wrapping(translated)
            segment.target_language = target
            segment.translation_status = "done"
        except Exception as exc:
            logger.exception("Translation failed")
            segment.translation_status = "error"
            self._warn(f"Translation failed: {exc}")
        finally:
            self._bump(-1)
        self.database.update_translation(
            segment.id,
            segment.translated_text,
            segment.target_language,
            segment.translation_status,
        )
        self._remember(segment)
        self._safe(self.on_translation, segment)

    def _remember(self, segment: TranscriptSegment) -> None:
        line = f"{segment.id}|{format_context_line(segment)}"
        with self._context_lock:
            for index, existing in enumerate(self._context):
                if existing.startswith(f"{segment.id}|"):
                    self._context[index] = line
                    return
            self._context.append(line)
            if len(self._context) > self.context_limit:
                self._context = self._context[-self.context_limit :]

    def _context_lines(self) -> list[str]:
        with self._context_lock:
            return [item.split("|", 1)[1] for item in self._context]

    def _bump(self, delta: int) -> None:
        with self._inflight_lock:
            self._inflight += delta
            busy = self._inflight > 0
        if self._running:
            self._emit_status("processing" if busy else "listening")

    def _emit_status(self, status: str) -> None:
        if status == self._status:
            return
        self._status = status
        self._safe(self.on_status, status)

    def _warn(self, message: str) -> None:
        logger.warning(message)
        self._safe(self.on_warning, message)

    @staticmethod
    def _safe(callback, value) -> None:
        if callback is None:
            return
        try:
            callback(value)
        except Exception:
            logger.exception("Pipeline callback failed")

    def _close_writers(self) -> None:
        for writer in self._writers.values():
            writer.close()
        self._writers.clear()


def build_pipeline(config, database: Database, callbacks: dict | None = None) -> Pipeline:
    from app.stt.factory import create_local_fallback, create_stt
    from app.translate.factory import create_translator
    from app.utils.paths import audio_dir

    hooks = callbacks or {}
    provider = (config.stt.provider or "").lower()
    return Pipeline(
        stt=create_stt(config),
        translator=create_translator(config),
        database=database,
        vad_factory=lambda: create_vad(config),
        translation_mode=config.translation.mode,
        fixed_target=config.translation.target_language,
        forced_language=config.stt.language,
        no_speech_threshold=float(config.stt.no_speech_threshold),
        context_segments=int(config.translation.context_segments),
        save_audio_dir=audio_dir() if config.audio.save_audio else None,
        fallback_to_local=provider in {"openai", "cloud"},
        local_fallback_factory=(lambda: create_local_fallback(config)),
        on_segment=hooks.get("on_segment"),
        on_partial=hooks.get("on_partial"),
        on_translation=hooks.get("on_translation"),
        on_status=hooks.get("on_status"),
        on_warning=hooks.get("on_warning"),
    )
