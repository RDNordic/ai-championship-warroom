"""Milestone 3 greedy multi-bot strategy for Medium (v2 traffic control).

v2 features:
- Persistent intents: bots keep pick/deliver/park intent across ticks
- Blocked-counter recovery: reroute after N stuck ticks
- Drop-off parking + delivery right-of-way in collision resolver
"""

from __future__ import annotations

from grocerybot.grid import PassableGrid, adjacent_walkable, astar, direction_for_move
from grocerybot.models import BotAction, GameState, MoveAction, WaitAction
from grocerybot.planner import (
    AssignedTask,
    BotIntent,
    CollisionResolver,
    IntentManager,
    LocalTripPlanner,
    OrderTracker,
    ParkingManager,
    TaskAssigner,
    next_position_for_action,
)
from grocerybot.strategies.base import Strategy

Position = tuple[int, int]


def _manhattan(a: Position, b: Position) -> int:
    return abs(a[0] - b[0]) + abs(a[1] - b[1])


class GreedyStrategy(Strategy):
    """Greedy assignment with persistent intents and v2 traffic control."""

    def __init__(self) -> None:
        self._grid: PassableGrid | None = None
        self._order_tracker = OrderTracker()
        self._assigner = TaskAssigner()
        self._resolver = CollisionResolver()
        self._planner: LocalTripPlanner | None = None
        self._intents = IntentManager()
        self._parking: ParkingManager | None = None
        self._last_positions: dict[int, Position] = {}

    def on_game_start(self, state: GameState) -> None:
        self._grid = PassableGrid(state)
        self._planner = LocalTripPlanner(state, self._grid)
        self._parking = ParkingManager(state.drop_off, self._grid)
        self._last_positions = {bot.id: bot.position for bot in state.bots}

    def decide(self, state: GameState) -> list[BotAction]:
        planner = self._planner
        grid = self._grid
        parking = self._parking
        assert (
            planner is not None and grid is not None and parking is not None
        ), "on_game_start must be called before decide"

        snapshot = self._order_tracker.snapshot(state)
        bots = sorted(state.bots, key=lambda b: b.id)
        current_positions = {bot.id: bot.position for bot in bots}

        # Update blocked counters based on whether bots actually moved
        for bot in bots:
            prev = self._last_positions.get(bot.id)
            if prev is not None and prev == bot.position:
                self._intents.bump_blocked(bot.id)
            else:
                self._intents.reset_blocked(bot.id)

        if snapshot is None:
            return [WaitAction(bot=bot.id) for bot in bots]

        # --- Phase 1: Invalidate stale intents ---
        for bot in bots:
            if self._intents.should_invalidate(bot.id, state, snapshot):
                self._intents.clear(bot.id)

        # --- Phase 2: Assign tasks to bots without intents ---
        claimed_pickups: list[str] = []
        for bot in bots:
            intent = self._intents.get(bot.id)
            if intent is not None and intent.is_pick():
                # Only claim items not yet in inventory
                remaining = list(intent.pickups)
                for item in bot.inventory:
                    if item in remaining:
                        remaining.remove(item)
                claimed_pickups.extend(remaining)
        tasks = self._assigner.assign(state, snapshot, planner, claimed=claimed_pickups)

        for bot in bots:
            if self._intents.get(bot.id) is not None:
                continue

            task = tasks.get(bot.id, AssignedTask(bot.id, "wait"))

            if task.kind == "drop_off":
                self._intents.set(bot.id, BotIntent(
                    kind="deliver",
                    target=state.drop_off,
                    order_id=snapshot.active_order_id,
                ))
            elif task.kind == "pick" and task.pickups:
                self._intents.set(bot.id, BotIntent(
                    kind="pick",
                    pickups=task.pickups,
                    order_id=snapshot.active_order_id,
                ))
            else:
                # Idle → park. Full stale inventory parks far, others near.
                occupied = frozenset(b.position for b in bots if b.id != bot.id)
                is_stale = len(bot.inventory) >= 3
                park_cell = parking.best_park(bot.position, occupied, far=is_stale)
                if park_cell is not None:
                    self._intents.set(bot.id, BotIntent(
                        kind="park",
                        target=park_cell,
                        order_id=snapshot.active_order_id,
                    ))
                else:
                    self._intents.set(bot.id, BotIntent(kind="idle"))

        # --- Phase 3: Generate actions from intents ---
        delivery_bots = {
            bot.id for bot in bots
            if (self._intents.get(bot.id) or BotIntent(kind="idle")).is_deliver()
        }

        proposed: dict[int, BotAction] = {}
        for bot in bots:
            intent = self._intents.get(bot.id)
            if intent is None:
                proposed[bot.id] = WaitAction(bot=bot.id)
                continue

            # Don't block pathfinding on other bot positions — the collision
            # resolver handles contention. Blocking here causes oscillation
            # in narrow corridors when the blocked set flip-flops each tick.
            no_blocked: frozenset[Position] = frozenset()

            action: BotAction = WaitAction(bot=bot.id)

            if intent.is_pick():
                result = planner.next_pick_action(
                    state,
                    bot_id=bot.id,
                    pos=bot.position,
                    pickups=intent.pickups,
                    blocked=no_blocked,
                )
                if result is not None:
                    action = result

            elif intent.is_deliver():
                action = planner.go_drop_off(
                    bot.id, bot.position, blocked=no_blocked,
                )

            elif intent.is_park() and intent.target is not None:
                if bot.position != intent.target:
                    path = astar(
                        bot.position, intent.target, grid, blocked=no_blocked,
                    )
                    if path and len(path) > 1:
                        action = MoveAction(
                            bot=bot.id,
                            action=direction_for_move(bot.position, path[1]),
                        )

            # Drop-off area clearing: non-delivery bots near drop-off move away
            next_pos = next_position_for_action(bot.position, action)
            dist_to_drop = _manhattan(bot.position, state.drop_off)
            is_blocker = (
                bot.id not in delivery_bots
                and bool(delivery_bots)
                and (
                    dist_to_drop == 0  # always vacate the drop-off cell
                    or (
                        dist_to_drop <= 1
                        and (isinstance(action, WaitAction) or next_pos == state.drop_off)
                    )
                )
            )
            if is_blocker:
                other_positions = frozenset(
                    b.position for b in bots if b.id != bot.id
                )
                step = self._move_away_from_dropoff(
                    bot.id,
                    bot.position,
                    state.drop_off,
                    other_positions,
                    min_distance=1 if bot.position == state.drop_off else 2,
                )
                if step is not None:
                    action = step

            # Anti-stall nudge: if stuck on a task for too long, step aside
            if (
                isinstance(action, WaitAction)
                and intent.kind in {"pick", "deliver"}
                and intent.blocked_ticks >= 3
            ):
                other_positions = frozenset(
                    b.position for b in bots if b.id != bot.id
                )
                nudge = self._step_to_free_neighbor(
                    bot.id, bot.position, other_positions,
                )
                if nudge is not None:
                    action = nudge

            proposed[bot.id] = action

        resolved = self._resolver.resolve(
            state, proposed, priority_bots=delivery_bots,
        )
        self._last_positions = current_positions
        return resolved

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
