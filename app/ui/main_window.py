from __future__ import annotations

import threading
import time
from pathlib import Path

from PySide6.QtCore import QObject, Qt, QTimer, Signal
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMenu,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from app.audio.capture import create_capture
from app.audio.devices import (
    blackhole_present,
    recommended_mic,
    recommended_system_device,
)
from app.config import save_config
from app.pipeline import build_pipeline
from app.storage.db import Database
from app.storage.export import (
    render_ai_prompt,
    render_both,
    render_json,
    render_markdown,
    render_original,
    render_single_language,
    render_translation,
    render_txt,
)
from app.translate.factory import create_summarizer
from app.ui.history_dialog import HistoryDialog
from app.ui.i18n import I18n
from app.ui.overlay import OverlayWindow
from app.ui.settings_dialog import SettingsDialog
from app.ui.theme import apply_theme
from app.ui.widgets import CaptionRow
from app.utils.paths import database_path
from app.utils.text import format_timestamp

_DOT_COLORS = {
    "idle": "#8a8175",
    "listening": "#1f8a4c",
    "processing": "#c47b12",
    "error": "#b42318",
}


class UiBridge(QObject):
    segment = Signal(object)
    partial = Signal(object)
    translation = Signal(object)
    status = Signal(str)
    warning = Signal(str)
    stopped = Signal()
    summary_ready = Signal(str)
    summary_failed = Signal(str)


