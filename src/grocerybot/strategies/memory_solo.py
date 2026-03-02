"""Memory-enhanced solo bot strategy.

First run of the day: discovery mode (behaves like solo.py, saves order history).
Subsequent runs: optimized mode (uses memory for next-order prediction).
"""

from __future__ import annotations

from functools import cache
from itertools import combinations

from grocerybot.daily_memory import (
    DailySnapshot,
    OrderRecord,
    build_snapshot_from_state,
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
PREVIEW_DETOUR_BUDGET = 2
INF = 999999


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


def _remove_one(items: tuple[str, ...], item: str) -> tuple[str, ...]:
    idx = items.index(item)
    return items[:idx] + items[idx + 1:]


def _pick_multiset_combinations(
    items: list[str],
    k: int,
) -> set[tuple[str, ...]]:
    """Unique k-sized multiset combinations from a list with duplicates."""
    if k <= 0:
        return {()}
    if k > len(items):
        return set()
    result: set[tuple[str, ...]] = set()
    for idxs in combinations(range(len(items)), k):
        combo = tuple(sorted(items[i] for i in idxs))
        result.add(combo)
    return result


def _consume_needed(
    needed: list[str],
    picked: tuple[str, ...],
) -> tuple[int, list[str], list[str]]:
    """Consume picked items against needed multiset.

    Returns:
      matched_count, remaining_needed, picked_excess
    """
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


class MemorySoloStrategy(Strategy):
    """Single-bot strategy with memory + exact short-horizon trip planning."""

    def __init__(self, level: str = "easy") -> None:
        self._level = level
        self._grid: PassableGrid | None = None
        self._drop_off: Position = (0, 0)
        self._dropoff_dist: dict[Position, int] = {}
        self._type_to_adjs: dict[str, list[Position]] = {}

        self._snap: DailySnapshot | None = None
        self._seen_orders: list[OrderRecord] = []
        self._has_memory = False
        self._order_id_to_idx: dict[str, int] = {}

        self._dist_cache: dict[Position, dict[Position, int]] = {}

    def on_game_start(self, state: GameState) -> None:
        self._grid = PassableGrid(state)
        self._drop_off = state.drop_off
        self._dropoff_dist = bfs_distance_map(state.drop_off, self._grid)
        self._type_to_adjs = self._build_type_to_adjs(state, self._grid)

        snap = load_snapshot(self._level)
        if snap is not None:
            self._snap = snap
            self._has_memory = True
            self._order_id_to_idx = {
                o.id: i for i, o in enumerate(snap.orders)
            }
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
        self._type_to_adjs = self._build_type_to_adjs(state, grid)

        bot = state.bots[0]
        pos = bot.position
        inventory = bot.inventory

        active = _get_active_order(state)
        if active is None:
            return [WaitAction(bot=bot.id)]

        needed_active = _remaining_needed(active, inventory)
        rounds_left = state.max_rounds - state.round
        preview = _get_preview_order(state)
        if rounds_left > 25:
            needed_preview = _remaining_needed(preview, inventory) if preview else []
            if not needed_preview and self._has_memory:
                needed_preview = self._get_next_order_items(active, inventory)
        else:
            needed_preview = []

        # Inventory hard-cap always forces delivery.
        if len(inventory) >= 3:
            return [self._go_drop_off(bot.id, pos, state.drop_off, grid)]

        # Exact trip planner: choose best pickup multiset, then execute first step.
        trip = self._plan_trip(
            pos,
            inventory,
            needed_active,
            needed_preview,
            grid,
        )
        if trip:
            action = self._go_pick_planned_item(
                state,
                bot.id,
                pos,
                trip,
                grid,
            )
            if action is not None:
                return [action]

        if inventory:
            return [self._go_drop_off(bot.id, pos, state.drop_off, grid)]

        return [WaitAction(bot=bot.id)]

    def _build_type_to_adjs(
        self,
        state: GameState,
        grid: PassableGrid,
    ) -> dict[str, list[Position]]:
        """Precompute all walkable pickup cells per item type."""
        per_type: dict[str, set[Position]] = {}
        for item in state.items:
            for adj in adjacent_walkable(item.position, grid):
                per_type.setdefault(item.type, set()).add(adj)
        return {
            item_type: sorted(adjs)
            for item_type, adjs in per_type.items()
        }

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
    # Memory-based next-order prediction
    # ------------------------------------------------------------------

    def _get_next_order_items(
        self,
        active: Order,
        inventory: list[str],
    ) -> list[str]:
        """Predict items for the next order (preview) from memory."""
        if self._snap is None:
            return []

        active_idx = self._order_id_to_idx.get(active.id)
        if active_idx is None:
            return []

        next_idx = active_idx + 1
        orders = self._snap.orders
        if next_idx >= len(orders):
            return []

        next_items = list(orders[next_idx].items_required)
        for inv_item in inventory:
            if inv_item in next_items:
                next_items.remove(inv_item)
        return next_items

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
    ) -> tuple[str, ...]:
        """Choose pickup multiset using exact route costs (not nearest-first)."""
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
            if len(needed_active) > space:
                return self._choose_best_two_trip_candidate(
                    pos=pos,
                    candidates=candidates,
                    needed_active=needed_active,
                    needed_preview=needed_preview,
                    grid=grid,
                )
            return self._choose_best_active_candidate(
                pos=pos,
                candidates=candidates,
                needed_active=needed_active,
                needed_preview=needed_preview,
                grid=grid,
            )
        return self._choose_best_preview_candidate(
            pos=pos,
            candidates=candidates,
            needed_preview=needed_preview,
            grid=grid,
        )

    def _generate_trip_candidates(
        self,
        space: int,
        needed_active: list[str],
        needed_preview: list[str],
    ) -> set[tuple[str, ...]]:
        """Generate feasible pickup multisets for this trip."""
        if space <= 0:
            return set()

        candidates: set[tuple[str, ...]] = set()

        if needed_active:
            # Active doesn't fit in this trip: choose best subset of size=space.
            if len(needed_active) >= space:
                return _pick_multiset_combinations(needed_active, space)

            # Active fits: include all active, optionally fill with preview.
            base = tuple(sorted(needed_active))
            candidates.add(base)
            remaining_space = space - len(needed_active)
            for k in range(1, remaining_space + 1):
                for preview_combo in _pick_multiset_combinations(
                    needed_preview, k,
                ):
                    candidates.add(tuple(sorted(base + preview_combo)))
            return candidates

        # Active already satisfied by inventory: optional preview detour.
        candidates.add(())
        for k in range(1, space + 1):
            candidates.update(
                _pick_multiset_combinations(needed_preview, k),
            )
        return candidates

    def _choose_best_active_candidate(
        self,
        pos: Position,
        candidates: set[tuple[str, ...]],
        needed_active: list[str],
        needed_preview: list[str],
        grid: PassableGrid,
    ) -> tuple[str, ...]:
        """Choose active-focused trip by score efficiency per action."""
        best: tuple[str, ...] = ()
        best_key: tuple[int, int, int] | None = None

        for cand in sorted(candidates):
            route_cost, _, _ = self._best_route_for_pickups(pos, cand, grid)
            if route_cost >= INF:
                continue

            active_matched, active_remaining, excess = _consume_needed(
                needed_active,
                cand,
            )
            active_complete = not active_remaining

            preview_matched = 0
            if active_complete and excess:
                preview_matched, _, _ = _consume_needed(
                    needed_preview,
                    tuple(excess),
                )

            score_est = active_matched + preview_matched
            if active_complete:
                score_est += 5
            if score_est <= 0:
                continue

            # Higher is better: score per route action, then raw score, then lower cost.
            eff = (score_est * 1000) // route_cost
            key = (eff, score_est, -route_cost)
            if best_key is None or key > best_key:
                best_key = key
                best = cand

        return best

    def _choose_best_two_trip_candidate(
        self,
        pos: Position,
        candidates: set[tuple[str, ...]],
        needed_active: list[str],
        needed_preview: list[str],
        grid: PassableGrid,
    ) -> tuple[str, ...]:
        """Choose trip-1 items by minimizing total cost across 2 trips."""
        drop_off = self._drop_off
        best: tuple[str, ...] = ()
        best_total = INF
        best_trip1 = INF

        for cand in sorted(candidates):
            trip1_cost, _, _ = self._best_route_for_pickups(pos, cand, grid)
            if trip1_cost >= INF:
                continue

            _, remaining_active, _ = _consume_needed(needed_active, cand)
            if not remaining_active:
                continue

            remaining_tuple = tuple(sorted(remaining_active))
            best_trip2, _, _ = self._best_route_for_pickups(
                drop_off, remaining_tuple, grid,
            )
            if best_trip2 >= INF:
                continue

            total = trip1_cost + best_trip2
            if total < best_total or (
                total == best_total and trip1_cost < best_trip1
            ):
                best_total = total
                best_trip1 = trip1_cost
                best = cand

        if not best:
            return self._choose_best_active_candidate(
                pos=pos, candidates=candidates,
                needed_active=needed_active,
                needed_preview=needed_preview, grid=grid,
            )
        return best

    def _choose_best_preview_candidate(
        self,
        pos: Position,
        candidates: set[tuple[str, ...]],
        needed_preview: list[str],
        grid: PassableGrid,
    ) -> tuple[str, ...]:
        """Choose preview detours only when extra travel is bounded."""
        direct_to_drop = self._dropoff_dist.get(pos, INF)
        if direct_to_drop >= INF:
            return ()
        direct_cost = direct_to_drop + 1

        best: tuple[str, ...] = ()
        best_key: tuple[int, int, int] | None = None

        for cand in sorted(candidates):
            if not cand:
                continue

            route_cost, _, _ = self._best_route_for_pickups(pos, cand, grid)
            if route_cost >= INF:
                continue

            preview_matched, _, _ = _consume_needed(needed_preview, cand)
            if preview_matched <= 0:
                continue

            extra_cost = route_cost - direct_cost
            if extra_cost > PREVIEW_DETOUR_BUDGET + preview_matched:
                continue

            eff = (preview_matched * 1000) // max(extra_cost, 1)
            key = (eff, preview_matched, -extra_cost)
            if best_key is None or key > best_key:
                best_key = key
                best = cand

        return best

    def _best_route_for_pickups(
        self,
        start: Position,
        pickups: tuple[str, ...],
        grid: PassableGrid,
    ) -> tuple[int, str | None, Position | None]:
        """Exact shortest route cost for `start -> pickups -> drop_off`.

        Returns:
          (total_cost, first_item_type, first_pick_position)
        """
        remaining = tuple(sorted(pickups))
        if not remaining:
            d = self._dropoff_dist.get(start, INF)
            if d >= INF:
                return INF, None, None
            return d + 1, None, None

        @cache
        def tail_cost(current: Position, rem: tuple[str, ...]) -> int:
            if not rem:
                d_drop = self._dropoff_dist.get(current, INF)
                if d_drop >= INF:
                    return INF
                return d_drop + 1

            best = INF
            seen_types: set[str] = set()
            for item_type in rem:
                if item_type in seen_types:
                    continue
                seen_types.add(item_type)
                next_rem = _remove_one(rem, item_type)
                for adj in self._type_to_adjs.get(item_type, []):
                    d = self._cached_dist(adj, current, grid)
                    if d >= INF:
                        continue
                    rest = tail_cost(adj, next_rem)
                    if rest >= INF:
                        continue
                    total = d + 1 + rest  # move + pick + rest
                    if total < best:
                        best = total
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
                d = self._cached_dist(adj, start, grid)
                if d >= INF:
                    continue
                rest = tail_cost(adj, next_rem)
                if rest >= INF:
                    continue
                total = d + 1 + rest

                tie_key = (item_type, adj[0], adj[1])
                if best_first_adj is None or best_first_type is None:
                    best_tie_key = ("~", INF, INF)
                else:
                    best_tie_key = (
                        best_first_type,
                        best_first_adj[0],
                        best_first_adj[1],
                    )

                if total < best_total or (
                    total == best_total and tie_key < best_tie_key
                ):
                    best_total = total
                    best_first_type = item_type
                    best_first_adj = adj

        return best_total, best_first_type, best_first_adj

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

    def _go_pick_planned_item(
        self,
        state: GameState,
        bot_id: int,
        pos: Position,
        pickups: tuple[str, ...],
        grid: PassableGrid,
    ) -> BotAction | None:
        """Execute the first step of the planned pickup route."""
        _, item_type, target = self._best_route_for_pickups(pos, pickups, grid)
        if item_type is None or target is None:
            return None

        if pos == target:
            item_id = self._pick_item_id_for_type(state, pos, item_type, grid)
            if item_id is None:
                return None
            return PickUpAction(bot=bot_id, action="pick_up", item_id=item_id)

        path = astar(pos, target, grid)
        if path and len(path) > 1:
            return MoveAction(
                bot=bot_id, action=direction_for_move(pos, path[1]),
            )
        return None

    def _pick_item_id_for_type(
        self,
        state: GameState,
        pos: Position,
        item_type: str,
        grid: PassableGrid,
    ) -> str | None:
        """Pick a concrete item_id of `item_type` adjacent to current pos."""
        candidates: list[str] = []
        for item in state.items:
            if item.type != item_type:
                continue
            if pos in adjacent_walkable(item.position, grid):
                candidates.append(item.id)
        if not candidates:
            return None
        candidates.sort()
        return candidates[0]

    def _cached_dist(
        self,
        goal: Position,
        start: Position,
        grid: PassableGrid,
    ) -> int:
        """BFS distance from start to goal, with caching."""
        if goal not in self._dist_cache:
            self._dist_cache[goal] = bfs_distance_map(goal, grid)
        return self._dist_cache[goal].get(start, INF)
