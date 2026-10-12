from __future__ import annotations

import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path

from app.models import SessionRecord, TranscriptSegment


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


class Database:
    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(self.path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA synchronous=NORMAL")
        self._conn.execute("PRAGMA foreign_keys=ON")
        self._migrate()

    def close(self) -> None:
        with self._lock:
            self._conn.close()

    def _migrate(self) -> None:
        with self._lock:
            self._conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS sessions (
                    id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    started_at TEXT NOT NULL,
                    ended_at TEXT
                );
                CREATE TABLE IF NOT EXISTS segments (
                    id TEXT PRIMARY KEY,
                    session_id TEXT NOT NULL,
                    source TEXT NOT NULL,
                    start_time REAL NOT NULL,
                    end_time REAL NOT NULL,
                    language TEXT NOT NULL,
                    original_text TEXT NOT NULL,
                    translated_text TEXT,
                    target_language TEXT,
                    translation_status TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(session_id) REFERENCES sessions(id)
                );
                CREATE INDEX IF NOT EXISTS idx_segments_session
                    ON segments(session_id, start_time, created_at);
                """
            )
            self._conn.commit()

    def create_session(self, title: str | None = None) -> SessionRecord:
        import uuid

        started = utc_now()
        session_id = uuid.uuid4().hex
        label = title or f"Session {started.replace('T', ' ')}"
        with self._lock:
            self._conn.execute(
                "INSERT INTO sessions (id, title, started_at, ended_at) VALUES (?, ?, ?, NULL)",
                (session_id, label, started),
            )
            self._conn.commit()
        return SessionRecord(id=session_id, title=label, started_at=started, ended_at=None)

    def end_session(self, session_id: str) -> None:
        with self._lock:
            self._conn.execute(
                """
                UPDATE sessions
                SET ended_at = COALESCE(ended_at, ?)
                WHERE id = ?
                """,
                (utc_now(), session_id),
            )
            self._conn.commit()

    def insert_segment(self, segment: TranscriptSegment) -> None:
        with self._lock:
            self._conn.execute(
                """
                INSERT INTO segments (
                    id, session_id, source, start_time, end_time, language,
                    original_text, translated_text, target_language,
                    translation_status, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    segment.id,
                    segment.session_id,
                    segment.source,
                    segment.start_time,
                    segment.end_time,
                    segment.language,
                    segment.text,
                    segment.translated_text,
                    segment.target_language,
                    segment.translation_status,
                    segment.created_at,
                ),
            )
            self._conn.commit()

    def update_translation(
        self,
        segment_id: str,
        translated_text: str | None,
        target_language: str | None,
        status: str,
    ) -> None:
        with self._lock:
            self._conn.execute(
                """
                UPDATE segments
                SET translated_text = ?, target_language = ?, translation_status = ?
                WHERE id = ?
                """,
                (translated_text, target_language, status, segment_id),
            )
            self._conn.commit()

    def list_sessions(self) -> list[SessionRecord]:
        with self._lock:
            rows = self._conn.execute(
                """
                SELECT s.id, s.title, s.started_at, s.ended_at, COUNT(g.id) AS segment_count
                FROM sessions s
                LEFT JOIN segments g ON g.session_id = s.id
                GROUP BY s.id
                ORDER BY s.started_at DESC
                """
            ).fetchall()
        return [
            SessionRecord(
                id=row["id"],
                title=row["title"],
                started_at=row["started_at"],
                ended_at=row["ended_at"],
                segment_count=int(row["segment_count"]),
            )
            for row in rows
        ]

    def list_segments(self, session_id: str) -> list[TranscriptSegment]:
        with self._lock:
            rows = self._conn.execute(
                """
                SELECT * FROM segments
                WHERE session_id = ?
                ORDER BY start_time ASC, created_at ASC
                """,
                (session_id,),
            ).fetchall()
        return [_segment_from_row(row) for row in rows]

    def get_session(self, session_id: str) -> SessionRecord | None:
        for session in self.list_sessions():
            if session.id == session_id:
                return session
        return None


def _segment_from_row(row: sqlite3.Row) -> TranscriptSegment:
    return TranscriptSegment(
        id=row["id"],
        session_id=row["session_id"],
        source=row["source"],
        start_time=float(row["start_time"]),
        end_time=float(row["end_time"]),
        text=row["original_text"],
        language=row["language"],
        created_at=row["created_at"],
        is_partial=False,
        translated_text=row["translated_text"],
        target_language=row["target_language"],
        translation_status=row["translation_status"],
    )
