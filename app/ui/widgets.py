from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QLabel, QVBoxLayout

from app.utils.text import format_timestamp


class CaptionRow(QFrame):
    def __init__(self) -> None:
        super().__init__()
        self.segment = None
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(2)
        self.meta = QLabel()
        self.meta.setObjectName("captionMeta")
        self.original = QLabel()
        self.original.setObjectName("captionOriginal")
        self.original.setWordWrap(True)
        self.original.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.translation = QLabel()
        self.translation.setObjectName("captionTranslation")
        self.translation.setWordWrap(True)
        self.translation.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(self.meta)
        layout.addWidget(self.original)
        layout.addWidget(self.translation)

    def show_segment(self, segment, labels: dict[str, str], mode: str, pending: str, failed: str, partial_label: str) -> None:
        self.segment = segment
        speaker = labels.get(segment.source, segment.source)
        suffix = f" · {partial_label}" if segment.is_partial else ""
        self.meta.setText(f"{format_timestamp(segment.start_time)}  {speaker}{suffix}")
        self.original.setText(segment.text)
        self.setObjectName("captionPartial" if segment.is_partial else "captionCard")
        status = segment.translation_status
        if mode == "original":
            self.original.setVisible(True)
            self.translation.setVisible(False)
            return
        if mode == "both":
            self.original.setVisible(True)
            if status == "done" and segment.translated_text and segment.translated_text != segment.text:
                self.translation.setVisible(True)
                self.translation.setText(segment.translated_text)
            elif status == "pending" and not segment.is_partial:
                self.translation.setVisible(True)
                self.translation.setText(pending)
            elif status == "error":
                self.translation.setVisible(True)
                self.translation.setText(failed)
            else:
                self.translation.setVisible(False)
            return
        self.original.setVisible(False)
        self.translation.setVisible(True)
        if status == "done" and segment.translated_text:
            self.translation.setText(segment.translated_text)
        elif status == "error":
            self.translation.setText(failed)
        elif status == "pending" and not segment.is_partial:
            self.translation.setText(pending)
        else:
            self.translation.setText(segment.text)
