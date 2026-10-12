import os
import time

import pytest

pytest.importorskip("PySide6")

import numpy as np
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import QApplication

from app.config import AppConfig
from app.models import AudioChunk, AudioDevice, StartResult
from app.storage.db import Database
from app.ui.history_dialog import HistoryDialog
from app.ui.i18n import I18n
from app.ui.main_window import MainWindow
from app.ui.settings_dialog import SettingsDialog


class FakeCapture:
    platform_name = "macos"
    last_error = None
    default_output_name = None

    def __init__(self, system_name: str = "BlackHole 2ch") -> None:
        self.system_name = system_name
        self.on_chunk = None
        self.started = False
        self._levels = {"me": 0.1, "others": 0.4}

    def list_system_devices(self):
        if not self.system_name:
            return []
        return [AudioDevice("10", self.system_name, 2, 48000, "loopback", True)]

    def list_mic_devices(self):
        return [AudioDevice("2", "MacBook Microphone", 1, 48000, "mic", True)]

    def start(self, system_device, mic_device, on_chunk, on_error, clock):
        del on_error
        self.started = True
        self.on_chunk = on_chunk
        self.clock = clock
        self.system_device = system_device
        self.mic_device = mic_device
        return StartResult(True, True, [])

    def stop(self) -> None:
        self.started = False

    def levels(self):
        return dict(self._levels)


def _app():
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    return QApplication.instance() or QApplication([])


def _config(tmp_path) -> AppConfig:
    config = AppConfig()
    config.stt.provider = "mock"
    config.translation.provider = "mock"
    config.vad.provider = "energy"
    config.stt.language = "auto"
    config.translation.mode = "swap"
    config.translation.display = "both"
    config.config_path = tmp_path / "config.yaml"
    config.env_path = tmp_path / ".env"
    return config


def test_window_translates_a_mocked_utterance(tmp_path):
    app = _app()
    capture = FakeCapture()
    window = MainWindow(
        _config(tmp_path),
        capture=capture,
        database=Database(tmp_path / "sessions.sqlite3"),
    )
    window.show()
    app.processEvents()
    assert window.windowTitle()
    assert not window.hint.isVisible()
    window.start_btn.click()
    app.processEvents()
    assert capture.started
    assert capture.system_device == "10"
    sample_rate = 16000
    times = np.arange(int(sample_rate * 0.5))
    tone = (0.25 * np.sin(2 * np.pi * 220 * times / sample_rate)).astype(np.float32)
    silence = np.zeros(int(sample_rate * 0.8), dtype=np.float32)
    capture.on_chunk(AudioChunk("others", tone, sample_rate, 0.0))
    capture.on_chunk(AudioChunk("others", silence, sample_rate, 0.5))
    deadline = time.time() + 5
    text = ""
    while time.time() < deadline:
        app.processEvents()
        text = window.caption_plaintext()
        if "Hello" in text and "[id] Hello" in text:
            break
        time.sleep(0.02)
    assert "Hello" in text
    assert "[id] Hello" in text
    window.copy_ai_btn.click()
    app.processEvents()
    clipboard = QGuiApplication.clipboard().text()
    assert clipboard.startswith("Summarize this meeting:")
    assert "Hello" in clipboard
    window.stop_btn.click()
    deadline = time.time() + 5
    while time.time() < deadline and not window.start_btn.isEnabled():
        app.processEvents()
        time.sleep(0.02)
    assert window.start_btn.isEnabled()
    rows = window.database.list_segments(window.pipeline.session_id)
    assert rows[0].text == "Hello"
    assert rows[0].translated_text == "[id] Hello"
    window.overlay_btn.click()
    app.processEvents()
    assert window.overlay.isVisible()
    window.overlay_btn.click()
    app.processEvents()
    assert not window.overlay.isVisible()
    window.close()


def test_missing_blackhole_shows_setup_steps(tmp_path):
    app = _app()
    window = MainWindow(
        _config(tmp_path),
        capture=FakeCapture(system_name=""),
        database=Database(tmp_path / "sessions.sqlite3"),
    )
    window.show()
    app.processEvents()
    assert window.hint.isVisible()
    assert "BlackHole" in window.hint.text()
    assert "Multi-Output" in window.hint.text()
    window.close()


def test_settings_and_history_open(tmp_path, monkeypatch):
    app = _app()
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    config = _config(tmp_path)
    config.env_path.write_text("OPENAI_API_KEY=sk-test\n", encoding="utf-8")
    dialog = SettingsDialog(config, I18n("en"))
    dialog.openai_key.setText("")
    dialog._save()
    assert "sk-test" in config.env_path.read_text(encoding="utf-8")
    assert config.config_path.is_file()
    history = HistoryDialog(Database(tmp_path / "empty.sqlite3"), I18n("id"), "id")
    history.show()
    app.processEvents()
    assert history.sessions.count() == 0
    assert history.empty.isVisible()
    dialog.close()
    history.close()
