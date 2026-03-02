"""Medium v3 strategy: greedy assignment + reservation-based traffic control.

Architecture changes vs medium_v2:
1. Deterministic greedy active-item allocation (no combinatorial bundle search).
2. Reservation-based traffic resolution (no cartesian action search).
3. Delivery leader policy around drop-off congestion.
4. Conservative preview gating.
"""

from __future__ import annotations

from collections import Counter
from typing import TYPE_CHECKING, Any

from grocerybot.grid import PassableGrid, astar, direction_for_move
from grocerybot.models import BotAction, MoveAction, WaitAction
from grocerybot.planner import (
    BotIntent,
    IntentManager,
    LocalTripPlanner,
    OrderSnapshot,
    OrderTracker,
    ParkingManager,
    next_position_for_action,
)
from grocerybot.strategies.base import Strategy

if TYPE_CHECKING:
    from grocerybot.models import Bot, GameState

Position = tuple[int, int]
INF = 999_999
PREVIEW_TRIP_THRESHOLD = 6
DROP_OFF_CLEAR_RADIUS = 1
DROP_OFF_LANE_RADIUS = 3


def _counter_subtract(
    a: Counter[str],
    b: Counter[str],
) -> Counter[str]:
    out: Counter[str] = Counter(a)
    for key, value in b.items():
        if key in out:
            out[key] = max(0, out[key] - value)
            if out[key] == 0:
                out.pop(key, None)
    return out


def _counter_to_list(counter: Counter[str]) -> list[str]:
    out: list[str] = []
    for item, count in counter.items():
        out.extend([item] * count)
    return out


def _manhattan(a: Position, b: Position) -> int:
    return abs(a[0] - b[0]) + abs(a[1] - b[1])


