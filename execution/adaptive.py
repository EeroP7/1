"""
Adaptive performance memory.

The bot tags every bet with *why* it entered (e.g. "momentum-UP",
"value-DOWN"). When a position closes we record win/loss against that tag.
Over time each tag accumulates a rolling record, and the engine asks this
module two questions before betting:

  allow(tag)           → False to skip a tag that's been losing badly
  size_multiplier(tag) → scale stake down on weak tags, up on strong ones

State is persisted to a JSON file so the bot keeps what it learned across
restarts. This is not magic: it can only cut off strategies that are
demonstrably losing on real fills — it cannot create an edge that isn't
there. Its main value is damage control.
"""
import json
import os
from collections import deque
from dataclasses import dataclass, field
from typing import Deque

MEMORY_FILE = os.getenv("BOT_MEMORY_FILE", "bot_memory.json")

# how many recent trades per tag to weigh
WINDOW          = 30
# need at least this many before we trust a tag's win rate enough to act
MIN_SAMPLES     = 8
# pause a tag whose recent win rate drops below this
PAUSE_BELOW     = 0.35
# re-test a paused tag occasionally so it can recover (1 in N bets)
PROBE_EVERY     = 10


@dataclass
class TagStats:
    results: Deque[int] = field(default_factory=lambda: deque(maxlen=WINDOW))
    wins:   int = 0
    losses: int = 0
    skips_since_probe: int = 0

    def win_rate(self) -> float:
        if not self.results:
            return 0.5
        return sum(self.results) / len(self.results)


class AdaptiveMemory:
    def __init__(self, path: str = MEMORY_FILE) -> None:
        self._path = path
        self._tags: dict[str, TagStats] = {}
        self._load()

    # ── decision API ────────────────────────────────────────────────────────

    def allow(self, tag: str) -> bool:
        """False → skip this bet because the tag is on a losing streak.
        Occasionally probes a paused tag so it can earn its way back."""
        st = self._tags.get(tag)
        if st is None or len(st.results) < MIN_SAMPLES:
            return True                       # not enough data → let it run
        if st.win_rate() >= PAUSE_BELOW:
            return True
        # tag is paused — let one bet through every PROBE_EVERY skips
        st.skips_since_probe += 1
        if st.skips_since_probe >= PROBE_EVERY:
            st.skips_since_probe = 0
            return True
        return False

    def win_rate_of(self, tag: str) -> float:
        st = self._tags.get(tag)
        return st.win_rate() if st else 0.5

    def size_multiplier(self, tag: str) -> float:
        """Scale stake by recent performance: 0.5x for weak tags up to 1.3x
        for strong ones. Keeps sizing humble until a tag proves itself."""
        st = self._tags.get(tag)
        if st is None or len(st.results) < MIN_SAMPLES:
            return 1.0
        wr = st.win_rate()
        if wr < 0.40:
            return 0.5
        if wr < 0.50:
            return 0.75
        if wr > 0.60:
            return 1.3
        return 1.0

    # ── recording ─────────────────────────────────────────────────────────────

    def record(self, tag: str, won: bool) -> None:
        st = self._tags.setdefault(tag, TagStats())
        st.results.append(1 if won else 0)
        if won:
            st.wins += 1
        else:
            st.losses += 1
        self._save()

    # ── reporting ─────────────────────────────────────────────────────────────

    def summary(self) -> list[tuple[str, float, int]]:
        """(tag, recent_win_rate, total_trades) sorted by volume."""
        rows = [
            (tag, st.win_rate(), st.wins + st.losses)
            for tag, st in self._tags.items()
        ]
        return sorted(rows, key=lambda r: r[2], reverse=True)

    # ── persistence ────────────────────────────────────────────────────────────

    def _load(self) -> None:
        try:
            with open(self._path) as f:
                data = json.load(f)
            for tag, d in data.items():
                st = TagStats(
                    results=deque(d.get("results", []), maxlen=WINDOW),
                    wins=d.get("wins", 0),
                    losses=d.get("losses", 0),
                )
                self._tags[tag] = st
        except (FileNotFoundError, json.JSONDecodeError, ValueError):
            self._tags = {}

    def _save(self) -> None:
        try:
            data = {
                tag: {
                    "results": list(st.results),
                    "wins": st.wins,
                    "losses": st.losses,
                }
                for tag, st in self._tags.items()
            }
            tmp = self._path + ".tmp"
            with open(tmp, "w") as f:
                json.dump(data, f, indent=2)
            os.replace(tmp, self._path)
        except OSError:
            pass
