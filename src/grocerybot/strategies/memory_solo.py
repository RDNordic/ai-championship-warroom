"""Memory-enhanced solo bot strategy.

First run of the day: discovery mode (behaves like solo.py, saves order history).
Subsequent runs: optimized mode (pre-planned routes, batch pickups, preview pre-pick).
"""

from __future__ import annotations

from grocerybot.daily_memory import (
    DailySnapshot,
    OrderRecord,
    build_snapshot_from_state,
    get_item_positions,
    load_snapshot,
    merge_orders,
    save_snapshot,
)
from grocerybot.grid import (
    PassableGrid,
    adjacent_walkable,
    astar,
    bfs_distance_map,
    direction_for_move,
)
from grocerybot.models import (
    BotAction,
    DropOffAction,
    GameOver,
    GameState,
    MoveAction,
    Order,
    PickUpAction,
    WaitAction,
)
from grocerybot.strategies.base import Strategy

Position = tuple[int, int]


def _remaining_needed(order: Order, inventory: list[str]) -> list[str]:
    """Items still needed for an order, accounting for delivered + inventory."""
    needed = list(order.items_required)
    for delivered in order.items_delivered:
        if delivered in needed:
            needed.remove(delivered)
    for inv_item in inventory:
        if inv_item in needed:
            needed.remove(inv_item)
    return needed


def _get_active_order(state: GameState) -> Order | None:
    for order in state.orders:
        if order.status == "active":
            return order
    return None


def _get_preview_order(state: GameState) -> Order | None:
    for order in state.orders:
        if order.status == "preview":
            return order
    return None