class MediumV3Strategy(Strategy):
    """Medium strategy with greedy allocation and reservation traffic control."""

    def __init__(self) -> None:
        self._grid: PassableGrid | None = None
        self._planner: LocalTripPlanner | None = None
        self._parking: ParkingManager | None = None
        self._tracker = OrderTracker()
        self._intents = IntentManager()
        self._last_positions: dict[int, Position] = {}
        self._last_last_positions: dict[int, Position] = {}
        self._last_diag: dict[str, Any] | None = None
        self._last_blocked_moves = 0
        self._last_greedy_assignments = 0
        self._last_wait_overrides: dict[int, str] = {}

    def on_game_start(self, state: GameState) -> None:
        self._grid = PassableGrid(state)
        self._planner = LocalTripPlanner(state, self._grid)
        self._parking = ParkingManager(state.drop_off, self._grid)
        self._last_positions = {bot.id: bot.position for bot in state.bots}
        self._last_last_positions = dict(self._last_positions)
        self._last_diag = None
        self._last_blocked_moves = 0
        self._last_greedy_assignments = 0
        self._last_wait_overrides = {}

    def decide(self, state: GameState) -> list[BotAction]:
        planner = self._planner
        grid = self._grid
        parking = self._parking
        assert planner is not None and grid is not None and parking is not None

        bots = sorted(state.bots, key=lambda b: b.id)
        snapshot = self._tracker.snapshot(state)
        if snapshot is None:
            self._last_diag = None
            return [WaitAction(bot=b.id) for b in bots]

        # Track blocked bots so stale intents can be invalidated.
        for bot in bots:
            prev = self._last_positions.get(bot.id)
            if prev is not None and prev == bot.position:
                self._intents.bump_blocked(bot.id)
            else:
                self._intents.reset_blocked(bot.id)

        for bot in bots:
            if self._intents.should_invalidate(bot.id, state, snapshot):
                self._intents.clear(bot.id)

        self._last_greedy_assignments = 0
        self._assign_missing_intents(state, snapshot)

        primary: dict[int, BotAction] = {
            bot.id: self._action_for_intent(state, bot)
            for bot in bots
        }
        final_by_id, blocked_moves, wait_overrides = self._resolve_traffic(state, primary)
        self._last_blocked_moves = blocked_moves
        self._last_wait_overrides = wait_overrides
        self._last_diag = self._build_round_diagnostics(
            state=state,
            snapshot=snapshot,
            primary=primary,
            final=final_by_id,
            blocked_moves=blocked_moves,
            greedy_assignments=self._last_greedy_assignments,
            wait_overrides=wait_overrides,
        )
        self._last_last_positions = dict(self._last_positions)
        self._last_positions = {bot.id: bot.position for bot in bots}
        return [final_by_id[bot.id] for bot in bots]

    def replay_diagnostics(
        self,
        state: GameState,
        actions: list[BotAction],
        timed_out: bool,
    ) -> dict[str, Any] | None:
        if self._last_diag is None:
            return None
        by_bot_action = {action.bot: action for action in actions}
        per_bot = dict(self._last_diag.get("per_bot", {}))
        if timed_out:
            for key, value in per_bot.items():
                bot_diag = dict(value)
                bot_diag["final_action"] = "wait"
                bot_diag["wait_reason"] = "time_budget_exceeded"
                per_bot[key] = bot_diag
        else:
            for key, value in per_bot.items():
                bot_diag = dict(value)
                bot_id = int(key)
                action = by_bot_action.get(bot_id)
                if action is not None:
                    bot_diag["final_action"] = action.action
                per_bot[key] = bot_diag
        out = dict(self._last_diag)
        out["timed_out"] = timed_out
        out["per_bot"] = per_bot
        return out

    def _assign_missing_intents(self, state: GameState, snapshot: OrderSnapshot) -> None:
        planner = self._planner
        parking = self._parking
        assert planner is not None and parking is not None

        bots = sorted(state.bots, key=lambda b: b.id)
        active_remaining: Counter[str] = Counter(snapshot.active_needed)
        preview_remaining: Counter[str] = Counter(snapshot.preview_needed)

        # Reserve active items already in inventory.
        for bot in bots:
            inv = Counter(bot.inventory)
            for item in list(active_remaining.keys()):
                if inv.get(item, 0) <= 0:
                    continue
                take = min(active_remaining[item], inv[item])
                if take > 0:
                    active_remaining[item] -= take
                    if active_remaining[item] == 0:
                        active_remaining.pop(item, None)

        # Reserve active items from existing pick intents.
        for bot in bots:
            intent = self._intents.get(bot.id)
            if (
                intent is None
                or not intent.is_pick()
                or intent.order_id != snapshot.active_order_id
            ):
                continue
            remaining_pickups = self._remaining_pickups(bot, intent)
            active_remaining = _counter_subtract(
                active_remaining, Counter(remaining_pickups),
            )

        # Ensure bots carrying active-order items deliver.
        for bot in bots:
            if self._intents.get(bot.id) is not None:
                continue
            if any(item in snapshot.active_needed for item in bot.inventory):
                self._intents.set(
                    bot.id,
                    BotIntent(
                        kind="deliver",
                        target=state.drop_off,
                        order_id=snapshot.active_order_id,
                    ),
                )

        # Greedy active pickup assignment (one pickup item per bot).
        unassigned = [b for b in bots if self._intents.get(b.id) is None]
        if active_remaining:
            allocations = self._greedy_active_allocation(unassigned, active_remaining)
            for bot in unassigned:
                assigned_item = allocations.get(bot.id)
                if assigned_item is None:
                    continue
                self._intents.set(
                    bot.id,
                    BotIntent(
                        kind="pick",
                        pickups=(assigned_item,),
                        order_id=snapshot.active_order_id,
                    ),
                )

        # Preview is intentionally conservative on Medium:
        # only when active is fully guaranteed and no delivery is in progress.
        delivering_now = sum(
            1
            for bot in bots
            if (intent := self._intents.get(bot.id)) is not None and intent.is_deliver()
        )
        active_guaranteed = not active_remaining
        has_active_carry = any(
            item in snapshot.active_needed
            for bot in bots
            for item in bot.inventory
        )
        allow_preview = active_guaranteed and delivering_now == 0 and not has_active_carry
        if allow_preview:
            preview_remaining = self._consume_preview_claims(
                state, preview_remaining, snapshot,
            )
            for bot in bots:
                if not preview_remaining:
                    break
                if self._intents.get(bot.id) is not None:
                    continue
                if len(bot.inventory) >= 3:
                    continue
                picks = planner.plan_trip(
                    bot.position,
                    bot.inventory,
                    [],
                    _counter_to_list(preview_remaining),
                )
                if not picks:
                    continue
                trip_cost = planner._best_route_for_pickups(bot.position, picks)[0]
                if trip_cost >= PREVIEW_TRIP_THRESHOLD:
                    continue
                self._intents.set(
                    bot.id,
                    BotIntent(
                        kind="pick",
                        pickups=picks,
                        order_id=snapshot.active_order_id,
                    ),
                )
                preview_remaining = _counter_subtract(preview_remaining, Counter(picks))

        # Remaining bots park (far when delivery traffic is active).
        occupied = frozenset(bot.position for bot in bots)
        for bot in bots:
            if self._intents.get(bot.id) is not None:
                continue
            far = len(bot.inventory) >= 3 or delivering_now > 0 or bool(snapshot.active_needed)
            target = parking.best_park(bot.position, occupied, far=far)
            if target is not None:
                self._intents.set(
                    bot.id,
                    BotIntent(
                        kind="park",
                        target=target,
                        order_id=snapshot.active_order_id,
                    ),
                )
            else:
                self._intents.set(
                    bot.id,
                    BotIntent(kind="idle", order_id=snapshot.active_order_id),
                )

    def _consume_preview_claims(
        self,
        state: GameState,
        preview_remaining: Counter[str],
        snapshot: OrderSnapshot,
    ) -> Counter[str]:
        out = Counter(preview_remaining)
        for bot in state.bots:
            for item in bot.inventory:
                if item in out:
                    out[item] -= 1
                    if out[item] == 0:
                        out.pop(item, None)
        for bot in state.bots:
            intent = self._intents.get(bot.id)
            if (
                intent is None
                or not intent.is_pick()
                or intent.order_id != snapshot.active_order_id
            ):
                continue
            for item in self._remaining_pickups(bot, intent):
                if item in out:
                    out[item] -= 1
                    if out[item] == 0:
                        out.pop(item, None)
        return out

    def _remaining_pickups(self, bot: Bot, intent: BotIntent) -> tuple[str, ...]:
        remaining = list(intent.pickups)
        for item in bot.inventory:
            if item in remaining:
                remaining.remove(item)
        return tuple(remaining)

    def _greedy_active_allocation(
        self,
        bots: list[Bot],
        active_remaining: Counter[str],
    ) -> dict[int, str]:
        planner = self._planner
        assert planner is not None

        assignments: dict[int, str] = {}
        for bot in sorted(bots, key=lambda b: b.id):
            if not active_remaining:
                break
            if len(bot.inventory) >= 3:
                continue

            candidates: list[tuple[int, str]] = []
            for item_type in sorted(active_remaining.keys()):
                if active_remaining[item_type] <= 0:
                    continue
                route_cost, _, _ = planner._best_route_for_pickups(
                    bot.position, (item_type,),
                )
                if route_cost < INF:
                    candidates.append((route_cost, item_type))

            if not candidates:
                continue

            candidates.sort(key=lambda x: (x[0], x[1]))
            _, chosen = candidates[0]
            assignments[bot.id] = chosen
            active_remaining[chosen] -= 1
            if active_remaining[chosen] == 0:
                active_remaining.pop(chosen, None)
            self._last_greedy_assignments += 1

        return assignments

    def _action_for_intent(self, state: GameState, bot: Bot) -> BotAction:
        planner = self._planner
        grid = self._grid
        assert planner is not None and grid is not None

        intent = self._intents.get(bot.id)
        if intent is None:
            return WaitAction(bot=bot.id)

        if intent.is_pick():
            pickups = self._remaining_pickups(bot, intent)
            if not pickups:
                return WaitAction(bot=bot.id)
            action = planner.next_pick_action(
                state,
                bot_id=bot.id,
                pos=bot.position,
                pickups=pickups,
                blocked=frozenset(),
            )
            return action or WaitAction(bot=bot.id)

        if intent.is_deliver():
            return planner.go_drop_off(bot.id, bot.position, blocked=frozenset())

        if intent.is_park() and intent.target is not None:
            if bot.position == intent.target:
                return WaitAction(bot=bot.id)
            path = astar(bot.position, intent.target, grid)
            if path and len(path) > 1:
                return MoveAction(
                    bot=bot.id,
                    action=direction_for_move(bot.position, path[1]),
                )
        return WaitAction(bot=bot.id)

    def _resolve_traffic(
        self,
        state: GameState,
        primary: dict[int, BotAction],
    ) -> tuple[dict[int, BotAction], int, dict[int, str]]:
        bots = sorted(state.bots, key=lambda b: b.id)
        by_id = {bot.id: bot for bot in bots}
        current_positions = {bot.id: bot.position for bot in bots}
        reserved_cells: set[Position] = set(current_positions.values())
        reserved_edges: set[tuple[Position, Position]] = set()
        final: dict[int, BotAction] = {}
        blocked_moves = 0
        wait_overrides: dict[int, str] = {}
        delivery_bots = {
            bot.id
            for bot in bots
            if (intent := self._intents.get(bot.id)) is not None and intent.is_deliver()
        }

        priority_order, leader_id = self._priority_order(state, bots)
        for bot_id in priority_order:
            bot = by_id[bot_id]
            intent = self._intents.get(bot_id)
            action = primary.get(bot_id, WaitAction(bot=bot_id))

            # Hard decongestion rule: non-delivery bots cannot hold drop-off lane.
            if self._must_clear_dropoff_lane(
                state=state,
                bot=bot,
                delivery_bots=delivery_bots,
            ):
                clear_step = self._step_away_from_dropoff(
                    bot=bot,
                    reserved_cells=reserved_cells,
                    reserved_edges=reserved_edges,
                )
                if clear_step is not None:
                    action = clear_step
                else:
                    action = WaitAction(bot=bot_id)
                    wait_overrides[bot_id] = "clearance_blocked"

            # Delivery leader rule: non-leader deliverers park instead of contesting drop-off.
            if (
                leader_id is not None
                and intent is not None
                and intent.is_deliver()
                and bot_id != leader_id
            ):
                action = self._park_step_action(
                    bot=bot,
                    current_positions=current_positions,
                    reserved_cells=reserved_cells,
                )
                if action.action == "wait":
                    wait_overrides[bot_id] = "leader_restricted"

            if isinstance(action, MoveAction):
                current = current_positions[bot_id]
                nxt = next_position_for_action(current, action)
                blocked_ticks = intent.blocked_ticks if intent is not None else 0

                # Do not allow low-value two-cell oscillation for non-delivery intents.
                if (
                    not (intent is not None and intent.is_deliver())
                    and self._is_two_cell_oscillation(bot_id, current, nxt)
                    and _manhattan(current, state.drop_off) > (DROP_OFF_LANE_RADIUS + 1)
                ):
                    alt = self._alternate_move(
                        state=state,
                        bot=bot,
                        current=current,
                        reserved_cells=reserved_cells,
                        reserved_edges=reserved_edges,
                        avoid_cell=self._last_positions.get(bot_id),
                        allow_delivery_backtrack=False,
                    )
                    if alt is not None:
                        action = alt
                        nxt = next_position_for_action(current, action)
                    else:
                        final[bot_id] = WaitAction(bot=bot_id)
                        blocked_moves += 1
                        wait_overrides.setdefault(bot_id, "oscillation_blocked")
                        continue

                if (
                    nxt == state.drop_off
                    and not (intent is not None and intent.is_deliver())
                ):
                    final[bot_id] = WaitAction(bot=bot_id)
                    blocked_moves += 1
                    wait_overrides.setdefault(bot_id, "dropoff_restricted")
                    continue
                # Delivery moves should be monotonic toward drop-off when possible.
                if (
                    intent is not None
                    and intent.is_deliver()
                    and blocked_ticks < 2
                    and _manhattan(nxt, state.drop_off) > _manhattan(current, state.drop_off)
                ):
                    alt = self._alternate_move(
                        state=state,
                        bot=bot,
                        current=current,
                        reserved_cells=reserved_cells,
                        reserved_edges=reserved_edges,
                        allow_delivery_backtrack=False,
                    )
                    if alt is None:
                        final[bot_id] = WaitAction(bot=bot_id)
                        blocked_moves += 1
                        wait_overrides.setdefault(bot_id, "delivery_backtrack_blocked")
                        continue
                    alt_nxt = next_position_for_action(current, alt)
                    if _manhattan(alt_nxt, state.drop_off) > _manhattan(current, state.drop_off):
                        final[bot_id] = WaitAction(bot=bot_id)
                        blocked_moves += 1
                        wait_overrides.setdefault(bot_id, "delivery_backtrack_blocked")
                        continue
                    action = alt
                    nxt = alt_nxt

                if self._move_conflicts(current, nxt, reserved_cells, reserved_edges):
                    alt = self._alternate_move(
                        state=state,
                        bot=bot,
                        current=current,
                        reserved_cells=reserved_cells,
                        reserved_edges=reserved_edges,
                        avoid_cell=self._last_positions.get(bot_id),
                        allow_delivery_backtrack=bool(
                            intent is not None
                            and intent.is_deliver()
                            and blocked_ticks >= 2
                        ),
                    )
                    if alt is None:
                        final[bot_id] = WaitAction(bot=bot_id)
                        blocked_moves += 1
                        wait_overrides.setdefault(bot_id, "traffic_blocked")
                        continue
                    action = alt
                    nxt = next_position_for_action(current, action)
                    if self._move_conflicts(current, nxt, reserved_cells, reserved_edges):
                        final[bot_id] = WaitAction(bot=bot_id)
                        blocked_moves += 1
                        wait_overrides.setdefault(bot_id, "traffic_blocked")
                        continue

                final[bot_id] = action
                reserved_edges.add((current, nxt))
                reserved_cells.discard(current)
                reserved_cells.add(nxt)
                current_positions[bot_id] = nxt
                continue

            final[bot_id] = action

        return final, blocked_moves, wait_overrides

    def _must_clear_dropoff_lane(
        self,
        state: GameState,
        bot: Bot,
        delivery_bots: set[int],
    ) -> bool:
        intent = self._intents.get(bot.id)
        if intent is None:
            return False
        if intent.is_deliver() or intent.is_pick():
            return False
        if not delivery_bots:
            return False
        dist = _manhattan(bot.position, state.drop_off)
        same_drop_column = (
            bot.position[0] == state.drop_off[0]
            and abs(bot.position[1] - state.drop_off[1]) <= DROP_OFF_LANE_RADIUS
        )
        return dist <= DROP_OFF_CLEAR_RADIUS or same_drop_column

    def _step_away_from_dropoff(
        self,
        bot: Bot,
        reserved_cells: set[Position],
        reserved_edges: set[tuple[Position, Position]],
    ) -> MoveAction | None:
        grid = self._grid
        assert grid is not None
        current = bot.position
        drop_off = grid.drop_off
        best: Position | None = None
        best_dist = _manhattan(current, drop_off)
        for nb in sorted(grid.neighbors(current)):
            if self._move_conflicts(current, nb, reserved_cells, reserved_edges):
                continue
            dist = _manhattan(nb, drop_off)
            if dist > best_dist:
                best = nb
                best_dist = dist
        if best is None:
            return None
        return MoveAction(bot=bot.id, action=direction_for_move(current, best))

    def _priority_order(
        self,
        state: GameState,
        bots: list[Bot],
    ) -> tuple[list[int], int | None]:
        deliverers: list[int] = []
        fetchers: list[int] = []
        parkers: list[int] = []
        idles: list[int] = []
        for bot in sorted(bots, key=lambda b: b.id):
            intent = self._intents.get(bot.id)
            if intent is None:
                idles.append(bot.id)
            elif intent.is_deliver():
                deliverers.append(bot.id)
            elif intent.is_pick():
                fetchers.append(bot.id)
            elif intent.is_park():
                parkers.append(bot.id)
            else:
                idles.append(bot.id)

        leader_id = self._delivery_leader(state, bots)
        ordered: list[int] = []
        if leader_id is not None:
            ordered.append(leader_id)
        other_deliverers = [
            bot_id for bot_id in deliverers if bot_id != leader_id
        ]
        other_deliverers.sort(
            key=lambda bot_id: (
                _manhattan(
                    next(b.position for b in bots if b.id == bot_id),
                    state.drop_off,
                ),
                bot_id,
            ),
        )
        ordered.extend(other_deliverers)
        ordered.extend(sorted(fetchers))
        ordered.extend(sorted(parkers))
        ordered.extend(sorted(idles))
        return ordered, leader_id

    def _delivery_leader(self, state: GameState, bots: list[Bot]) -> int | None:
        deliverer_bots = [
            bot
            for bot in bots
            if (intent := self._intents.get(bot.id)) is not None and intent.is_deliver()
        ]
        if not deliverer_bots:
            return None
        return min(
            deliverer_bots,
            key=lambda bot: (_manhattan(bot.position, state.drop_off), bot.id),
        ).id

    def _park_step_action(
        self,
        bot: Bot,
        current_positions: dict[int, Position],
        reserved_cells: set[Position],
    ) -> BotAction:
        grid = self._grid
        parking = self._parking
        assert grid is not None and parking is not None

        occupied = frozenset(
            pos for bot_id, pos in current_positions.items() if bot_id != bot.id
        )
        target = parking.best_park(bot.position, occupied, far=False)
        if target is None or target == bot.position:
            return WaitAction(bot=bot.id)

        blocked = frozenset(reserved_cells - {bot.position})
        path = astar(bot.position, target, grid, blocked=blocked)
        if path and len(path) > 1:
            return MoveAction(
                bot=bot.id,
                action=direction_for_move(bot.position, path[1]),
            )
        return WaitAction(bot=bot.id)

    def _alternate_move(
        self,
        state: GameState,
        bot: Bot,
        current: Position,
        reserved_cells: set[Position],
        reserved_edges: set[tuple[Position, Position]],
        avoid_cell: Position | None = None,
        allow_delivery_backtrack: bool = False,
    ) -> MoveAction | None:
        grid = self._grid
        assert grid is not None

        intent = self._intents.get(bot.id)
        is_deliver = bool(intent is not None and intent.is_deliver())

        # Delivery bots queued at drop-off should hold lane instead of wandering.
        if (
            is_deliver
            and _manhattan(current, state.drop_off) <= 1
            and any(
                other.id != bot.id and other.position == state.drop_off
                for other in state.bots
            )
        ):
            return None

        goal = self._goal_for_bot(state, bot)
        if goal is not None and current != goal:
            blocked = frozenset(reserved_cells - {current})
            path = astar(current, goal, grid, blocked=blocked)
            if path and len(path) > 1:
                nxt = path[1]
                if avoid_cell is not None and nxt == avoid_cell:
                    pass
                elif (
                    is_deliver
                    and not allow_delivery_backtrack
                    and _manhattan(nxt, state.drop_off) > _manhattan(current, state.drop_off)
                ):
                    pass
                elif not self._move_conflicts(current, nxt, reserved_cells, reserved_edges):
                    return MoveAction(
                        bot=bot.id,
                        action=direction_for_move(current, nxt),
                    )

        neighbors = sorted(
            grid.neighbors(current),
            key=lambda nb: (self._goal_distance(goal, nb), nb[0], nb[1]),
        )
        for nb in neighbors:
            if not is_deliver and nb == state.drop_off:
                continue
            if avoid_cell is not None and nb == avoid_cell:
                continue
            if (
                is_deliver
                and not allow_delivery_backtrack
                and _manhattan(nb, state.drop_off) > _manhattan(current, state.drop_off)
            ):
                continue
            if self._move_conflicts(current, nb, reserved_cells, reserved_edges):
                continue
            return MoveAction(
                bot=bot.id,
                action=direction_for_move(current, nb),
            )
        return None

    def _is_two_cell_oscillation(
        self,
        bot_id: int,
        current: Position,
        nxt: Position,
    ) -> bool:
        prev = self._last_positions.get(bot_id)
        prev_prev = self._last_last_positions.get(bot_id)
        return prev is not None and prev_prev is not None and current == prev_prev and nxt == prev

    def _move_conflicts(
        self,
        current: Position,
        nxt: Position,
        reserved_cells: set[Position],
        reserved_edges: set[tuple[Position, Position]],
    ) -> bool:
        if nxt in reserved_cells:
            return True
        if (nxt, current) in reserved_edges:
            return True
        return False

    def _build_round_diagnostics(
        self,
        state: GameState,
        snapshot: OrderSnapshot,
        primary: dict[int, BotAction],
        final: dict[int, BotAction],
        blocked_moves: int,
        greedy_assignments: int,
        wait_overrides: dict[int, str],
    ) -> dict[str, Any]:
        per_bot: dict[str, dict[str, Any]] = {}
        primary_waits = 0
        final_waits = 0
        traffic_blocks = 0
        for bot in sorted(state.bots, key=lambda b: b.id):
            intent = self._intents.get(bot.id)
            prim = primary.get(bot.id, WaitAction(bot=bot.id))
            fin = final.get(bot.id, WaitAction(bot=bot.id))
            if prim.action == "wait":
                primary_waits += 1
            if fin.action == "wait":
                final_waits += 1
            wait_reason = wait_overrides.get(bot.id)
            if wait_reason is None:
                wait_reason = self._infer_wait_reason(state, bot, prim, fin, intent)
            if wait_reason == "traffic_blocked":
                traffic_blocks += 1
            goal = self._goal_for_bot(state, bot)
            per_bot[str(bot.id)] = {
                "position": [bot.position[0], bot.position[1]],
                "inventory_size": len(bot.inventory),
                "intent": intent.kind if intent is not None else "none",
                "blocked_ticks": intent.blocked_ticks if intent is not None else 0,
                "goal": [goal[0], goal[1]] if goal is not None else None,
                "primary_action": prim.action,
                "final_action": fin.action,
                "wait_reason": wait_reason,
            }
        return {
            "active_order_id": snapshot.active_order_id,
            "active_needed": list(snapshot.active_needed),
            "preview_needed": list(snapshot.preview_needed),
            "primary_waits": primary_waits,
            "final_waits": final_waits,
            "traffic_blocks": traffic_blocks,
            "blocked_moves": blocked_moves,
            "greedy_assignments": greedy_assignments,
            "per_bot": per_bot,
        }

    def _infer_wait_reason(
        self,
        state: GameState,
        bot: Bot,
        primary: BotAction,
        final: BotAction,
        intent: BotIntent | None,
    ) -> str | None:
        if final.action != "wait":
            return None
        if primary.action != "wait":
            return "traffic_blocked"
        if intent is None:
            return "no_intent"
        if intent.kind == "park":
            if intent.target is not None and bot.position == intent.target:
                return "parked"
            return "park_path_unavailable"
        if intent.kind == "deliver":
            if bot.position == state.drop_off:
                return "at_dropoff_waiting"
            return "delivery_path_unavailable"
        if intent.kind == "pick":
            remaining = self._remaining_pickups(bot, intent)
            if not remaining:
                return "pick_intent_complete"
            return "pick_path_unavailable"
        return "idle_wait"

    def _goal_for_bot(self, state: GameState, bot: Bot) -> Position | None:
        planner = self._planner
        assert planner is not None
        intent = self._intents.get(bot.id)
        if intent is None:
            return None
        if intent.is_deliver():
            return state.drop_off
        if intent.is_park():
            return intent.target
        if intent.is_pick():
            pickups = self._remaining_pickups(bot, intent)
            if not pickups:
                return None
            _, _, first_adj = planner._best_route_for_pickups(bot.position, pickups)
            return first_adj
        return None

    def _goal_distance(self, goal: Position | None, pos: Position) -> int:
        if goal is None:
            return 0
        return _manhattan(goal, pos)
