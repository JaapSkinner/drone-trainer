"""Training games for the Trainer panel (issue #6).

A game is driven by ``TrainerService``: ``start()`` → countdown → ``tick()``
every frame → finished (with a ``GameResult``) or failed. Games only read the
pilot object's pose, so they work the same for a simulated drone flown from
the Command panel and for a real drone tracked by motion capture.

Add a game by subclassing ``TrainingGame`` (declare ``SETTINGS`` — the panel
builds the settings form from them) and appending it to ``GAMES``.
"""
from __future__ import annotations

import math
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Callable, Dict, List, Optional, Sequence, Tuple

import numpy as np

from models import frames
from models.gate_frame import GateFrame, gate_crossed
from models.polyline import Polyline, dashed_segments
from models.sphere import Sphere


class GameState(Enum):
    IDLE = "idle"
    COUNTDOWN = "countdown"
    RUNNING = "running"
    FINISHED = "finished"
    FAILED = "failed"
    STOPPED = "stopped"

    @property
    def active(self) -> bool:
        return self in (GameState.COUNTDOWN, GameState.RUNNING)


@dataclass
class Setting:
    key: str
    label: str
    kind: str                      # "float" | "int" | "bool"
    default: object
    minimum: float = 0.0
    maximum: float = 1000.0
    step: float = 1.0
    decimals: int = 2
    suffix: str = ""
    tooltip: str = ""


@dataclass
class GameResult:
    game: str
    game_title: str
    pilot: str
    score: float
    unit: str
    lower_is_better: bool
    success: bool
    details: dict = field(default_factory=dict)
    settings: dict = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)

    def score_text(self) -> str:
        return f"{self.score:.2f} {self.unit}".strip()

    def to_dict(self) -> dict:
        return dict(self.__dict__)

    @classmethod
    def from_dict(cls, data: dict) -> "GameResult":
        known = set(cls.__dataclass_fields__)
        return cls(**{k: v for k, v in data.items() if k in known})


@dataclass
class GameAction:
    label: str
    tooltip: str
    run: Callable                  # run(game, object_service, pilot) -> optional message
    confirm: str = ""              # ask before running (empty = no confirmation)


class TrainingGame:
    key = ""
    title = ""
    description = ""
    unit = "s"
    lower_is_better = True
    SETTINGS: Sequence[Setting] = ()

    def __init__(self, settings: Optional[dict] = None):
        self.settings = {s.key: s.default for s in self.SETTINGS}
        self.settings.update({k: v for k, v in (settings or {}).items() if k in self.settings})
        self.state = GameState.IDLE
        self.result: Optional[GameResult] = None
        self.object_service = None
        self.pilot = None
        self.pilot_name = ""
        self._go_time = None       # when the countdown ends and the clock starts
        self._now = 0.0

    # -- lifecycle ------------------------------------------------------------

    def actions(self) -> List[GameAction]:
        return []

    def validate(self, object_service, pilot) -> Optional[str]:
        """Return a message if the game can't start (e.g. no gates in the scene)."""
        return None if pilot is not None else "Choose the object you are flying."

    def start(self, object_service, pilot, pilot_name: str, now: float):
        self.object_service, self.pilot, self.pilot_name = object_service, pilot, pilot_name
        self.result = None
        self._now = now
        self._go_time = now + float(self.settings.get("countdown_s", 0.0))
        self.state = GameState.COUNTDOWN if self._go_time > now else GameState.RUNNING
        self._prepare(now)

    def stop(self):
        if self.state.active:
            self.state = GameState.STOPPED

    def tick(self, now: float):
        self._now = now
        if self.state == GameState.COUNTDOWN and now >= self._go_time:
            self.state = GameState.RUNNING
            self._on_go(now)
        if self.state == GameState.RUNNING:
            self._update(now)

    def elapsed(self, now: Optional[float] = None) -> float:
        now = self._now if now is None else now
        return max(0.0, now - self._go_time) if self._go_time is not None else 0.0

    def _finish(self, score: float, success: bool, details: dict):
        self.state = GameState.FINISHED if success else GameState.FAILED
        self.result = GameResult(self.key, self.title, self.pilot_name, round(float(score), 3), self.unit,
                                 self.lower_is_better, success, details, dict(self.settings))

    def pilot_position(self) -> np.ndarray:
        return np.asarray(self.pilot.pose[:3], dtype=float)

    # -- for subclasses ------------------------------------------------------------

    def _prepare(self, now):
        pass

    def _on_go(self, now):
        pass

    def _update(self, now):
        pass

    def hud_text(self) -> str:
        if self.state == GameState.COUNTDOWN:
            return f"{self.title} — get ready… {math.ceil(self._go_time - self._now)}"
        if self.state == GameState.STOPPED:
            return f"{self.title} stopped"
        if self.state in (GameState.FINISHED, GameState.FAILED) and self.result is not None:
            return self._result_text()
        return ""

    def _result_text(self) -> str:
        return f"{self.title}: {self.result.score_text()}"

    # -- viewport ------------------------------------------------------------

    def drawables(self) -> list:
        return []

    def colour_for(self, obj):
        return None


