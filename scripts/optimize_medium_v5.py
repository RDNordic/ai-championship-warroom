"""Build a robust medium v5 replay plan using all 3 bots.

v5 is simulation-first:
- plan actions round-by-round for all bots,
- apply server-like action resolution in bot-id order,
- score inside the simulator and emit checkpoints for robust replay.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, deque
from dataclasses import dataclass
from datetime import UTC, datetime
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
    parse_rounds_used_from_replay,
)

from grocerybot.grid import PassableGrid, adjacent_walkable, astar, direction_for_move

NUM_BOTS = 3
INVENTORY_MAX = 3
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


def build_snapshot_from_replay(path: Path, level: str, date: str) -> Snapshot | None:
    grid_width: int | None = None
    grid_height: int | None = None
    walls: tuple[Position, ...] | None = None
    drop_off: Position | None = None
    item_type_to_positions: dict[str, set[Position]] = {}
    seen_orders: set[str] = set()
    orders: list[SnapshotOrder] = []

    for line in path.read_text(encoding="utf-8").splitlines():
        obj = json.loads(line)
        if obj.get("type") != "game_state":
            continue

        grid = obj.get("grid")
        if (
            grid_width is None
            and isinstance(grid, dict)
            and isinstance(grid.get("width"), int)
            and isinstance(grid.get("height"), int)
            and isinstance(grid.get("walls"), list)
            and isinstance(obj.get("drop_off"), list)
            and len(obj["drop_off"]) == 2
            and all(isinstance(v, int) for v in obj["drop_off"])
        ):
            grid_width = int(grid["width"])
            grid_height = int(grid["height"])
            parsed_walls: list[Position] = []
            for w in grid["walls"]:
                if (
                    isinstance(w, list)
                    and len(w) == 2
                    and isinstance(w[0], int)
                    and isinstance(w[1], int)
                ):
                    parsed_walls.append((w[0], w[1]))
            walls = tuple(parsed_walls)
            drop_off = (obj["drop_off"][0], obj["drop_off"][1])

        items = obj.get("items")
        if isinstance(items, list):
            for item in items:
                if not isinstance(item, dict):
                    continue
                item_type = item.get("type")
                pos = item.get("position")
                if (
                    isinstance(item_type, str)
                    and isinstance(pos, list)
                    and len(pos) == 2
                    and all(isinstance(v, int) for v in pos)
                ):
                    item_type_to_positions.setdefault(item_type, set()).add((pos[0], pos[1]))

        raw_orders = obj.get("orders")
        if isinstance(raw_orders, list):
            for order in raw_orders:
                if not isinstance(order, dict):
                    continue
                order_id = order.get("id")
                items_required = order.get("items_required")
                if (
                    isinstance(order_id, str)
                    and order_id not in seen_orders
                    and isinstance(items_required, list)
                    and all(isinstance(v, str) for v in items_required)
                ):
                    seen_orders.add(order_id)
                    orders.append(
                        SnapshotOrder(id=order_id, items_required=tuple(items_required)),
                    )

    if (
        grid_width is None
        or grid_height is None
        or walls is None
        or drop_off is None
        or not item_type_to_positions
    ):
        return None

    compact_item_positions = {
        item_type: tuple(sorted(positions))
        for item_type, positions in item_type_to_positions.items()
    }
    return Snapshot(
        date=date,
        level=level,
        grid_width=grid_width,
        grid_height=grid_height,
        walls=walls,
        drop_off=drop_off,
        item_type_to_positions=compact_item_positions,
        orders=tuple(orders),
    )


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


def latest_snapshot_path(level: str) -> Path | None:
    files = sorted(
        p for p in Path("data").glob(f"{level}_*.json") if "_plan" not in p.stem
    )
    if not files:
        return None
    return files[-1]


def _remaining_needed(order: SimOrder) -> list[str]:
    rem = list(order.required)
    for delivered in order.delivered:
        if delivered in rem:
            rem.remove(delivered)
    return rem


def _active_order_snapshot(active: SimOrder | None) -> tuple[str | None, list[str]]:
    if active is None:
        return None, []
    return active.id, sorted(_remaining_needed(active))


def _apply_boundary_carryover(
    active: SimOrder,
    bots: list[SimBot],
    drop_off: Position,
) -> int:
    """Consume newly-active order items from carried inventory in same tick."""
    rem = Counter(_remaining_needed(active))
    if not rem:
        return 0
    delivered = 0
    for bot in sorted(bots, key=lambda b: b.id):
        if bot.pos != drop_off or not bot.inventory:
            continue
        kept: list[str] = []
        for item in bot.inventory:
            if rem[item] > 0:
                rem[item] -= 1
                active.delivered.append(item)
                delivered += 1
            else:
                kept.append(item)
        bot.inventory = kept
        if not any(rem.values()):
            break
    return delivered


def _multi_source_dist(starts: set[Position], grid: PassableGrid) -> dict[Position, int]:
    dist: dict[Position, int] = {}
    queue: deque[Position] = deque()
    for s in starts:
        if grid.is_passable(s):
            dist[s] = 0
            queue.append(s)
    while queue:
        cur = queue.popleft()
        nxt_dist = dist[cur] + 1
        for nb in grid.neighbors(cur):
            if nb not in dist:
                dist[nb] = nxt_dist
                queue.append(nb)
    return dist


def _preview_need(
    next_order: SimOrder | None,
    active_need: Counter[str],
    bots: list[SimBot],
) -> Counter[str]:
    if next_order is None:
        return Counter()
    need = Counter(next_order.required)
    # Inventory already covers some preview. Active coverage has priority.
    inv_pool: Counter[str] = Counter()
    for bot in bots:
        inv_pool.update(bot.inventory)
    active_cover = active_need.copy()
    for item, count in list(inv_pool.items()):
        use = min(active_cover[item], count)
        if use:
            active_cover[item] -= use
            inv_pool[item] -= use
            if inv_pool[item] <= 0:
                inv_pool.pop(item, None)
    need.subtract(inv_pool)
    return Counter({k: v for k, v in need.items() if v > 0})


def _active_uncovered(active_need: Counter[str], bots: list[SimBot]) -> Counter[str]:
    pool: Counter[str] = Counter()
    for bot in bots:
        pool.update(bot.inventory)
    rem = active_need.copy()
    rem.subtract(pool)
    return Counter({k: v for k, v in rem.items() if v > 0})


def _count_active_in_inventory(inv: list[str], active_need: Counter[str]) -> int:
    tmp = active_need.copy()
    count = 0
    for item in inv:
        if tmp[item] > 0:
            tmp[item] -= 1
            count += 1
    return count


def _assign_targets(
    bots: list[SimBot],
    pickup_bot_ids: list[int],
    active_units: list[str],
    preview_units: list[str],
    dist_to_type: dict[str, dict[Position, int]],
) -> dict[int, str]:
    units: list[tuple[str, str]] = [("active", t) for t in active_units] + [
        ("preview", t) for t in preview_units
    ]
    if not pickup_bot_ids or not units:
        return {}

    best_key: tuple[int, int, int, tuple[int, ...]] | None = None
    best_map: dict[int, str] = {}

    def rec(
        idx: int,
        used: set[int],
        assign: dict[int, int],
    ) -> None:
        nonlocal best_key, best_map
        if idx == len(pickup_bot_ids):
            covered_active = 0
            covered_preview = 0
            cost = 0
            sig: list[int] = []
            for bot_id in pickup_bot_ids:
                unit_idx = assign.get(bot_id, -1)
                sig.append(unit_idx)
                if unit_idx < 0:
                    continue
                kind, item_type = units[unit_idx]
                dmap = dist_to_type.get(item_type, {})
                d = dmap.get(bots[bot_id].pos, 10**6)
                weight = 1 if kind == "active" else 2
                cost += d * weight
                if kind == "active":
                    covered_active += 1
                else:
                    covered_preview += 1
            key = (-covered_active, -covered_preview, cost, tuple(sig))
            if best_key is None or key < best_key:
                best_key = key
                best_map = {
                    bot_id: units[unit_idx][1]
                    for bot_id, unit_idx in assign.items()
                    if unit_idx >= 0
                }
            return

        bot_id = pickup_bot_ids[idx]
        rec(idx + 1, used, assign)
        for unit_idx in range(len(units)):
            if unit_idx in used:
                continue
            used.add(unit_idx)
            assign[bot_id] = unit_idx
            rec(idx + 1, used, assign)
            used.remove(unit_idx)
            assign.pop(bot_id, None)

    rec(0, set(), {})
    return best_map


def _nearest_pick_cell(
    start: Position,
    item_type: str,
    type_to_cells: dict[str, tuple[Position, ...]],
    grid: PassableGrid,
    blocked: set[Position],
) -> tuple[Position | None, list[Position]]:
    best_goal: Position | None = None
    best_path: list[Position] = []
    best_len = 10**9
    for goal in type_to_cells.get(item_type, ()):
        # Allow moving onto goal even if blocked set contains it.
        eff_blocked = blocked - {goal}
        path = astar(start, goal, grid, blocked=frozenset(eff_blocked))
        if path and len(path) < best_len:
            best_len = len(path)
            best_path = path
            best_goal = goal
    return best_goal, best_path


def plan_medium_v5(
    snapshot: Snapshot,
    spawns: list[Position],
    max_orders: int,
    round_cap: int,
) -> dict[str, object]:
    orders = [
        SimOrder(id=o.id, required=list(o.items_required), delivered=[])
        for o in snapshot.orders[:max_orders]
    ]
    bots = [SimBot(id=i, pos=spawns[i], inventory=[]) for i in range(NUM_BOTS)]
    active_idx = 0
    score = 0
    items_delivered = 0
    orders_completed = 0
    checkpoints: list[dict[str, object]] = []
    actions_out: list[dict[str, object]] = []
    order_starts: dict[int, int] = {0: 0}
    order_summaries: list[dict[str, object]] = []

    grid = build_grid(snapshot, spawns[0])
    type_to_cells: dict[str, set[Position]] = {}
    pickable_types: dict[Position, set[str]] = {}
    for item_type, shelves in snapshot.item_type_to_positions.items():
        for shelf in shelves:
            for cell in adjacent_walkable(shelf, grid):
                type_to_cells.setdefault(item_type, set()).add(cell)
                pickable_types.setdefault(cell, set()).add(item_type)
    type_to_cells_tuple = {
        item_type: tuple(sorted(cells))
        for item_type, cells in type_to_cells.items()
    }
    dist_to_type = {
        item_type: _multi_source_dist(set(cells), grid)
        for item_type, cells in type_to_cells_tuple.items()
    }

    def active_order() -> SimOrder | None:
        if active_idx >= len(orders):
            return None
        return orders[active_idx]

    def preview_order() -> SimOrder | None:
        nxt = active_idx + 1
        if nxt >= len(orders):
            return None
        return orders[nxt]

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
        nonlocal active_idx, score, items_delivered, orders_completed
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
            carry = _apply_boundary_carryover(
                orders[active_idx],
                bots,
                snapshot.drop_off,
            )
            if carry:
                score += carry
                items_delivered += carry

    for round_no in range(round_cap):
        active = active_order()
        active_id, active_needed_list = _active_order_snapshot(active)
        checkpoints.append(
            {
                "round": round_no,
                "active_order_id": active_id,
                "active_needed": active_needed_list,
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

        active_need = Counter(active_needed_list)
        uncovered = _active_uncovered(active_need, bots)
        next_order = preview_order()
        preview_need = _preview_need(next_order, active_need, bots)

        forced_deliver: set[int] = set()
        inv_active_counts: dict[int, int] = {}
        for bot in bots:
            inv_active = _count_active_in_inventory(bot.inventory, active_need)
            inv_active_counts[bot.id] = inv_active
            if len(bot.inventory) >= INVENTORY_MAX:
                forced_deliver.add(bot.id)
            elif inv_active >= 2:
                forced_deliver.add(bot.id)
            elif inv_active > 0 and not uncovered:
                forced_deliver.add(bot.id)

        pickup_bot_ids = [
            bot.id
            for bot in bots
            if bot.id not in forced_deliver and len(bot.inventory) < INVENTORY_MAX
        ]
        active_units = list(uncovered.elements())
        allow_preview = (not active_units) and (len(forced_deliver) <= 1)
        preview_units = list(preview_need.elements()) if allow_preview else []
        targets = _assign_targets(
            bots=bots,
            pickup_bot_ids=pickup_bot_ids,
            active_units=active_units,
            preview_units=preview_units,
            dist_to_type=dist_to_type,
        )

        counts: dict[Position, int] = {}
        for bot in bots:
            counts[bot.pos] = counts.get(bot.pos, 0) + 1
        round_actions: list[dict[str, object]] = []

        for bot in sorted(bots, key=lambda b: b.id):
            current_active_need = Counter(_remaining_needed(active))
            has_drop_item = any(current_active_need[it] > 0 for it in bot.inventory)
            if bot.pos == snapshot.drop_off and has_drop_item:
                round_actions.append(
                    {"round": round_no, "bot": bot.id, "action": "drop_off"}
                )
                apply_drop(bot, active)
                continue

            # Keep drop-off traversable: if a bot is idling on drop-off while other
            # bots are carrying active-order items, proactively step off.
            if bot.pos == snapshot.drop_off and not has_drop_item:
                waiting_deliverers = [
                    other
                    for other in bots
                    if (
                        other.id != bot.id
                        and other.pos != snapshot.drop_off
                        and any(current_active_need[it] > 0 for it in other.inventory)
                    )
                ]
                if waiting_deliverers:
                    free_neighbors = [
                        nb
                        for nb in grid.neighbors(bot.pos)
                        if counts.get(nb, 0) <= 0 and nb != snapshot.drop_off
                    ]
                    if free_neighbors:
                        nxt = max(
                            free_neighbors,
                            key=lambda nb: (
                                min(
                                    abs(nb[0] - other.pos[0]) + abs(nb[1] - other.pos[1])
                                    for other in waiting_deliverers
                                ),
                                nb[0],
                                nb[1],
                            ),
                        )
                        counts[bot.pos] -= 1
                        if counts[bot.pos] == 0:
                            counts.pop(bot.pos, None)
                        counts[nxt] = counts.get(nxt, 0) + 1
                        prev = bot.pos
                        bot.pos = nxt
                        round_actions.append(
                            {
                                "round": round_no,
                                "bot": bot.id,
                                "action": direction_for_move(prev, nxt),
                            },
                        )
                        continue

            target_type = targets.get(bot.id)
            if bot.id in forced_deliver and bot.inventory:
                target_cell = snapshot.drop_off
                blocked = {
                    pos
                    for pos, c in counts.items()
                    if c > 0 and pos != bot.pos
                }
                path = astar(
                    bot.pos,
                    target_cell,
                    grid,
                    blocked=frozenset(blocked - {target_cell}),
                )
                if path and len(path) >= 2:
                    nxt = path[1]
                    if grid.is_passable(nxt) and counts.get(nxt, 0) <= 0:
                        counts[bot.pos] -= 1
                        if counts[bot.pos] == 0:
                            counts.pop(bot.pos, None)
                        counts[nxt] = counts.get(nxt, 0) + 1
                        prev = bot.pos
                        bot.pos = nxt
                        round_actions.append(
                            {
                                "round": round_no,
                                "bot": bot.id,
                                "action": direction_for_move(prev, nxt),
                            },
                        )
                        continue

            if target_type is not None and len(bot.inventory) < INVENTORY_MAX:
                if target_type in pickable_types.get(bot.pos, set()):
                    bot.inventory.append(target_type)
                    round_actions.append(
                        {
                            "round": round_no,
                            "bot": bot.id,
                            "action": "pick_up",
                            "item_type": target_type,
                        },
                    )
                    continue

                blocked = {
                    pos
                    for pos, c in counts.items()
                    if c > 0 and pos != bot.pos
                }
                _goal, path = _nearest_pick_cell(
                    start=bot.pos,
                    item_type=target_type,
                    type_to_cells=type_to_cells_tuple,
                    grid=grid,
                    blocked=blocked,
                )
                if path and len(path) >= 2:
                    nxt = path[1]
                    if grid.is_passable(nxt) and counts.get(nxt, 0) <= 0:
                        counts[bot.pos] -= 1
                        if counts[bot.pos] == 0:
                            counts.pop(bot.pos, None)
                        counts[nxt] = counts.get(nxt, 0) + 1
                        prev = bot.pos
                        bot.pos = nxt
                        round_actions.append(
                            {
                                "round": round_no,
                                "bot": bot.id,
                                "action": direction_for_move(prev, nxt),
                            },
                        )
                        continue

            round_actions.append({"round": round_no, "bot": bot.id, "action": "wait"})

        actions_out.extend(round_actions)
        handle_completion_chain(round_no + 1)
        if active_idx >= len(orders):
            break

    return {
        "rounds_used": len({a["round"] for a in actions_out}),
        "score": score,
        "items_delivered": items_delivered,
        "orders_completed": orders_completed,
        "actions": actions_out,
        "checkpoints": checkpoints,
        "orders": order_summaries,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Offline medium v5 plan builder.")
    parser.add_argument("--level", default="medium")
    parser.add_argument("--date", default=None)
    parser.add_argument("--snapshot", default=None)
    parser.add_argument("--output", default=None)
    parser.add_argument("--spawns", default="14,10 14,10 14,10")
    parser.add_argument("--max-orders", type=int, default=12)
    parser.add_argument("--round-cap", type=int, default=300)
    parser.add_argument("--baseline-rounds", type=int, default=300)
    parser.add_argument("--current-run", default=None)
    args = parser.parse_args()

    replay_path = Path(args.current_run) if args.current_run else latest_replay_file()

    if args.snapshot:
        snapshot_path = Path(args.snapshot)
        if not snapshot_path.exists():
            raise SystemExit(f"Snapshot not found: {snapshot_path}")
    else:
        target_date = args.date or datetime.now(tz=UTC).strftime("%Y-%m-%d")
        candidate = Path("data") / f"{args.level}_{target_date}.json"
        if candidate.exists():
            snapshot_path = candidate
        else:
            if args.date:
                if replay_path and replay_path.exists():
                    built = build_snapshot_from_replay(
                        path=replay_path,
                        level=args.level,
                        date=target_date,
                    )
                    if built is None:
                        raise SystemExit(
                            f"Snapshot not found for {args.level} date {target_date}, "
                            f"and replay {replay_path} did not contain enough state "
                            "to build one."
                        )
                    save_snapshot(built, candidate)
                    print(
                        f"Snapshot for {args.level} date {target_date} was missing. "
                        f"Built snapshot from replay: {candidate}"
                    )
                    snapshot_path = candidate
                else:
                    raise SystemExit(
                        f"Snapshot not found for {args.level} date {target_date}. "
                        "Run one game first or pass --current-run with a replay file."
                    )
            else:
                fallback = latest_snapshot_path(args.level)
                if fallback is None:
                    raise SystemExit(
                        f"Snapshot not found for {args.level} date {target_date}, and no "
                        "fallback snapshot exists in data/."
                    )
                print(
                    f"Snapshot for {args.level} date {target_date} not found. "
                    f"Using latest available snapshot: {fallback}"
                )
                snapshot_path = fallback

    snapshot = load_snapshot(snapshot_path)
    if replay_path and replay_path.exists():
        replay_orders = orders_from_replay(replay_path)
        if replay_orders:
            merged = merge_snapshot_orders(snapshot, replay_orders)
            if len(merged.orders) > len(snapshot.orders):
                save_snapshot(merged, snapshot_path)
            snapshot = merged

    spawns = parse_spawns(args.spawns)
    sim = plan_medium_v5(
        snapshot=snapshot,
        spawns=spawns,
        max_orders=args.max_orders,
        round_cap=args.round_cap,
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
        else Path("data") / f"{args.level}_{snapshot.date}_plan_v5.json"
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
            "planner_mode": "multi_bot_assignment_prioritized_astar",
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


if __name__ == "__main__":
    main()
