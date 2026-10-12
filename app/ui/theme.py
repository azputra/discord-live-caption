from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPalette


def _is_dark(app, mode: str) -> bool:
    if mode == "dark":
        return True
    if mode == "light":
        return False
    scheme = app.styleHints().colorScheme()
    return scheme == Qt.ColorScheme.Dark


def _palette(dark: bool) -> QPalette:
    palette = QPalette()
    if dark:
        bg = QColor("#141311")
        panel = QColor("#221f1b")
        text = QColor("#f4efe6")
        muted = QColor("#b3aa9e")
        accent = QColor("#2f8f86")
    else:
        bg = QColor("#f6f3ec")
        panel = QColor("#fffdf8")
        text = QColor("#1e1a16")
        muted = QColor("#6f675e")
        accent = QColor("#0f6e68")
    palette.setColor(QPalette.ColorRole.Window, bg)
    palette.setColor(QPalette.ColorRole.WindowText, text)
    palette.setColor(QPalette.ColorRole.Base, panel)
    palette.setColor(QPalette.ColorRole.AlternateBase, bg)
    palette.setColor(QPalette.ColorRole.Text, text)
    palette.setColor(QPalette.ColorRole.Button, panel)
    palette.setColor(QPalette.ColorRole.ButtonText, text)
    palette.setColor(QPalette.ColorRole.Highlight, accent)
    palette.setColor(QPalette.ColorRole.HighlightedText, QColor("#ffffff"))
    palette.setColor(QPalette.ColorRole.PlaceholderText, muted)
    palette.setColor(QPalette.ColorRole.ToolTipBase, panel)
    palette.setColor(QPalette.ColorRole.ToolTipText, text)
    return palette


def _stylesheet(dark: bool) -> str:
    if dark:
        bg, panel, text, muted = "#141311", "#221f1b", "#f4efe6", "#b3aa9e"
        line, accent, warn_bg, warn_border = "#3a342c", "#8fd0c8", "#3a2e1c", "#8a6a32"
        start, stop = "#1f7a72", "#8c3d36"
    else:
        bg, panel, text, muted = "#f6f3ec", "#fffdf8", "#1e1a16", "#6f675e"
        line, accent, warn_bg, warn_border = "#e4ddd2", "#0f6e68", "#fff6e8", "#e2c48a"
        start, stop = "#0f6e68", "#8c3d36"
    return f"""
    QWidget {{ color: {text}; font-size: 13px; }}
    QMainWindow, QDialog {{ background: {bg}; }}
    QFrame#captionCard, QFrame#captionPartial {{
        background: {panel};
        border: 1px solid {line};
        border-radius: 10px;
    }}
    QFrame#captionPartial {{ border-style: dashed; }}
    QLabel#captionMeta {{ color: {muted}; font-size: 12px; }}
    QLabel#captionOriginal {{ font-size: 15px; }}
    QLabel#captionTranslation {{ color: {accent}; font-size: 14px; }}
    QLabel#hintBanner {{
        background: {warn_bg};
        border: 1px solid {warn_border};
        border-radius: 8px;
        padding: 8px;
    }}
    QLabel#placeholder {{ color: {muted}; }}
    QPushButton {{
        background: {panel};
        border: 1px solid {line};
        border-radius: 6px;
        padding: 6px 10px;
    }}
    QPushButton:disabled {{ color: {muted}; }}
    QPushButton#startButton {{ background: {start}; color: white; border: none; }}
    QPushButton#stopButton {{ background: {stop}; color: white; border: none; }}
    QComboBox, QLineEdit, QTextEdit, QListWidget {{
        background: {panel};
        border: 1px solid {line};
        border-radius: 6px;
        padding: 4px;
    }}
    QProgressBar {{
        background: {line};
        border: none;
        border-radius: 4px;
        max-height: 8px;
    }}
    QProgressBar::chunk {{ background: {accent}; border-radius: 4px; }}
    """


def apply_theme(app, mode: str) -> bool:
    dark = _is_dark(app, mode)
    app.setStyle("Fusion")
    app.setPalette(_palette(dark))
    app.setStyleSheet(_stylesheet(dark))
    return dark
