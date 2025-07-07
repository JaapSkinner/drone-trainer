from PyQt5.QtWidgets import QWidget, QLabel, QVBoxLayout

class TrainerPanel(QWidget):
    NavTag = "trainer"
    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Trainer Panel"))