class MemorySoloStrategy(Strategy):
    """Single-bot strategy with daily memory for route optimization."""

    def __init__(self, level: str = "easy") -> None:
        self._level = level
        self._grid: PassableGrid | None = None
        self._dropoff_dist: dict[Position, int] = {}
        self._snap: DailySnapshot | None = None
        self._seen_orders: list[OrderRecord] = []
        self._has_memory = False
        self._dist_cache: dict[Position, dict[Position, int]] = {}

    def on_game_start(self, state: GameState) -> None:
        self._grid = PassableGrid(state)
        self._dropoff_dist = bfs_distance_map(state.drop_off, self._grid)

        snap = load_snapshot(self._level)
        if snap is not None:
            self._snap = snap
            self._has_memory = True
        else:
            self._snap = build_snapshot_from_state(state, self._level)
            self._has_memory = False

        self._accumulate_orders(state)

    def on_game_over(self, result: GameOver) -> None:
        if self._snap is not None:
            updated = merge_orders(self._snap, self._seen_orders)
            save_snapshot(updated)

    def decide(self, state: GameState) -> list[BotAction]:
        grid = self._grid
        assert grid is not None

        self._accumulate_orders(state)

        bot = state.bots[0]
        pos = bot.position
        inventory = bot.inventory

        active = _get_active_order(state)
        if active is None:
            return [WaitAction(bot=bot.id)]

        needed_active = _remaining_needed(active, inventory)
        preview = _get_preview_order(state)
        needed_preview = _remaining_needed(preview, inventory) if preview else []

        # Phase 1: Inventory full → deliver
        if len(inventory) >= 3:
            return [self._go_drop_off(bot.id, pos, state.drop_off, grid)]

        # Phase 2: All active items collected → deliver
        # On the way, opportunistically grab adjacent preview items
        if not needed_active and inventory:
            if needed_preview and len(inventory) < 3:
                opp = self._opportunistic_pick(
                    state, bot.id, pos, needed_preview, grid,
                )
                if opp is not None:
                    return [opp]
            return [self._go_drop_off(bot.id, pos, state.drop_off, grid)]

        # Phase 3: Plan what to pick up this trip
        trip = self._plan_trip(
            pos, inventory, needed_active, needed_preview, grid,
        )
        if trip:
            action = self._go_pick_item(state, bot.id, pos, trip, grid)
            if action is not None:
                return [action]

        # Phase 4: Have items but can't find more → deliver
        if inventory:
            return [self._go_drop_off(bot.id, pos, state.drop_off, grid)]

        return [WaitAction(bot=bot.id)]

    # ------------------------------------------------------------------
    # Accumulate orders for memory
    # ------------------------------------------------------------------

    def _accumulate_orders(self, state: GameState) -> None:
        existing_ids = {o.id for o in self._seen_orders}
        for order in state.orders:
            if order.id not in existing_ids:
                self._seen_orders.append(
                    OrderRecord(
                        id=order.id,
                        items_required=list(order.items_required),
                    ),
                )

    # ------------------------------------------------------------------
    # Trip planning
    # ------------------------------------------------------------------

    def _plan_trip(
        self,
        pos: Position,
        inventory: list[str],
        needed_active: list[str],
        needed_preview: list[str],
        grid: PassableGrid,
    ) -> set[str]:
        """Decide item types to collect this trip. Active first, then preview."""
        space = 3 - len(inventory)
        if space <= 0:
            return set()

        # Order active items by nearest-neighbor from current position
        ordered = self._nearest_neighbor_order(pos, needed_active, grid)
        trip = ordered[:space]

        # Fill remaining space with preview items
        remaining_space = space - len(trip)
        if remaining_space > 0 and needed_preview:
            preview_ordered = self._nearest_neighbor_order(
                pos, needed_preview, grid,
            )
            trip.extend(preview_ordered[:remaining_space])

        return set(trip)

    def _nearest_neighbor_order(
        self,
        start: Position,
        item_types: list[str],
        grid: PassableGrid,
    ) -> list[str]:
        """Reorder item types by nearest-neighbor greedy from start."""
        if not item_types:
            return []

        remaining = list(item_types)
        result: list[str] = []
        current = start

        while remaining:
            best_type: str | None = None
            best_dist = 999999
            best_adj: Position | None = None

            for itype in remaining:
                adj_pos = self._find_nearest_shelf_adj(
                    current, itype, grid,
                )
                if adj_pos is None:
                    continue
                dist = self._cached_dist(adj_pos, current, grid)
                if dist < best_dist:
                    best_dist = dist
                    best_type = itype
                    best_adj = adj_pos

            if best_type is None:
                break
            result.append(best_type)
            remaining.remove(best_type)
            if best_adj is not None:
                current = best_adj

        return result

    def _find_nearest_shelf_adj(
        self,
        from_pos: Position,
        item_type: str,
        grid: PassableGrid,
    ) -> Position | None:
        """Find the nearest walkable cell adjacent to any shelf of item_type."""
        if self._snap is None:
            return None

        positions = get_item_positions(self._snap, item_type)
        best_adj: Position | None = None
        best_dist = 999999

        for shelf_pos in positions:
            for adj in adjacent_walkable(shelf_pos, grid):
                d = self._cached_dist(adj, from_pos, grid)
                if d < best_dist:
                    best_dist = d
                    best_adj = adj
        return best_adj

    def _cached_dist(
        self, goal: Position, start: Position, grid: PassableGrid,
    ) -> int:
        """BFS distance from start to goal, with caching."""
        if goal not in self._dist_cache:
            self._dist_cache[goal] = bfs_distance_map(goal, grid)
        return self._dist_cache[goal].get(start, 999999)

    # ------------------------------------------------------------------
    # Navigation actions
    # ------------------------------------------------------------------

    def _go_drop_off(
        self,
        bot_id: int,
        pos: Position,
        drop_off: Position,
        grid: PassableGrid,
    ) -> BotAction:
        if pos == drop_off:
            return DropOffAction(bot=bot_id, action="drop_off")
        path = astar(pos, drop_off, grid)
        if path and len(path) > 1:
            return MoveAction(
                bot=bot_id, action=direction_for_move(pos, path[1]),
            )
        return WaitAction(bot=bot_id)

    def _go_pick_item(
        self,
        state: GameState,
        bot_id: int,
        pos: Position,
        wanted_types: set[str],
        grid: PassableGrid,
    ) -> BotAction | None:
        """Navigate to the nearest item of any wanted type and pick it up."""
        candidates: list[tuple[int, str, Position, list[Position]]] = []
        for item in state.items:
            if item.type not in wanted_types:
                continue
            for adj in adjacent_walkable(item.position, grid):
                path = astar(pos, adj, grid)
                if path:
                    candidates.append((len(path), item.id, adj, path))

        if not candidates:
            return None

        candidates.sort()
        _, item_id, target, path = candidates[0]

        if pos == target:
            return PickUpAction(bot=bot_id, action="pick_up", item_id=item_id)
        if len(path) > 1:
            return MoveAction(
                bot=bot_id, action=direction_for_move(pos, path[1]),
            )
        return None

    def _opportunistic_pick(
        self,
        state: GameState,
        bot_id: int,
        pos: Position,
        needed_preview: list[str],
        grid: PassableGrid,
    ) -> BotAction | None:
        """Grab a preview item only if we're already adjacent to its shelf."""
        needed_set = set(needed_preview)
        for item in state.items:
            if item.type not in needed_set:
                continue
            adj = adjacent_walkable(item.position, grid)
            if pos in adj:
                return PickUpAction(
                    bot=bot_id, action="pick_up", item_id=item.id,
                )
        return None
