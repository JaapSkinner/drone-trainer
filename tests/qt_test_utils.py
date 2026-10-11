"""Shared helpers for tests that need a Qt application.

Import this module before anything that creates a QApplication or initialises
SDL so the headless defaults below take effect.
"""
import os
import time

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

from PyQt5.QtCore import QtMsgType, qInstallMessageHandler
from PyQt5.QtWidgets import QApplication


def get_app() -> QApplication:
    return QApplication.instance() or QApplication([])


def wait_until(predicate, timeout_s: float = 3.0, interval_s: float = 0.01) -> bool:
    """Process Qt events until ``predicate()`` is true or the timeout expires."""
    app = get_app()
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        app.processEvents()
        if predicate():
            return True
        time.sleep(interval_s)
    app.processEvents()
    return bool(predicate())


def process_events_for(duration_s: float) -> None:
    wait_until(lambda: False, timeout_s=duration_s)


class QtMessageCapture:
    """Context manager that records Qt warnings/errors (qDebug output)."""

    def __init__(self):
        self.messages = []
        self._previous = None

    def __enter__(self):
        def handler(msg_type, _context, message):
            if msg_type != QtMsgType.QtDebugMsg:
                self.messages.append(message)

        self._handler = handler
        self._previous = qInstallMessageHandler(handler)
        return self

    def __exit__(self, *exc):
        qInstallMessageHandler(self._previous)
        return False

    def matching(self, *needles):
        return [m for m in self.messages if any(n in m for n in needles)]


# Qt messages that indicate a cross-thread misuse of a QObject.
THREAD_VIOLATION_MARKERS = (
    "Timers cannot",
    "different thread",
    "Cannot create children for a parent",
    "QThread: Destroyed while thread is still running",
)
