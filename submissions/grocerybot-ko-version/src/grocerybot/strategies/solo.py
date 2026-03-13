"""Milestone 2: Solo bot strategy for Easy maps (single bot).

Logic per round:
1. Inventory full OR all needed items collected? → go to drop-off → drop_off
2. Still need items for active order? → A* to nearest needed → move/pick_up
3. Have any items? → go deliver what we have
4. Else → wait
"""

from __future__ import annotations

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
    GameState,
    MoveAction,
    PickUpAction,
    WaitAction,
)
from grocerybot.strategies.base import Strategy

Position = tuple[int, int]


def _find_active_order_needed(state: GameState, inventory: list[str]) -> list[str]:
    """Compute items still needed for the active order, accounting for inventory."""
    active = None
    for order in state.orders:
        if order.status == "active":
            active = order
            break
    if active is None:
        return []

    needed = list(active.items_required)
    for delivered in active.items_delivered:
        if delivered in needed:
            needed.remove(delivered)
    for inv_item in inventory:
        if inv_item in needed:
            needed.remove(inv_item)
    return needed


class SoloStrategy(Strategy):
    """Single-bot A* pathfinding strategy for Easy difficulty."""

    def __init__(self) -> None:
        self._grid: PassableGrid | None = None
        self._dropoff_dist: dict[Position, int] = {}

    def on_game_start(self, state: GameState) -> None:
        self._grid = PassableGrid(state)
        self._dropoff_dist = bfs_distance_map(state.drop_off, self._grid)

    def decide(self, state: GameState) -> list[BotAction]:
        grid = self._grid
        assert grid is not None, "on_game_start must be called before decide"

        bot = state.bots[0]
        pos = bot.position
        inventory = bot.inventory
        needed = _find_active_order_needed(state, inventory)

        # Phase 1: Inventory full → must deliver
        if len(inventory) >= 3:
            return [self._go_drop_off(bot.id, pos, state.drop_off, grid)]

        # Phase 2: All needed items collected (nothing left to pick) → deliver
        if not needed and inventory:
            return [self._go_drop_off(bot.id, pos, state.drop_off, grid)]

        # Phase 3: Still need items → go pick one up
        if needed and len(inventory) < 3:
            action = self._go_pick_item(
                state, bot.id, pos, set(needed), grid,
            )
            if action is not None:
                return [action]

        # Phase 4: Have items but couldn't find needed on map → deliver anyway
        if inventory:
            return [self._go_drop_off(bot.id, pos, state.drop_off, grid)]

        return [WaitAction(bot=bot.id)]

    def _go_drop_off(
        self,
        bot_id: int,
        pos: Position,
        drop_off: Position,
        grid: PassableGrid,
    ) -> BotAction:
        """Navigate to drop-off and deliver."""
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
        needed_types: set[str],
        grid: PassableGrid,
    ) -> BotAction | None:
        """Navigate to the nearest needed item and pick it up."""
        candidates: list[tuple[int, str, Position, list[Position]]] = []
        for item in state.items:
            if item.type not in needed_types:
                continue
            adj = adjacent_walkable(item.position, grid)
            if not adj:
                continue
            for a in adj:
                path = astar(pos, a, grid)
                if path:
                    candidates.append((len(path), item.id, a, path))

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
