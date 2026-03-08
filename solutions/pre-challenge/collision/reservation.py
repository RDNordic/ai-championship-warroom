"""Single-step reservation-based collision avoidance.

Extracted from run_hard.py and run_expert.py _move_toward.

Priority-based: bots processed in order; each bot's chosen next cell
is added to reserved_next so subsequent bots avoid it.
"""

from __future__ import annotations

import random
from typing import Optional

from core.types import Coord, Grid, action_from_step, neighbors
from pathfinding.base import Pathfinder

from .base import CollisionResolver


class ReservationResolver(CollisionResolver):
    """
    Reservation-based collision resolution with progressive relaxation.

    1. Try BFS with full blocked set (occupied + reserved)
    2. If blocked: relax to just occupied (drop reservations)
    3. If still blocked: relax to only adjacent blockers
    4. Final fallback: wait
    """

    def __init__(self, wait_streak_nudge_threshold: int = 3) -> None:
        self._wait_streak_nudge_threshold = wait_streak_nudge_threshold

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
        blocked = (occupied_now - {start}) | reserved_next
        if allow_occupied_goals:
            blocked = blocked - goals

        step = pathfinder.first_step(grid, start, goals, blocked)

        if step is None and relax_reservation_if_blocked:
            # Relaxation 1: drop reservations, keep only occupied
            relaxed = occupied_now - {start}
            if allow_occupied_goals:
                relaxed = relaxed - goals
            step = pathfinder.first_step(grid, start, goals, relaxed)

        if step is None and relax_reservation_if_blocked:
            # Relaxation 2: only block immediately adjacent bots
            adjacent = set(neighbors(start))
            near_blocked = (occupied_now - {start}) & adjacent
            step = pathfinder.first_step(grid, start, goals, near_blocked)

        if step is None:
            return {"bot": bot_id, "action": "wait"}

        action = action_from_step(start, step)
        reserved_next.add(step)
        return {"bot": bot_id, "action": action}

    def wait_or_nudge(
        self,
        bot_id: int,
        pos: Coord,
        grid: Grid,
        occupied_now: set[Coord],
        reserved_next: set[Coord],
        wait_streak: int = 0,
    ) -> dict:
        """Wait, or nudge randomly if stuck too long."""
        if wait_streak >= self._wait_streak_nudge_threshold:
            nudge = self._random_nudge(bot_id, pos, grid, occupied_now, reserved_next)
            if nudge is not None:
                return nudge
        return {"bot": bot_id, "action": "wait"}

    @staticmethod
    def _random_nudge(
        bot_id: int,
        pos: Coord,
        grid: Grid,
        occupied_now: set[Coord],
        reserved_next: set[Coord],
    ) -> Optional[dict]:
        blocked = (occupied_now - {pos}) | reserved_next
        options: list[Coord] = []
        for n in neighbors(pos):
            if grid.walkable(n) and n not in blocked:
                options.append(n)
        if not options:
            return None
        step = random.choice(options)
        reserved_next.add(step)
        return {"bot": bot_id, "action": action_from_step(pos, step)}
