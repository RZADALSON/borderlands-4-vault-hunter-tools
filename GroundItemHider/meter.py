"""The counting itself: hits go in, DPS comes out. Nothing here touches the game."""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass

# How damage per second gets worked out
MODE_FIGHT = "fight"  # All of it, over the time from the first hit to the last
MODE_WINDOW = "window"  # Only the last few seconds

# A single hit has no length, this stops it counting as a huge DPS
MIN_DURATION = 1.0


@dataclass
class FightSummary:
    """How a finished fight went."""

    dps: float
    total: float
    duration: float
    kills: int = 0


class Meter:
    """Counts one fight at a time, and remembers how the last one went."""

    def __init__(self) -> None:
        self.mode = MODE_FIGHT
        self.window = 5.0
        # Seconds without a hit before starting over, None if only by hand
        self.reset_after: float | None = 5.0
        self.last_fight: FightSummary | None = None
        self.clear()

    def clear(self) -> None:
        """Forgets the current fight."""
        self.total = 0.0
        self.crit = 0.0
        self.hits = 0
        self.kills = 0
        self.killed: set[int] = set()
        self.biggest = 0.0
        self.first = 0.0
        self.last = 0.0
        self.recent: deque[tuple[float, float]] = deque()

    def add(self, now: float, damage: float, crit: bool = False, kill: bool = False, target: int = 0) -> None:
        """Counts one hit. Every pellet or blast still landing on what just died says it killed it too."""
        if not self.hits:
            self.first = now
        self.last = now
        self.hits += 1
        self.total += damage
        self.crit += damage if crit else 0.0
        if kill and target not in self.killed:
            self.killed.add(target)
            self.kills += 1
        self.biggest = max(self.biggest, damage)
        self.recent.append((now, damage))
        self.forget_old(now)

    def forget_old(self, now: float) -> None:
        """Drops the hits which are too old for the window, however long it's been set to."""
        while self.recent and now - self.recent[0][0] > self.window:
            self.recent.popleft()

    def duration(self, now: float) -> float:
        """Gets how long the fight has lasted, the way the current mode sees it."""
        if not self.hits:
            return 0.0
        if self.mode == MODE_WINDOW:
            return min(now - self.first, self.window)
        return self.last - self.first

    def dps(self, now: float) -> float:
        """Gets the current damage per second."""
        if not self.hits:
            return 0.0
        if self.mode == MODE_WINDOW:
            self.forget_old(now)
            return sum(damage for _, damage in self.recent) / max(self.duration(now), MIN_DURATION)
        return self.total / max(self.duration(now), MIN_DURATION)

    def summary(self) -> FightSummary:
        """Sums up the fight as of its last hit. The time since then wasn't part of the fight."""
        duration = self.last - self.first
        return FightSummary(self.total / max(duration, MIN_DURATION), self.total, duration, self.kills)

    def tick(self, now: float) -> None:
        """Starts over once it's been long enough without a hit."""
        if self.reset_after is not None and self.hits and now - self.last >= self.reset_after:
            self.reset()

    def reset(self) -> None:
        """Ends the fight, keeping how it went."""
        if self.hits:
            self.last_fight = self.summary()
        self.clear()


def format_number(value: float) -> str:
    """Keeps numbers short, damage in this game gets huge."""
    if value < 10_000:
        return f"{value:,.0f}".replace(",", " ")
    if value < 1e6:
        return f"{value / 1e3:.1f}K"
    if value < 1e9:
        return f"{value / 1e6:.2f}M"
    if value < 1e12:
        return f"{value / 1e9:.2f}B"
    return f"{value / 1e12:.2f}T"


def format_time(seconds: float) -> str:
    """Formats a duration as minutes and seconds."""
    whole = int(seconds)
    return f"{whole // 60:02d}:{whole % 60:02d}"
