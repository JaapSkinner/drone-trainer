from PyQt5.QtWidgets import QWidget, QLabel, QVBoxLayout

class SettingsPanel(QWidget):
    NavTag = "settings"
    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Settings Panel"))