class MainWindow(QMainWindow):
    def __init__(self, config, capture=None, database=None, pipeline_builder=None) -> None:
        super().__init__()
        self.config = config
        self.i18n = I18n(config.ui.language)
        self.capture = capture if capture is not None else create_capture()
        self.database = database if database is not None else Database(database_path())
        self._pipeline_builder = pipeline_builder or build_pipeline
        self.pipeline = None
        self._running = False
        self._stick = True
        self._indicator = "idle"
        self._banner = ""
        self._banner_error = False
        self._banner_until = 0.0
        self._loading_ui = True
        self._rows: dict[str, CaptionRow] = {}
        self._partials: dict[str, CaptionRow] = {}
        self._segments: list = []
        self._system_devices = []
        self._mic_devices = []
        self.bridge = UiBridge()
        self._connect_bridge()
        self._build()
        self._loading_ui = True
        self._retranslate()
        self._refresh_devices()
        self.apply_system_theme()
        self._connect_prefs()
        self.i18n.language_changed.connect(self._retranslate)
        self._loading_ui = False
        self.level_timer = QTimer(self)
        self.level_timer.setInterval(200)
        self.level_timer.timeout.connect(self._tick)
        self.level_timer.start()
        self.resize(1100, 760)

    def _connect_bridge(self) -> None:
        queued = Qt.ConnectionType.QueuedConnection
        self.bridge.segment.connect(self._add_segment, queued)
        self.bridge.partial.connect(self._add_partial, queued)
        self.bridge.translation.connect(self._update_translation, queued)
        self.bridge.status.connect(self._on_status, queued)
        self.bridge.warning.connect(self._on_warning, queued)
        self.bridge.stopped.connect(self._on_stopped, queued)
        self.bridge.summary_ready.connect(self._show_summary, queued)
        self.bridge.summary_failed.connect(self._summary_failed, queued)

    def _build(self) -> None:
        shell = QWidget()
        shell.setObjectName("root")
        self.setCentralWidget(shell)
        root = QVBoxLayout(shell)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(8)

        top = QHBoxLayout()
        self.start_btn = QPushButton()
        self.start_btn.setObjectName("startButton")
        self.stop_btn = QPushButton()
        self.stop_btn.setObjectName("stopButton")
        self.stop_btn.setEnabled(False)
        self.dot = QLabel()
        self.dot.setFixedSize(12, 12)
        self.status_label = QLabel()
        self.ui_lang_combo = QComboBox()
        self.theme_combo = QComboBox()
        self.overlay_btn = QPushButton()
        top.addWidget(self.start_btn)
        top.addWidget(self.stop_btn)
        top.addWidget(self.dot)
        top.addWidget(self.status_label, 1)
        top.addWidget(self.ui_lang_combo)
        top.addWidget(self.theme_combo)
        top.addWidget(self.overlay_btn)
        root.addLayout(top)

        options = QHBoxLayout()
        self.speech_combo = QComboBox()
        self.mode_combo = QComboBox()
        self.target_combo = QComboBox()
        self.display_combo = QComboBox()
        self.summary_combo = QComboBox()
        for combo in (
            self.speech_combo,
            self.mode_combo,
            self.target_combo,
            self.display_combo,
            self.summary_combo,
            self.ui_lang_combo,
            self.theme_combo,
        ):
            combo.setMinimumWidth(120)
        options.addWidget(self.speech_combo)
        options.addWidget(self.mode_combo)
        options.addWidget(self.target_combo)
        options.addWidget(self.display_combo)
        options.addWidget(self.summary_combo)
        options.addStretch(1)
        root.addLayout(options)

        devices = QHBoxLayout()
        self.system_combo = QComboBox()
        self.mic_combo = QComboBox()
        self.system_combo.setMinimumWidth(220)
        self.mic_combo.setMinimumWidth(220)
        self.others_caption = QLabel()
        self.me_caption = QLabel()
        self.others_meter = self._meter()
        self.me_meter = self._meter()
        self.refresh_btn = QPushButton()
        devices.addWidget(self.system_combo, 2)
        devices.addWidget(self.others_caption)
        devices.addWidget(self.others_meter, 1)
        devices.addWidget(self.mic_combo, 2)
        devices.addWidget(self.me_caption)
        devices.addWidget(self.me_meter, 1)
        devices.addWidget(self.refresh_btn)
        root.addLayout(devices)

        self.hint = QLabel()
        self.hint.setObjectName("hintBanner")
        self.hint.setWordWrap(True)
        self.hint.hide()
        root.addWidget(self.hint)

        self.placeholder = QLabel()
        self.placeholder.setObjectName("placeholder")
        self.placeholder.setWordWrap(True)
        root.addWidget(self.placeholder)

        self.feed = QWidget()
        self.feed_layout = QVBoxLayout(self.feed)
        self.feed_layout.setContentsMargins(0, 0, 0, 0)
        self.feed_layout.setSpacing(8)
        self.feed_layout.addStretch(1)
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setWidget(self.feed)
        self.scroll.verticalScrollBar().valueChanged.connect(self._on_scroll)
        root.addWidget(self.scroll, 1)

        self.jump_btn = QPushButton()
        self.jump_btn.hide()
        root.addWidget(self.jump_btn, alignment=Qt.AlignmentFlag.AlignRight)

        copies = QHBoxLayout()
        self.copy_original_btn = QPushButton()
        self.copy_translation_btn = QPushButton()
        self.copy_both_btn = QPushButton()
        self.copy_single_btn = QPushButton()
        self.copy_ai_btn = QPushButton()
        for button in (
            self.copy_original_btn,
            self.copy_translation_btn,
            self.copy_both_btn,
            self.copy_single_btn,
            self.copy_ai_btn,
        ):
            copies.addWidget(button)
        root.addLayout(copies)

        tools = QHBoxLayout()
        self.export_btn = QPushButton()
        self.export_menu = QMenu(self)
        self.action_txt = self.export_menu.addAction("")
        self.action_md = self.export_menu.addAction("")
        self.action_json = self.export_menu.addAction("")
        self.action_single = self.export_menu.addAction("")
        self.export_btn.setMenu(self.export_menu)
        self.summarize_btn = QPushButton()
        self.history_btn = QPushButton()
        self.settings_btn = QPushButton()
        tools.addWidget(self.export_btn)
        tools.addWidget(self.summarize_btn)
        tools.addWidget(self.history_btn)
        tools.addWidget(self.settings_btn)
        tools.addStretch(1)
        root.addLayout(tools)

        self.overlay = OverlayWindow(
            on_change=self._on_overlay_change,
            on_close=self._on_overlay_closed,
            opacity=float(self.config.ui.overlay_opacity),
            font_size=int(self.config.ui.overlay_font_size),
            placeholder="",
        )

        self.start_btn.clicked.connect(self._on_start)
        self.stop_btn.clicked.connect(self._on_stop)
        self.refresh_btn.clicked.connect(self._refresh_devices)
        self.jump_btn.clicked.connect(self._jump_latest)
        self.overlay_btn.clicked.connect(self._toggle_overlay)
        self.copy_original_btn.clicked.connect(lambda: self._copy("original"))
        self.copy_translation_btn.clicked.connect(lambda: self._copy("translation"))
        self.copy_both_btn.clicked.connect(lambda: self._copy("both"))
        self.copy_single_btn.clicked.connect(lambda: self._copy("single"))
        self.copy_ai_btn.clicked.connect(lambda: self._copy("ai"))
        self.action_txt.triggered.connect(lambda: self._export("txt"))
        self.action_md.triggered.connect(lambda: self._export("md"))
        self.action_json.triggered.connect(lambda: self._export("json"))
        self.action_single.triggered.connect(lambda: self._export("single"))
        self.summarize_btn.clicked.connect(self._summarize)
        self.history_btn.clicked.connect(self._open_history)
        self.settings_btn.clicked.connect(self._open_settings)
        self._paint("idle")

    def _meter(self) -> QProgressBar:
        meter = QProgressBar()
        meter.setRange(0, 100)
        meter.setValue(0)
        meter.setTextVisible(False)
        return meter

    def _connect_prefs(self) -> None:
        self.speech_combo.currentIndexChanged.connect(self._on_pref_changed)
        self.mode_combo.currentIndexChanged.connect(self._on_pref_changed)
        self.target_combo.currentIndexChanged.connect(self._on_pref_changed)
        self.display_combo.currentIndexChanged.connect(self._on_display_changed)
        self.summary_combo.currentIndexChanged.connect(self._on_pref_changed)
        self.ui_lang_combo.currentIndexChanged.connect(self._on_ui_language)
        self.theme_combo.currentIndexChanged.connect(self._on_theme)
        self.system_combo.currentIndexChanged.connect(self._on_pref_changed)
        self.mic_combo.currentIndexChanged.connect(self._on_pref_changed)

    def _set_combo(self, combo: QComboBox, items: list[tuple[str, str]], current: str) -> None:
        combo.blockSignals(True)
        combo.clear()
        for label, value in items:
            combo.addItem(label, value)
        index = combo.findData(current)
        combo.setCurrentIndex(index if index >= 0 else 0)
        combo.blockSignals(False)

    def _retranslate(self, *_args) -> None:
        self._loading_ui = True
        i18n = self.i18n
        self.setWindowTitle(i18n.t("app_title"))
        self.start_btn.setText(i18n.t("start"))
        self.stop_btn.setText(i18n.t("stop"))
        self.refresh_btn.setText(i18n.t("refresh"))
        self.jump_btn.setText(i18n.t("jump_latest"))
        self.others_caption.setText(i18n.t("level_others"))
        self.me_caption.setText(i18n.t("level_me"))
        self.copy_original_btn.setText(i18n.t("copy_original"))
        self.copy_translation_btn.setText(i18n.t("copy_translation"))
        self.copy_both_btn.setText(i18n.t("copy_both"))
        self.copy_single_btn.setText(i18n.t("copy_single"))
        self.copy_ai_btn.setText(i18n.t("copy_ai"))
        self.export_btn.setText(i18n.t("export"))
        self.summarize_btn.setText(i18n.t("summarize"))
        self.history_btn.setText(i18n.t("history"))
        self.settings_btn.setText(i18n.t("settings"))
        self.action_txt.setText(i18n.t("export_txt"))
        self.action_md.setText(i18n.t("export_md"))
        self.action_json.setText(i18n.t("export_json"))
        self.action_single.setText(i18n.t("export_single"))
        self.placeholder.setText(i18n.t("caption_placeholder"))
        self.overlay_btn.setText(i18n.t("overlay_hide") if self.overlay.isVisible() else i18n.t("overlay_show"))
        self.overlay.set_placeholder(i18n.t("caption_placeholder"))
        self.overlay.set_chrome(i18n.t("overlay_drag"), i18n.t("overlay_opacity"), i18n.t("overlay_font"))
        self._set_combo(
            self.speech_combo,
            [
                (i18n.t("speech_auto"), "auto"),
                (i18n.t("lang_id"), "id"),
                (i18n.t("lang_en"), "en"),
            ],
            self.config.stt.language,
        )
        self._set_combo(
            self.mode_combo,
            [(i18n.t("mode_swap"), "swap"), (i18n.t("mode_fixed"), "fixed")],
            self.config.translation.mode,
        )
        self._set_combo(
            self.target_combo,
            [(i18n.t("lang_en"), "en"), (i18n.t("lang_id"), "id")],
            self.config.translation.target_language,
        )
        self._set_combo(
            self.display_combo,
            [
                (i18n.t("display_both"), "both"),
                (i18n.t("display_original"), "original"),
                (i18n.t("display_translation"), "translation"),
            ],
            self.config.translation.display,
        )
        self._set_combo(
            self.summary_combo,
            [(i18n.t("lang_en"), "en"), (i18n.t("lang_id"), "id")],
            self.config.ui.summary_language,
        )
        self._set_combo(
            self.ui_lang_combo,
            [(i18n.t("lang_en"), "en"), (i18n.t("lang_id"), "id")],
            self.i18n.language,
        )
        self._set_combo(
            self.theme_combo,
            [
                (i18n.t("theme_system"), "system"),
                (i18n.t("theme_light"), "light"),
                (i18n.t("theme_dark"), "dark"),
            ],
            self.config.ui.theme,
        )
        self._prefix_combo(self.speech_combo, i18n.t("speech_language"))
        self._prefix_combo(self.mode_combo, i18n.t("translation_mode"))
        self._prefix_combo(self.target_combo, i18n.t("target_language"))
        self._prefix_combo(self.display_combo, i18n.t("display"))
        self._prefix_combo(self.summary_combo, i18n.t("summary_language"))
        self._prefix_combo(self.ui_lang_combo, i18n.t("ui_language"))
        self._prefix_combo(self.theme_combo, i18n.t("theme"))
        self.target_combo.setEnabled(self.mode_combo.currentData() == "fixed")
        self._refresh_rows()
        self._refresh_hint()
        self._refresh_status()
        self._sync_overlay()
        self._loading_ui = False

    def _prefix_combo(self, combo: QComboBox, prefix: str) -> None:
        combo.blockSignals(True)
        current = combo.currentData()
        for index in range(combo.count()):
            value = combo.itemData(index)
            label = combo.itemText(index)
            if ":" in label:
                label = label.split(":", 1)[1].strip()
            combo.setItemText(index, f"{prefix}: {label}")
        restored = combo.findData(current)
        if restored >= 0:
            combo.setCurrentIndex(restored)
        combo.blockSignals(False)

    def apply_system_theme(self) -> None:
        if self.config.ui.theme != "system":
            return
        app = QApplication.instance()
        if app is not None:
            apply_theme(app, "system")

    def _apply_selected_theme(self) -> None:
        app = QApplication.instance()
        if app is not None:
            apply_theme(app, self.config.ui.theme)

    def _refresh_devices(self) -> None:
        self._system_devices = list(self.capture.list_system_devices())
        self._mic_devices = list(self.capture.list_mic_devices())
        output_name = getattr(self.capture, "default_output_name", None)
        system_pick = recommended_system_device(
            self._system_devices,
            self.capture.platform_name,
            output_name,
        )
        mic_pick = recommended_mic(self._mic_devices)
        missing_system = self._fill_devices(
            self.system_combo,
            self._system_devices,
            self.config.audio.system_device,
            system_pick,
        )
        missing_mic = self._fill_devices(
            self.mic_combo,
            self._mic_devices,
            self.config.audio.mic_device,
            mic_pick,
        )
        self._refresh_hint()
        if missing_system or missing_mic:
            self._flash(self.i18n.t("saved_device_missing"), error=True)

    def _fill_devices(self, combo, devices, saved_id, recommended) -> bool:
        combo.blockSignals(True)
        combo.clear()
        for device in devices:
            combo.addItem(device.name, device.id)
        saved = None if saved_id is None else str(saved_id)
        known = {device.id for device in devices}
        missing = bool(saved) and saved not in known
        target = saved if saved in known else None
        if target is None and recommended is not None:
            target = recommended.id
        index = combo.findData(target) if target is not None else -1
        if index < 0 and combo.count():
            index = 0
        if index >= 0:
            combo.setCurrentIndex(index)
        combo.blockSignals(False)
        return missing

    def _refresh_hint(self) -> None:
        platform_name = getattr(self.capture, "platform_name", "")
        if platform_name == "macos" and not blackhole_present(self._system_devices):
            self.hint.setText(
                self.i18n.t("blackhole_missing") + "\n\n" + self.i18n.t("blackhole_steps")
            )
            self.hint.show()
            return
        if platform_name == "windows" and not self._system_devices:
            message = getattr(self.capture, "last_error", None) or self.i18n.t(
                "windows_loopback_missing"
            )
            self.hint.setText(message)
            self.hint.show()
            return
        self.hint.hide()

    def _on_pref_changed(self) -> None:
        if self._loading_ui:
            return
        self._pull_prefs()
        self.target_combo.setEnabled(self.config.translation.mode == "fixed")
        self._sync_pipeline_settings()
        save_config(self.config)

    def _on_display_changed(self) -> None:
        self._on_pref_changed()
        self._refresh_rows()
        self._sync_overlay()

    def _on_ui_language(self) -> None:
        if self._loading_ui:
            return
        self.config.ui.language = self.ui_lang_combo.currentData() or "en"
        save_config(self.config)
        self.i18n.set_language(self.config.ui.language)

    def _on_theme(self) -> None:
        if self._loading_ui:
            return
        self.config.ui.theme = self.theme_combo.currentData() or "system"
        save_config(self.config)
        self._apply_selected_theme()

    def _pull_prefs(self) -> None:
        self.config.stt.language = self.speech_combo.currentData() or "auto"
        self.config.translation.mode = self.mode_combo.currentData() or "swap"
        self.config.translation.target_language = self.target_combo.currentData() or "en"
        self.config.translation.display = self.display_combo.currentData() or "both"
        self.config.ui.summary_language = self.summary_combo.currentData() or "en"
        self.config.audio.system_device = self.system_combo.currentData()
        self.config.audio.mic_device = self.mic_combo.currentData()

    def _sync_pipeline_settings(self) -> None:
        if self.pipeline is None:
            return
        self.pipeline.forced_language = self.config.stt.language
        self.pipeline.translation_mode = self.config.translation.mode
        self.pipeline.fixed_target = self.config.translation.target_language

    def _on_start(self) -> None:
        if self._running:
            return
        self._pull_prefs()
        save_config(self.config)
        self._clear_feed()
        callbacks = {
            "on_segment": self.bridge.segment.emit,
            "on_partial": self.bridge.partial.emit,
            "on_translation": self.bridge.translation.emit,
            "on_status": self.bridge.status.emit,
            "on_warning": self.bridge.warning.emit,
        }
        try:
            self.pipeline = self._pipeline_builder(self.config, self.database, callbacks)
            self.pipeline.open_session()
            result = self.capture.start(
                self.config.audio.system_device,
                self.config.audio.mic_device,
                on_chunk=self.pipeline.push_audio,
                on_error=self._on_capture_error,
                clock=self.pipeline.clock,
            )
            if not result.system_started and not result.mic_started:
                self.pipeline.close_session()
                self.pipeline = None
                detail = "; ".join(result.errors) or self.i18n.t("capture_failed")
                self._fail(detail)
                return
            self.pipeline.start_workers()
        except Exception as exc:
            self.capture.stop()
            if self.pipeline is not None:
                self.pipeline.close_session()
                self.pipeline = None
            self._fail(str(exc))
            return
        self._running = True
        self._stick = True
        self.start_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)
        self.system_combo.setEnabled(False)
        self.mic_combo.setEnabled(False)
        if result.errors:
            self._flash("; ".join(result.errors), error=True)
        self._sync_overlay()

    def _on_stop(self) -> None:
        if not self._running:
            return
        self._running = False
        self.start_btn.setEnabled(False)
        self.stop_btn.setEnabled(False)
        self.capture.stop()
        pipeline = self.pipeline

        def worker() -> None:
            try:
                if pipeline is not None:
                    pipeline.shutdown()
            finally:
                self.bridge.stopped.emit()

        threading.Thread(target=worker, name="session-stop", daemon=True).start()

    def _on_stopped(self) -> None:
        self._running = False
        self.start_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        self.system_combo.setEnabled(True)
        self.mic_combo.setEnabled(True)
        self.others_meter.setValue(0)
        self.me_meter.setValue(0)
        self._indicator = "idle"
        self._refresh_status()

    def _on_capture_error(self, source: str, message: str) -> None:
        label = self.i18n.t("level_me" if source == "me" else "level_others")
        self.bridge.warning.emit(f"{self.i18n.t('device_error')} ({label}): {message}")

    def _add_partial(self, segment) -> None:
        row = self._partials.get(segment.source)
        if row is None:
            row = CaptionRow()
            self._partials[segment.source] = row
            self.feed_layout.insertWidget(self.feed_layout.count() - 1, row)
        row.show_segment(
            segment,
            self.i18n.labels(),
            self._display_mode(),
            self.i18n.t("translation_pending"),
            self.i18n.t("translation_failed"),
            self.i18n.t("partial"),
        )
        self.placeholder.hide()
        self._follow_scroll()
        self._sync_overlay()

    def _add_segment(self, segment) -> None:
        partial = self._partials.pop(segment.source, None)
        if partial is not None:
            self.feed_layout.removeWidget(partial)
            partial.deleteLater()
        row = self._rows.get(segment.id)
        if row is None:
            row = CaptionRow()
            self._rows[segment.id] = row
            self._segments.append(segment)
            self.feed_layout.insertWidget(self.feed_layout.count() - 1, row)
        row.show_segment(
            segment,
            self.i18n.labels(),
            self._display_mode(),
            self.i18n.t("translation_pending"),
            self.i18n.t("translation_failed"),
            self.i18n.t("partial"),
        )
        self.placeholder.hide()
        self._follow_scroll()
        self._sync_overlay()

    def _update_translation(self, segment) -> None:
        for index, existing in enumerate(self._segments):
            if existing.id == segment.id:
                self._segments[index] = segment
                break
        row = self._rows.get(segment.id)
        if row is not None:
            row.show_segment(
                segment,
                self.i18n.labels(),
                self._display_mode(),
                self.i18n.t("translation_pending"),
                self.i18n.t("translation_failed"),
                self.i18n.t("partial"),
            )
        self._sync_overlay()

    def _refresh_rows(self) -> None:
        labels = self.i18n.labels()
        mode = self._display_mode()
        pending = self.i18n.t("translation_pending")
        failed = self.i18n.t("translation_failed")
        partial = self.i18n.t("partial")
        for row in list(self._rows.values()) + list(self._partials.values()):
            if row.segment is not None:
                row.show_segment(row.segment, labels, mode, pending, failed, partial)

    def _clear_feed(self) -> None:
        for row in list(self._rows.values()) + list(self._partials.values()):
            self.feed_layout.removeWidget(row)
            row.deleteLater()
        self._rows.clear()
        self._partials.clear()
        self._segments.clear()
        self.placeholder.show()
        self.jump_btn.hide()
        self._stick = True

    def _display_mode(self) -> str:
        return self.display_combo.currentData() or "both"

    def _summary_language(self) -> str:
        return self.summary_combo.currentData() or "en"

    def _on_scroll(self, value: int) -> None:
        bar = self.scroll.verticalScrollBar()
        at_bottom = bar.maximum() - value <= 24
        self._stick = at_bottom
        self.jump_btn.setVisible(not at_bottom and bool(self._segments or self._partials))

    def _follow_scroll(self) -> None:
        if not self._stick:
            self.jump_btn.show()
            return
        bar = self.scroll.verticalScrollBar()
        QTimer.singleShot(0, lambda: bar.setValue(bar.maximum()))

    def _jump_latest(self) -> None:
        bar = self.scroll.verticalScrollBar()
        bar.setValue(bar.maximum())
        self._stick = True
        self.jump_btn.hide()

    def _toggle_overlay(self) -> None:
        if self.overlay.isVisible():
            self.overlay.hide()
        else:
            self.overlay.setWindowOpacity(float(self.config.ui.overlay_opacity))
            self.overlay.show()
            self.overlay.raise_()
            self._sync_overlay()
        self.overlay_btn.setText(
            self.i18n.t("overlay_hide") if self.overlay.isVisible() else self.i18n.t("overlay_show")
        )

    def _on_overlay_closed(self) -> None:
        self.overlay_btn.setText(self.i18n.t("overlay_show"))

    def _on_overlay_change(self, opacity: float, font_size: int) -> None:
        self.config.ui.overlay_opacity = float(opacity)
        self.config.ui.overlay_font_size = int(font_size)
        if not self._loading_ui:
            save_config(self.config)

    def _sync_overlay(self) -> None:
        if not self.overlay.isVisible():
            return
        entries = list(self._segments)
        for source in ("others", "me"):
            row = self._partials.get(source)
            if row is not None and row.segment is not None:
                entries.append(row.segment)
        limit = max(1, int(self.config.ui.overlay_lines))
        blocks = [self._overlay_block(segment) for segment in entries[-limit:]]
        self.overlay.set_lines(blocks)

    def _overlay_block(self, segment) -> str:
        speaker = self.i18n.labels().get(segment.source, segment.source)
        lines = [f"{format_timestamp(segment.start_time)}  {speaker}"]
        mode = self._display_mode()
        if mode in {"original", "both"}:
            lines.append(segment.text)
        if mode in {"translation", "both"} and not (mode == "both" and segment.translation_status == "skipped"):
            if segment.translation_status == "done" and segment.translated_text:
                if mode == "translation" or segment.translated_text != segment.text:
                    lines.append(segment.translated_text)
            elif mode == "translation":
                lines.append(segment.text)
            elif segment.translation_status == "pending" and not segment.is_partial:
                lines.append(self.i18n.t("translation_pending"))
        return "\n".join(lines)

    def _current_segments(self):
        if self.pipeline is not None and self.pipeline.session_id:
            return self.database.list_segments(self.pipeline.session_id)
        return []

    def _require_segments(self):
        segments = self._current_segments()
        if not segments:
            self._flash(self.i18n.t("empty_transcript"), error=True)
            return None
        return segments

    def _copy(self, kind: str) -> None:
        segments = self._require_segments()
        if segments is None:
            return
        labels = self.i18n.labels()
        language = self._summary_language()
        if kind == "original":
            text = render_original(segments, labels)
        elif kind == "translation":
            text = render_translation(segments, labels)
        elif kind == "both":
            text = render_both(segments, labels)
        elif kind == "single":
            text = render_single_language(segments, language, labels)
        else:
            text = render_ai_prompt(segments, language, labels)
        QGuiApplication.clipboard().setText(text)
        self._flash(self.i18n.t("copied"), error=False)

    def _export(self, kind: str) -> None:
        segments = self._require_segments()
        if segments is None:
            return
        suffix = {"txt": ".txt", "md": ".md", "json": ".json", "single": ".txt"}[kind]
        filters = {
            "txt": "Text (*.txt)",
            "md": "Markdown (*.md)",
            "json": "JSON (*.json)",
            "single": "Text (*.txt)",
        }[kind]
        path, _selected = QFileDialog.getSaveFileName(
            self,
            self.i18n.t("export"),
            f"transcript{suffix}",
            filters,
        )
        if not path:
            return
        labels = self.i18n.labels()
        if kind == "txt":
            text = render_txt(segments, labels)
        elif kind == "md":
            title = "Meeting transcript"
            session = None
            if self.pipeline is not None and self.pipeline.session_id:
                session = self.database.get_session(self.pipeline.session_id)
            if session is not None:
                title = session.title
            text = render_markdown(segments, title, labels)
        elif kind == "json":
            session_id = self.pipeline.session_id if self.pipeline is not None else ""
            text = render_json(session_id or "", segments)
        else:
            text = render_single_language(segments, self._summary_language(), labels)
        Path(path).write_text(text, encoding="utf-8")
        self._flash(self.i18n.t("export_done"), error=False)

    def _summarize(self) -> None:
        segments = self._require_segments()
        if segments is None:
            return
        prompt = render_ai_prompt(segments, self._summary_language(), self.i18n.labels())
        self.summarize_btn.setEnabled(False)
        self._flash(self.i18n.t("summarize_running"), error=False)

        def work() -> None:
            try:
                summary = create_summarizer(self.config).summarize(prompt)
            except Exception as exc:
                self.bridge.summary_failed.emit(str(exc))
                return
            self.bridge.summary_ready.emit(summary)

        threading.Thread(target=work, name="summarize", daemon=True).start()

    def _show_summary(self, text: str) -> None:
        self.summarize_btn.setEnabled(True)
        box = QMessageBox(self)
        box.setWindowTitle(self.i18n.t("summarize_title"))
        box.setText(self.i18n.t("summarize_title"))
        box.setDetailedText(text)
        box.setInformativeText(text[:1200])
        box.exec()

    def _summary_failed(self, message: str) -> None:
        self.summarize_btn.setEnabled(True)
        self._flash(f"{self.i18n.t('summary_failed')}: {message}", error=True)

    def _open_history(self) -> None:
        dialog = HistoryDialog(
            self.database,
            self.i18n,
            self._summary_language(),
            self,
        )
        dialog.exec()

    def _open_settings(self) -> None:
        dialog = SettingsDialog(self.config, self.i18n, self)
        dialog.exec()

    def _on_status(self, status: str) -> None:
        if status in _DOT_COLORS:
            self._indicator = status
        self._refresh_status()

    def _on_warning(self, message: str) -> None:
        self._flash(message, error=True)

    def _fail(self, message: str) -> None:
        self._indicator = "error"
        self._flash(message, error=True)
        self.start_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)

    def _flash(self, message: str, error: bool) -> None:
        self._banner = message
        self._banner_error = error
        self._banner_until = time.monotonic() + (8 if error else 2)
        if error:
            self._indicator = "error" if self._indicator == "idle" else self._indicator
        self._refresh_status()

    def _tick(self) -> None:
        if self._running:
            levels = self.capture.levels()
            self.others_meter.setValue(int(max(0.0, min(1.0, levels.get("others", 0.0))) * 100))
            self.me_meter.setValue(int(max(0.0, min(1.0, levels.get("me", 0.0))) * 100))
        self._refresh_status()

    def _refresh_status(self) -> None:
        now = time.monotonic()
        if self._banner and now < self._banner_until:
            self.status_label.setText(self._banner)
            self._paint("error" if self._banner_error else self._indicator)
            return
        label = self.i18n.t(f"status_{self._indicator}")
        if self._running and self.pipeline is not None:
            label = f"{label} · {format_timestamp(self.pipeline.clock())}"
        self.status_label.setText(label)
        self._paint(self._indicator)

    def _paint(self, status: str) -> None:
        color = _DOT_COLORS.get(status, _DOT_COLORS["idle"])
        self.dot.setStyleSheet(f"background: {color}; border-radius: 6px;")

    def caption_plaintext(self) -> str:
        chunks: list[str] = []
        for row in list(self._rows.values()) + list(self._partials.values()):
            chunks.append(row.original.text())
            chunks.append(row.translation.text())
        return "\n".join(chunks)

    def closeEvent(self, event) -> None:
        self.capture.stop()
        if self.pipeline is not None and self.pipeline.session_id:
            self.database.end_session(self.pipeline.session_id)
        if self._running and self.pipeline is not None:
            pipeline = self.pipeline
            threading.Thread(target=pipeline.shutdown, name="session-close", daemon=True).start()
        self.overlay.hide()
        event.accept()