# ---------------------------------------------------------------------------

NEXT_GATE_COLOUR = (0.1, 0.85, 0.25, 1.0)
PASSED_GATE_COLOUR = (0.62, 0.62, 0.62, 1.0)
GUIDE_COLOUR = (0.1, 0.75, 0.25, 0.8)


def course_gates(object_service) -> list:
    return sorted((o for o in object_service.get_objects() if o.gate_order is not None),
                  key=lambda o: (o.gate_order, o.name))


def create_sample_course(object_service, count=4, radius=2.0, height=1.2, size=0.9) -> list:
    """Replace generated gates with ``count`` gates on a circle, facing along it."""
    for obj in course_gates(object_service):
        if isinstance(obj, GateFrame):
            object_service.remove_object(obj=obj)
    gates = []
    for i in range(count):
        a = 2.0 * math.pi * i / count
        q = frames.quat_from_axis_angle((0.0, 1.0, 0.0), -a)  # opening normal along the circle
        gate = GateFrame(name=f"Gate {i + 1}", width=size, height=size)
        gate.set_pose((radius * math.cos(a), height, radius * math.sin(a), *q))
        gate.gate_order = i + 1
        gates.append(object_service.add_object(gate))
    return gates


class GateRace(TrainingGame):
    key = "gate_race"
    title = "Gate race"
    description = ("Fly through every gate in order (lowest gate number first), for the number of "
                   "laps set below, as fast as you can. Any object with the “Race gate” feature counts; "
                   "gate frames and boxes must be flown through, other objects just touched.")
    SETTINGS = (
        Setting("laps", "Laps", "int", 1, 1, 20),
        Setting("countdown_s", "Countdown", "float", 3.0, 0, 10, 1, 0, " s"),
    )

    def actions(self):
        return [GameAction("Create sample course", "Add four gates on a 2 m circle (replaces generated gates)",
                           lambda game, objects, pilot: f"Created {len(create_sample_course(objects))} gates.",
                           "Replace the gate frames in the scene with a new 4-gate course?")]

    def validate(self, object_service, pilot):
        message = super().validate(object_service, pilot)
        if message:
            return message
        if not course_gates(object_service):
            return "No gates in the scene — use “Create sample course” or give objects the Race gate feature."
        if pilot.gate_order is not None:
            return "The pilot object is itself a gate."
        return None

    def _prepare(self, now):
        self.gates = course_gates(self.object_service)
        self.laps = int(self.settings["laps"])
        self.lap = 0
        self.next_index = 0
        self.splits: List[Tuple[int, str, float]] = []
        self._last_position = self.pilot_position()

    def _on_go(self, now):
        # Moving through a gate during the countdown doesn't count.
        self._last_position = self.pilot_position()

    def _update(self, now):
        position = self.pilot_position()
        gate = self.gates[self.next_index]
        if gate_crossed(gate, self._last_position, position):
            self.splits.append((self.lap + 1, gate.name, round(self.elapsed(now), 3)))
            self.next_index += 1
            if self.next_index == len(self.gates):
                self.next_index = 0
                self.lap += 1
                if self.lap == self.laps:
                    self._finish(self.elapsed(now), True, {"splits": self.splits, "gates": len(self.gates)})
        self._last_position = position

    def next_gate(self):
        if self.state in (GameState.COUNTDOWN, GameState.RUNNING):
            return self.gates[self.next_index]
        return None

    def hud_text(self):
        if self.state == GameState.RUNNING:
            return (f"Lap {self.lap + 1}/{self.laps} · Gate {self.next_index + 1}/{len(self.gates)} "
                    f"({self.gates[self.next_index].name}) · {self.elapsed():.2f} s")
        return super().hud_text()

    def _result_text(self):
        return f"Finished in {self.result.score:.2f} s"

    def colour_for(self, obj):
        if not self.state.active or obj.gate_order is None:
            return None
        if obj is self.next_gate():
            return NEXT_GATE_COLOUR
        index = next((i for i, g in enumerate(self.gates) if g is obj), None)
        if index is not None and index < self.next_index:
            return PASSED_GATE_COLOUR
        return None

    def drawables(self):
        gate = self.next_gate()
        if gate is None or self.pilot is None:
            return []
        return [Polyline(dashed_segments(self.pilot.pose[:3], gate.pose[:3], 0.12, 0.08), GUIDE_COLOUR, 2.0)]


