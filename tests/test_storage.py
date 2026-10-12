from app.models import TranscriptSegment
from app.storage.db import Database


def _segment(session_id: str, text: str = "Halo") -> TranscriptSegment:
    return TranscriptSegment(
        id=f"seg-{text}",
        session_id=session_id,
        source="me",
        start_time=1,
        end_time=2,
        text=text,
        language="id",
        created_at="2026-01-01T00:00:01+00:00",
    )


def test_session_and_segment_roundtrip(tmp_path):
    database = Database(tmp_path / "sessions.sqlite3")
    session = database.create_session("Morning sync")
    segment = _segment(session.id)
    database.insert_segment(segment)
    database.update_translation(segment.id, "Hello", "en", "done")
    database.end_session(session.id)

    stored = database.list_sessions()
    assert stored[0].id == session.id
    assert stored[0].segment_count == 1
    assert stored[0].ended_at is not None
    rows = database.list_segments(session.id)
    assert rows[0].text == "Halo"
    assert rows[0].translated_text == "Hello"
    assert rows[0].target_language == "en"
    assert rows[0].translation_status == "done"
    database.close()


def test_segments_survive_reopen(tmp_path):
    path = tmp_path / "sessions.sqlite3"
    first = Database(path)
    session = first.create_session()
    first.insert_segment(_segment(session.id, "Keep me"))
    first.close()
    second = Database(path)
    assert second.list_segments(session.id)[0].text == "Keep me"
    second.close()
