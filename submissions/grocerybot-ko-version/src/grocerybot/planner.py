"""Milestone 3 planner utilities for multi-bot coordination.

Includes:
- OrderTracker: active/preview remaining needs with inventory accounting
- LocalTripPlanner: exact short-horizon pickup trip planning
- TaskAssigner: greedy sequential assignment in bot-id order
- CollisionResolver: single-step collision safety in bot-id order
- BotIntent / IntentManager: persistent per-bot intents (v2 traffic control)
"""

from __future__ import annotations

from dataclasses import dataclass, field
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
IntentKind = Literal["pick", "deliver", "park", "idle"]

INF = 999_999
PREVIEW_DETOUR_BUDGET = 2
BLOCKED_REROUTE_THRESHOLD = 3


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


@dataclass
class BotIntent:
    """Persistent intent for a bot — survives across ticks until invalidated."""

    kind: IntentKind
    target: Position | None = None
    pickups: tuple[str, ...] = ()
    order_id: str = ""
    blocked_ticks: int = field(default=0, compare=False)

    def is_pick(self) -> bool:
        return self.kind == "pick"

    def is_deliver(self) -> bool:
        return self.kind == "deliver"

    def is_park(self) -> bool:
        return self.kind == "park"


class IntentManager:
    """Track and invalidate persistent bot intents."""

    def __init__(self) -> None:
        self._intents: dict[int, BotIntent] = {}

    def get(self, bot_id: int) -> BotIntent | None:
        return self._intents.get(bot_id)

    def set(self, bot_id: int, intent: BotIntent) -> None:
        self._intents[bot_id] = intent

    def clear(self, bot_id: int) -> None:
        self._intents.pop(bot_id, None)

    def bump_blocked(self, bot_id: int) -> int:
        intent = self._intents.get(bot_id)
        if intent is not None:
            intent.blocked_ticks += 1
            return intent.blocked_ticks
        return 0

    def reset_blocked(self, bot_id: int) -> None:
        intent = self._intents.get(bot_id)
        if intent is not None:
            intent.blocked_ticks = 0

    def should_invalidate(
        self,
        bot_id: int,
        state: GameState,
        snapshot: OrderSnapshot | None,
    ) -> bool:
        """Check if the current intent should be dropped and replanned."""
        intent = self._intents.get(bot_id)
        if intent is None:
            return True

        # Order changed → replan
        if snapshot is None:
            return intent.kind != "idle"
        if intent.order_id and intent.order_id != snapshot.active_order_id:
            return True

        bot = next((b for b in state.bots if b.id == bot_id), None)
        if bot is None:
            return True

        # Pick intent: all pickups collected → done
        if intent.is_pick():
            remaining = list(intent.pickups)
            for item in bot.inventory:
                if item in remaining:
                    remaining.remove(item)
            if not remaining:
                return True
            # Items no longer exist on map → replan
            available_types = {i.type for i in state.items}
            if any(r not in available_types for r in remaining):
                return True

        # Deliver intent: arrived at drop-off → done
        if intent.is_deliver():
            if bot.position == state.drop_off:
                return True
            # No matching items for active order → stop delivering
            if not any(item in snapshot.active_needed for item in bot.inventory):
                return True
            # Empty inventory → nothing to deliver
            if not bot.inventory:
                return True

        # Park intent: arrived → stay, BUT replan if there's work to do
        if intent.is_park() and intent.target == bot.position:
            has_space = len(bot.inventory) < 3
            has_work = bool(snapshot.active_needed or snapshot.preview_needed)
            return has_space and has_work

        # Blocked too long → reroute
        if intent.blocked_ticks >= BLOCKED_REROUTE_THRESHOLD:
            return True

        return False

    def all_intents(self) -> dict[int, BotIntent]:
        return dict(self._intents)


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
            path = astar(pos, tgt, self._grid, blocked=blocked - {tgt})
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
        # Never block the goal itself — resolver handles contention
        path = astar(pos, self._drop_off, self._grid, blocked=blocked - {self._drop_off})
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


class ParkingManager:
    """Precompute parking cells near drop-off for idle bots.

    Two tiers:
    - near (BFS 2-4): for bots with inventory space, ready for next task
    - far (BFS 5+): for bots with full stale inventory blocking corridors
    """

    def __init__(self, drop_off: Position, grid: PassableGrid) -> None:
        self._drop_off = drop_off
        dist_map = bfs_distance_map(drop_off, grid)
        near = [
            (d, pos) for pos, d in dist_map.items()
            if 2 <= d <= 4 and pos != drop_off
        ]
        far = [
            (d, pos) for pos, d in dist_map.items()
            if d >= 5 and pos != drop_off
        ]
        near.sort()
        far.sort()
        self._near_cells = [pos for _, pos in near[:10]]
        self._far_cells = [pos for _, pos in far[:10]]

    def best_park(
        self,
        pos: Position,
        occupied: frozenset[Position],
        far: bool = False,
    ) -> Position | None:
        cells = self._far_cells if far else self._near_cells
        best: Position | None = None
        best_dist = INF
        for cell in cells:
            if cell in occupied:
                continue
            d = abs(cell[0] - pos[0]) + abs(cell[1] - pos[1])
            if d < best_dist:
                best_dist = d
                best = cell
        return best