# ---------------------------------------------------------------------------

INSIDE_COLOUR = (0.1, 0.8, 0.25, 0.3)
OUTSIDE_COLOUR = (1.0, 0.55, 0.0, 0.3)


class HoverChallenge(TrainingGame):
    key = "hover_hold"
    title = "Hover hold"
    description = ("Get into the target zone and hold it there without leaving for the hold time. "
                   "Leaving the zone restarts the hold. Your score is the total time taken.")
    SETTINGS = (
        Setting("target_x", "Target X", "float", 0.0, -20, 20, 0.1, 2, " m"),
        Setting("target_y", "Target height", "float", 1.0, 0, 10, 0.1, 2, " m"),
        Setting("target_z", "Target Z", "float", 0.0, -20, 20, 0.1, 2, " m"),
        Setting("radius", "Zone radius", "float", 0.25, 0.05, 3, 0.05, 2, " m"),
        Setting("hold_s", "Hold for", "float", 5.0, 1, 120, 1, 1, " s"),
        Setting("time_limit_s", "Time limit", "float", 60.0, 5, 600, 5, 0, " s"),
        Setting("countdown_s", "Countdown", "float", 3.0, 0, 10, 1, 0, " s"),
    )

    def actions(self):
        def use_pilot_position(game, objects, pilot):
            if pilot is None:
                return "Choose the object you are flying first."
            game.settings["target_x"], game.settings["target_y"], game.settings["target_z"] = (
                round(float(v), 2) for v in pilot.pose[:3])
            return "Target set to the pilot's current position."
        return [GameAction("Target = pilot position", "Put the zone where the pilot object is now",
                           use_pilot_position)]

    def target(self) -> np.ndarray:
        return np.array([self.settings["target_x"], self.settings["target_y"], self.settings["target_z"]], float)

    def _prepare(self, now):
        self.hold_started = None
        self.best_hold = 0.0

    def inside(self) -> bool:
        return float(np.linalg.norm(self.pilot_position() - self.target())) <= float(self.settings["radius"])

    def held_for(self, now=None) -> float:
        now = self._now if now is None else now
        return 0.0 if self.hold_started is None else now - self.hold_started

    def _update(self, now):
        if self.inside():
            if self.hold_started is None:
                self.hold_started = now
            held = self.held_for(now)
            self.best_hold = max(self.best_hold, held)
            if held >= float(self.settings["hold_s"]):
                self._finish(self.elapsed(now), True, {"hold_s": self.settings["hold_s"]})
                return
        else:
            self.hold_started = None
        if self.elapsed(now) > float(self.settings["time_limit_s"]):
            self._finish(self.elapsed(now), False, {"best_hold_s": round(self.best_hold, 2)})

    def hud_text(self):
        if self.state == GameState.RUNNING:
            hold = float(self.settings["hold_s"])
            status = (f"holding {self.held_for():.1f}/{hold:.0f} s" if self.hold_started is not None
                      else "get into the zone")
            return f"Hover hold — {status} · {self.elapsed():.1f} s"
        return super().hud_text()

    def _result_text(self):
        if self.result.success:
            return f"Held! Total time {self.result.score:.2f} s"
        return f"Time's up — best hold {self.result.details.get('best_hold_s', 0):.1f} s"

    def drawables(self):
        if self.state in (GameState.IDLE, GameState.STOPPED):
            return []
        inside = self.pilot is not None and self.inside()
        zone = Sphere(name="target zone", radius=float(self.settings["radius"]),
                      colour=INSIDE_COLOUR if inside else OUTSIDE_COLOUR)
        zone.set_pose((*self.target(), *frames.IDENTITY_QUAT))
        items = [zone]
        if self.pilot is not None and not inside and self.state.active:
            items.append(Polyline(dashed_segments(self.pilot.pose[:3], self.target(), 0.12, 0.08), GUIDE_COLOUR, 2.0))
        return items


GAMES = [GateRace, HoverChallenge]
GAMES_BY_KEY: Dict[str, type] = {g.key: g for g in GAMES}
