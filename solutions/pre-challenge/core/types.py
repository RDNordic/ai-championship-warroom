"""Shared type definitions used across all modules."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

# (x, y) coordinate on the grid
Coord = tuple[int, int]

DIRECTIONS = [(1, 0), (-1, 0), (0, 1), (0, -1)]


def neighbors(p: Coord) -> list[Coord]:
    x, y = p
    return [(x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)]


def manhattan(a: Coord, b: Coord) -> int:
    return abs(a[0] - b[0]) + abs(a[1] - b[1])


def action_from_step(start: Coord, step: Coord) -> str:
    sx, sy = start
    nx, ny = step
    if nx == sx + 1:
        return "move_right"
    if nx == sx - 1:
        return "move_left"
    if ny == sy + 1:
        return "move_down"
    if ny == sy - 1:
        return "move_up"
    return "wait"


@dataclass
class Grid:
    """Immutable grid info — cached once at round 0."""

    width: int
    height: int
    walls: frozenset[Coord]
    shelves: set[Coord] = field(default_factory=set)

    def in_bounds(self, p: Coord) -> bool:
        x, y = p
        return 0 <= x < self.width and 0 <= y < self.height

    def walkable(self, p: Coord) -> bool:
        return self.in_bounds(p) and p not in self.walls and p not in self.shelves

    def walkable_neighbors(self, p: Coord) -> list[Coord]:
        return [n for n in neighbors(p) if self.walkable(n)]

    def adjacent_walkable(
        self,
        shelf_pos: Coord,
        blocked: set[Coord] | frozenset[Coord] = frozenset(),
    ) -> set[Coord]:
        """Walkable cells adjacent to a shelf (for pickup positioning)."""
        goals: set[Coord] = set()
        for n in neighbors(shelf_pos):
            if self.walkable(n) and n not in blocked:
                goals.add(n)
        return goals

    def update_shelves(self, items: list[dict]) -> None:
        """Update shelf positions from item list (call each round)."""
        for item in items:
            self.shelves.add(tuple(item["position"]))
