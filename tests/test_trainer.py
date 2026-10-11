import math
import os
import tempfile
import unittest

from qt_test_utils import get_app

from models import frames
from models.gate_frame import GateFrame, gate_crossed
from models.rect_prism import RectPrism
from models.sphere import Sphere
from services.object_service import ObjectService
from services.trainer.games import GameResult, GameState, GateRace, HoverChallenge, create_sample_course
from services.trainer.results import ResultsStore
from services.trainer_service import TrainerService
from ui.dock.panels.leaderboard_panel import LeaderboardPanel
from ui.dock.panels.trainer_panel import TrainerPanel


def _at(obj, x, y, z):
    obj.set_pose((x, y, z, *frames.IDENTITY_QUAT))


class GateGeometryTests(unittest.TestCase):
    def test_frame_is_flown_through_its_opening(self):
        gate = GateFrame(width=1.0, height=1.0)
        self.assertTrue(gate_crossed(gate, (0, 0, -1), (0, 0, 1)))
        self.assertTrue(gate_crossed(gate, (0.4, -0.4, 1), (0.4, -0.4, -1)))   # either direction
        self.assertFalse(gate_crossed(gate, (0.6, 0, -1), (0.6, 0, 1)))      # outside the opening
        self.assertFalse(gate_crossed(gate, (0, 0, -1), (0, 0, -0.5)))       # didn't reach it
        self.assertFalse(gate_crossed(gate, (-1, 0, 0.2), (1, 0, 0.2)))      # alongside

    def test_rotated_gate(self):
        gate = GateFrame(width=1.0, height=1.0)
        gate.set_pose((2, 1, 0, *frames.quat_from_axis_angle((0, 1, 0), math.pi / 2)))  # opening faces ±X
        self.assertTrue(gate_crossed(gate, (1.5, 1, 0), (2.5, 1, 0)))
        self.assertFalse(gate_crossed(gate, (2, 1, -1), (2, 1, 1)))

    def test_other_objects_are_checkpoints(self):
        ball = Sphere(radius=0.3)
        _at(ball, 1, 1, 1)
        self.assertTrue(gate_crossed(ball, (0, 0, 0), (1.1, 1.0, 1.0)))
        self.assertFalse(gate_crossed(ball, (0, 0, 0), (2, 2, 2)))

    def test_box_is_a_portal_with_its_xy_size(self):
        box = RectPrism(dimensions=(2.0, 1.0, 0.05))
        self.assertTrue(gate_crossed(box, (0.9, 0, -1), (0.9, 0, 1)))
        self.assertFalse(gate_crossed(box, (1.1, 0, -1), (1.1, 0, 1)))


