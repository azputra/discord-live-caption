from __future__ import annotations

import logging
import sys

from PySide6.QtWidgets import QApplication, QMessageBox

from app.audio.capture import UnsupportedPlatform
from app.config import load_config
from app.ui.main_window import MainWindow
from app.ui.theme import apply_theme
from app.utils.logging_setup import setup_logging

logger = logging.getLogger(__name__)


def main() -> int:
    try:
        config = load_config()
    except Exception as exc:
        logging.basicConfig(level=logging.INFO)
        logger.exception("Could not load configuration")
        raise SystemExit(str(exc)) from exc
    setup_logging(config.logging.level)
    from app.utils.paths import database_path

    logger.info("Database: %s", database_path())
    app = QApplication.instance() or QApplication(sys.argv)
    app.setApplicationName("Discord Live Caption")
    apply_theme(app, config.ui.theme)
    try:
        window = MainWindow(config)
    except UnsupportedPlatform as exc:
        QMessageBox.critical(None, "Discord Live Caption", str(exc))
        return 1
    window.show()
    hints = app.styleHints()
    if hasattr(hints, "colorSchemeChanged"):
        hints.colorSchemeChanged.connect(lambda _scheme: window.apply_system_theme())
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
