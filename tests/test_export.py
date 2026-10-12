import json

from app.models import TranscriptSegment
from app.storage.export import (
    AI_SUMMARY_INSTRUCTION,
    render_ai_prompt,
    render_both,
    render_json,
    render_markdown,
    render_original,
    render_single_language,
    render_translation,
)


def _segment(**overrides) -> TranscriptSegment:
    values = {
        "id": "1",
        "session_id": "session",
        "source": "others",
        "start_time": 1.2,
        "end_time": 2.4,
        "text": "Halo",
        "language": "id",
        "created_at": "2026-01-01T00:00:00+00:00",
        "translated_text": "Hello",
        "target_language": "en",
        "translation_status": "done",
    }
    values.update(overrides)
    return TranscriptSegment(**values)


def _segments() -> list[TranscriptSegment]:
    return [
        _segment(),
        _segment(
            id="2",
            source="me",
            start_time=4,
            end_time=5,
            text="Thanks",
            language="en",
            translated_text="Terima kasih",
            target_language="id",
        ),
    ]


def test_original_translation_and_both():
    segments = _segments()
    original = render_original(segments)
    assert "[00:00:01] Others (id): Halo" in original
    assert "[00:00:04] Me (en): Thanks" in original
    translated = render_translation(segments)
    assert "[00:00:01] Others: Hello" in translated
    assert "[00:00:04] Me: Terima kasih" in translated
    both = render_both(segments)
    assert "Halo" in both and "Hello" in both
    assert "Thanks" in both and "Terima kasih" in both


def test_single_language_uses_original_when_it_already_matches():
    segments = _segments()
    english = render_single_language(segments, "en")
    indonesian = render_single_language(segments, "id")
    assert "[00:00:01] Others: Hello" in english
    assert "[00:00:04] Me: Thanks" in english
    assert "Halo" not in english
    assert "[00:00:01] Others: Halo" in indonesian
    assert "[00:00:04] Me: Terima kasih" in indonesian
    assert "Thanks" not in indonesian.split("Terima kasih")[-1]


def test_missing_translation_falls_back_to_original():
    segment = _segment(translated_text=None, target_language=None, translation_status="error")
    assert "Halo" in render_single_language([segment], "en")
    assert "Halo" in render_translation([segment])


def test_ai_prompt_has_the_required_instruction():
    text = render_ai_prompt(_segments(), "en")
    assert text.startswith(AI_SUMMARY_INSTRUCTION + "\n\n")
    assert "[00:00:01] Others: Hello" in text
    assert "[00:00:04] Me: Thanks" in text


def test_markdown_and_json():
    markdown = render_markdown(_segments(), "Standup")
    assert markdown.startswith("# Standup")
    assert "> Hello" in markdown
    payload = json.loads(render_json("session", _segments()))
    assert payload["session_id"] == "session"
    row = payload["segments"][0]
    assert row["timestamp"] == "00:00:01"
    assert row["source"] == "others"
    assert row["language"] == "id"
    assert row["original_text"] == "Halo"
    assert row["translated_text"] == "Hello"


def test_custom_speaker_labels():
    text = render_original(_segments(), {"me": "Saya", "others": "Yang lain"})
    assert "Yang lain" in text
    assert "Saya" in text
