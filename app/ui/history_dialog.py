from __future__ import annotations

from pathlib import Path

from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import (
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
)

from app.storage.export import (
    render_ai_prompt,
    render_both,
    render_json,
    render_markdown,
    render_original,
    render_translation,
)


class HistoryDialog(QDialog):
    def __init__(self, database, i18n, summary_language: str, parent=None) -> None:
        super().__init__(parent)
        self.database = database
        self.i18n = i18n
        self.summary_language = summary_language
        self.setModal(True)
        self.resize(860, 560)
        layout = QVBoxLayout(self)
        body = QHBoxLayout()
        self.sessions = QListWidget()
        self.preview = QTextEdit()
        self.preview.setReadOnly(True)
        body.addWidget(self.sessions, 1)
        body.addWidget(self.preview, 2)
        layout.addLayout(body)
        self.empty = QLabel()
        layout.addWidget(self.empty)
        buttons = QHBoxLayout()
        self.copy_original_btn = QPushButton()
        self.copy_translation_btn = QPushButton()
        self.copy_both_btn = QPushButton()
        self.copy_ai_btn = QPushButton()
        self.export_btn = QPushButton()
        buttons.addWidget(self.copy_original_btn)
        buttons.addWidget(self.copy_translation_btn)
        buttons.addWidget(self.copy_both_btn)
        buttons.addWidget(self.copy_ai_btn)
        buttons.addWidget(self.export_btn)
        layout.addLayout(buttons)
        self.sessions.currentRowChanged.connect(self._show_current)
        self.copy_original_btn.clicked.connect(lambda: self._copy(render_original))
        self.copy_translation_btn.clicked.connect(lambda: self._copy(render_translation))
        self.copy_both_btn.clicked.connect(lambda: self._copy(render_both))
        self.copy_ai_btn.clicked.connect(self._copy_ai)
        self.export_btn.clicked.connect(self._export)
        self._retranslate()
        self.reload()

    def _retranslate(self) -> None:
        i18n = self.i18n
        self.setWindowTitle(i18n.t("history_title"))
        self.empty.setText(i18n.t("history_empty"))
        self.copy_original_btn.setText(i18n.t("copy_original"))
        self.copy_translation_btn.setText(i18n.t("copy_translation"))
        self.copy_both_btn.setText(i18n.t("copy_both"))
        self.copy_ai_btn.setText(i18n.t("copy_ai"))
        self.export_btn.setText(i18n.t("export_md"))

    def reload(self) -> None:
        self.sessions.clear()
        self._records = self.database.list_sessions()
        self.empty.setVisible(not self._records)
        for record in self._records:
            end = record.ended_at or "…"
            self.sessions.addItem(
                f"{record.title}  ({record.segment_count})  {record.started_at} → {end}"
            )
        if self._records:
            self.sessions.setCurrentRow(0)
        else:
            self.preview.clear()

    def _selected(self):
        row = self.sessions.currentRow()
        if row < 0 or row >= len(self._records):
            return None, []
        record = self._records[row]
        return record, self.database.list_segments(record.id)

    def _show_current(self, _row: int) -> None:
        record, segments = self._selected()
        if record is None:
            self.preview.clear()
            return
        self.preview.setPlainText(render_both(segments, self.i18n.labels()))

    def _copy(self, renderer) -> None:
        _record, segments = self._selected()
        if not segments:
            return
        QGuiApplication.clipboard().setText(renderer(segments, self.i18n.labels()))

    def _copy_ai(self) -> None:
        _record, segments = self._selected()
        if not segments:
            return
        text = render_ai_prompt(segments, self.summary_language, self.i18n.labels())
        QGuiApplication.clipboard().setText(text)

    def _export(self) -> None:
        record, segments = self._selected()
        if record is None:
            return
        path, _selected_filter = QFileDialog.getSaveFileName(
            self,
            self.i18n.t("export"),
            "transcript.md",
            "Markdown (*.md);;Text (*.txt);;JSON (*.json)",
        )
        if not path:
            return
        destination = Path(path)
        labels = self.i18n.labels()
        suffix = destination.suffix.lower()
        if suffix == ".json":
            text = render_json(record.id, segments)
        elif suffix == ".txt":
            text = render_both(segments, labels)
        else:
            text = render_markdown(segments, record.title, labels)
        destination.write_text(text, encoding="utf-8")
