"""Build a robust medium v4 replay plan from exact single-bot optimization.

Approach:
- Solve first N known orders exactly for one bot (offline DP from scripts/optimize.py).
- Replay those bot0 actions in a 3-bot simulator with bot1/bot2 waiting.
- Emit per-round checkpoints + actions for strict live plan replay.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from optimize import (
    Position,
    Snapshot,
    SnapshotOrder,
    build_grid,
    latest_replay_file,
    load_snapshot,
    optimize_snapshot,
    parse_rounds_used_from_replay,
)

from grocerybot.grid import adjacent_walkable

NUM_BOTS = 3
MOVE_DELTAS: dict[str, Position] = {
    "move_up": (0, -1),
    "move_down": (0, 1),
    "move_left": (-1, 0),
    "move_right": (1, 0),
}


@dataclass
class SimBot:
    id: int
    pos: Position
    inventory: list[str]


@dataclass
class SimOrder:
    id: str
    required: list[str]
    delivered: list[str]


def parse_spawns(raw: str) -> list[Position]:
    parts = raw.split()
    out: list[Position] = []
    for part in parts:
        x_raw, y_raw = part.split(",", 1)
        out.append((int(x_raw), int(y_raw)))
    if len(out) != NUM_BOTS:
        msg = f"Expected {NUM_BOTS} spawn positions, got {len(out)}"
        raise ValueError(msg)
    return out


def orders_from_replay(path: Path) -> tuple[SnapshotOrder, ...]:
    seen: set[str] = set()
    out: list[SnapshotOrder] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        obj = json.loads(line)
        if obj.get("type") != "game_state":
            continue
        orders = obj.get("orders")
        if not isinstance(orders, list):
            continue
        for order in orders:
            if not isinstance(order, dict):
                continue
            order_id = order.get("id")
            items = order.get("items_required")
            if not isinstance(order_id, str) or order_id in seen:
                continue
            if not isinstance(items, list) or not all(isinstance(it, str) for it in items):
                continue
            seen.add(order_id)
            out.append(SnapshotOrder(id=order_id, items_required=tuple(items)))
    return tuple(out)


def merge_snapshot_orders(snapshot: Snapshot, replay_orders: tuple[SnapshotOrder, ...]) -> Snapshot:
    existing = {o.id for o in snapshot.orders}
    merged_orders = list(snapshot.orders)
    for order in replay_orders:
        if order.id not in existing:
            merged_orders.append(order)
            existing.add(order.id)
    return Snapshot(
        date=snapshot.date,
        level=snapshot.level,
        grid_width=snapshot.grid_width,
        grid_height=snapshot.grid_height,
        walls=snapshot.walls,
        drop_off=snapshot.drop_off,
        item_type_to_positions=snapshot.item_type_to_positions,
        orders=tuple(merged_orders),
    )


def save_snapshot(snapshot: Snapshot, path: Path) -> None:
    payload = {
        "date": snapshot.date,
        "level": snapshot.level,
        "grid_width": snapshot.grid_width,
        "grid_height": snapshot.grid_height,
        "walls": [[x, y] for x, y in snapshot.walls],
        "drop_off": [snapshot.drop_off[0], snapshot.drop_off[1]],
        "item_type_to_positions": {
            item_type: [[x, y] for x, y in positions]
            for item_type, positions in snapshot.item_type_to_positions.items()
        },
        "orders": [
            {"id": order.id, "items_required": list(order.items_required)}
            for order in snapshot.orders
        ],
    }
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _remaining_needed(order: SimOrder) -> list[str]:
    rem = list(order.required)
    for delivered in order.delivered:
        if delivered in rem:
            rem.remove(delivered)
    return rem


def _pickable_type_at_pos(snapshot: Snapshot, pos: Position, item_type: str) -> bool:
    # Build once? Tiny set, so linear scan is fine.
    grid = build_grid(snapshot, pos)
    for shelf in snapshot.item_type_to_positions.get(item_type, ()):
        if pos in adjacent_walkable(shelf, grid):
            return True
    return False


def _active_order_snapshot(active: SimOrder | None) -> tuple[str | None, list[str]]:
    if active is None:
        return None, []
    return active.id, sorted(_remaining_needed(active))


def simulate_three_bot_plan(
    snapshot: Snapshot,
    spawns: list[Position],
    single_actions: tuple[dict[str, object], ...],
    max_orders: int,
) -> dict[str, object]:
    """Simulate 3-bot server semantics using bot0 optimized actions and 2 idle bots."""
    orders = [
        SimOrder(id=o.id, required=list(o.items_required), delivered=[])
        for o in snapshot.orders[:max_orders]
    ]
    bots = [
        SimBot(id=0, pos=spawns[0], inventory=[]),
        SimBot(id=1, pos=spawns[1], inventory=[]),
        SimBot(id=2, pos=spawns[2], inventory=[]),
    ]
    active_idx = 0
    score = 0
    items_delivered = 0
    orders_completed = 0
    checkpoints: list[dict[str, object]] = []
    actions_out: list[dict[str, object]] = []
    order_starts: dict[int, int] = {0: 0}
    order_summaries: list[dict[str, object]] = []
    grid = build_grid(snapshot, spawns[0])

    def active_order() -> SimOrder | None:
        if active_idx >= len(orders):
            return None
        return orders[active_idx]

    def apply_drop(bot: SimBot, active: SimOrder) -> None:
        nonlocal score, items_delivered
        rem = _remaining_needed(active)
        if not rem:
            return
        new_inv: list[str] = []
        delivered_any = False
        for item in bot.inventory:
            if item in rem:
                rem.remove(item)
                active.delivered.append(item)
                score += 1
                items_delivered += 1
                delivered_any = True
            else:
                new_inv.append(item)
        if delivered_any:
            bot.inventory = new_inv

    def finalize_order(order_idx: int, end_round_exclusive: int) -> None:
        start = order_starts.get(order_idx, 0)
        o = orders[order_idx]
        order_summaries.append(
            {
                "order_index": order_idx,
                "order_id": o.id,
                "items_required": list(o.required),
                "start_round": start,
                "end_round_exclusive": end_round_exclusive,
                "ticks_used": end_round_exclusive - start,
            },
        )

    def handle_completion_chain(end_round_exclusive: int) -> None:
        nonlocal active_idx, score, orders_completed, items_delivered
        while active_idx < len(orders):
            active = orders[active_idx]
            if _remaining_needed(active):
                return
            score += 5
            orders_completed += 1
            finalize_order(active_idx, end_round_exclusive)
            active_idx += 1
            if active_idx >= len(orders):
                return
            order_starts[active_idx] = end_round_exclusive
            next_active = orders[active_idx]
            rem = _remaining_needed(next_active)
            for bot in bots:
                new_inv: list[str] = []
                for item in bot.inventory:
                    if item in rem:
                        rem.remove(item)
                        next_active.delivered.append(item)
                        score += 1
                        items_delivered += 1
                    else:
                        new_inv.append(item)
                bot.inventory = new_inv

    for round_no, single_action in enumerate(single_actions):
        active = active_order()
        active_id, active_needed = _active_order_snapshot(active)
        checkpoints.append(
            {
                "round": round_no,
                "active_order_id": active_id,
                "active_needed": active_needed,
                "orders_completed": orders_completed,
                "score": score,
                "bots": [
                    {
                        "id": bot.id,
                        "position": [bot.pos[0], bot.pos[1]],
                        "inventory": sorted(bot.inventory),
                    }
                    for bot in bots
                ],
            },
        )

        if active is None:
            break

        bot0_name_raw = single_action.get("action")
        bot0_action_name = bot0_name_raw if isinstance(bot0_name_raw, str) else "wait"
        bot0_item_type = single_action.get("item_type")
        round_actions: list[dict[str, object]] = [
            {"round": round_no, "bot": 0, "action": bot0_action_name},
            {"round": round_no, "bot": 1, "action": "wait"},
            {"round": round_no, "bot": 2, "action": "wait"},
        ]
        if bot0_action_name == "pick_up" and isinstance(bot0_item_type, str):
            round_actions[0]["item_type"] = bot0_item_type
        actions_out.extend(round_actions)

        counts: dict[Position, int] = {}
        for bot in bots:
            counts[bot.pos] = counts.get(bot.pos, 0) + 1

        for bot in sorted(bots, key=lambda b: b.id):
            action = round_actions[bot.id]
            name_obj = action.get("action")
            if not isinstance(name_obj, str):
                continue
            name = name_obj
            if name in MOVE_DELTAS:
                dx, dy = MOVE_DELTAS[name]
                nxt = (bot.pos[0] + dx, bot.pos[1] + dy)
                if grid.is_passable(nxt) and counts.get(nxt, 0) <= 0:
                    counts[bot.pos] -= 1
                    if counts[bot.pos] == 0:
                        counts.pop(bot.pos, None)
                    counts[nxt] = counts.get(nxt, 0) + 1
                    bot.pos = nxt
                continue
            if name == "pick_up":
                item_type = action.get("item_type")
                if (
                    isinstance(item_type, str)
                    and len(bot.inventory) < 3
                    and _pickable_type_at_pos(snapshot, bot.pos, item_type)
                ):
                    bot.inventory.append(item_type)
                continue
            if name == "drop_off":
                if bot.pos == tuple(snapshot.drop_off):
                    apply_drop(bot, active)

        handle_completion_chain(round_no + 1)
        if active_idx >= len(orders):
            break

    total_rounds = len({a["round"] for a in actions_out})
    return {
        "rounds_used": total_rounds,
        "score": score,
        "items_delivered": items_delivered,
        "orders_completed": orders_completed,
        "actions": actions_out,
        "checkpoints": checkpoints,
        "orders": order_summaries,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Offline medium v4 plan builder.")
    parser.add_argument("--level", default="medium")
    parser.add_argument("--date", default=None)
    parser.add_argument("--snapshot", default=None)
    parser.add_argument("--output", default=None)
    parser.add_argument("--spawns", default="14,10 14,10 14,10")
    parser.add_argument("--max-orders", type=int, default=7)
    parser.add_argument("--baseline-rounds", type=int, default=300)
    parser.add_argument("--current-run", default=None)
    parser.add_argument("--print-actions", action="store_true")
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

    replay_path = Path(args.current_run) if args.current_run else latest_replay_file()

    snapshot: Snapshot = load_snapshot(snapshot_path)
    if replay_path and replay_path.exists():
        replay_orders = orders_from_replay(replay_path)
        if replay_orders:
            merged = merge_snapshot_orders(snapshot, replay_orders)
            if len(merged.orders) > len(snapshot.orders):
                save_snapshot(merged, snapshot_path)
            snapshot = merged

    spawns = parse_spawns(args.spawns)
    single_plan, _meta = optimize_snapshot(snapshot, spawn=spawns[0], max_orders=args.max_orders)
    sim = simulate_three_bot_plan(
        snapshot=snapshot,
        spawns=spawns,
        single_actions=single_plan.actions,
        max_orders=args.max_orders,
    )

    rounds_used_obj = sim.get("rounds_used")
    score_obj = sim.get("score")
    items_delivered_obj = sim.get("items_delivered")
    orders_completed_obj = sim.get("orders_completed")
    actions_obj = sim.get("actions")
    checkpoints_obj = sim.get("checkpoints")
    orders_obj = sim.get("orders")
    if (
        not isinstance(rounds_used_obj, int)
        or not isinstance(score_obj, int)
        or not isinstance(items_delivered_obj, int)
        or not isinstance(orders_completed_obj, int)
        or not isinstance(actions_obj, list)
        or not isinstance(checkpoints_obj, list)
        or not isinstance(orders_obj, list)
    ):
        raise RuntimeError("Simulation output malformed")
    rounds_used = rounds_used_obj
    score = score_obj
    items_delivered = items_delivered_obj
    orders_completed = orders_completed_obj
    actions = actions_obj
    checkpoints = checkpoints_obj
    orders = orders_obj

    current_rounds: int | None = None
    if replay_path and replay_path.exists():
        current_rounds, _ = parse_rounds_used_from_replay(replay_path)
    baseline = current_rounds if current_rounds is not None else args.baseline_rounds
    rounds_saved = baseline - rounds_used

    output_path = (
        Path(args.output)
        if args.output
        else Path("data") / f"{args.level}_{snapshot.date}_plan_v4.json"
    )
    payload = {
        "meta": {
            "level": snapshot.level,
            "date": snapshot.date,
            "orders_planned": args.max_orders,
            "grid_width": snapshot.grid_width,
            "grid_height": snapshot.grid_height,
            "spawns": [[x, y] for x, y in spawns],
            "drop_off": list(snapshot.drop_off),
            "planner_mode": "single_bot_exact_plus_two_idle",
        },
        "summary": {
            "optimal_rounds": rounds_used,
            "baseline_rounds": baseline,
            "rounds_saved": rounds_saved,
            "orders_completed_in_plan": orders_completed,
            "score_in_plan": score,
            "items_delivered_in_plan": items_delivered,
            "replay_compared": str(replay_path) if replay_path and replay_path.exists() else None,
        },
        "orders": orders,
        "checkpoints": checkpoints,
        "actions": actions,
    }
    output_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    print(f"Snapshot: {snapshot_path}")
    print(f"Plan file: {output_path}")
    print(f"Rounds used (planned): {rounds_used}")
    print(f"Orders completed (planned): {orders_completed}/{args.max_orders}")
    print(f"Score in plan: {score}")
    print(f"Rounds saved vs baseline {baseline}: {rounds_saved}")
    if replay_path and replay_path.exists():
        print(f"Compared replay: {replay_path}")
    if args.print_actions:
        print("\nStep-by-step actions:")
        for entry in actions:
            if not isinstance(entry, dict):
                continue
            act = str(entry.get("action", "?"))
            rnd = entry.get("round", 0)
            bot = entry.get("bot", 0)
            if act == "pick_up":
                print(f"R{rnd:03d} B{bot}: pick_up {entry.get('item_type', '?')}")
            else:
                print(f"R{rnd:03d} B{bot}: {act}")


if __name__ == "__main__":
    main()
