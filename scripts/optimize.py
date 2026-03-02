"""Offline optimizer for known daily order snapshots.

Usage examples:
    python scripts/optimize.py --level easy --date 2026-03-02
    python scripts/optimize.py --snapshot data/easy_2026-03-02.json \\
        --current-run game_20260302_103154.jsonl
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from dataclasses import dataclass
from heapq import heappop, heappush
from pathlib import Path
from typing import Literal

# Add src/ to path so grocerybot package is importable
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from grocerybot.grid import PassableGrid, adjacent_walkable, astar, direction_for_move
from grocerybot.models import GameState

Position = tuple[int, int]
Inventory = tuple[str, ...]
NeedTuple = tuple[tuple[str, int], ...]
StateKey = tuple[Position, Inventory, NeedTuple]


@dataclass(frozen=True)
class SnapshotOrder:
    id: str
    items_required: tuple[str, ...]


@dataclass(frozen=True)
class Snapshot:
    date: str
    level: str
    grid_width: int
    grid_height: int
    walls: tuple[Position, ...]
    drop_off: Position
    item_type_to_positions: dict[str, tuple[Position, ...]]
    orders: tuple[SnapshotOrder, ...]


@dataclass(frozen=True)
class MacroAction:
    kind: Literal["move", "pick", "drop"]
    target: Position | None = None
    item_type: str | None = None


@dataclass(frozen=True)
class Transition:
    ticks: int
    end_inventory: Inventory
    actions: tuple[dict[str, object], ...]


@dataclass(frozen=True)
class PlanPrefix:
    ticks: int
    inventory: Inventory
    actions: tuple[dict[str, object], ...]
    order_summaries: tuple[dict[str, object], ...]


class RouteCache:
    def __init__(self, grid: PassableGrid) -> None:
        self._grid = grid
        self._path_cache: dict[tuple[Position, Position], tuple[Position, ...] | None] = {}

    def path(self, start: Position, goal: Position) -> tuple[Position, ...] | None:
        key = (start, goal)
        if key in self._path_cache:
            return self._path_cache[key]
        path = astar(start, goal, self._grid)
        if not path:
            self._path_cache[key] = None
            return None
        as_tuple = tuple(path)
        self._path_cache[key] = as_tuple
        return as_tuple


def _canonical_inventory(items: tuple[str, ...] | list[str]) -> Inventory:
    return tuple(sorted(items))


def _need_tuple(counter: Counter[str]) -> NeedTuple:
    return tuple(sorted((item, cnt) for item, cnt in counter.items() if cnt > 0))


def _parse_pos(raw: object) -> Position:
    if (
        isinstance(raw, list)
        and len(raw) == 2
        and isinstance(raw[0], int)
        and isinstance(raw[1], int)
    ):
        return (raw[0], raw[1])
    msg = f"Expected [x, y], got {raw!r}"
    raise ValueError(msg)


def load_snapshot(path: Path) -> Snapshot:
    raw = json.loads(path.read_text(encoding="utf-8"))
    orders = tuple(
        SnapshotOrder(
            id=str(order["id"]),
            items_required=tuple(str(it) for it in order["items_required"]),
        )
        for order in raw["orders"]
    )
    item_type_to_positions = {
        str(item_type): tuple(_parse_pos(pos) for pos in positions)
        for item_type, positions in raw["item_type_to_positions"].items()
    }
    return Snapshot(
        date=str(raw["date"]),
        level=str(raw["level"]),
        grid_width=int(raw["grid_width"]),
        grid_height=int(raw["grid_height"]),
        walls=tuple(_parse_pos(w) for w in raw["walls"]),
        drop_off=_parse_pos(raw["drop_off"]),
        item_type_to_positions=item_type_to_positions,
        orders=orders,
    )


def build_grid(snapshot: Snapshot, spawn: Position) -> PassableGrid:
    items: list[dict[str, object]] = []
    for item_type, positions in snapshot.item_type_to_positions.items():
        for idx, pos in enumerate(positions):
            items.append(
                {
                    "id": f"{item_type}_{idx}_{pos[0]}_{pos[1]}",
                    "type": item_type,
                    "position": [pos[0], pos[1]],
                },
            )
    bootstrap_order = snapshot.orders[0].items_required[:1] if snapshot.orders else ("milk",)
    state = GameState.model_validate(
        {
            "type": "game_state",
            "round": 0,
            "max_rounds": 300,
            "grid": {
                "width": snapshot.grid_width,
                "height": snapshot.grid_height,
                "walls": [[x, y] for x, y in snapshot.walls],
            },
            "bots": [{"id": 0, "position": [spawn[0], spawn[1]], "inventory": []}],
            "items": items,
            "orders": [
                {
                    "id": "bootstrap_active",
                    "items_required": list(bootstrap_order),
                    "items_delivered": [],
                    "complete": False,
                    "status": "active",
                },
            ],
            "drop_off": [snapshot.drop_off[0], snapshot.drop_off[1]],
            "score": 0,
            "active_order_index": 0,
            "total_orders": max(len(snapshot.orders), 1),
        },
    )
    return PassableGrid(state)


def pickup_maps(
    snapshot: Snapshot,
    grid: PassableGrid,
) -> tuple[dict[str, tuple[Position, ...]], dict[Position, tuple[str, ...]]]:
    type_to_tiles: dict[str, set[Position]] = {}
    pos_to_types: dict[Position, set[str]] = {}
    for item_type, shelves in snapshot.item_type_to_positions.items():
        for shelf in shelves:
            for adj in adjacent_walkable(shelf, grid):
                type_to_tiles.setdefault(item_type, set()).add(adj)
                pos_to_types.setdefault(adj, set()).add(item_type)
    compact_type_to_tiles = {
        item_type: tuple(sorted(tiles))
        for item_type, tiles in type_to_tiles.items()
    }
    compact_pos_to_types = {
        pos: tuple(sorted(types))
        for pos, types in pos_to_types.items()
    }
    return compact_type_to_tiles, compact_pos_to_types


def reconstruct_macros(
    final_state: StateKey,
    parent: dict[StateKey, tuple[StateKey, MacroAction]],
    start_state: StateKey,
) -> tuple[MacroAction, ...]:
    macros: list[MacroAction] = []
    current = final_state
    while current != start_state:
        prev, action = parent[current]
        macros.append(action)
        current = prev
    macros.reverse()
    return tuple(macros)


def expand_macros(
    start_pos: Position,
    macros: tuple[MacroAction, ...],
    route_cache: RouteCache,
) -> tuple[dict[str, object], ...]:
    pos = start_pos
    actions: list[dict[str, object]] = []
    for macro in macros:
        if macro.kind == "move":
            assert macro.target is not None
            path = route_cache.path(pos, macro.target)
            if path is None:
                msg = f"Missing path for move expansion: {pos} -> {macro.target}"
                raise RuntimeError(msg)
            for nxt in path[1:]:
                actions.append({"bot": 0, "action": direction_for_move(pos, nxt)})
                pos = nxt
        elif macro.kind == "pick":
            assert macro.item_type is not None
            actions.append({"bot": 0, "action": "pick_up", "item_type": macro.item_type})
        else:
            actions.append({"bot": 0, "action": "drop_off"})
    return tuple(actions)


def solve_order_transitions(
    start_pos: Position,
    start_inventory: Inventory,
    order_items: tuple[str, ...],
    drop_off: Position,
    allowed_types: frozenset[str],
    type_to_tiles: dict[str, tuple[Position, ...]],
    pos_to_types: dict[Position, tuple[str, ...]],
    route_cache: RouteCache,
) -> dict[Inventory, Transition]:
    need0 = Counter(order_items)

    # Server behavior at order boundaries: when prior drop_off completes an order,
    # remaining carried items that match the next active order can be consumed
    # immediately in that same tick. Model that as zero-cost pre-consumption for
    # transitions that start at drop-off (all orders after the first).
    inv_after_boundary: list[str] = []
    if start_pos == drop_off and start_inventory:
        for item in start_inventory:
            if need0[item] > 0:
                need0[item] -= 1
            else:
                inv_after_boundary.append(item)
    else:
        inv_after_boundary = list(start_inventory)

    start_state: StateKey = (
        start_pos,
        _canonical_inventory(tuple(inv_after_boundary)),
        _need_tuple(need0),
    )
    pq: list[tuple[int, int, StateKey]] = []
    seq = 0
    heappush(pq, (0, seq, start_state))
    best: dict[StateKey, int] = {start_state: 0}
    parent: dict[StateKey, tuple[StateKey, MacroAction]] = {}
    best_final: dict[Inventory, StateKey] = {}
    best_final_cost: dict[Inventory, int] = {}

    target_positions: set[Position] = {drop_off}
    for item_type in allowed_types:
        target_positions.update(type_to_tiles.get(item_type, ()))
    sorted_targets = tuple(sorted(target_positions))

    while pq:
        cost, _, state = heappop(pq)
        if cost != best.get(state):
            continue
        pos, inv, need_t = state
        need = Counter(dict(need_t))

        if not need and pos == drop_off:
            current_best = best_final_cost.get(inv)
            if current_best is None or cost < current_best:
                best_final_cost[inv] = cost
                best_final[inv] = state
            continue

        if pos == drop_off and inv:
            new_inv_list: list[str] = []
            new_need = need.copy()
            delivered_any = False
            for item in inv:
                if new_need[item] > 0:
                    new_need[item] -= 1
                    delivered_any = True
                else:
                    new_inv_list.append(item)
            if delivered_any:
                next_state: StateKey = (
                    pos,
                    _canonical_inventory(tuple(new_inv_list)),
                    _need_tuple(new_need),
                )
                new_cost = cost + 1
                if new_cost < best.get(next_state, 10**9):
                    best[next_state] = new_cost
                    parent[next_state] = (state, MacroAction(kind="drop"))
                    seq += 1
                    heappush(pq, (new_cost, seq, next_state))

        if len(inv) < 3:
            for item_type in pos_to_types.get(pos, ()):
                if item_type not in allowed_types:
                    continue
                next_inv = _canonical_inventory(inv + (item_type,))
                next_state = (pos, next_inv, need_t)
                new_cost = cost + 1
                if new_cost < best.get(next_state, 10**9):
                    best[next_state] = new_cost
                    parent[next_state] = (
                        state,
                        MacroAction(kind="pick", item_type=item_type),
                    )
                    seq += 1
                    heappush(pq, (new_cost, seq, next_state))

        for target in sorted_targets:
            if target == pos:
                continue
            path = route_cache.path(pos, target)
            if path is None:
                continue
            move_cost = len(path) - 1
            if move_cost <= 0:
                continue
            next_state = (target, inv, need_t)
            new_cost = cost + move_cost
            if new_cost < best.get(next_state, 10**9):
                best[next_state] = new_cost
                parent[next_state] = (state, MacroAction(kind="move", target=target))
                seq += 1
                heappush(pq, (new_cost, seq, next_state))

    transitions: dict[Inventory, Transition] = {}
    for end_inv, final_state in best_final.items():
        macros = reconstruct_macros(final_state, parent, start_state)
        actions = expand_macros(start_pos, macros, route_cache)
        transitions[end_inv] = Transition(
            ticks=len(actions),
            end_inventory=end_inv,
            actions=actions,
        )
    return transitions


def optimize_snapshot(
    snapshot: Snapshot,
    spawn: Position,
    max_orders: int | None = None,
) -> tuple[PlanPrefix, dict[str, object]]:
    grid = build_grid(snapshot, spawn)
    route_cache = RouteCache(grid)
    type_to_tiles, pos_to_types = pickup_maps(snapshot, grid)

    orders = snapshot.orders if max_orders is None else snapshot.orders[:max_orders]
    future_types: list[frozenset[str]] = []
    for idx in range(len(orders)):
        types = {
            item
            for order in orders[idx:]
            for item in order.items_required
        }
        future_types.append(frozenset(types))

    transition_cache: dict[tuple[int, Inventory], dict[Inventory, Transition]] = {}
    dp: dict[Inventory, PlanPrefix] = {
        (): PlanPrefix(
            ticks=0,
            inventory=(),
            actions=(),
            order_summaries=(),
        ),
    }

    for idx, order in enumerate(orders):
        new_dp: dict[Inventory, PlanPrefix] = {}
        for inv_start, prefix in dp.items():
            key = (idx, inv_start)
            if key not in transition_cache:
                start_pos = spawn if idx == 0 else snapshot.drop_off
                transition_cache[key] = solve_order_transitions(
                    start_pos=start_pos,
                    start_inventory=inv_start,
                    order_items=order.items_required,
                    drop_off=snapshot.drop_off,
                    allowed_types=future_types[idx],
                    type_to_tiles=type_to_tiles,
                    pos_to_types=pos_to_types,
                    route_cache=route_cache,
                )
            transitions = transition_cache[key]
            for inv_end, transition in transitions.items():
                start_round = prefix.ticks
                end_round = prefix.ticks + transition.ticks
                summary = {
                    "order_index": idx,
                    "order_id": order.id,
                    "items_required": list(order.items_required),
                    "start_inventory": list(inv_start),
                    "end_inventory": list(inv_end),
                    "start_round": start_round,
                    "end_round_exclusive": end_round,
                    "ticks_used": transition.ticks,
                }
                candidate = PlanPrefix(
                    ticks=end_round,
                    inventory=inv_end,
                    actions=prefix.actions + transition.actions,
                    order_summaries=prefix.order_summaries + (summary,),
                )
                incumbent = new_dp.get(inv_end)
                if incumbent is None or candidate.ticks < incumbent.ticks:
                    new_dp[inv_end] = candidate
        dp = new_dp

    if not dp:
        raise RuntimeError("No feasible plan found")
    best_plan = min(dp.values(), key=lambda p: p.ticks)
    meta = {
        "date": snapshot.date,
        "level": snapshot.level,
        "orders_planned": len(orders),
        "grid_width": snapshot.grid_width,
        "grid_height": snapshot.grid_height,
        "spawn": list(spawn),
        "drop_off": list(snapshot.drop_off),
    }
    return best_plan, meta


def parse_rounds_used_from_replay(path: Path) -> tuple[int | None, dict[str, object] | None]:
    last_game_over: dict[str, object] | None = None
    for line in path.read_text(encoding="utf-8").splitlines():
        obj = json.loads(line)
        if obj.get("type") == "game_over":
            last_game_over = obj
    if last_game_over is None:
        return None, None
    rounds = last_game_over.get("rounds_used")
    if isinstance(rounds, int):
        return rounds, last_game_over
    return None, last_game_over


def latest_replay_file() -> Path | None:
    files = list(Path(".").glob("game_*.jsonl"))
    if not files:
        return None
    return max(files, key=lambda p: p.stat().st_mtime)


def parse_spawn(raw: str) -> Position:
    x_raw, y_raw = raw.split(",", 1)
    return (int(x_raw), int(y_raw))


def main() -> None:
    parser = argparse.ArgumentParser(description="Offline optimizer for daily known orders.")
    parser.add_argument("--level", default="easy", help="Snapshot level (default: easy)")
    parser.add_argument("--date", default=None, help="Snapshot date YYYY-MM-DD")
    parser.add_argument("--snapshot", default=None, help="Path to snapshot JSON")
    parser.add_argument("--output", default=None, help="Path to output plan JSON")
    parser.add_argument(
        "--spawn",
        default="10,8",
        help="Bot spawn as x,y (default: 10,8 for Easy)",
    )
    parser.add_argument(
        "--baseline-rounds",
        type=int,
        default=300,
        help="Baseline round count used for saved-rounds comparison",
    )
    parser.add_argument(
        "--current-run",
        default=None,
        help="Optional replay JSONL to compare rounds used against",
    )
    parser.add_argument(
        "--max-orders",
        type=int,
        default=None,
        help="Optional limit on number of known orders to optimize",
    )
    parser.add_argument(
        "--print-actions",
        action="store_true",
        help="Print full step-by-step action list to stdout",
    )
    args = parser.parse_args()

    snapshot_path = (
        Path(args.snapshot)
        if args.snapshot
        else Path("data") / f"{args.level}_{args.date}.json"
    )
    if args.date is None and args.snapshot is None:
        msg = "--date is required when --snapshot is not provided"
        raise SystemExit(msg)
    if not snapshot_path.exists():
        msg = f"Snapshot not found: {snapshot_path}"
        raise SystemExit(msg)

    snapshot = load_snapshot(snapshot_path)
    spawn = parse_spawn(args.spawn)
    best_plan, meta = optimize_snapshot(snapshot, spawn, max_orders=args.max_orders)

    replay_path: Path | None
    if args.current_run:
        replay_path = Path(args.current_run)
    else:
        replay_path = latest_replay_file()
    current_run_rounds: int | None = None
    current_run_stats: dict[str, object] | None = None
    if replay_path and replay_path.exists():
        current_run_rounds, current_run_stats = parse_rounds_used_from_replay(replay_path)

    baseline_rounds = current_run_rounds if current_run_rounds is not None else args.baseline_rounds
    rounds_saved = baseline_rounds - best_plan.ticks

    saved_for_same_orders: int | None = None
    optimized_rounds_for_same_orders: int | None = None
    current_orders_completed: int | None = None
    if current_run_stats is not None:
        completed = current_run_stats.get("orders_completed")
        if isinstance(completed, int) and completed > 0:
            current_orders_completed = completed
            if completed <= len(best_plan.order_summaries):
                end_round = best_plan.order_summaries[completed - 1].get("end_round_exclusive")
                if isinstance(end_round, int):
                    optimized_rounds_for_same_orders = end_round
                if current_run_rounds is not None and optimized_rounds_for_same_orders is not None:
                    saved_for_same_orders = current_run_rounds - optimized_rounds_for_same_orders

    actions_with_round: tuple[dict[str, object], ...] = tuple(
        {"round": idx, **action}
        for idx, action in enumerate(best_plan.actions)
    )
    output_path = (
        Path(args.output)
        if args.output
        else snapshot_path.with_name(snapshot_path.stem + "_plan.json")
    )
    output_payload = {
        "meta": meta,
        "summary": {
            "optimal_rounds": best_plan.ticks,
            "baseline_rounds": baseline_rounds,
            "rounds_saved": rounds_saved,
            "final_inventory": list(best_plan.inventory),
            "current_run_orders_completed": current_orders_completed,
            "optimal_rounds_for_current_run_orders": optimized_rounds_for_same_orders,
            "rounds_saved_for_current_run_orders": saved_for_same_orders,
            "replay_compared": str(replay_path) if replay_path and replay_path.exists() else None,
            "replay_game_over": current_run_stats,
        },
        "orders": list(best_plan.order_summaries),
        "actions": list(actions_with_round),
    }
    output_path.write_text(json.dumps(output_payload, indent=2), encoding="utf-8")

    print(f"Snapshot: {snapshot_path}")
    print(f"Plan file: {output_path}")
    print(f"Orders planned: {len(best_plan.order_summaries)}")
    print(f"Optimal rounds: {best_plan.ticks}")
    print(f"Baseline rounds: {baseline_rounds}")
    print(f"Rounds saved: {rounds_saved}")
    if current_orders_completed is not None and optimized_rounds_for_same_orders is not None:
        print(
            f"Optimal rounds for first {current_orders_completed} orders: "
            f"{optimized_rounds_for_same_orders}",
        )
        if saved_for_same_orders is not None:
            print(f"Rounds saved vs current run at same order count: {saved_for_same_orders}")
    if replay_path and replay_path.exists():
        print(f"Compared replay: {replay_path}")
    if args.print_actions:
        print("\nStep-by-step actions:")
        for round_no, action_entry in enumerate(best_plan.actions):
            action = str(action_entry["action"])
            if action == "pick_up":
                print(f"{round_no:03d}: pick_up {action_entry['item_type']}")
            else:
                print(f"{round_no:03d}: {action}")


if __name__ == "__main__":
    main()
