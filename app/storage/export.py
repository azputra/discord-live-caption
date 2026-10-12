from __future__ import annotations

import json

from app.models import TranscriptSegment
from app.utils.text import format_timestamp

DEFAULT_LABELS = {"me": "Me", "others": "Others"}

AI_SUMMARY_INSTRUCTION = (
    "Summarize this meeting: key points, decisions, action items "
    "with owners, open questions."
)


def _labels(labels: dict[str, str] | None) -> dict[str, str]:
    return labels or DEFAULT_LABELS


def _speaker(source: str, labels: dict[str, str] | None) -> str:
    return _labels(labels).get(source, source)


def text_for_language(segment: TranscriptSegment, language: str) -> str:
    if segment.language == language:
        return segment.text
    if segment.target_language == language and segment.translated_text:
        return segment.translated_text
    return segment.text


def _join(lines: list[str]) -> str:
    if not lines:
        return ""
    return "\n".join(lines).rstrip() + "\n"


def render_original(segments: list[TranscriptSegment], labels: dict[str, str] | None = None) -> str:
    lines = [
        f"[{format_timestamp(segment.start_time)}] {_speaker(segment.source, labels)} "
        f"({segment.language}): {segment.text}"
        for segment in segments
    ]
    return _join(lines)


def render_translation(segments: list[TranscriptSegment], labels: dict[str, str] | None = None) -> str:
    lines = []
    for segment in segments:
        if segment.translation_status == "done" and segment.translated_text:
            body = segment.translated_text
        else:
            body = segment.text
        lines.append(
            f"[{format_timestamp(segment.start_time)}] {_speaker(segment.source, labels)}: {body}"
        )
    return _join(lines)


def render_both(segments: list[TranscriptSegment], labels: dict[str, str] | None = None) -> str:
    blocks: list[str] = []
    for segment in segments:
        stamp = format_timestamp(segment.start_time)
        speaker = _speaker(segment.source, labels)
        lines = [f"[{stamp}] {speaker} ({segment.language})", segment.text]
        if (
            segment.translation_status == "done"
            and segment.translated_text
            and segment.translated_text != segment.text
        ):
            lines.append(segment.translated_text)
        blocks.append("\n".join(lines))
    return _join(["\n\n".join(blocks)] if blocks else [])


def render_single_language(
    segments: list[TranscriptSegment],
    language: str,
    labels: dict[str, str] | None = None,
) -> str:
    lines = [
        f"[{format_timestamp(segment.start_time)}] {_speaker(segment.source, labels)}: "
        f"{text_for_language(segment, language)}"
        for segment in segments
    ]
    return _join(lines)


def render_ai_prompt(
    segments: list[TranscriptSegment],
    language: str,
    labels: dict[str, str] | None = None,
) -> str:
    body = render_single_language(segments, language, labels).rstrip()
    return f"{AI_SUMMARY_INSTRUCTION}\n\n{body}\n"


def render_txt(segments: list[TranscriptSegment], labels: dict[str, str] | None = None) -> str:
    return render_both(segments, labels)


def render_markdown(
    segments: list[TranscriptSegment],
    title: str,
    labels: dict[str, str] | None = None,
) -> str:
    parts = [f"# {title}", ""]
    if not segments:
        parts.append("_No captions._")
        parts.append("")
    for segment in segments:
        stamp = format_timestamp(segment.start_time)
        speaker = _speaker(segment.source, labels)
        parts.append(f"## [{stamp}] {speaker} ({segment.language})")
        parts.append("")
        parts.append(segment.text)
        parts.append("")
        if (
            segment.translation_status == "done"
            and segment.translated_text
            and segment.translated_text != segment.text
        ):
            parts.append(f"> {segment.translated_text}")
            parts.append("")
    return "\n".join(parts).rstrip() + "\n"


def render_json(session_id: str, segments: list[TranscriptSegment]) -> str:
    payload = {
        "session_id": session_id,
        "segments": [
            {
                "timestamp": format_timestamp(segment.start_time),
                "start_time": segment.start_time,
                "end_time": segment.end_time,
                "source": segment.source,
                "language": segment.language,
                "original_text": segment.text,
                "translated_text": segment.translated_text,
                "target_language": segment.target_language,
            }
            for segment in segments
        ],
    }
    return json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
