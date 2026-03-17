"""Medium v2 strategy: min-cost assignment + traffic-aware action resolution.

This strategy keeps the proven local trip planner, but replaces the global
coordination loop with:
1. Distance/cost-based active-item bundle allocation across bots.
2. Persistent intents (pick/deliver/park/idle) with stale-intent invalidation.
3. Per-tick multi-candidate traffic resolution by exact one-step simulation.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from itertools import combinations, product
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


def _multiset_combinations(items: list[str], k: int) -> set[tuple[str, ...]]:
    if k <= 0:
        return {()}
    if k > len(items):
        return set()
    combos: set[tuple[str, ...]] = set()
    for idxs in combinations(range(len(items)), k):
        combos.add(tuple(sorted(items[i] for i in idxs)))
    return combos


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


def _bundle_fits(bundle: tuple[str, ...], remaining: Counter[str]) -> bool:
    need = Counter(bundle)
    return all(remaining.get(item, 0) >= count for item, count in need.items())


@dataclass(frozen=True)
class _PlanKey:
    matched: int
    cost: int
    used_bots: int


class MediumV2Strategy(Strategy):
    """Medium strategy with costed assignment and local traffic search."""

    def __init__(self) -> None:
        self._grid: PassableGrid | None = None
        self._planner: LocalTripPlanner | None = None
        self._parking: ParkingManager | None = None
        self._tracker = OrderTracker()
        self._intents = IntentManager()
        self._last_positions: dict[int, Position] = {}
        self._last_diag: dict[str, Any] | None = None

    def on_game_start(self, state: GameState) -> None:
        self._grid = PassableGrid(state)
        self._planner = LocalTripPlanner(state, self._grid)
        self._parking = ParkingManager(state.drop_off, self._grid)
        self._last_positions = {bot.id: bot.position for bot in state.bots}
        self._last_diag = None

    def decide(self, state: GameState) -> list[BotAction]:
        planner = self._planner
        grid = self._grid
        parking = self._parking
        assert planner is not None and grid is not None and parking is not None

        bots = sorted(state.bots, key=lambda b: b.id)
        snapshot = self._tracker.snapshot(state)
        if snapshot is None:
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

        self._assign_missing_intents(state, snapshot)

        primary: dict[int, BotAction] = {
            bot.id: self._action_for_intent(state, bot)
            for bot in bots
        }
        final_by_id = self._resolve_traffic(state, primary)
        self._last_diag = self._build_round_diagnostics(
            state=state,
            snapshot=snapshot,
            primary=primary,
            final=final_by_id,
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
            if intent is None or not intent.is_pick():
                continue
            remaining_pickups = self._remaining_pickups(bot, intent)
            active_remaining = _counter_subtract(
                active_remaining, Counter(remaining_pickups),
            )

        # Ensure bots with active-carry inventory deliver.
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

        # Assign active pickups using joint min-cost bundle allocation.
        unassigned = [b for b in bots if self._intents.get(b.id) is None]
        if active_remaining:
            active_plan = self._best_active_allocation(unassigned, active_remaining)
            for bot in unassigned:
                bundle = active_plan.get(bot.id, ())
                if bundle:
                    self._intents.set(
                        bot.id,
                        BotIntent(
                            kind="pick",
                            pickups=bundle,
                            order_id=snapshot.active_order_id,
                        ),
                    )
                    active_remaining = _counter_subtract(active_remaining, Counter(bundle))

        # If active work is guaranteed (in-flight + in inventory), allow preview.
        active_guaranteed = not active_remaining
        if active_guaranteed:
            preview_remaining = self._consume_preview_claims(
                state, preview_remaining, snapshot,
            )
            for bot in bots:
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
                if picks:
                    self._intents.set(
                        bot.id,
                        BotIntent(
                            kind="pick",
                            pickups=picks,
                            order_id=snapshot.active_order_id,
                        ),
                    )
                    preview_remaining = _counter_subtract(
                        preview_remaining, Counter(picks),
                    )

        # Remaining bots park (far if full stale inventory, near otherwise).
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

    def _best_active_allocation(
        self,
        bots: list[Bot],
        active_remaining: Counter[str],
    ) -> dict[int, tuple[str, ...]]:
        planner = self._planner
        assert planner is not None

        if not bots:
            return {}
        remaining_items = _counter_to_list(active_remaining)
        if not remaining_items:
            return {bot.id: () for bot in bots}

        options: dict[int, list[tuple[str, ...]]] = {}
        bundle_cost: dict[tuple[int, tuple[str, ...]], int] = {}

        for bot in bots:
            cap = max(0, 3 - len(bot.inventory))
            bot_options: set[tuple[str, ...]] = {()}
            for k in range(1, min(cap, len(remaining_items)) + 1):
                bot_options.update(_multiset_combinations(remaining_items, k))
            filtered = []
            for bundle in sorted(bot_options):
                if not bundle:
                    filtered.append(bundle)
                    continue
                cost = planner._best_route_for_pickups(bot.position, bundle)[0]
                if cost >= INF:
                    continue
                bundle_cost[(bot.id, bundle)] = cost
                filtered.append(bundle)
            options[bot.id] = filtered or [()]

        best_key: _PlanKey | None = None
        best_assign: dict[int, tuple[str, ...]] = {}

        def search(
            idx: int,
            remaining: Counter[str],
            matched: int,
            cost: int,
            used_bots: int,
            assign: dict[int, tuple[str, ...]],
        ) -> None:
            nonlocal best_key, best_assign
            if idx >= len(bots):
                key = _PlanKey(matched=matched, cost=cost, used_bots=used_bots)
                if best_key is None or self._plan_better(key, best_key):
                    best_key = key
                    best_assign = dict(assign)
                return

            bot = bots[idx]
            for bundle in options[bot.id]:
                if bundle and not _bundle_fits(bundle, remaining):
                    continue
                next_remaining = remaining
                add_matched = 0
                add_cost = 0
                add_used = 0
                if bundle:
                    next_remaining = _counter_subtract(remaining, Counter(bundle))
                    add_matched = len(bundle)
                    add_cost = bundle_cost.get((bot.id, bundle), INF)
                    add_used = 1
                assign[bot.id] = bundle
                search(
                    idx + 1,
                    next_remaining,
                    matched + add_matched,
                    cost + add_cost,
                    used_bots + add_used,
                    assign,
                )
                assign.pop(bot.id, None)

        search(0, active_remaining, matched=0, cost=0, used_bots=0, assign={})
        return best_assign

    def _plan_better(self, a: _PlanKey, b: _PlanKey) -> bool:
        if a.matched != b.matched:
            return a.matched > b.matched
        if a.cost != b.cost:
            return a.cost < b.cost
        return a.used_bots < b.used_bots

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
    ) -> dict[int, BotAction]:
        bots = sorted(state.bots, key=lambda b: b.id)
        bot_ids = [b.id for b in bots]
        candidates = {
            bot.id: self._candidate_actions_for_bot(state, bot, primary[bot.id])
            for bot in bots
        }

        best_actions: dict[int, BotAction] | None = None
        best_key: tuple[int, int, int, int] | None = None

        rotation = state.round % max(len(bot_ids), 1)
        order = bot_ids[rotation:] + bot_ids[:rotation]
        weight = {bot_id: len(bot_ids) - idx for idx, bot_id in enumerate(order)}
        delivery_bonus = len(bot_ids) + 1

        for combo in product(*(candidates[bot_id] for bot_id in bot_ids)):
            chosen = {bot_id: combo[idx] for idx, bot_id in enumerate(bot_ids)}
            final, moved, positions = self._simulate(state, chosen)

            delivered = 0
            picked = 0
            weighted_moved = 0
            progress = 0
            for bot in bots:
                action = final[bot.id]
                if action.action == "drop_off":
                    delivered += 1
                elif action.action == "pick_up":
                    picked += 1
                if bot.id in moved:
                    bonus = delivery_bonus if self._is_delivery_bot(bot.id) else 0
                    weighted_moved += weight[bot.id] + bonus
                progress += self._progress_delta(bot, positions[bot.id], state)

            key = (delivered, picked, weighted_moved, progress)
            if best_key is None or key > best_key:
                best_key = key
                best_actions = final

        assert best_actions is not None
        return best_actions

    def _build_round_diagnostics(
        self,
        state: GameState,
        snapshot: OrderSnapshot,
        primary: dict[int, BotAction],
        final: dict[int, BotAction],
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

    def _candidate_actions_for_bot(
        self,
        state: GameState,
        bot: Bot,
        primary: BotAction,
    ) -> list[BotAction]:
        grid = self._grid
        assert grid is not None

        result: list[BotAction] = []

        def add(action: BotAction) -> None:
            sig = (action.action, getattr(action, "item_id", ""))
            if any((a.action, getattr(a, "item_id", "")) == sig for a in result):
                return
            result.append(action)

        add(primary)
        if primary.action in {"pick_up", "drop_off"}:
            add(WaitAction(bot=bot.id))
            return result

        add(WaitAction(bot=bot.id))
        goal = self._goal_for_bot(state, bot)
        if goal is not None and bot.position != goal:
            path = astar(bot.position, goal, grid)
            if path and len(path) > 1:
                add(
                    MoveAction(
                        bot=bot.id,
                        action=direction_for_move(bot.position, path[1]),
                    ),
                )

        if len(result) < 4:
            nbrs = sorted(
                grid.neighbors(bot.position),
                key=lambda nb: self._goal_distance(goal, nb),
            )
            for nb in nbrs:
                if len(result) >= 4:
                    break
                add(
                    MoveAction(
                        bot=bot.id,
                        action=direction_for_move(bot.position, nb),
                    ),
                )
        return result

    def _simulate(
        self,
        state: GameState,
        chosen: dict[int, BotAction],
    ) -> tuple[dict[int, BotAction], set[int], dict[int, Position]]:
        bots = sorted(state.bots, key=lambda b: b.id)
        positions = {bot.id: bot.position for bot in bots}
        counts: dict[Position, int] = {}
        for pos in positions.values():
            counts[pos] = counts.get(pos, 0) + 1

        moved: set[int] = set()
        final: dict[int, BotAction] = {}
        for bot in bots:
            action = chosen.get(bot.id, WaitAction(bot=bot.id))
            if isinstance(action, MoveAction):
                current = positions[bot.id]
                nxt = next_position_for_action(current, action)
                if counts.get(nxt, 0) > 0:
                    action = WaitAction(bot=bot.id)
                else:
                    counts[current] -= 1
                    if counts[current] == 0:
                        counts.pop(current, None)
                    counts[nxt] = counts.get(nxt, 0) + 1
                    positions[bot.id] = nxt
                    moved.add(bot.id)
            final[bot.id] = action
        return final, moved, positions

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
        return abs(goal[0] - pos[0]) + abs(goal[1] - pos[1])

    def _is_delivery_bot(self, bot_id: int) -> bool:
        intent = self._intents.get(bot_id)
        return bool(intent and intent.is_deliver())

    def _progress_delta(self, bot: Bot, new_pos: Position, state: GameState) -> int:
        goal = self._goal_for_bot(state, bot)
        if goal is None:
            return 0
        before = self._goal_distance(goal, bot.position)
        after = self._goal_distance(goal, new_pos)
        return before - after
