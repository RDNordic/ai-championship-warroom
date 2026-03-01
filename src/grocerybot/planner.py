"""Milestone 3 planner utilities for multi-bot coordination.

Includes:
- OrderTracker: active/preview remaining needs with inventory accounting
- LocalTripPlanner: exact short-horizon pickup trip planning
- TaskAssigner: greedy sequential assignment in bot-id order
- CollisionResolver: single-step collision safety in bot-id order
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import cache
from itertools import combinations
from typing import Literal

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
    Order,
    PickUpAction,
    WaitAction,
)

Position = tuple[int, int]
TaskKind = Literal["pick", "drop_off", "wait"]

INF = 999_999
PREVIEW_DETOUR_BUDGET = 2


@dataclass(frozen=True)
class OrderSnapshot:
    active_order_id: str
    active_needed: list[str]
    preview_needed: list[str]


@dataclass(frozen=True)
class AssignedTask:
    bot_id: int
    kind: TaskKind
    pickups: tuple[str, ...] = ()


def _get_order_by_status(state: GameState, status: str) -> Order | None:
    for order in state.orders:
        if order.status == status:
            return order
    return None


def _remaining_for_order(order: Order) -> list[str]:
    needed = list(order.items_required)
    for delivered in order.items_delivered:
        if delivered in needed:
            needed.remove(delivered)
    return needed


def _consume_pool(
    needed: list[str],
    pool: list[str],
) -> tuple[list[str], list[str]]:
    """Consume pool items against needed multiset.

    Returns:
      remaining_needed, leftover_pool
    """
    remaining = list(needed)
    leftover = list(pool)
    for item in pool:
        if item in remaining:
            remaining.remove(item)
            leftover.remove(item)
    return remaining, leftover


def _remove_one(items: tuple[str, ...], item: str) -> tuple[str, ...]:
    idx = items.index(item)
    return items[:idx] + items[idx + 1:]


def _pick_multiset_combinations(
    items: list[str],
    k: int,
) -> set[tuple[str, ...]]:
    if k <= 0:
        return {()}
    if k > len(items):
        return set()
    result: set[tuple[str, ...]] = set()
    for idxs in combinations(range(len(items)), k):
        result.add(tuple(sorted(items[i] for i in idxs)))
    return result


def _consume_needed(
    needed: list[str],
    picked: tuple[str, ...],
) -> tuple[int, list[str], list[str]]:
    remaining = list(needed)
    excess: list[str] = []
    matched = 0
    for item in picked:
        if item in remaining:
            remaining.remove(item)
            matched += 1
        else:
            excess.append(item)
    return matched, remaining, excess


def next_position_for_action(pos: Position, action: BotAction) -> Position:
    """Return position after applying one action."""
    if not isinstance(action, MoveAction):
        return pos
    x, y = pos
    if action.action == "move_up":
        return (x, y - 1)
    if action.action == "move_down":
        return (x, y + 1)
    if action.action == "move_left":
        return (x - 1, y)
    return (x + 1, y)


class OrderTracker:
    """Compute active/preview needed item lists with inventory accounting."""

    def snapshot(self, state: GameState) -> OrderSnapshot | None:
        active = _get_order_by_status(state, "active")
        if active is None:
            return None
        preview = _get_order_by_status(state, "preview")

        # M3 baseline: track outstanding order state from server-delivered items.
        # Inventory handling is done explicitly in TaskAssigner per-bot.
        active_remaining = _remaining_for_order(active)
        preview_remaining = _remaining_for_order(preview) if preview is not None else []

        return OrderSnapshot(
            active_order_id=active.id,
            active_needed=active_remaining,
            preview_needed=preview_remaining,
        )


class LocalTripPlanner:
    """Exact short-horizon route planner for a single bot."""

    def __init__(self, state: GameState, grid: PassableGrid) -> None:
        self._grid = grid
        self._drop_off = state.drop_off
        self._dropoff_dist = bfs_distance_map(state.drop_off, grid)
        self._type_to_adjs = self._build_type_to_adjs(state)
        self._dist_cache: dict[Position, dict[Position, int]] = {}

    def _build_type_to_adjs(self, state: GameState) -> dict[str, list[Position]]:
        by_type: dict[str, set[Position]] = {}
        for item in state.items:
            for adj in adjacent_walkable(item.position, self._grid):
                by_type.setdefault(item.type, set()).add(adj)
        return {t: sorted(adjs) for t, adjs in by_type.items()}

    def plan_trip(
        self,
        pos: Position,
        inventory: list[str],
        needed_active: list[str],
        needed_preview: list[str],
    ) -> tuple[str, ...]:
        space = 3 - len(inventory)
        if space <= 0:
            return ()

        candidates = self._generate_trip_candidates(
            space=space,
            needed_active=needed_active,
            needed_preview=needed_preview,
        )
        if not candidates:
            return ()
        if needed_active:
            return self._choose_best_active(pos, candidates, needed_active, needed_preview)
        return self._choose_best_preview(pos, candidates, needed_preview)

    def _generate_trip_candidates(
        self,
        space: int,
        needed_active: list[str],
        needed_preview: list[str],
    ) -> set[tuple[str, ...]]:
        if needed_active:
            if len(needed_active) >= space:
                return _pick_multiset_combinations(needed_active, space)
            base = tuple(sorted(needed_active))
            active_candidates: set[tuple[str, ...]] = {base}
            for k in range(1, space - len(needed_active) + 1):
                for combo in _pick_multiset_combinations(needed_preview, k):
                    active_candidates.add(tuple(sorted(base + combo)))
            return active_candidates

        preview_candidates: set[tuple[str, ...]] = {()}
        for k in range(1, space + 1):
            preview_candidates.update(_pick_multiset_combinations(needed_preview, k))
        return preview_candidates

    def _choose_best_active(
        self,
        pos: Position,
        candidates: set[tuple[str, ...]],
        needed_active: list[str],
        needed_preview: list[str],
    ) -> tuple[str, ...]:
        best: tuple[str, ...] = ()
        best_key: tuple[int, int, int] | None = None
        for cand in sorted(candidates):
            route_cost, _, _ = self._best_route_for_pickups(pos, cand)
            if route_cost >= INF:
                continue
            active_matched, active_remaining, excess = _consume_needed(needed_active, cand)
            preview_matched = 0
            if not active_remaining and excess:
                preview_matched, _, _ = _consume_needed(needed_preview, tuple(excess))
            score_est = active_matched + preview_matched + (5 if not active_remaining else 0)
            if score_est <= 0:
                continue
            key = ((score_est * 1000) // route_cost, score_est, -route_cost)
            if best_key is None or key > best_key:
                best_key = key
                best = cand
        return best

    def _choose_best_preview(
        self,
        pos: Position,
        candidates: set[tuple[str, ...]],
        needed_preview: list[str],
    ) -> tuple[str, ...]:
        direct = self._dropoff_dist.get(pos, INF)
        if direct >= INF:
            return ()
        direct_cost = direct + 1
        best: tuple[str, ...] = ()
        best_key: tuple[int, int, int] | None = None
        for cand in sorted(candidates):
            if not cand:
                continue
            route_cost, _, _ = self._best_route_for_pickups(pos, cand)
            if route_cost >= INF:
                continue
            matched, _, _ = _consume_needed(needed_preview, cand)
            if matched <= 0:
                continue
            extra_cost = route_cost - direct_cost
            if extra_cost > PREVIEW_DETOUR_BUDGET + matched:
                continue
            key = ((matched * 1000) // max(extra_cost, 1), matched, -extra_cost)
            if best_key is None or key > best_key:
                best_key = key
                best = cand
        return best

    def _best_route_for_pickups(
        self,
        start: Position,
        pickups: tuple[str, ...],
    ) -> tuple[int, str | None, Position | None]:
        remaining = tuple(sorted(pickups))
        if not remaining:
            d = self._dropoff_dist.get(start, INF)
            return (d + 1, None, None) if d < INF else (INF, None, None)

        @cache
        def tail_cost(current: Position, rem: tuple[str, ...]) -> int:
            if not rem:
                d_drop = self._dropoff_dist.get(current, INF)
                return d_drop + 1 if d_drop < INF else INF
            best = INF
            seen_types: set[str] = set()
            for item_type in rem:
                if item_type in seen_types:
                    continue
                seen_types.add(item_type)
                next_rem = _remove_one(rem, item_type)
                for adj in self._type_to_adjs.get(item_type, []):
                    d = self._cached_dist(adj, current)
                    if d >= INF:
                        continue
                    rest = tail_cost(adj, next_rem)
                    if rest < INF:
                        best = min(best, d + 1 + rest)
            return best

        best_total = INF
        best_first_type: str | None = None
        best_first_adj: Position | None = None
        seen_types: set[str] = set()
        for item_type in remaining:
            if item_type in seen_types:
                continue
            seen_types.add(item_type)
            next_rem = _remove_one(remaining, item_type)
            for adj in self._type_to_adjs.get(item_type, []):
                d = self._cached_dist(adj, start)
                rest = tail_cost(adj, next_rem) if d < INF else INF
                if rest >= INF:
                    continue
                total = d + 1 + rest
                if total < best_total:
                    best_total = total
                    best_first_type = item_type
                    best_first_adj = adj
        return best_total, best_first_type, best_first_adj

    def next_pick_action(
        self,
        state: GameState,
        bot_id: int,
        pos: Position,
        pickups: tuple[str, ...],
        blocked: frozenset[Position] = frozenset(),
    ) -> BotAction | None:
        _, item_type, target = self._best_route_for_pickups(pos, pickups)
        if item_type is None:
            return None
        candidates = [target] if target is not None else []
        for adj in self._type_to_adjs.get(item_type, []):
            if adj not in candidates:
                candidates.append(adj)
        for tgt in candidates:
            if tgt is None:
                continue
            if pos == tgt:
                item_id = self._pick_item_id_for_type(state, pos, item_type)
                if item_id is not None:
                    return PickUpAction(bot=bot_id, action="pick_up", item_id=item_id)
                continue
            path = astar(pos, tgt, self._grid, blocked=blocked)
            if path and len(path) > 1:
                return MoveAction(
                    bot=bot_id, action=direction_for_move(pos, path[1]),
                )
        return None

    def go_drop_off(
        self,
        bot_id: int,
        pos: Position,
        blocked: frozenset[Position] = frozenset(),
    ) -> BotAction:
        if pos == self._drop_off:
            return DropOffAction(bot=bot_id, action="drop_off")
        path = astar(pos, self._drop_off, self._grid, blocked=blocked)
        if path and len(path) > 1:
            return MoveAction(bot=bot_id, action=direction_for_move(pos, path[1]))
        return WaitAction(bot=bot_id)

    def _pick_item_id_for_type(
        self,
        state: GameState,
        pos: Position,
        item_type: str,
    ) -> str | None:
        candidates = [
            item.id for item in state.items
            if item.type == item_type and pos in adjacent_walkable(item.position, self._grid)
        ]
        return sorted(candidates)[0] if candidates else None

    def _cached_dist(self, goal: Position, start: Position) -> int:
        if goal not in self._dist_cache:
            self._dist_cache[goal] = bfs_distance_map(goal, self._grid)
        return self._dist_cache[goal].get(start, INF)


class TaskAssigner:
    """Two-phase assignment: delivery-first, then pickups."""

    def assign(
        self,
        state: GameState,
        snapshot: OrderSnapshot,
        planner: LocalTripPlanner,
    ) -> dict[int, AssignedTask]:
        tasks: dict[int, AssignedTask] = {}
        remaining_active = list(snapshot.active_needed)
        bots = sorted(state.bots, key=lambda b: b.id)

        # Phase A: bots carrying active items → drop_off
        for bot in bots:
            matched, rem, _ = _consume_needed(
                remaining_active, tuple(bot.inventory),
            )
            if matched > 0:
                tasks[bot.id] = AssignedTask(bot.id, "drop_off")
                remaining_active = rem

        # Phase B: unassigned bots → pickup or wait
        for bot in bots:
            if bot.id in tasks:
                continue
            if len(bot.inventory) >= 3:
                tasks[bot.id] = AssignedTask(bot.id, "wait")
                continue
            if remaining_active:
                picks = planner.plan_trip(
                    bot.position, bot.inventory, remaining_active, [],
                )
                if picks:
                    tasks[bot.id] = AssignedTask(bot.id, "pick", picks)
                    _, remaining_active, _ = _consume_needed(remaining_active, picks)
                    continue
            tasks[bot.id] = AssignedTask(bot.id, "wait")

        return tasks


class CollisionResolver:
    """Single-step collision resolver mirroring server id-order semantics."""

    def resolve(
        self,
        state: GameState,
        proposed: dict[int, BotAction],
    ) -> list[BotAction]:
        spawn = (state.grid.width - 2, state.grid.height - 2)
        positions: dict[int, Position] = {
            bot.id: bot.position for bot in state.bots
        }
        final_actions: list[BotAction] = []
        for bot in sorted(state.bots, key=lambda b: b.id):
            action = proposed.get(bot.id, WaitAction(bot=bot.id))
            current_pos = positions[bot.id]
            next_pos = next_position_for_action(current_pos, action)

            occupied_by_other = {
                pos for other_id, pos in positions.items()
                if other_id != bot.id
            }
            if next_pos != spawn and next_pos in occupied_by_other:
                action = WaitAction(bot=bot.id)
                next_pos = current_pos

            positions[bot.id] = next_pos
            final_actions.append(action)
        return final_actions
