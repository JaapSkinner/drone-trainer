"""Leaderboard panel: best results per training game."""
import datetime

from PyQt5.QtCore import Qt, pyqtSlot
from PyQt5.QtWidgets import (QAbstractItemView, QCheckBox, QComboBox, QHBoxLayout, QHeaderView, QLabel,
                             QMessageBox, QPushButton, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget)

from ui import theme
from ui.widgets.empty_state import EmptyState

MEDALS = ("#D4A017", "#9CA3AF", "#B87333")   # gold, silver, bronze trophies for the top three


class LeaderboardPanel(QWidget):
    NavTag = "leaderboard"
    COLUMNS = ("#", "Pilot", "Score", "When")

    def __init__(self, parent=None, trainer_service=None):
        super().__init__(parent)
        self.trainer = trainer_service

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)
        layout.addWidget(theme.page_header("Leaderboard", "Best results for each game."))

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
        self.table.verticalHeader().setDefaultSectionSize(36)
        self.table.setShowGrid(False)
        self.table.setAlternatingRowColors(True)
        self.table.setFocusPolicy(Qt.NoFocus)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.Stretch)
        layout.addWidget(self.table, 1)

        self.empty_label = EmptyState("trophy", "No results yet", "Play a game in the Trainer panel and the best "
                                                                  "times show up here.")
        layout.addWidget(self.empty_label, 1)

        clear_row = QHBoxLayout()
        clear_row.addStretch()
        self.clear_button = theme.button("Clear results…", "ghost", "trash")
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
                if col == 0 and row < len(MEDALS):
                    item.setIcon(theme.icon("trophy", MEDALS[row], 16))
                if col == 2:
                    item.setFont(theme.mono_font(10))
                self.table.setItem(row, col, item)
        self.empty_label.setVisible(not results)
        self.table.setVisible(bool(results))
        self.clear_button.setEnabled(bool(results))

    def _on_clear_clicked(self):
        title = self.game_combo.currentText()
        answer = QMessageBox.question(self, "Clear results", f"Delete all saved results for {title}?",
                                      QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if answer == QMessageBox.Yes:
            self.trainer.results.clear(self.game_combo.currentData())
            self.refresh()
