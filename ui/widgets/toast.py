"""Short confirmations ("Scene saved") that fade in over the 3-D view and go away by themselves.

Anything on the GUI thread can call ``toast("…")``; MainWindow shows it. Services
must not call this directly; they emit a signal and a panel decides to toast.
"""
from PyQt5.QtCore import QEasingCurve, QObject, QPropertyAnimation, Qt, QTimer, pyqtSignal, pyqtSlot
from PyQt5.QtWidgets import QGraphicsOpacityEffect, QHBoxLayout, QLabel, QWidget

from ui import theme


class _Notifier(QObject):
    requested = pyqtSignal(str, str)   # text, state ('ok' | 'warn' | 'bad' | 'off')


notifier = _Notifier()


def toast(text: str, state: str = "ok"):
    """Show a brief message (GUI thread only)."""
    notifier.requested.emit(text, state)


class Toast(QWidget):
    """A pill at the bottom centre of its parent. One at a time; a new message replaces the old."""

    SHOW_MS = 2600
    MARGIN = 28

    def __init__(self, parent):
        super().__init__(parent)
        self.setObjectName("ToastFrame")
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setAttribute(Qt.WA_TransparentForMouseEvents)
        row = QHBoxLayout(self)
        row.setContentsMargins(14, 9, 18, 9)
        row.setSpacing(9)
        self.icon_label = QLabel()
        row.addWidget(self.icon_label)
        self.text_label = QLabel()
        self.text_label.setObjectName("ToastText")
        row.addWidget(self.text_label)
        self._effect = QGraphicsOpacityEffect(self)
        self._effect.setOpacity(0.0)
        self.setGraphicsEffect(self._effect)
        self._fade = QPropertyAnimation(self._effect, b"opacity", self)
        self._fade.setEasingCurve(QEasingCurve.OutCubic)
        self._fade.finished.connect(self._on_fade_finished)
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self.dismiss)
        self.hide()

    def text(self) -> str:
        return self.text_label.text()

    @pyqtSlot(str, str)
    def show_message(self, text: str, state: str = "ok"):
        self.text_label.setText(text)
        # The pill uses the tooltip colours (dark on a light theme), so take the icon colour from the
        # opposite palette to keep it readable.
        inverse = theme.DARK if theme.current_name() == "light" else theme.LIGHT
        token = {"ok": "success", "warn": "warning", "bad": "danger"}.get(state, "text_muted")
        icon_name = theme.ICON_FOR_STATE.get(state, "circle-dot")
        self.icon_label.setPixmap(theme.icon(icon_name, getattr(inverse, token), 16).pixmap(16, 16))
        self.adjustSize()
        self.reposition()
        self.show()
        self.raise_()
        self._animate_to(1.0, 180)
        self._timer.start(self.SHOW_MS)

    @pyqtSlot()
    def dismiss(self):
        self._timer.stop()
        if self.isVisible():
            self._animate_to(0.0, 260)

    def _animate_to(self, opacity, duration):
        self._fade.stop()
        self._fade.setDuration(duration)
        self._fade.setStartValue(self._effect.opacity())
        self._fade.setEndValue(opacity)
        self._fade.start()

    @pyqtSlot()
    def _on_fade_finished(self):
        if self._effect.opacity() <= 0.01:
            self.hide()

    def reposition(self):
        parent = self.parentWidget()
        if parent is not None:
            bottom = parent.height() - self.MARGIN
            hud = getattr(parent, "game_hud", None)   # keep clear of the game read-out in the viewport
            if hud is not None and hud.isVisible():
                bottom = min(bottom, hud.y() - 10)
            self.move((parent.width() - self.width()) // 2, bottom - self.height())
