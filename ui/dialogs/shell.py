"""The common dialog layout: a header (title and a line of explanation), a body, and a footer
with Cancel and one primary button, as in the Add-a-drone wizard.

    dialog = DialogShell("Add object", "A box, sphere, mesh or race gate.", accept_text="Add")
    dialog.body.addLayout(form)
    if dialog.exec_() == QDialog.Accepted: ...

``accept_button`` (primary, default) and ``cancel_button`` sit on the right, Cancel first as in the
wizard; put extra buttons in ``footer_left``.
"""
from PyQt5.QtCore import QEasingCurve, QPropertyAnimation
from PyQt5.QtWidgets import QDialog, QFrame, QHBoxLayout, QVBoxLayout

from ui import theme


class DialogShell(QDialog):
    def __init__(self, title: str, subtitle: str = "", accept_text: str = "OK", accept_icon: str = "check",
                 parent=None, window_title: str = None):
        super().__init__(parent)
        self.setWindowTitle(window_title or title)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        header = QFrame()
        header.setObjectName("DialogHeader")
        header_layout = QVBoxLayout(header)
        header_layout.setContentsMargins(24, 18, 24, 14)
        header_layout.setSpacing(2)
        self.title_label = theme.label(title, "subtitle")
        header_layout.addWidget(self.title_label)
        self.subtitle_label = theme.hint(subtitle)
        self.subtitle_label.setVisible(bool(subtitle))
        header_layout.addWidget(self.subtitle_label)
        layout.addWidget(header)

        self.body = QVBoxLayout()
        self.body.setContentsMargins(24, 18, 24, 18)
        self.body.setSpacing(10)
        layout.addLayout(self.body, 1)

        footer = QFrame()
        footer.setObjectName("DialogFooter")
        footer_layout = QHBoxLayout(footer)
        footer_layout.setContentsMargins(24, 12, 24, 14)
        self.footer_left = QHBoxLayout()
        footer_layout.addLayout(self.footer_left)
        footer_layout.addStretch()
        self.cancel_button = theme.button("Cancel", "ghost")
        self.cancel_button.setAutoDefault(False)
        self.cancel_button.clicked.connect(self.reject)
        footer_layout.addWidget(self.cancel_button)
        self.accept_button = theme.button(accept_text, "primary", accept_icon)
        self.accept_button.setDefault(True)
        self.accept_button.setMinimumWidth(90)
        self.accept_button.clicked.connect(self.accept)
        footer_layout.addWidget(self.accept_button)
        layout.addWidget(footer)

    def showEvent(self, event):
        super().showEvent(event)
        fade_in_window(self)


def fade_in_window(window, duration=150):
    """Fade a top-level window in (where the window system supports opacity)."""
    window.setWindowOpacity(0.0)
    animation = QPropertyAnimation(window, b"windowOpacity", window)
    animation.setDuration(duration)
    animation.setStartValue(0.0)
    animation.setEndValue(1.0)
    animation.setEasingCurve(QEasingCurve.OutCubic)
    animation.start(QPropertyAnimation.DeleteWhenStopped)
    return animation