class TaskAssigner:
    """Two-phase assignment: delivery-first, then pickups."""

    def assign(
        self,
        state: GameState,
        snapshot: OrderSnapshot,
        planner: LocalTripPlanner,
        claimed: list[str] | None = None,
    ) -> dict[int, AssignedTask]:
        tasks: dict[int, AssignedTask] = {}
        remaining_active = list(snapshot.active_needed)
        # Subtract items already claimed by persistent intents
        if claimed:
            for item in claimed:
                if item in remaining_active:
                    remaining_active.remove(item)
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
        remaining_preview = list(snapshot.preview_needed)
        for bot in bots:
            if bot.id in tasks:
                continue
            if len(bot.inventory) >= 3:
                # Only drop_off if at least one item matches the ACTIVE order
                # (server ignores drop_off for non-active items)
                has_active_match = any(
                    item in remaining_active for item in bot.inventory
                )
                if has_active_match:
                    tasks[bot.id] = AssignedTask(bot.id, "drop_off")
                else:
                    tasks[bot.id] = AssignedTask(bot.id, "wait")
                continue
            if remaining_active:
                picks = planner.plan_trip(
                    bot.position, bot.inventory, remaining_active, remaining_preview,
                )
                if picks:
                    tasks[bot.id] = AssignedTask(bot.id, "pick", picks)
                    _, remaining_active, _ = _consume_needed(remaining_active, picks)
                    continue
            if remaining_preview:
                picks = planner.plan_trip(
                    bot.position, bot.inventory, remaining_preview, [],
                )
                if picks:
                    tasks[bot.id] = AssignedTask(bot.id, "pick", picks)
                    _, remaining_preview, _ = _consume_needed(remaining_preview, picks)
                    continue
            tasks[bot.id] = AssignedTask(bot.id, "wait")

        return tasks


class CollisionResolver:
    """Single-step traffic resolver under server id-order semantics.

    Chooses a best-effort subset of proposed move actions each tick using:
    - exact simulation of server movement rules (id order, occupied-cell blocking)
    - rotating tie-break priority for fairness across bots
    """

    def _simulate(
        self,
        state: GameState,
        candidate: dict[int, BotAction],
    ) -> tuple[dict[int, BotAction], set[int]]:
        bots = sorted(state.bots, key=lambda b: b.id)
        positions: dict[int, Position] = {bot.id: bot.position for bot in bots}
        counts: dict[Position, int] = {}
        for pos in positions.values():
            counts[pos] = counts.get(pos, 0) + 1

        final: dict[int, BotAction] = {}
        moved: set[int] = set()
        for bot in bots:
            bot_id = bot.id
            action = candidate.get(bot_id, WaitAction(bot=bot_id))
            if isinstance(action, MoveAction):
                current = positions[bot_id]
                nxt = next_position_for_action(current, action)
                if counts.get(nxt, 0) > 0:
                    action = WaitAction(bot=bot_id)
                else:
                    counts[current] -= 1
                    if counts[current] == 0:
                        del counts[current]
                    counts[nxt] = counts.get(nxt, 0) + 1
                    positions[bot_id] = nxt
                    moved.add(bot_id)
            final[bot_id] = action
        return final, moved

    def resolve(
        self,
        state: GameState,
        proposed: dict[int, BotAction],
        priority_bots: set[int] | None = None,
    ) -> list[BotAction]:
        bots = sorted(state.bots, key=lambda b: b.id)
        bot_ids = [b.id for b in bots]
        movers = [
            bot_id
            for bot_id in bot_ids
            if isinstance(proposed.get(bot_id, WaitAction(bot=bot_id)), MoveAction)
        ]

        # Fair tie-break among equal-throughput candidates.
        rotation = state.round % max(len(bot_ids), 1)
        priority = bot_ids[rotation:] + bot_ids[:rotation]
        base_weight = {
            bot_id: len(priority) - idx
            for idx, bot_id in enumerate(priority)
        }
        # Delivery bots get bonus weight for right-of-way
        priority_bonus = len(bot_ids) + 1
        weight = {
            bot_id: base_weight[bot_id] + (
                priority_bonus if priority_bots and bot_id in priority_bots else 0
            )
            for bot_id in bot_ids
        }

        best_actions: dict[int, BotAction] | None = None
        best_key: tuple[int, int] | None = None

        for mask in range(1 << len(movers)):
            enabled = {
                movers[i] for i in range(len(movers))
                if mask & (1 << i)
            }
            candidate: dict[int, BotAction] = {}
            for bot_id in bot_ids:
                action = proposed.get(bot_id, WaitAction(bot=bot_id))
                if isinstance(action, MoveAction) and bot_id not in enabled:
                    candidate[bot_id] = WaitAction(bot=bot_id)
                else:
                    candidate[bot_id] = action

            final, moved = self._simulate(state, candidate)
            key = (len(moved), sum(weight[bot_id] for bot_id in moved))
            if best_key is None or key > best_key:
                best_key = key
                best_actions = final

        assert best_actions is not None
        return [best_actions[bot_id] for bot_id in bot_ids]
