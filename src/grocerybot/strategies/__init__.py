"""Strategy registry. Maps strategy names to classes."""

from __future__ import annotations

from typing import TYPE_CHECKING

from grocerybot.strategies.logger import LoggerStrategy

if TYPE_CHECKING:
    from grocerybot.strategies.base import Strategy

STRATEGIES: dict[str, type[Strategy]] = {
    "logger": LoggerStrategy,
}


def get_strategy(name: str) -> Strategy:
    """Look up a strategy by name and return an instance."""
    cls = STRATEGIES.get(name)
    if cls is None:
        available = ", ".join(sorted(STRATEGIES))
        msg = f"Unknown strategy {name!r}. Available: {available}"
        raise ValueError(msg)
    return cls()
