"""Trainer panel (issue #6): pick a training game, configure it and play."""
from PyQt5.QtCore import Qt, pyqtSignal, pyqtSlot
from PyQt5.QtWidgets import (QCheckBox, QComboBox, QDoubleSpinBox, QFormLayout, QGroupBox, QHBoxLayout,
                             QLabel, QLineEdit, QMessageBox, QPushButton, QScrollArea, QSpinBox,
                             QVBoxLayout, QWidget)

from services.trainer.games import GameState

FOLLOW_COMMAND_PANEL = "__command_panel__"


def _discard(widget):
    if widget is not None:
        widget.hide()
        widget.setParent(None)
        widget.deleteLater()


class TrainerPanel(QWidget):
    NavTag = "trainer"

    pilot_name_changed = pyqtSignal(str)
    preferences_changed = pyqtSignal(object)   # {"game": key, "settings": {key: {...}}}

    def __init__(self, parent=None, trainer_service=None, object_service=None):
        super().__init__(parent)
        self.trainer = trainer_service
        self.object_service = object_service
        self._game_settings = {}          # game key → settings dict (remembered per game)
        self._setting_widgets = {}

        outer = QVBoxLayout(self)
        title = QLabel("Trainer")
        title.setStyleSheet("font-size: 16px; font-weight: bold; margin-bottom: 6px;")
        outer.addWidget(title)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.NoFrame)
        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setAlignment(Qt.AlignTop)
        scroll.setWidget(content)
        outer.addWidget(scroll, 1)

        # -- pilot --------------------------------------------------------------
        pilot_group = QGroupBox("Pilot")
        pilot_form = QFormLayout(pilot_group)
        self.pilot_edit = QLineEdit()
        self.pilot_edit.setPlaceholderText("Your name (for the leaderboard)")
        self.pilot_edit.editingFinished.connect(lambda: self.pilot_name_changed.emit(self.pilot_name()))
        pilot_form.addRow("Name:", self.pilot_edit)
        self.object_combo = QComboBox()
        self.object_combo.setToolTip("The object whose position is scored")
        pilot_form.addRow("Flying:", self.object_combo)
        layout.addWidget(pilot_group)

        # -- game ----------------------------------------------------------------
        game_group = QGroupBox("Game")
        game_layout = QVBoxLayout(game_group)
        self.game_combo = QComboBox()
        for game_cls in (self.trainer.available_games() if self.trainer else []):
            self.game_combo.addItem(game_cls.title, game_cls.key)
        game_layout.addWidget(self.game_combo)
        self.description_label = QLabel()
        self.description_label.setWordWrap(True)
        self.description_label.setStyleSheet("color: #555;")
        game_layout.addWidget(self.description_label)
        self.settings_form_holder = QVBoxLayout()
        game_layout.addLayout(self.settings_form_holder)
        self.actions_row = QHBoxLayout()
        game_layout.addLayout(self.actions_row)
        self.action_message = QLabel()
        self.action_message.setWordWrap(True)
        self.action_message.setStyleSheet("color: #1e7e34;")
        game_layout.addWidget(self.action_message)
        layout.addWidget(game_group)

        # -- play ----------------------------------------------------------------
        self.start_button = QPushButton("Start")
        self.start_button.setStyleSheet(
            "QPushButton { background-color: #28a745; color: white; font-weight: bold; font-size: 15px;"
            " padding: 10px; border: none; border-radius: 6px; }"
            "QPushButton:hover { background-color: #218838; }")
        self.start_button.clicked.connect(self._on_start_stop_clicked)
        layout.addWidget(self.start_button)
        self.status_label = QLabel("Ready")
        self.status_label.setWordWrap(True)
        self.status_label.setStyleSheet("font-size: 15px; font-weight: 600; padding: 6px 0;")
        layout.addWidget(self.status_label)
        self.result_label = QLabel()
        self.result_label.setWordWrap(True)
        layout.addWidget(self.result_label)
        layout.addStretch()

        self.game_combo.currentIndexChanged.connect(self._on_game_changed)
        if self.trainer is not None:
            self.trainer.hud_changed.connect(self.on_hud_changed)
            self.trainer.state_changed.connect(self.on_state_changed)
            self.trainer.game_finished.connect(self.on_game_finished)
        if self.object_service is not None:
            self.object_service.objects_changed.connect(self.refresh_objects)
        self.refresh_objects()
        self._on_game_changed(self.game_combo.currentIndex())

    # ------------------------------------------------------------------
    # Pilot
    # ------------------------------------------------------------------

    def pilot_name(self) -> str:
        return self.pilot_edit.text().strip()

    def set_pilot_name(self, name: str):
        self.pilot_edit.setText(name)

    @pyqtSlot()
    def refresh_objects(self):
        current = self.object_combo.currentData()
        self.object_combo.blockSignals(True)
        self.object_combo.clear()
        self.object_combo.addItem("Command panel's object", FOLLOW_COMMAND_PANEL)
        if self.object_service is not None:
            for obj in self.object_service.get_objects():
                if not obj.helper and obj.gate_order is None:
                    self.object_combo.addItem(obj.name, obj)
        index = next((i for i in range(self.object_combo.count()) if self.object_combo.itemData(i) is current), 0)
        self.object_combo.setCurrentIndex(index)
        self.object_combo.blockSignals(False)

    def pilot_object(self):
        data = self.object_combo.currentData()
        if data == FOLLOW_COMMAND_PANEL or data is None:
            return self.object_service.get_controlled_object() if self.object_service else None
        return data

    # ------------------------------------------------------------------
    # Game selection and settings
    # ------------------------------------------------------------------

    def current_game_class(self):
        key = self.game_combo.currentData()
        return self.trainer.game_class(key) if (self.trainer and key) else None

    def load_preferences(self, prefs: dict):
        """Restore the last game and per-game settings (from AppSettings.trainer)."""
        prefs = prefs or {}
        self._game_settings = {k: dict(v) for k, v in (prefs.get("settings") or {}).items()}
        index = self.game_combo.findData(prefs.get("game"))
        if index >= 0:
            self.game_combo.setCurrentIndex(index)
        self._on_game_changed(self.game_combo.currentIndex())

    def preferences(self) -> dict:
        return {"game": self.game_combo.currentData(), "settings": self._game_settings}

    def _on_game_changed(self, _index):
        game_cls = self.current_game_class()
        self.description_label.setText(game_cls.description if game_cls else "")
        self._build_settings_form(game_cls)
        self._build_actions(game_cls)
        self.action_message.setText("")
        self.preferences_changed.emit(self.preferences())

    def _build_settings_form(self, game_cls):
        while self.settings_form_holder.count():
            _discard(self.settings_form_holder.takeAt(0).widget())
        self._setting_widgets = {}
        if game_cls is None:
            return
        values = self.current_settings()
        holder = QWidget()
        form = QFormLayout(holder)
        form.setContentsMargins(0, 4, 0, 4)
        for setting in game_cls.SETTINGS:
            value = values.get(setting.key, setting.default)
            if setting.kind == "bool":
                widget = QCheckBox()
                widget.setChecked(bool(value))
                widget.toggled.connect(self._on_setting_edited)
            elif setting.kind == "int":
                widget = QSpinBox()
                widget.setRange(int(setting.minimum), int(setting.maximum))
                widget.setSingleStep(int(setting.step) or 1)
                widget.setValue(int(value))
                widget.valueChanged.connect(self._on_setting_edited)
            else:
                widget = QDoubleSpinBox()
                widget.setRange(setting.minimum, setting.maximum)
                widget.setDecimals(setting.decimals)
                widget.setSingleStep(setting.step)
                widget.setValue(float(value))
                widget.valueChanged.connect(self._on_setting_edited)
            if setting.suffix and hasattr(widget, "setSuffix"):
                widget.setSuffix(setting.suffix)
            if setting.tooltip:
                widget.setToolTip(setting.tooltip)
            self._setting_widgets[setting.key] = widget
            form.addRow(setting.label + ":", widget)
        self.settings_form_holder.addWidget(holder)

    def current_settings(self) -> dict:
        game_cls = self.current_game_class()
        if game_cls is None:
            return {}
        values = {s.key: s.default for s in game_cls.SETTINGS}
        values.update(self._game_settings.get(game_cls.key, {}))
        return values

    def _on_setting_edited(self, _value=None):
        game_cls = self.current_game_class()
        values = {}
        for key, widget in self._setting_widgets.items():
            values[key] = widget.isChecked() if isinstance(widget, QCheckBox) else widget.value()
        self._game_settings[game_cls.key] = values
        self.preferences_changed.emit(self.preferences())

    def _build_actions(self, game_cls):
        while self.actions_row.count():
            _discard(self.actions_row.takeAt(0).widget())
        self._actions = game_cls(self.current_settings()).actions() if game_cls else []
        for action in self._actions:
            button = QPushButton(action.label)
            button.setToolTip(action.tooltip)
            button.clicked.connect(lambda _c=False, a=action: self.run_action(a, ask=True))
            self.actions_row.addWidget(button)
        self.actions_row.addStretch()

    def run_action(self, action, ask=False):
        if ask and action.confirm:
            answer = QMessageBox.question(self, action.label, action.confirm,
                                          QMessageBox.Yes | QMessageBox.No, QMessageBox.Yes)
            if answer != QMessageBox.Yes:
                return None
        game = self.current_game_class()(self.current_settings())
        message = action.run(game, self.object_service, self.pilot_object())
        # Actions may change settings (e.g. "target = pilot position").
        self._game_settings[game.key] = dict(game.settings)
        self._build_settings_form(self.current_game_class())
        self.action_message.setText(message or "")
        self.preferences_changed.emit(self.preferences())
        return message

    # ------------------------------------------------------------------
    # Playing
    # ------------------------------------------------------------------

    def start_game(self):
        game_cls = self.current_game_class()
        if game_cls is None or self.trainer is None:
            return "No game selected."
        game = game_cls(self.current_settings())
        error = self.trainer.start(game, self.pilot_object(), self.pilot_name())
        if error:
            self.status_label.setText(error)
            self.status_label.setStyleSheet("font-size: 14px; font-weight: 600; color: #c82333;")
        return error

    def _on_start_stop_clicked(self):
        if self.trainer is not None and self.trainer.running:
            self.trainer.stop()
        else:
            self.start_game()

    @pyqtSlot(str)
    def on_hud_changed(self, text):
        if text:
            self.status_label.setText(text)
            self.status_label.setStyleSheet("font-size: 15px; font-weight: 600; padding: 6px 0;")

    @pyqtSlot(object)
    def on_state_changed(self, state):
        running = state.active
        self.start_button.setText("Stop" if running else "Start")
        self.start_button.setStyleSheet(
            "QPushButton { background-color: %s; color: white; font-weight: bold; font-size: 15px;"
            " padding: 10px; border: none; border-radius: 6px; }" % ("#dc3545" if running else "#28a745"))
        for widget in (self.game_combo, self.object_combo, *self._setting_widgets.values()):
            widget.setEnabled(not running)
        if state == GameState.STOPPED:
            self.status_label.setText("Stopped")

    @pyqtSlot(object)
    def on_game_finished(self, result):
        if not result.success:
            self.result_label.setText("No result recorded.")
            return
        best = self.trainer.results.personal_best(result.game, result.pilot)
        text = f"<b>{result.pilot}</b>: {result.score_text()}"
        if best is not None and best.timestamp == result.timestamp:
            text += " — personal best!"
        elif best is not None:
            text += f" (personal best {best.score_text()})"
        self.result_label.setText(text)
