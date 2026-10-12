from __future__ import annotations

import logging
import sys

from PySide6.QtCore import QPoint, Qt, QTimer
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizeGrip,
    QSlider,
    QVBoxLayout,
    QWidget,
)

logger = logging.getLogger(__name__)


def apply_windows_topmost(widget) -> None:
    if sys.platform != "win32":
        return
    try:
        import ctypes

        hwnd = int(widget.winId())
        hwnd_topmost = -1
        flags = 0x0002 | 0x0001 | 0x0010
        ctypes.windll.user32.SetWindowPos(hwnd, hwnd_topmost, 0, 0, 0, 0, flags)
    except Exception:
        logger.debug("Could not reapply the Windows topmost flag", exc_info=True)


def apply_macos_overlay_level(widget) -> None:
    """Raise the overlay above normal windows and many fullscreen spaces.

    The Cocoa call needs a real NSView. Offscreen and other Qt platform
    plugins do not provide one, and a bad pointer cannot be caught in Python.
    """
    if sys.platform != "darwin":
        return
    from PySide6.QtWidgets import QApplication

    application = QApplication.instance()
    if application is None or application.platformName() != "cocoa":
        return
    try:
        import objc
        from AppKit import NSScreenSaverWindowLevel

        handle = widget.windowHandle()
        if handle is None:
            return
        pointer = int(handle.winId())
        if pointer <= 0:
            return
        view = objc.objc_object(c_void_p=pointer)
        window = view.window()
        if window is None:
            return
        window.setLevel_(int(NSScreenSaverWindowLevel))
        window.setCollectionBehavior_(1 | 64 | 256)
        window.setHidesOnDeactivate_(False)
    except Exception:
        logger.debug("Could not raise the macOS overlay level", exc_info=True)


class DragBar(QWidget):
    def __init__(self, window: QWidget) -> None:
        super().__init__(window)
        self._window = window
        self._offset: QPoint | None = None
        self.setCursor(Qt.CursorShape.OpenHandCursor)

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._offset = event.globalPosition().toPoint() - self._window.frameGeometry().topLeft()
            self.setCursor(Qt.CursorShape.ClosedHandCursor)

    def mouseMoveEvent(self, event) -> None:
        if self._offset is not None and event.buttons() & Qt.MouseButton.LeftButton:
            self._window.move(event.globalPosition().toPoint() - self._offset)

    def mouseReleaseEvent(self, event) -> None:
        del event
        self._offset = None
        self.setCursor(Qt.CursorShape.OpenHandCursor)


class OverlayWindow(QWidget):
    def __init__(self, on_change, on_close, opacity: float, font_size: int, placeholder: str) -> None:
        super().__init__(None)
        self._on_change = on_change
        self._on_close = on_close
        self._placeholder = placeholder
        self._shown = False
        self._font = QFont()
        self._font.setPointSize(font_size)
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint
        )
        self.setWindowOpacity(opacity)
        self.setMinimumSize(320, 160)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, False)
        self.setStyleSheet(
            """
            OverlayWindow { background: #161411; color: #f4efe6; border-radius: 12px; }
            QLabel { color: #f4efe6; background: transparent; }
            QLabel#dragLabel { color: #d7c4a3; }
            QPushButton { color: #f4efe6; background: #2a261f; border: none; border-radius: 6px; padding: 4px 8px; }
            """
        )
        root = QVBoxLayout(self)
        root.setContentsMargins(10, 8, 10, 8)
        bar = QHBoxLayout()
        self.drag = DragBar(self)
        drag_row = QHBoxLayout(self.drag)
        self.drag_label = QLabel()
        self.drag_label.setObjectName("dragLabel")
        drag_row.addWidget(self.drag_label)
        drag_row.setContentsMargins(4, 0, 4, 0)
        bar.addWidget(self.drag, 1)
        self.opacity_label = QLabel()
        self.font_label = QLabel()
        self.opacity_slider = QSlider(Qt.Orientation.Horizontal)
        self.opacity_slider.setRange(45, 100)
        self.opacity_slider.setValue(int(round(opacity * 100)))
        self.opacity_slider.setFixedWidth(90)
        self.font_slider = QSlider(Qt.Orientation.Horizontal)
        self.font_slider.setRange(12, 36)
        self.font_slider.setValue(font_size)
        self.font_slider.setFixedWidth(90)
        self.close_btn = QPushButton("×")
        self.close_btn.setFixedWidth(28)
        bar.addWidget(self.opacity_label)
        bar.addWidget(self.opacity_slider)
        bar.addWidget(self.font_label)
        bar.addWidget(self.font_slider)
        bar.addWidget(self.close_btn)
        root.addLayout(bar)
        self._lines_host = QWidget()
        self._lines_layout = QVBoxLayout(self._lines_host)
        self._lines_layout.setContentsMargins(4, 0, 4, 0)
        self._lines_layout.addStretch(1)
        root.addWidget(self._lines_host, 1)
        grip_row = QHBoxLayout()
        grip_row.addStretch(1)
        grip_row.addWidget(QSizeGrip(self))
        root.addLayout(grip_row)

        self.opacity_slider.valueChanged.connect(self._emit_change)
        self.font_slider.valueChanged.connect(self._emit_font)
        self.close_btn.clicked.connect(self._close)
        self._pin_timer = QTimer(self)
        self._pin_timer.setInterval(3000)
        self._pin_timer.timeout.connect(self._pin_native)
        self.set_lines([])

    def set_chrome(self, drag: str, opacity: str, font: str) -> None:
        self.drag_label.setText(drag)
        self.opacity_label.setText(opacity)
        self.font_label.setText(font)

    def set_placeholder(self, text: str) -> None:
        self._placeholder = text

    def set_lines(self, blocks: list[str]) -> None:
        while self._lines_layout.count():
            item = self._lines_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        shown = blocks or [self._placeholder]
        for block in shown:
            label = QLabel(block)
            label.setObjectName("overlayLine")
            label.setWordWrap(True)
            label.setFont(self._font)
            label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            self._lines_layout.addWidget(label)
        self._lines_layout.addStretch(1)

    def _emit_font(self, value: int) -> None:
        self._font.setPointSize(value)
        for label in self.findChildren(QLabel):
            if label.objectName() == "overlayLine":
                label.setFont(self._font)
        self._emit_change()

    def _emit_change(self, *_args) -> None:
        opacity = self.opacity_slider.value() / 100
        self.setWindowOpacity(opacity)
        self._on_change(opacity, self.font_slider.value())

    def _close(self) -> None:
        self.hide()
        self._on_close()

    def showEvent(self, event) -> None:
        super().showEvent(event)
        if not self._shown:
            self.resize(520, 280)
            self.move(120, 80)
            self._shown = True
        self._pin_native()
        self._pin_timer.start()

    def hideEvent(self, event) -> None:
        self._pin_timer.stop()
        super().hideEvent(event)

    def _pin_native(self) -> None:
        apply_windows_topmost(self)
        apply_macos_overlay_level(self)
