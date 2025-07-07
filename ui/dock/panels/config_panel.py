from PyQt5.QtWidgets import QWidget, QLabel, QVBoxLayout

class ConfigPanel(QWidget):
    NavTag = "config"
    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Config Panel"))