"""Time-budget guard for per-round deadline enforcement.

Usage:
    with TimeBudget(limit=1.8) as timer:
        actions = strategy.decide(state)
    if timer.exceeded:
        actions = all_wait(state.bots)
"""

from __future__ import annotations

import time
from types import TracebackType


class TimeBudget:
    """Context manager that tracks elapsed wall-clock time."""

    def __init__(self, limit: float = 1.8) -> None:
        self.limit = limit
        self._start: float = 0.0
        self._elapsed: float = 0.0

    def __enter__(self) -> TimeBudget:
        self._start = time.monotonic()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        self._elapsed = time.monotonic() - self._start

    @property
    def elapsed(self) -> float:
        """Seconds elapsed since entering the context (live if still inside)."""
        if self._elapsed > 0:
            return self._elapsed
        return time.monotonic() - self._start

    def remaining(self) -> float:
        """Seconds remaining before the budget is exhausted."""
        return max(0.0, self.limit - self.elapsed)

    @property
    def exceeded(self) -> bool:
        """True if the time budget has been exceeded."""
        return self.elapsed >= self.limit
