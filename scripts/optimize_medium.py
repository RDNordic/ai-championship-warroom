"""Offline optimizer for medium difficulty (3 bots).

Decomposes multi-bot planning: greedy item→bot assignment per order,
then per-bot single-bot DP (reusing solve_order_transitions from optimize.py),
then merge action streams with drop-off staggering.

Usage:
    python scripts/optimize_medium.py --snapshot data/medium_2026-03-02.json \
        --spawns 1,1 8,1 15,1
    python scripts/optimize_medium.py --level medium --date 2026-03-02 \
        --spawns 1,10 8,10 14,10
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from optimize import (
    Inventory,
    Position,
    RouteCache,
    Snapshot,
    Transition,
    _canonical_inventory,
    build_grid,
    latest_replay_file,
    load_snapshot,
    parse_rounds_used_from_replay,
    pickup_maps,
    solve_order_transitions,
)

from grocerybot.grid import PassableGrid, astar

NUM_BOTS = 3
MAX_INVENTORY = 3


def _item_aisle_x(
    item_type: str,
    type_to_tiles: dict[str, tuple[Position, ...]],
) -> float:
    """Average x-coordinate of pickup tiles for an item type (aisle proxy)."""
    tiles = type_to_tiles.get(item_type, ())
    if not tiles:
        return 0.0
    return sum(t[0] for t in tiles) / len(tiles)


def greedy_assign(
    order_items: tuple[str, ...],
    bot_positions: list[Position],
    bot_inventories: list[Inventory],
    drop_off: Position,
    type_to_tiles: dict[str, tuple[Position, ...]],
    route_cache: RouteCache,
) -> list[list[str]]:
    """Assign order items to bots with spatial separation.

    Groups items by aisle (x-coordinate clusters) and distributes groups
    across bots to minimize route overlap. Falls back to cost-based
    assignment for remaining items.
    """
    assignments: list[list[str]] = [[] for _ in range(NUM_BOTS)]
    capacities = [MAX_INVENTORY - len(inv) for inv in bot_inventories]

    # Sort items by aisle x-coordinate for clustering
    items_with_x = [
        (item, _item_aisle_x(item, type_to_tiles))
        for item in order_items
    ]
    items_with_x.sort(key=lambda pair: pair[1])

    # Distribute items round-robin across bots by spatial order.
    # This sends bot 0 to the leftmost items, bot 1 to middle, etc.
    effective_pos = list(bot_positions)
    unassigned: list[str] = []

    for i, (item_type, _) in enumerate(items_with_x):
        # Pick bot by round-robin over spatial order
        preferred_bot = i % NUM_BOTS
        # Try preferred bot, then others
        assigned = False
        for offset in range(NUM_BOTS):
            bot_id = (preferred_bot + offset) % NUM_BOTS
            if capacities[bot_id] <= 0:
                continue
            assignments[bot_id].append(item_type)
            capacities[bot_id] -= 1
            # Update effective position to nearest pickup tile
            tiles = type_to_tiles.get(item_type, ())
            best_tile: Position | None = None
            best_dist = 10**9
            for tile in tiles:
                path = route_cache.path(effective_pos[bot_id], tile)
                if path is not None and len(path) - 1 < best_dist:
                    best_dist = len(path) - 1
                    best_tile = tile
            if best_tile is not None:
                effective_pos[bot_id] = best_tile
            assigned = True
            break
        if not assigned:
            unassigned.append(item_type)

    # Any items that couldn't be assigned (all bots full) — try harder
    for item_type in unassigned:
        for bot_id in range(NUM_BOTS):
            if capacities[bot_id] > 0:
                assignments[bot_id].append(item_type)
                capacities[bot_id] -= 1
                break

    return assignments


def _apply_boundary_consumption(
    inventory: Inventory,
    order_items: tuple[str, ...],
) -> tuple[Inventory, Counter[str]]:
    """Model server auto-consumption at order boundaries.

    When a new order activates, items already in inventory that match the
    new order are consumed immediately. Returns updated inventory and
    remaining needs.
    """
    need = Counter(order_items)
    remaining_inv: list[str] = []
    for item in inventory:
        if need[item] > 0:
            need[item] -= 1
        else:
            remaining_inv.append(item)
    return _canonical_inventory(tuple(remaining_inv)), need


MOVE_DELTAS: dict[str, Position] = {
    "move_up": (0, -1),
    "move_down": (0, 1),
    "move_left": (-1, 0),
    "move_right": (1, 0),
}

STAGGER_DELAY = 2  # Ticks between each bot's departure from shared spawn


def merge_bot_actions(
    per_bot_actions: list[tuple[dict[str, object], ...]],
    bot_positions: list[Position],
) -> tuple[list[dict[str, object]], int, list[Position]]:
    """Merge N bot action streams with staggered departure.

    Simple interleaving: each round has one action per bot. Shorter streams
    are padded with waits. Bots sharing a start position get staggered
    departures (wait padding) to reduce initial collisions.

    The replay strategy handles remaining collisions live via per-bot
    validation and fallback.

    Returns (merged_actions, total_rounds, final_positions).
    """
    # Apply stagger delays for shared starting positions
    queues: list[list[dict[str, object]]] = []
    for bot_id in range(NUM_BOTS):
        acts = list(per_bot_actions[bot_id])
        # Check if this bot shares spawn with an earlier bot
        shares_spawn = any(
            bot_positions[bot_id] == bot_positions[b]
            for b in range(bot_id)
        )
        if shares_spawn:
            delay = STAGGER_DELAY * bot_id
            waits = [{"bot": bot_id, "action": "wait"} for _ in range(delay)]
            acts = waits + acts
        queues.append(acts)

    max_ticks = max((len(q) for q in queues), default=0)

    # Interleave: one action per bot per round
    all_actions: list[dict[str, object]] = []
    for tick in range(max_ticks):
        for bot_id in range(NUM_BOTS):
            if tick < len(queues[bot_id]):
                all_actions.append({"round": tick, **queues[bot_id][tick]})
            else:
                all_actions.append(
                    {"round": tick, "bot": bot_id, "action": "wait"}
                )

    # Compute final positions by tracing actions
    final_positions = list(bot_positions)
    for action in all_actions:
        bot_id = action.get("bot")
        act_name = action.get("action")
        if (
            isinstance(bot_id, int)
            and isinstance(act_name, str)
            and act_name in MOVE_DELTAS
        ):
            dx, dy = MOVE_DELTAS[act_name]
            final_positions[bot_id] = (
                final_positions[bot_id][0] + dx,
                final_positions[bot_id][1] + dy,
            )

    return all_actions, max_ticks, final_positions


def _extract_path_cells(
    actions: tuple[dict[str, object], ...],
    start_pos: Position,
) -> set[Position]:
    """Extract all cells visited by a bot's action sequence."""
    cells: set[Position] = {start_pos}
    pos = start_pos
    for action in actions:
        act = action.get("action")
        if isinstance(act, str) and act in MOVE_DELTAS:
            dx, dy = MOVE_DELTAS[act]
            pos = (pos[0] + dx, pos[1] + dy)
            cells.add(pos)
    return cells


