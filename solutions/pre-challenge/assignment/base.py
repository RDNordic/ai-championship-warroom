"""Abstract task assignment interface."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections import Counter
from typing import Callable

from core.types import Coord, Grid


class Assigner(ABC):
    """
    Single responsibility: assign items to bots.

    Input:
    - bots: list of bot dicts (id, position, inventory)
    - items: list of item dicts (id, type, position)
    - needed: Counter of item types still required
    - distance_fn: (bot_pos, item_pos) -> int
    - excluded_bots: bot IDs to skip (e.g. clearing dropoff)
    - excluded_items: item IDs to skip (e.g. pick-blocked)
    - delivery_bots: bot IDs currently delivering (get distance penalty)

    Output: dict[bot_id -> item_id]
    """

    @abstractmethod
    def assign(
        self,
        bots: list[dict],
        items: list[dict],
        needed: Counter,
        distance_fn: Callable[[Coord, Coord], int],
        excluded_bots: set[int] = frozenset(),
        excluded_items: set[str] = frozenset(),
        delivery_bots: set[int] = frozenset(),
        bot_locks: dict[int, str] | None = None,
    ) -> dict[int, str]:
        """Return mapping of bot_id -> item_id."""
