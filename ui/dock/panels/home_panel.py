from PyQt5.QtWidgets import QWidget, QLabel, QVBoxLayout

class HomePanel(QWidget):
    NavTag = "home"
    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Home Panel"))