class _AvoidanceRouteCache:
    """RouteCache that routes around avoided cells using A*."""

    def __init__(
        self,
        grid: PassableGrid,
        base_cache: RouteCache,
        avoid: frozenset[Position],
    ) -> None:
        self._grid = grid
        self._base = base_cache
        self._avoid = avoid
        self._cache: dict[tuple[Position, Position], tuple[Position, ...] | None] = {}

    def path(
        self, start: Position, goal: Position,
    ) -> tuple[Position, ...] | None:
        key = (start, goal)
        if key in self._cache:
            return self._cache[key]
        # Try routing around avoided cells
        result = astar(start, goal, self._grid, blocked=self._avoid)
        if result:
            as_tuple = tuple(result)
            self._cache[key] = as_tuple
            return as_tuple
        # If avoidance makes path impossible, fall back to base
        base_path = self._base.path(start, goal)
        self._cache[key] = base_path
        return base_path


def _make_avoidance_cache(
    grid: PassableGrid,
    base_cache: RouteCache,
    avoid_cells: set[Position],
) -> RouteCache | _AvoidanceRouteCache:
    """Create a route cache that avoids specific cells if any."""
    if not avoid_cells:
        return base_cache
    return _AvoidanceRouteCache(grid, base_cache, frozenset(avoid_cells))