class GateRaceTests(unittest.TestCase):
    def setUp(self):
        self.objects = ObjectService()
        self.gates = create_sample_course(self.objects, count=4, radius=2.0, height=1.2)
        self.pilot = self.objects.add_object(Sphere(name="Pilot", radius=0.05, controllable=True))
        self.place_on_circle(-0.3)

    def place_on_circle(self, angle):
        _at(self.pilot, 2.0 * math.cos(angle), 1.2, 2.0 * math.sin(angle))

    def fly(self, game, start_angle, end_angle, t0, steps=400, duration=10.0):
        for i in range(1, steps + 1):
            f = i / steps
            self.place_on_circle(start_angle + f * (end_angle - start_angle))
            game.tick(t0 + f * duration)

    def test_sample_course_is_ordered_on_a_circle(self):
        self.assertEqual([g.gate_order for g in self.gates], [1, 2, 3, 4])
        for gate in self.gates:
            self.assertAlmostEqual(math.hypot(gate.pose[0], gate.pose[2]), 2.0)
        # Regenerating replaces the generated gates rather than adding more.
        create_sample_course(self.objects)
        self.assertEqual(len([o for o in self.objects.get_objects() if o.gate_order is not None]), 4)

    def test_one_lap_round_the_circle_finishes_with_splits(self):
        game = GateRace({"laps": 1, "countdown_s": 0})
        self.assertIsNone(game.validate(self.objects, self.pilot))
        game.start(self.objects, self.pilot, "Jaap", now=100.0)
        self.assertEqual(game.state, GameState.RUNNING)
        self.fly(game, -0.3, 2 * math.pi - 0.3, t0=100.0, duration=8.0)
        self.assertEqual(game.state, GameState.FINISHED)
        self.assertTrue(game.result.success)
        self.assertEqual([name for _lap, name, _t in game.result.details["splits"]],
                         ["Gate 1", "Gate 2", "Gate 3", "Gate 4"])
        # Gate 4 is at 270°: 3/4 of the way plus the 0.3 rad run-up, over 8 s.
        expected = 8.0 * (0.3 + 1.5 * math.pi) / (2 * math.pi)
        self.assertAlmostEqual(game.result.score, expected, delta=0.05)

    def test_gates_must_be_flown_in_order(self):
        game = GateRace({"laps": 1, "countdown_s": 0})
        self.place_on_circle(math.pi / 2 - 0.3)       # start just before gate 2
        game.start(self.objects, self.pilot, "Jaap", now=0.0)
        self.fly(game, math.pi / 2 - 0.3, math.pi / 2 + 0.3, t0=0.0)
        self.assertEqual(game.next_gate().name, "Gate 1")
        self.assertEqual(game.state, GameState.RUNNING)

    def test_gate_passed_during_countdown_does_not_count(self):
        game = GateRace({"laps": 1, "countdown_s": 3})
        game.start(self.objects, self.pilot, "Jaap", now=0.0)
        self.fly(game, -0.3, 0.3, t0=0.0, steps=50, duration=2.0)   # through gate 1 during countdown
        self.assertEqual(game.state, GameState.COUNTDOWN)
        game.tick(3.5)
        self.assertEqual(game.state, GameState.RUNNING)
        self.assertEqual(game.next_gate().name, "Gate 1")

    def test_two_laps(self):
        game = GateRace({"laps": 2, "countdown_s": 0})
        game.start(self.objects, self.pilot, "Jaap", now=0.0)
        self.fly(game, -0.3, 2 * math.pi - 0.3, t0=0.0)
        self.assertEqual((game.state, game.lap), (GameState.RUNNING, 1))
        self.fly(game, 2 * math.pi - 0.3, 4 * math.pi - 0.3, t0=10.0)
        self.assertEqual(game.state, GameState.FINISHED)
        self.assertEqual(len(game.result.details["splits"]), 8)

    def test_next_gate_is_highlighted(self):
        game = GateRace({"laps": 1, "countdown_s": 0})
        game.start(self.objects, self.pilot, "Jaap", now=0.0)
        self.assertIsNotNone(game.colour_for(self.gates[0]))
        self.assertIsNone(game.colour_for(self.gates[2]))
        self.assertIsNone(game.colour_for(self.pilot))
        self.assertEqual(len(game.drawables()), 1)   # guide line to the next gate

    def test_validation(self):
        game = GateRace()
        self.assertIsNotNone(game.validate(self.objects, None))
        empty = ObjectService()
        self.assertIn("No gates", game.validate(empty, self.pilot))
        self.assertIsNotNone(game.validate(self.objects, self.gates[0]))


