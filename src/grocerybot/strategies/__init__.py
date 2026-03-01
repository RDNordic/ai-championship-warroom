"""Strategy registry. Maps strategy names to classes."""

from __future__ import annotations

from typing import TYPE_CHECKING

from grocerybot.strategies.greedy import GreedyStrategy
from grocerybot.strategies.logger import LoggerStrategy
from grocerybot.strategies.memory_solo import MemorySoloStrategy
from grocerybot.strategies.solo import SoloStrategy

if TYPE_CHECKING:
    from grocerybot.strategies.base import Strategy

STRATEGIES: dict[str, type[Strategy]] = {
    "greedy": GreedyStrategy,
    "logger": LoggerStrategy,
    "solo": SoloStrategy,
    "memory_solo": MemorySoloStrategy,
}


def get_strategy(name: str, level: str | None = None) -> Strategy:
    """Look up a strategy by name and return an instance."""
    cls = STRATEGIES.get(name)
    if cls is None:
        available = ", ".join(sorted(STRATEGIES))
        msg = f"Unknown strategy {name!r}. Available: {available}"
        raise ValueError(msg)
    if name == "memory_solo" and level:
        return MemorySoloStrategy(level=level)
    return cls()
