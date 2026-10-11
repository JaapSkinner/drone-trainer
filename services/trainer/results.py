"""Game results, persisted as JSON in the data directory (for the Leaderboard)."""
import json
import logging
import os
from typing import List, Optional

from services.paths import data_dir
from services.trainer.games import GameResult

logger = logging.getLogger(__name__)


def default_results_path() -> str:
    return os.path.join(data_dir(), "results.json")


class ResultsStore:
    def __init__(self, path: Optional[str] = None):
        self.path = path or default_results_path()
        self._results: Optional[List[GameResult]] = None

    def _load(self) -> List[GameResult]:
        if self._results is None:
            self._results = []
            if os.path.exists(self.path):
                try:
                    with open(self.path, "r", encoding="utf-8") as fh:
                        self._results = [GameResult.from_dict(d) for d in json.load(fh)]
                except (OSError, ValueError, TypeError) as exc:
                    logger.warning("Could not read results from %s: %s", self.path, exc)
        return self._results

    def _save(self):
        os.makedirs(os.path.dirname(os.path.abspath(self.path)), exist_ok=True)
        tmp = self.path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump([r.to_dict() for r in self._load()], fh, indent=2)
        os.replace(tmp, self.path)

    def add(self, result: GameResult):
        self._load().append(result)
        self._save()

    def all(self, game: Optional[str] = None) -> List[GameResult]:
        return [r for r in self._load() if game is None or r.game == game]

    def leaderboard(self, game: str, limit: int = 20, best_per_pilot: bool = False) -> List[GameResult]:
        """Successful results for ``game``, best first."""
        results = [r for r in self.all(game) if r.success]
        if not results:
            return []
        sign = 1 if results[0].lower_is_better else -1
        results.sort(key=lambda r: (sign * r.score, r.timestamp))
        if best_per_pilot:
            seen, unique = set(), []
            for r in results:
                key = r.pilot.strip().lower()
                if key not in seen:
                    seen.add(key)
                    unique.append(r)
            results = unique
        return results[:limit]

    def personal_best(self, game: str, pilot: str) -> Optional[GameResult]:
        mine = [r for r in self.leaderboard(game, limit=10_000) if r.pilot.strip().lower() == pilot.strip().lower()]
        return mine[0] if mine else None

    def clear(self, game: Optional[str] = None):
        self._results = [r for r in self._load() if game is not None and r.game != game]
        self._save()
