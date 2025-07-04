from PyQt5.QtWidgets import QWidget, QVBoxLayout, QPushButton
from PyQt5.QtCore import pyqtSignal

class SideNavbar(QWidget):
    panel_selected = pyqtSignal(str)  # e.g. "objects", "radio", etc.

    def __init__(self, parent=None):
        super().__init__(parent)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self.buttons = { }

        for name in ["Objects", "Radio"]:
            key = name.lower()
            btn = QPushButton(name)
            layout.addWidget(btn)
            btn.clicked.connect(lambda _, k=key: self.panel_selected.emit(k))
            self.buttons[key] = btn

        layout.addStretch()
