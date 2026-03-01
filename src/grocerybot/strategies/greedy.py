"""Milestone 3 greedy multi-bot strategy for Medium."""

from __future__ import annotations

from grocerybot.grid import PassableGrid, adjacent_walkable, direction_for_move
from grocerybot.models import BotAction, GameState, MoveAction, WaitAction
from grocerybot.planner import (
    AssignedTask,
    CollisionResolver,
    LocalTripPlanner,
    OrderTracker,
    TaskAssigner,
    next_position_for_action,
)
from grocerybot.strategies.base import Strategy

Position = tuple[int, int]


def _manhattan(a: Position, b: Position) -> int:
    return abs(a[0] - b[0]) + abs(a[1] - b[1])


class GreedyStrategy(Strategy):
    """Greedy assignment with exact local trip planning."""

    def __init__(self) -> None:
        self._grid: PassableGrid | None = None
        self._order_tracker = OrderTracker()
        self._assigner = TaskAssigner()
        self._resolver = CollisionResolver()
        self._planner: LocalTripPlanner | None = None
        self._last_positions: dict[int, Position] = {}
        self._stuck_rounds: dict[int, int] = {}

    def on_game_start(self, state: GameState) -> None:
        self._grid = PassableGrid(state)
        self._planner = LocalTripPlanner(state, self._grid)
        self._last_positions = {bot.id: bot.position for bot in state.bots}
        self._stuck_rounds = {bot.id: 0 for bot in state.bots}

    def _step_to_free_neighbor(
        self,
        bot_id: int,
        pos: Position,
        blocked: frozenset[Position],
    ) -> MoveAction | None:
        grid = self._grid
        assert grid is not None
        for nb in grid.neighbors(pos):
            if nb in blocked:
                continue
            return MoveAction(bot=bot_id, action=direction_for_move(pos, nb))
        return None

    def _move_away_from_dropoff(
        self,
        bot_id: int,
        pos: Position,
        drop_off: Position,
        blocked: frozenset[Position],
        min_distance: int,
    ) -> MoveAction | None:
        grid = self._grid
        assert grid is not None

        current_dist = _manhattan(pos, drop_off)
        best_target: Position | None = None
        best_dist = current_dist
        for adj in adjacent_walkable(pos, grid):
            if adj in blocked:
                continue
            dist = _manhattan(adj, drop_off)
            if dist < min_distance:
                continue
            if dist > best_dist:
                best_dist = dist
                best_target = adj
        if best_target is None:
            return None
        return MoveAction(bot=bot_id, action=direction_for_move(pos, best_target))

    def decide(self, state: GameState) -> list[BotAction]:
        planner = self._planner
        grid = self._grid
        assert (
            planner is not None and grid is not None
        ), "on_game_start must be called before decide"

        snapshot = self._order_tracker.snapshot(state)
        bots = sorted(state.bots, key=lambda b: b.id)
        current_positions = {bot.id: bot.position for bot in bots}
        for bot in bots:
            prev = self._last_positions.get(bot.id)
            if prev is None or prev != bot.position:
                self._stuck_rounds[bot.id] = 0
            else:
                self._stuck_rounds[bot.id] = self._stuck_rounds.get(bot.id, 0) + 1
        if snapshot is None:
            return [WaitAction(bot=bot.id) for bot in bots]

        tasks = self._assigner.assign(state, snapshot, planner)
        dropoff_seekers = {
            bot_id for bot_id, task in tasks.items()
            if task.kind == "drop_off"
        }
        seeker_cells = frozenset(
            b.position for b in bots if b.id in dropoff_seekers
        )
        proposed: dict[int, BotAction] = {}

        for bot in bots:
            task = tasks.get(bot.id, AssignedTask(bot.id, "wait"))
            occupied_now = {
                other.position for other in bots
                if other.id != bot.id and other.position != bot.position
            }
            blocked = frozenset(occupied_now)

            if task.kind == "pick":
                action = planner.next_pick_action(
                    state,
                    bot_id=bot.id,
                    pos=bot.position,
                    pickups=task.pickups,
                    blocked=blocked,
                )
                if action is None:
                    action = WaitAction(bot=bot.id)
            elif task.kind == "drop_off":
                action = planner.go_drop_off(bot.id, bot.position, blocked=blocked)
            else:
                action = WaitAction(bot=bot.id)

            next_pos = next_position_for_action(bot.position, action)
            dist_to_drop = _manhattan(bot.position, state.drop_off)
            is_blocker = (
                bot.id not in dropoff_seekers
                and bool(dropoff_seekers)
                and dist_to_drop <= 1
                and (isinstance(action, WaitAction) or next_pos == state.drop_off)
            )
            if is_blocker:
                min_distance = 1 if bot.position == state.drop_off else 2
                step = self._move_away_from_dropoff(
                    bot.id,
                    bot.position,
                    state.drop_off,
                    blocked | seeker_cells,
                    min_distance=min_distance,
                )
                if step is not None:
                    action = step
                    next_pos = next_position_for_action(bot.position, action)

            if (
                isinstance(action, WaitAction)
                and task.kind in {"pick", "drop_off"}
                and self._stuck_rounds.get(bot.id, 0) >= 3
            ):
                nudge = self._step_to_free_neighbor(
                    bot.id, bot.position, blocked,
                )
                if nudge is not None:
                    action = nudge

            proposed[bot.id] = action

        resolved = self._resolver.resolve(state, proposed)
        self._last_positions = current_positions
        return resolved
