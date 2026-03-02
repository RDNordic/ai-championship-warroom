"""Medium v4 strategy: exact small matching + prioritized reservation traffic.

Design goals for Medium:
- deterministic, fast assignment of bots to active items
- persistent intents to reduce thrash
- one-step reservation with edge-swap blocking to reduce stalls
"""

from __future__ import annotations

from collections import Counter
from itertools import combinations, permutations
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


def _counter_subtract(a: Counter[str], b: Counter[str]) -> Counter[str]:
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


class MediumV4Strategy(Strategy):
    """Medium strategy with exact tiny matching + reservation traffic control."""

    def __init__(self) -> None:
        self._grid: PassableGrid | None = None
        self._planner: LocalTripPlanner | None = None
        self._parking: ParkingManager | None = None
        self._tracker = OrderTracker()
        self._intents = IntentManager()
        self._last_positions: dict[int, Position] = {}
        self._last_diag: dict[str, Any] | None = None
        self._last_blocked_moves = 0
        self._last_assignments = 0
        self._last_wait_overrides: dict[int, str] = {}

    def on_game_start(self, state: GameState) -> None:
        self._grid = PassableGrid(state)
        self._planner = LocalTripPlanner(state, self._grid)
        self._parking = ParkingManager(state.drop_off, self._grid)
        self._last_positions = {bot.id: bot.position for bot in state.bots}
        self._last_diag = None
        self._last_blocked_moves = 0
        self._last_assignments = 0
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

        for bot in bots:
            prev = self._last_positions.get(bot.id)
            if prev is not None and prev == bot.position:
                self._intents.bump_blocked(bot.id)
            else:
                self._intents.reset_blocked(bot.id)

        for bot in bots:
            if self._intents.should_invalidate(bot.id, state, snapshot):
                self._intents.clear(bot.id)

        self._last_assignments = 0
        self._assign_missing_intents(state, snapshot)

        leader_id = self._delivery_leader(state, bots)
        primary: dict[int, BotAction] = {
            bot.id: self._action_for_intent(state, bot, leader_id)
            for bot in bots
        }
        final_by_id, blocked_moves, wait_overrides = self._resolve_traffic(
            state,
            primary,
            leader_id,
        )
        self._last_blocked_moves = blocked_moves
        self._last_wait_overrides = wait_overrides
        self._last_diag = self._build_round_diagnostics(
            state=state,
            snapshot=snapshot,
            primary=primary,
            final=final_by_id,
            blocked_moves=blocked_moves,
            assignments=self._last_assignments,
            wait_overrides=wait_overrides,
        )
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
                active_remaining,
                Counter(remaining_pickups),
            )

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

        unassigned = [b for b in bots if self._intents.get(b.id) is None and len(b.inventory) < 3]
        if active_remaining and unassigned:
            assignments = self._optimal_matching(
                bots=unassigned,
                needed=active_remaining,
                max_cost=None,
            )
            for bot in unassigned:
                assigned_item = assignments.get(bot.id)
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
                active_remaining[assigned_item] -= 1
                if active_remaining[assigned_item] <= 0:
                    active_remaining.pop(assigned_item, None)
                self._last_assignments += 1

        active_guaranteed = not active_remaining
        delivering_now = sum(
            1
            for bot in bots
            if (intent := self._intents.get(bot.id)) is not None and intent.is_deliver()
        )
        allow_preview = active_guaranteed and delivering_now <= 1
        if allow_preview:
            preview_remaining = self._consume_preview_claims(state, preview_remaining, snapshot)
            preview_candidates = [
                b
                for b in bots
                if self._intents.get(b.id) is None and len(b.inventory) < 3
            ]
            preview_assignments = self._optimal_matching(
                bots=preview_candidates,
                needed=preview_remaining,
                max_cost=PREVIEW_TRIP_THRESHOLD,
            )
            for bot in preview_candidates:
                preview_item = preview_assignments.get(bot.id)
                if preview_item is None:
                    continue
                self._intents.set(
                    bot.id,
                    BotIntent(
                        kind="pick",
                        pickups=(preview_item,),
                        order_id=snapshot.active_order_id,
                    ),
                )
                preview_remaining[preview_item] -= 1
                if preview_remaining[preview_item] <= 0:
                    preview_remaining.pop(preview_item, None)
                self._last_assignments += 1

        occupied = frozenset(bot.position for bot in bots)
        for bot in bots:
            if self._intents.get(bot.id) is not None:
                continue
            far = len(bot.inventory) >= 3
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

    def _optimal_matching(
        self,
        bots: list[Bot],
        needed: Counter[str],
        max_cost: int | None,
    ) -> dict[int, str]:
        planner = self._planner
        assert planner is not None

        items = _counter_to_list(needed)
        if not bots or not items:
            return {}

        bots = sorted(bots, key=lambda b: b.id)
        cost_cache: dict[tuple[int, str], int] = {}
        for bot in bots:
            for item in sorted(set(items)):
                cost = planner._best_route_for_pickups(bot.position, (item,))[0]
                cost_cache[(bot.id, item)] = cost

        best_assign: dict[int, str] = {}
        best_cost = INF
        best_tie: tuple[tuple[int, str], ...] = ()
        max_matched = 0

        for k in range(min(len(bots), len(items)), 0, -1):
            found_for_k = False
            for bot_idxs in combinations(range(len(bots)), k):
                for item_idxs in combinations(range(len(items)), k):
                    for perm in permutations(item_idxs):
                        total_cost = 0
                        assign: dict[int, str] = {}
                        feasible = True
                        for bi, item_idx in zip(bot_idxs, perm):
                            bot = bots[bi]
                            item_type = items[item_idx]
                            cost = cost_cache.get((bot.id, item_type), INF)
                            if cost >= INF:
                                feasible = False
                                break
                            if max_cost is not None and cost > max_cost:
                                feasible = False
                                break
                            total_cost += cost
                            assign[bot.id] = item_type
                        if not feasible:
                            continue
                        found_for_k = True
                        tie = tuple(sorted(assign.items()))
                        if (
                            k > max_matched
                            or (k == max_matched and total_cost < best_cost)
                            or (k == max_matched and total_cost == best_cost and tie < best_tie)
                        ):
                            max_matched = k
                            best_cost = total_cost
                            best_assign = assign
                            best_tie = tie
            if found_for_k:
                break
        return best_assign

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

    def _action_for_intent(
        self,
        state: GameState,
        bot: Bot,
        leader_id: int | None,
    ) -> BotAction:
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
                state=state,
                bot_id=bot.id,
                pos=bot.position,
                pickups=pickups,
                blocked=frozenset(),
            )
            return action or WaitAction(bot=bot.id)

        if intent.is_deliver():
            # Soft gating to avoid three-bot pileup on drop-off in one tick.
            if leader_id is not None and bot.id != leader_id and bot.position == state.drop_off:
                return WaitAction(bot=bot.id)
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
        leader_id: int | None,
    ) -> tuple[dict[int, BotAction], int, dict[int, str]]:
        bots = sorted(state.bots, key=lambda b: b.id)
        by_id = {bot.id: bot for bot in bots}
        current_positions = {bot.id: bot.position for bot in bots}
        reserved_cells: set[Position] = set(current_positions.values())
        reserved_edges: set[tuple[Position, Position]] = set()
        final: dict[int, BotAction] = {}
        blocked_moves = 0
        wait_overrides: dict[int, str] = {}

        priority_order = self._priority_order(state, bots, leader_id)
        for bot_id in priority_order:
            bot = by_id[bot_id]
            intent = self._intents.get(bot_id)
            action = primary.get(bot_id, WaitAction(bot=bot_id))

            if isinstance(action, MoveAction):
                current = current_positions[bot_id]
                nxt = next_position_for_action(current, action)
                reserved_cells.discard(current)

                if self._leader_adjacent_gate(
                    state=state,
                    bot_id=bot_id,
                    intent=intent,
                    nxt=nxt,
                    leader_id=leader_id,
                ):
                    reserved_cells.add(current)
                    final[bot_id] = WaitAction(bot=bot_id)
                    wait_overrides[bot_id] = "leader_gate"
                    continue

                if self._move_conflicts(current, nxt, reserved_cells, reserved_edges):
                    alt = self._alternate_move(
                        state=state,
                        bot=bot,
                        current=current,
                        reserved_cells=reserved_cells,
                        reserved_edges=reserved_edges,
                    )
                    if alt is None:
                        reserved_cells.add(current)
                        final[bot_id] = WaitAction(bot=bot_id)
                        blocked_moves += 1
                        wait_overrides[bot_id] = "traffic_blocked"
                        continue
                    action = alt
                    nxt = next_position_for_action(current, action)
                    if self._move_conflicts(current, nxt, reserved_cells, reserved_edges):
                        reserved_cells.add(current)
                        final[bot_id] = WaitAction(bot=bot_id)
                        blocked_moves += 1
                        wait_overrides[bot_id] = "traffic_blocked"
                        continue

                final[bot_id] = action
                reserved_edges.add((current, nxt))
                reserved_cells.add(nxt)
                current_positions[bot_id] = nxt
                continue

            final[bot_id] = action

        return final, blocked_moves, wait_overrides

    def _leader_adjacent_gate(
        self,
        state: GameState,
        bot_id: int,
        intent: BotIntent | None,
        nxt: Position,
        leader_id: int | None,
    ) -> bool:
        if intent is None or not intent.is_deliver() or leader_id is None:
            return False
        if bot_id == leader_id:
            return False
        return _manhattan(nxt, state.drop_off) <= 1

    def _priority_order(
        self,
        state: GameState,
        bots: list[Bot],
        leader_id: int | None,
    ) -> list[int]:
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

        if leader_id is not None and leader_id in deliverers:
            deliverers.remove(leader_id)
            deliverers = [leader_id] + deliverers

        rotation = state.round % max(len(bots), 1)
        fetchers = self._rotate(fetchers, rotation)
        parkers = self._rotate(parkers, rotation)
        idles = self._rotate(idles, rotation)
        return deliverers + fetchers + parkers + idles

    def _rotate(self, values: list[int], amount: int) -> list[int]:
        if not values:
            return []
        offset = amount % len(values)
        return values[offset:] + values[:offset]

    def _alternate_move(
        self,
        state: GameState,
        bot: Bot,
        current: Position,
        reserved_cells: set[Position],
        reserved_edges: set[tuple[Position, Position]],
    ) -> MoveAction | None:
        grid = self._grid
        assert grid is not None

        intent = self._intents.get(bot.id)
        goal = self._goal_for_bot(state, bot)
        blocked_ticks = intent.blocked_ticks if intent is not None else 0

        neighbors = sorted(
            grid.neighbors(current),
            key=lambda nb: (self._goal_distance(goal, nb), nb[0], nb[1]),
        )
        for nb in neighbors:
            if intent is not None and not intent.is_deliver() and nb == state.drop_off:
                continue
            if (
                goal is not None
                and blocked_ticks < 2
                and self._goal_distance(goal, nb) > self._goal_distance(goal, current)
            ):
                continue
            if self._move_conflicts(current, nb, reserved_cells, reserved_edges):
                continue
            return MoveAction(bot=bot.id, action=direction_for_move(current, nb))
        return None

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

    def _delivery_leader(self, state: GameState, bots: list[Bot]) -> int | None:
        deliverers = [
            bot
            for bot in bots
            if (intent := self._intents.get(bot.id)) is not None and intent.is_deliver()
        ]
        if not deliverers:
            return None
        return min(
            deliverers,
            key=lambda bot: (_manhattan(bot.position, state.drop_off), bot.id),
        ).id

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

    def _build_round_diagnostics(
        self,
        state: GameState,
        snapshot: OrderSnapshot,
        primary: dict[int, BotAction],
        final: dict[int, BotAction],
        blocked_moves: int,
        assignments: int,
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
            "greedy_assignments": assignments,
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
