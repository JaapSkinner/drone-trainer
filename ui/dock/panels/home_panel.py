from PyQt5.QtWidgets import QWidget, QLabel, QVBoxLayout, QPushButton
from PyQt5.QtGui import QPixmap, QFont, QCursor
from PyQt5.QtCore import Qt
import webbrowser
from ui.style import load_stylesheet

class HomePanel(QWidget):
    NavTag = "home"
    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignTop | Qt.AlignHCenter)

        # Brand logo (updated to use dtrg_full.png, full width and responsive)
        logo = QLabel()
        pixmap = QPixmap("ui/assets/dtrg_full.png")
        # Set a large default width, will be resized dynamically
        logo.setPixmap(pixmap.scaled(240, 80, Qt.KeepAspectRatio | Qt.SmoothTransformation))
        logo.setAlignment(Qt.AlignCenter)
        layout.addWidget(logo)
        logo.setMinimumHeight(80)
        logo.setMaximumHeight(160)
        logo.setStyleSheet("padding: 8px 0px;")
        layout.addSpacing(16)

        # Make logo responsive to panel resize
        def resize_logo():
            w = max(160, self.width() - 32)
            logo.setPixmap(pixmap.scaled(w, 120, Qt.KeepAspectRatio | Qt.SmoothTransformation))
        # Welcome text
        welcome = QLabel("<b>Welcome to Drone Trainer!</b>")
        welcome.setFont(QFont("Arial", 14))
        welcome.setAlignment(Qt.AlignCenter)
        layout.addWidget(welcome)

        layout.addSpacing(8)

        # Description
        desc = QLabel("""
        <div style='text-align:center;'>
        This is your mission control for drone training.<br><br>
        Use the navigation bar to explore features.<br>
        </div>
        """)
        desc.setWordWrap(True)
        desc.setAlignment(Qt.AlignCenter)
        layout.addWidget(desc)

        layout.addSpacing(12)

        # Load and apply custom stylesheet for this panel
        self.setStyleSheet(load_stylesheet("ui/dock/panels/home_panel.qss"))

        # GitHub link button
        github_btn = QPushButton("View on GitHub")
        github_btn.setObjectName("githubBtn")
        github_btn.setProperty("class", "home-panel-btn")
        github_btn.setCursor(QCursor(Qt.PointingHandCursor))
        github_btn.clicked.connect(lambda: webbrowser.open_new_tab("https://github.com/jski306/drone-trainer"))
        layout.addWidget(github_btn)

        # dtrg.org website button
        web_btn = QPushButton("Visit dtrg.org")
        web_btn.setObjectName("webBtn")
        web_btn.setProperty("class", "home-panel-btn")
        web_btn.setCursor(QCursor(Qt.PointingHandCursor))
        web_btn.clicked.connect(lambda: webbrowser.open_new_tab("https://dtrg.org"))
        layout.addWidget(web_btn)

        # Spacer
        layout.addStretch()
