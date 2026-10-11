"""Runs the active training game (issue #6) and records its results.

Lives on the GUI thread (like ObjectService and ControlService) and doubles as
a viewport overlay: the active game can highlight objects and draw guides.
"""
import logging
import time
from typing import Optional

from PyQt5.QtCore import QObject, QTimer, pyqtSignal

from services.trainer.games import GAMES, GAMES_BY_KEY, GameState, TrainingGame
from services.trainer.results import ResultsStore

logger = logging.getLogger(__name__)


class TrainerService(QObject):
    state_changed = pyqtSignal(object)    # GameState
    hud_changed = pyqtSignal(str)         # one-line status for the viewport ("" = hide)
    game_finished = pyqtSignal(object)    # GameResult (success or failure)
    results_changed = pyqtSignal()

    TICK_MS = 33
    RESULT_HUD_SECONDS = 8.0

    def __init__(self, object_service, results: Optional[ResultsStore] = None, parent=None):
        super().__init__(parent)
        self.object_service = object_service
        self.results = results or ResultsStore()
        self.game: Optional[TrainingGame] = None
        self._last_state = None
        self._last_hud = None
        self._result_shown_at = None
        if object_service is not None:
            object_service.object_removed.connect(self._on_object_removed)
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._on_timer)
        self._timer.start(self.TICK_MS)

    @staticmethod
    def available_games():
        return list(GAMES)

    @staticmethod
    def game_class(key):
        return GAMES_BY_KEY[key]

    @property
    def running(self) -> bool:
        return self.game is not None and self.game.state.active

    def start(self, game: TrainingGame, pilot, pilot_name: str, now: Optional[float] = None) -> Optional[str]:
        """Start ``game`` flown by ``pilot``. Returns an error message instead if it can't."""
        if self.running:
            self.stop()
        error = game.validate(self.object_service, pilot)
        if error:
            return error
        self.game = game
        self._result_shown_at = None
        game.start(self.object_service, pilot, pilot_name.strip() or "Anonymous",
                   time.monotonic() if now is None else now)
        logger.info("Started %s (pilot %s, object %s)", game.title, game.pilot_name, pilot.name)
        self._publish(time.monotonic() if now is None else now)
        return None

    def stop(self):
        if self.game is not None and self.game.state.active:
            self.game.stop()
            logger.info("Stopped %s", self.game.title)
            self._publish(time.monotonic())

    def tick(self, now: float):
        game = self.game
        if game is None:
            return
        was_active = game.state.active
        game.tick(now)
        if was_active and game.state in (GameState.FINISHED, GameState.FAILED) and game.result is not None:
            self._result_shown_at = now
            if game.result.success:
                self.results.add(game.result)
                self.results_changed.emit()
            logger.info("%s: %s (%s)", game.title, game.result.score_text(),
                        "success" if game.result.success else "failed")
            self.game_finished.emit(game.result)
        self._publish(now)

    def _on_timer(self):
        self.tick(time.monotonic())

    def _publish(self, now):
        game = self.game
        if game is None:
            return
        if game.state != self._last_state:
            self._last_state = game.state
            self.state_changed.emit(game.state)
        text = game.hud_text()
        if self._result_shown_at is not None and now - self._result_shown_at > self.RESULT_HUD_SECONDS:
            text = ""
        if game.state == GameState.STOPPED:
            text = ""
        if text != self._last_hud:
            self._last_hud = text
            self.hud_changed.emit(text)

    def _on_object_removed(self, obj):
        game = self.game
        if game is not None and game.state.active and (obj is game.pilot or obj in getattr(game, "gates", [])):
            self.stop()

    # -- viewport overlay -------------------------------------------------------

    def drawables(self):
        return self.game.drawables() if self.game is not None else []

    def colour_for(self, obj):
        return self.game.colour_for(obj) if self.game is not None else None
