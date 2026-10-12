from __future__ import annotations

from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLabel,
    QLineEdit,
    QVBoxLayout,
)

from app.config import api_key_status, save_config, write_env_key
from app.utils.paths import database_path, log_dir


class SettingsDialog(QDialog):
    def __init__(self, config, i18n, parent=None) -> None:
        super().__init__(parent)
        self.config = config
        self.i18n = i18n
        self.setModal(True)
        layout = QVBoxLayout(self)
        form = QFormLayout()
        self.stt_combo = QComboBox()
        self.model_combo = QComboBox()
        self.translation_combo = QComboBox()
        self.vendor_combo = QComboBox()
        self.openai_model = QLineEdit(config.translation.openai_model)
        self.anthropic_model = QLineEdit(config.translation.anthropic_model)
        self.openai_key = QLineEdit()
        self.openai_key.setEchoMode(QLineEdit.EchoMode.Password)
        self.anthropic_key = QLineEdit()
        self.anthropic_key.setEchoMode(QLineEdit.EchoMode.Password)
        self.openai_status = QLabel()
        self.anthropic_status = QLabel()
        self.save_audio = QCheckBox()
        self.save_audio.setChecked(bool(config.audio.save_audio))
        self.hint = QLabel()
        self.hint.setWordWrap(True)
        self.log_path = QLabel(str(log_dir() / "app.log"))
        self.log_path.setWordWrap(True)
        self.data_path = QLabel(str(database_path()))
        self.data_path.setWordWrap(True)
        self.log_label = QLabel()
        self.data_label = QLabel()
        form.addRow(self._row_label("stt"), self.stt_combo)
        form.addRow(self._row_label("model"), self.model_combo)
        form.addRow(self._row_label("translation"), self.translation_combo)
        form.addRow(self._row_label("vendor"), self.vendor_combo)
        self.openai_model_label = QLabel("OpenAI model")
        self.anthropic_model_label = QLabel("Anthropic model")
        form.addRow(self.openai_model_label, self.openai_model)
        form.addRow(self.anthropic_model_label, self.anthropic_model)
        form.addRow(self._row_label("openai"), self.openai_status)
        form.addRow(self.openai_key)
        form.addRow(self._row_label("anthropic"), self.anthropic_status)
        form.addRow(self.anthropic_key)
        form.addRow(self.save_audio)
        form.addRow(self.log_label, self.log_path)
        form.addRow(self.data_label, self.data_path)
        layout.addLayout(form)
        layout.addWidget(self.hint)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._save)
        buttons.rejected.connect(self.reject)
        self.buttons = buttons
        layout.addWidget(buttons)
        self.stt_combo.currentIndexChanged.connect(self._sync_model_enabled)
        self._retranslate()
        self._fill()
        self.resize(520, 460)

    def _row_label(self, name: str) -> QLabel:
        label = QLabel()
        setattr(self, f"{name}_caption", label)
        return label

    def _fill(self) -> None:
        i18n = self.i18n
        self._set_combo(
            self.stt_combo,
            [
                (i18n.t("provider_faster_whisper"), "faster-whisper"),
                (i18n.t("provider_openai"), "openai"),
                (i18n.t("provider_mock"), "mock"),
            ],
            self.config.stt.provider,
        )
        self._set_combo(
            self.model_combo,
            [(i18n.t("model_small"), "small"), (i18n.t("model_medium"), "medium")],
            self.config.stt.model_size,
        )
        self._set_combo(
            self.translation_combo,
            [
                (i18n.t("provider_llm"), "llm"),
                (i18n.t("provider_argos"), "argos"),
                (i18n.t("provider_mock"), "mock"),
            ],
            self.config.translation.provider,
        )
        self._set_combo(
            self.vendor_combo,
            [
                (i18n.t("vendor_openai"), "openai"),
                (i18n.t("vendor_anthropic"), "anthropic"),
            ],
            self.config.translation.llm_vendor,
        )
        status = api_key_status()
        self.openai_status.setText(i18n.t("key_set") if status["openai"] else i18n.t("key_missing"))
        self.anthropic_status.setText(
            i18n.t("key_set") if status["anthropic"] else i18n.t("key_missing")
        )
        self._sync_model_enabled()

    def _set_combo(self, combo: QComboBox, items: list[tuple[str, str]], current: str) -> None:
        combo.blockSignals(True)
        combo.clear()
        for label, value in items:
            combo.addItem(label, value)
        index = combo.findData(current)
        combo.setCurrentIndex(index if index >= 0 else 0)
        combo.blockSignals(False)

    def _sync_model_enabled(self) -> None:
        self.model_combo.setEnabled(self.stt_combo.currentData() == "faster-whisper")

    def _retranslate(self) -> None:
        i18n = self.i18n
        self.setWindowTitle(i18n.t("settings_title"))
        self.stt_caption.setText(i18n.t("stt_provider"))
        self.model_caption.setText(i18n.t("model_size"))
        self.translation_caption.setText(i18n.t("translation_provider"))
        self.vendor_caption.setText(i18n.t("llm_vendor"))
        self.openai_caption.setText(i18n.t("openai_key"))
        self.anthropic_caption.setText(i18n.t("anthropic_key"))
        self.openai_key.setPlaceholderText(i18n.t("key_placeholder"))
        self.anthropic_key.setPlaceholderText(i18n.t("key_placeholder"))
        self.save_audio.setText(i18n.t("save_audio"))
        self.log_label.setText(i18n.t("log_file"))
        self.data_label.setText(i18n.t("data_file"))
        self.hint.setText(i18n.t("apply_hint"))
        save_button = self.buttons.button(QDialogButtonBox.StandardButton.Save)
        cancel_button = self.buttons.button(QDialogButtonBox.StandardButton.Cancel)
        if save_button is not None:
            save_button.setText(i18n.t("save"))
        if cancel_button is not None:
            cancel_button.setText(i18n.t("cancel"))

    def _save(self) -> None:
        self.config.stt.provider = self.stt_combo.currentData()
        self.config.stt.model_size = self.model_combo.currentData()
        self.config.translation.provider = self.translation_combo.currentData()
        self.config.translation.llm_vendor = self.vendor_combo.currentData()
        self.config.translation.openai_model = self.openai_model.text().strip() or self.config.translation.openai_model
        self.config.translation.anthropic_model = (
            self.anthropic_model.text().strip() or self.config.translation.anthropic_model
        )
        self.config.audio.save_audio = self.save_audio.isChecked()
        if self.openai_key.text().strip():
            write_env_key(self.config.env_path, "OPENAI_API_KEY", self.openai_key.text())
        if self.anthropic_key.text().strip():
            write_env_key(self.config.env_path, "ANTHROPIC_API_KEY", self.anthropic_key.text())
        save_config(self.config)
        self.accept()
