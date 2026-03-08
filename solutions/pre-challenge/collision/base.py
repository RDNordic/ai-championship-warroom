"""Abstract collision resolution interface."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Optional

from core.types import Coord, Grid
from pathfinding.base import Pathfinder


class CollisionResolver(ABC):
    """
    Single responsibility: resolve movement for a single bot,
    respecting occupied cells and reservations from higher-priority bots.

    Input:
    - bot_id, start position
    - goal cells
    - grid, pathfinder
    - currently occupied cells
    - already-reserved cells (from bots processed earlier this round)
    - flags: allow_occupied_goals, relax_reservation_if_blocked

    Output: action dict {"bot": id, "action": action_name}
    Side effect: adds the bot's next position to reserved_next
    """

    @abstractmethod
    def move_toward(
        self,
        bot_id: int,
        start: Coord,
        goals: set[Coord],
        grid: Grid,
        pathfinder: Pathfinder,
        occupied_now: set[Coord],
        reserved_next: set[Coord],
        allow_occupied_goals: bool = False,
        relax_reservation_if_blocked: bool = False,
    ) -> dict:
        """Return action dict and update reserved_next."""
