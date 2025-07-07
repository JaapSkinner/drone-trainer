from PyQt5.QtWidgets import QWidget, QLabel, QVBoxLayout

class LeaderboardPanel(QWidget):
    NavTag = "leaderboard"
    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Leaderboard Panel"))