"""BFS pathfinder — extracted from run_hard.py."""

from __future__ import annotations

from collections import deque
from typing import Optional

from core.types import Coord, Grid, neighbors

from .base import Pathfinder


class BFSPathfinder(Pathfinder):
    """
    Breadth-first search on unweighted grid.
    Optimal for shortest-path on grids with uniform movement cost.

    Features:
    - Per-round distance cache (cleared via clear_cache)
    - Targets walkable cells adjacent to shelf positions
    """

    def __init__(self) -> None:
        self._dist_cache: dict[tuple[Coord, Coord], int] = {}

    def clear_cache(self) -> None:
        self._dist_cache.clear()

    def distance(
        self,
        grid: Grid,
        start: Coord,
        goal_pos: Coord,
        blocked: set[Coord] | frozenset[Coord] = frozenset(),
    ) -> int:
        cache_key = (start, goal_pos)
        if cache_key in self._dist_cache:
            return self._dist_cache[cache_key]

        # Goals are walkable cells adjacent to the shelf/item position
        goals: set[Coord] = set()
        for n in neighbors(goal_pos):
            if grid.walkable(n) and n not in blocked:
                goals.add(n)

        if not goals:
            self._dist_cache[cache_key] = 9999
            return 9999

        if start in goals:
            self._dist_cache[cache_key] = 0
            return 0

        q: deque[tuple[Coord, int]] = deque([(start, 0)])
        visited: set[Coord] = {start}

        while q:
            pos, dist = q.popleft()
            for nxt in neighbors(pos):
                if nxt in visited:
                    continue
                if not grid.walkable(nxt) or nxt in blocked:
                    continue
                new_dist = dist + 1
                if nxt in goals:
                    self._dist_cache[cache_key] = new_dist
                    return new_dist
                visited.add(nxt)
                q.append((nxt, new_dist))

        self._dist_cache[cache_key] = 9999
        return 9999

    def first_step(
        self,
        grid: Grid,
        start: Coord,
        goals: set[Coord],
        blocked: set[Coord] | frozenset[Coord] = frozenset(),
    ) -> Optional[Coord]:
        if start in goals or not goals:
            return None

        q: deque[Coord] = deque([start])
        prev: dict[Coord, Optional[Coord]] = {start: None}

        while q:
            cur = q.popleft()
            for nxt in neighbors(cur):
                if nxt in prev:
                    continue
                if not grid.walkable(nxt) or nxt in blocked:
                    continue
                prev[nxt] = cur
                if nxt in goals:
                    return _unwind_first_step(start, nxt, prev)
                q.append(nxt)
        return None


def _unwind_first_step(
    start: Coord,
    goal: Coord,
    prev: dict[Coord, Optional[Coord]],
) -> Optional[Coord]:
    cur = goal
    parent = prev[cur]
    while parent is not None and parent != start:
        cur = parent
        parent = prev[cur]
    if parent is None:
        return None
    return cur