def optimize_medium_snapshot(
    snapshot: Snapshot,
    spawns: list[Position],
    max_orders: int | None = None,
) -> tuple[dict[str, object], list[dict[str, object]]]:
    """Optimize a medium snapshot with 3 bots.

    Returns (meta, merged_actions_with_round_numbers).
    """
    grid = build_grid(snapshot, spawns[0])
    route_cache = RouteCache(grid)
    type_to_tiles, pos_to_types = pickup_maps(snapshot, grid)

    orders = snapshot.orders if max_orders is None else snapshot.orders[:max_orders]
    future_types: list[frozenset[str]] = []
    for idx in range(len(orders)):
        types = {item for order in orders[idx:] for item in order.items_required}
        future_types.append(frozenset(types))

    # Per-bot state across orders
    bot_positions = list(spawns)
    bot_inventories: list[Inventory] = [() for _ in range(NUM_BOTS)]

    all_actions: list[dict[str, object]] = []
    total_rounds = 0
    order_summaries: list[dict[str, object]] = []

    for idx, order in enumerate(orders):
        start_round = total_rounds

        # Apply boundary auto-consumption for each bot
        if idx > 0:
            for bot_id in range(NUM_BOTS):
                new_inv, _ = _apply_boundary_consumption(
                    bot_inventories[bot_id], order.items_required
                )
                bot_inventories[bot_id] = new_inv

        # Greedy assignment
        assignments = greedy_assign(
            order_items=order.items_required,
            bot_positions=bot_positions,
            bot_inventories=bot_inventories,
            drop_off=snapshot.drop_off,
            type_to_tiles=type_to_tiles,
            route_cache=route_cache,
        )

        # Prioritized per-bot solve: plan each bot sequentially,
        # later bots avoid cells used by earlier bots' paths.
        per_bot_actions: list[tuple[dict[str, object], ...]] = []
        per_bot_transitions: list[Transition | None] = []
        used_path_cells: set[Position] = set()

        for bot_id in range(NUM_BOTS):
            assigned = assignments[bot_id]
            if not assigned:
                per_bot_actions.append(())
                per_bot_transitions.append(None)
                continue

            bot_order_items = tuple(assigned)

            # Build route cache that avoids earlier bots' path cells.
            # Don't block drop-off or this bot's start position.
            avoidance = used_path_cells - {
                snapshot.drop_off, bot_positions[bot_id],
            }
            bot_route_cache = _make_avoidance_cache(
                grid, route_cache, avoidance,
            )

            transitions = solve_order_transitions(
                start_pos=bot_positions[bot_id],
                start_inventory=bot_inventories[bot_id],
                order_items=bot_order_items,
                drop_off=snapshot.drop_off,
                allowed_types=future_types[idx],
                type_to_tiles=type_to_tiles,
                pos_to_types=pos_to_types,
                route_cache=bot_route_cache,
            )

            # Fallback: if avoidance made the route infeasible,
            # retry with the unconstrained route cache
            if not transitions and avoidance:
                transitions = solve_order_transitions(
                    start_pos=bot_positions[bot_id],
                    start_inventory=bot_inventories[bot_id],
                    order_items=bot_order_items,
                    drop_off=snapshot.drop_off,
                    allowed_types=future_types[idx],
                    type_to_tiles=type_to_tiles,
                    pos_to_types=pos_to_types,
                    route_cache=route_cache,
                )

            if not transitions:
                per_bot_actions.append(())
                per_bot_transitions.append(None)
                continue

            best_inv = min(transitions, key=lambda inv: transitions[inv].ticks)
            best_trans = transitions[best_inv]

            # Record path cells so later bots avoid them
            path_cells = _extract_path_cells(
                best_trans.actions, bot_positions[bot_id],
            )
            used_path_cells.update(path_cells)

            tagged = tuple({**a, "bot": bot_id} for a in best_trans.actions)
            per_bot_actions.append(tagged)
            per_bot_transitions.append(best_trans)

        # Merge with stagger delays; replay strategy handles collisions live
        merged, order_rounds, final_positions = merge_bot_actions(
            per_bot_actions, bot_positions
        )

        # Offset round numbers by total_rounds
        for action in merged:
            action["round"] = action["round"] + total_rounds

        all_actions.extend(merged)

        # Update bot states for next order using simulated final positions
        bot_positions = final_positions
        for bot_id in range(NUM_BOTS):
            trans = per_bot_transitions[bot_id]
            if trans is not None:
                bot_inventories[bot_id] = trans.end_inventory

        order_summaries.append({
            "order_index": idx,
            "order_id": order.id,
            "items_required": list(order.items_required),
            "assignments": [assignments[b] for b in range(NUM_BOTS)],
            "start_round": start_round,
            "end_round_exclusive": total_rounds + order_rounds,
            "ticks_used": order_rounds,
        })
        total_rounds += order_rounds

    meta = {
        "date": snapshot.date,
        "level": snapshot.level,
        "orders_planned": len(orders),
        "grid_width": snapshot.grid_width,
        "grid_height": snapshot.grid_height,
        "spawns": [list(s) for s in spawns],
        "drop_off": list(snapshot.drop_off),
        "total_rounds": total_rounds,
    }

    return meta, all_actions, order_summaries  # type: ignore[return-value]


