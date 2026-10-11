"""Leaderboard panel: best results per training game."""
import datetime

from PyQt5.QtCore import Qt, pyqtSlot
from PyQt5.QtWidgets import (QAbstractItemView, QCheckBox, QComboBox, QHBoxLayout, QHeaderView, QLabel,
                             QMessageBox, QPushButton, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget)


class LeaderboardPanel(QWidget):
    NavTag = "leaderboard"
    COLUMNS = ("#", "Pilot", "Score", "When")

    def __init__(self, parent=None, trainer_service=None):
        super().__init__(parent)
        self.trainer = trainer_service

        layout = QVBoxLayout(self)
        title = QLabel("Leaderboard")
        title.setStyleSheet("font-size: 16px; font-weight: bold; margin-bottom: 6px;")
        layout.addWidget(title)

        row = QHBoxLayout()
        self.game_combo = QComboBox()
        for game_cls in (self.trainer.available_games() if self.trainer else []):
            self.game_combo.addItem(game_cls.title, game_cls.key)
        self.game_combo.currentIndexChanged.connect(self.refresh)
        row.addWidget(self.game_combo, 1)
        self.best_per_pilot_check = QCheckBox("Best per pilot")
        self.best_per_pilot_check.setChecked(True)
        self.best_per_pilot_check.toggled.connect(self.refresh)
        row.addWidget(self.best_per_pilot_check)
        layout.addLayout(row)

        self.table = QTableWidget(0, len(self.COLUMNS))
        self.table.setHorizontalHeaderLabels(self.COLUMNS)
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.Stretch)
        layout.addWidget(self.table, 1)

        self.empty_label = QLabel("No results yet — play a game in the Trainer panel.")
        self.empty_label.setStyleSheet("color: #666; font-style: italic;")
        layout.addWidget(self.empty_label)

        clear_row = QHBoxLayout()
        clear_row.addStretch()
        self.clear_button = QPushButton("Clear results…")
        self.clear_button.clicked.connect(self._on_clear_clicked)
        clear_row.addWidget(self.clear_button)
        layout.addLayout(clear_row)

        if self.trainer is not None:
            self.trainer.results_changed.connect(self.refresh)
        self.refresh()

    @pyqtSlot()
    def refresh(self):
        key = self.game_combo.currentData()
        results = (self.trainer.results.leaderboard(key, limit=50,
                                                    best_per_pilot=self.best_per_pilot_check.isChecked())
                   if (self.trainer and key) else [])
        self.table.setRowCount(len(results))
        for row, result in enumerate(results):
            when = datetime.datetime.fromtimestamp(result.timestamp).strftime("%Y-%m-%d %H:%M")
            for col, text in enumerate((str(row + 1), result.pilot, result.score_text(), when)):
                item = QTableWidgetItem(text)
                if col in (0, 2):
                    item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                self.table.setItem(row, col, item)
        self.empty_label.setVisible(not results)
        self.clear_button.setEnabled(bool(results))

    def _on_clear_clicked(self):
        title = self.game_combo.currentText()
        answer = QMessageBox.question(self, "Clear results", f"Delete all saved results for {title}?",
                                      QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if answer == QMessageBox.Yes:
            self.trainer.results.clear(self.game_combo.currentData())
            self.refresh()