class HoverChallengeTests(unittest.TestCase):
    def setUp(self):
        self.objects = ObjectService()
        self.pilot = self.objects.add_object(Sphere(name="Pilot", controllable=True))
        _at(self.pilot, 0, 0, 0)
        self.game = HoverChallenge({"target_x": 0.0, "target_y": 1.0, "target_z": 0.0, "radius": 0.25,
                                    "hold_s": 2.0, "time_limit_s": 10.0, "countdown_s": 0})

    def test_holding_inside_the_zone_succeeds(self):
        self.game.start(self.objects, self.pilot, "Jaap", now=0.0)
        self.game.tick(1.0)                     # still on the ground
        _at(self.pilot, 0.1, 1.1, 0.0)
        for t in (2.0, 3.0, 3.9):
            self.game.tick(t)
        self.assertEqual(self.game.state, GameState.RUNNING)
        self.game.tick(4.0)
        self.assertEqual(self.game.state, GameState.FINISHED)
        self.assertAlmostEqual(self.game.result.score, 4.0)

    def test_leaving_the_zone_restarts_the_hold(self):
        self.game.start(self.objects, self.pilot, "Jaap", now=0.0)
        _at(self.pilot, 0, 1, 0)
        self.game.tick(1.0)
        self.game.tick(2.5)
        _at(self.pilot, 0, 2, 0)
        self.game.tick(2.6)
        _at(self.pilot, 0, 1, 0)
        self.game.tick(3.0)
        self.game.tick(4.5)
        self.assertEqual(self.game.state, GameState.RUNNING)
        self.game.tick(5.0)
        self.assertEqual(self.game.state, GameState.FINISHED)

    def test_time_limit_fails(self):
        self.game.start(self.objects, self.pilot, "Jaap", now=0.0)
        self.game.tick(10.5)
        self.assertEqual(self.game.state, GameState.FAILED)
        self.assertFalse(self.game.result.success)

    def test_target_from_pilot_action(self):
        _at(self.pilot, 1.234, 1.5, -0.5)
        message = self.game.actions()[0].run(self.game, self.objects, self.pilot)
        self.assertIn("Target set", message)
        self.assertEqual((self.game.settings["target_x"], self.game.settings["target_y"]), (1.23, 1.5))


def _result(pilot, score, game="gate_race", success=True, t=0.0):
    return GameResult(game, "Gate race", pilot, score, "s", True, success, timestamp=t)


class ResultsStoreTests(unittest.TestCase):
    def test_ranking_persistence_and_clear(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "results.json")
            store = ResultsStore(path)
            for pilot, score, t in [("Ana", 30.0, 1), ("Ben", 25.0, 2), ("ana", 20.0, 3), ("Cy", 10.0, 4)]:
                store.add(_result(pilot, score, t=t))
            store.add(_result("Cy", 5.0, success=False, t=5))          # failures never rank
            store.add(_result("Ana", 1.0, game="hover_hold", t=6))

            reloaded = ResultsStore(path)
            self.assertEqual([r.score for r in reloaded.leaderboard("gate_race")], [10.0, 20.0, 25.0, 30.0])
            self.assertEqual([r.pilot for r in reloaded.leaderboard("gate_race", best_per_pilot=True)],
                             ["Cy", "ana", "Ben"])
            self.assertEqual(reloaded.personal_best("gate_race", "ANA").score, 20.0)
            reloaded.clear("gate_race")
            self.assertEqual(reloaded.leaderboard("gate_race"), [])
            self.assertEqual(len(reloaded.leaderboard("hover_hold")), 1)


class TrainerServiceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = get_app()

    def setUp(self):
        self._dir = tempfile.TemporaryDirectory()
        self.objects = ObjectService()
        self.pilot = self.objects.add_object(Sphere(name="Pilot", controllable=True))
        _at(self.pilot, 0, 1, 0)
        self.service = TrainerService(self.objects, ResultsStore(os.path.join(self._dir.name, "r.json")))
        self.service._timer.stop()
        self.events = []
        self.service.hud_changed.connect(lambda text: self.events.append(("hud", text)))
        self.service.results_changed.connect(lambda: self.events.append(("results",)))

    def tearDown(self):
        self._dir.cleanup()

    def hover(self, **settings):
        defaults = {"target_y": 1.0, "hold_s": 1.0, "countdown_s": 0}
        defaults.update(settings)
        return HoverChallenge(defaults)

    def test_successful_game_is_recorded(self):
        self.assertIsNone(self.service.start(self.hover(), self.pilot, "Jaap", now=0.0))
        self.service.tick(0.5)
        self.service.tick(1.6)
        self.assertFalse(self.service.running)
        self.assertIn(("results",), self.events)
        self.assertEqual(self.service.results.leaderboard("hover_hold")[0].pilot, "Jaap")
        self.assertTrue(any(e[0] == "hud" and "Held" in e[1] for e in self.events))

    def test_stop_records_nothing(self):
        self.service.start(self.hover(), self.pilot, "Jaap", now=0.0)
        self.service.stop()
        self.assertEqual(self.service.game.state, GameState.STOPPED)
        self.assertEqual(self.service.results.all(), [])

    def test_validation_error_is_returned(self):
        self.assertIn("No gates", self.service.start(GateRace(), self.pilot, "Jaap", now=0.0))
        self.assertFalse(self.service.running)

    def test_removing_the_pilot_stops_the_game(self):
        self.service.start(self.hover(), self.pilot, "Jaap", now=0.0)
        self.objects.remove_object(obj=self.pilot)
        self.assertFalse(self.service.running)


class TrainerPanelTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = get_app()

    def setUp(self):
        self._dir = tempfile.TemporaryDirectory()
        self.objects = ObjectService()
        self.pilot = self.objects.add_object(Sphere(name="Pilot", controllable=True))
        _at(self.pilot, 2.0, 1.2, -0.3)
        self.objects.set_controlled_object(obj=self.pilot)
        self.service = TrainerService(self.objects, ResultsStore(os.path.join(self._dir.name, "r.json")))
        self.service._timer.stop()
        self.panel = TrainerPanel(trainer_service=self.service, object_service=self.objects)

    def tearDown(self):
        self.service.stop()
        self.panel.deleteLater()
        self._dir.cleanup()

    def test_settings_form_is_built_from_the_schema(self):
        self.panel.game_combo.setCurrentIndex(self.panel.game_combo.findData("hover_hold"))
        self.assertIn("radius", self.panel._setting_widgets)
        prefs = []
        self.panel.preferences_changed.connect(prefs.append)
        self.panel._setting_widgets["radius"].setValue(0.5)
        self.assertEqual(prefs[-1]["settings"]["hover_hold"]["radius"], 0.5)
        self.assertEqual(self.panel.current_settings()["radius"], 0.5)

    def test_preferences_restore_game_and_settings(self):
        self.panel.load_preferences({"game": "hover_hold", "settings": {"hover_hold": {"hold_s": 9.0}}})
        self.assertEqual(self.panel.game_combo.currentData(), "hover_hold")
        self.assertEqual(self.panel._setting_widgets["hold_s"].value(), 9.0)

    def test_follows_the_command_panel_object_by_default(self):
        self.assertIs(self.panel.pilot_object(), self.pilot)

    def test_start_without_gates_explains_why(self):
        self.panel.game_combo.setCurrentIndex(self.panel.game_combo.findData("gate_race"))
        self.assertIn("No gates", self.panel.start_game())
        self.assertIn("No gates", self.panel.status_label.text())

    def test_create_course_then_race(self):
        self.panel.game_combo.setCurrentIndex(self.panel.game_combo.findData("gate_race"))
        self.panel.run_action(self.panel._actions[0])
        self.assertEqual(len([o for o in self.objects.get_objects() if o.gate_order]), 4)
        self.assertIsNone(self.panel.start_game())
        self.assertTrue(self.service.running)
        self.assertEqual(self.panel.start_button.text(), "Stop")
        self.assertFalse(self.panel.game_combo.isEnabled())
        self.panel.start_button.click()
        self.assertEqual(self.panel.start_button.text(), "Start")

    def test_hover_target_action_updates_the_form(self):
        self.panel.game_combo.setCurrentIndex(self.panel.game_combo.findData("hover_hold"))
        self.panel.run_action(self.panel._actions[0])
        self.assertAlmostEqual(self.panel._setting_widgets["target_x"].value(), 2.0)

    def test_leaderboard_shows_results(self):
        board = LeaderboardPanel(trainer_service=self.service)
        self.assertTrue(board.empty_label.isVisibleTo(board))
        self.service.results.add(_result("Jaap", 12.5))
        self.service.results_changed.emit()
        board.game_combo.setCurrentIndex(board.game_combo.findData("gate_race"))
        board.refresh()
        self.assertEqual(board.table.rowCount(), 1)
        self.assertEqual(board.table.item(0, 1).text(), "Jaap")
        self.assertEqual(board.table.item(0, 2).text(), "12.50 s")
        board.deleteLater()


if __name__ == "__main__":
    unittest.main()
