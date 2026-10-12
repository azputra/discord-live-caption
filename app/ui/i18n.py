from __future__ import annotations

import json
from pathlib import Path

from PySide6.QtCore import QObject, Signal


def _load(language: str) -> dict[str, str]:
    path = Path(__file__).resolve().parent / "locales" / f"{language}.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    return {str(key): str(value) for key, value in payload.items()}


class I18n(QObject):
    language_changed = Signal(str)

    def __init__(self, language: str = "en") -> None:
        super().__init__()
        self._catalogs = {"en": _load("en"), "id": _load("id")}
        self.language = language if language in self._catalogs else "en"

    def t(self, key: str) -> str:
        catalog = self._catalogs.get(self.language, {})
        if key in catalog:
            return catalog[key]
        return self._catalogs["en"].get(key, key)

    def set_language(self, language: str) -> None:
        if language not in self._catalogs or language == self.language:
            return
        self.language = language
        self.language_changed.emit(language)

    def labels(self) -> dict[str, str]:
        return {"me": self.t("me"), "others": self.t("others")}
