"""Strategy registry. Maps strategy names to classes."""

from __future__ import annotations

from typing import TYPE_CHECKING

from grocerybot.strategies.greedy import GreedyStrategy
from grocerybot.strategies.logger import LoggerStrategy
from grocerybot.strategies.medium_v2 import MediumV2Strategy
from grocerybot.strategies.medium_v3 import MediumV3Strategy
from grocerybot.strategies.medium_v4 import MediumV4Strategy
from grocerybot.strategies.memory_solo import MemorySoloStrategy
from grocerybot.strategies.optimized_easy import OptimizedEasyStrategy
from grocerybot.strategies.optimized_medium import OptimizedMediumStrategy
from grocerybot.strategies.optimized_medium_v4 import OptimizedMediumV4Strategy
from grocerybot.strategies.optimized_medium_v5 import OptimizedMediumV5Strategy
from grocerybot.strategies.solo import SoloStrategy

if TYPE_CHECKING:
    from grocerybot.strategies.base import Strategy

STRATEGIES: dict[str, type[Strategy]] = {
    "greedy": GreedyStrategy,
    "logger": LoggerStrategy,
    "optimized_easy": OptimizedEasyStrategy,
    "optimized_medium": OptimizedMediumStrategy,
    "optimized_medium_v4": OptimizedMediumV4Strategy,
    "optimized_medium_v5": OptimizedMediumV5Strategy,
    "solo": SoloStrategy,
    "memory_solo": MemorySoloStrategy,
    "medium_v2": MediumV2Strategy,
    "medium_v3": MediumV3Strategy,
    "medium_v4": MediumV4Strategy,
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
    if name == "optimized_easy" and level:
        return OptimizedEasyStrategy(level=level)
    if name == "optimized_medium" and level:
        return OptimizedMediumStrategy(level=level)
    if name == "optimized_medium_v4" and level:
        return OptimizedMediumV4Strategy(level=level)
    if name == "optimized_medium_v5" and level:
        return OptimizedMediumV5Strategy(level=level)
    if name == "medium_v3" and level:
        return MediumV3Strategy(level=level)
    return cls()
