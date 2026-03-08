"""Abstract pathfinder interface."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Optional

from core.types import Coord, Grid


class Pathfinder(ABC):
    """
    Single responsibility: compute distances and first-steps on a grid.

    Input:  grid, start position, goal positions, blocked cells
    Output: distance (int) or next step toward goal (Coord | None)
    """

    @abstractmethod
    def distance(
        self,
        grid: Grid,
        start: Coord,
        goal_pos: Coord,
        blocked: set[Coord] | frozenset[Coord] = frozenset(),
    ) -> int:
        """
        Walkable distance from start to any cell adjacent to goal_pos.
        goal_pos is typically a shelf (not walkable), so we target neighbors.
        Returns 9999 if unreachable.
        """

    @abstractmethod
    def first_step(
        self,
        grid: Grid,
        start: Coord,
        goals: set[Coord],
        blocked: set[Coord] | frozenset[Coord] = frozenset(),
    ) -> Optional[Coord]:
        """
        First step from start toward the nearest goal, avoiding blocked cells.
        Returns None if already at goal or no path exists.
        """

    def clear_cache(self) -> None:
        """Clear any per-round caches. Called at the start of each round."""