def parse_spawns(raw: str) -> list[Position]:
    """Parse space-separated x,y spawn positions."""
    parts = raw.split()
    result: list[Position] = []
    for part in parts:
        x_raw, y_raw = part.split(",", 1)
        result.append((int(x_raw), int(y_raw)))
    if len(result) != NUM_BOTS:
        msg = f"Expected {NUM_BOTS} spawn positions, got {len(result)}"
        raise ValueError(msg)
    return result


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Offline optimizer for medium difficulty (3 bots)."
    )
    parser.add_argument("--level", default="medium", help="Snapshot level")
    parser.add_argument("--date", default=None, help="Snapshot date YYYY-MM-DD")
    parser.add_argument("--snapshot", default=None, help="Path to snapshot JSON")
    parser.add_argument("--output", default=None, help="Path to output plan JSON")
    parser.add_argument(
        "--spawns",
        default="14,10 14,10 14,10",
        help='Bot spawns as "x0,y0 x1,y1 x2,y2" (default: 14,10 for all)',
    )
    parser.add_argument(
        "--max-orders",
        type=int,
        default=None,
        help="Limit on number of orders to optimize",
    )
    parser.add_argument(
        "--baseline-rounds",
        type=int,
        default=300,
        help="Baseline round count for comparison",
    )
    parser.add_argument(
        "--current-run",
        default=None,
        help="Optional replay JSONL to compare against",
    )
    parser.add_argument(
        "--print-actions",
        action="store_true",
        help="Print step-by-step actions to stdout",
    )
    args = parser.parse_args()

    snapshot_path = (
        Path(args.snapshot)
        if args.snapshot
        else Path("data") / f"{args.level}_{args.date}.json"
    )
    if args.date is None and args.snapshot is None:
        raise SystemExit("--date is required when --snapshot is not provided")
    if not snapshot_path.exists():
        raise SystemExit(f"Snapshot not found: {snapshot_path}")

    snapshot = load_snapshot(snapshot_path)
    spawns = parse_spawns(args.spawns)
    meta, all_actions, order_summaries = optimize_medium_snapshot(
        snapshot, spawns, max_orders=args.max_orders
    )

    # Compare with replay if available
    replay_path: Path | None
    if args.current_run:
        replay_path = Path(args.current_run)
    else:
        replay_path = latest_replay_file()
    current_run_rounds: int | None = None
    if replay_path and replay_path.exists():
        current_run_rounds, _ = parse_rounds_used_from_replay(replay_path)

    baseline_rounds = (
        current_run_rounds if current_run_rounds is not None else args.baseline_rounds
    )
    total_rounds = meta["total_rounds"]
    rounds_saved = baseline_rounds - total_rounds

    output_path = (
        Path(args.output)
        if args.output
        else snapshot_path.with_name(snapshot_path.stem + "_plan.json")
    )
    output_payload = {
        "meta": meta,
        "summary": {
            "optimal_rounds": total_rounds,
            "baseline_rounds": baseline_rounds,
            "rounds_saved": rounds_saved,
            "replay_compared": (
                str(replay_path) if replay_path and replay_path.exists() else None
            ),
        },
        "orders": order_summaries,
        "actions": all_actions,
    }
    output_path.write_text(json.dumps(output_payload, indent=2), encoding="utf-8")

    print(f"Snapshot: {snapshot_path}")
    print(f"Plan file: {output_path}")
    print(f"Orders planned: {meta['orders_planned']}")
    print(f"Optimal rounds: {total_rounds}")
    print(f"Baseline rounds: {baseline_rounds}")
    print(f"Rounds saved: {rounds_saved}")
    if replay_path and replay_path.exists():
        print(f"Compared replay: {replay_path}")

    if args.print_actions:
        print("\nStep-by-step actions:")
        for entry in all_actions:
            rnd = entry.get("round", "?")
            bot = entry.get("bot", "?")
            act = str(entry.get("action", "?"))
            if act == "pick_up":
                print(f"R{rnd:03d} B{bot}: pick_up {entry.get('item_type', '?')}")
            else:
                print(f"R{rnd:03d} B{bot}: {act}")


if __name__ == "__main__":
    main()
