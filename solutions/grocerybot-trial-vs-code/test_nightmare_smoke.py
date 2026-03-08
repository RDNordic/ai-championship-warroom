from __future__ import annotations

import argparse
import os
import random
import statistics
import time
from pathlib import Path
from typing import Any


BASE_DIR = Path(__file__).resolve().parent
RUN_NIGHTMARE_PATH = BASE_DIR / "run_nightmare.py"
VALID_ACTIONS = {"move_up", "move_down", "move_left", "move_right", "pick_up", "drop_off", "wait"}
MOVE_DELTAS = {
    "move_up": (0, -1),
    "move_down": (0, 1),
    "move_left": (-1, 0),
    "move_right": (1, 0),
}
ITEM_TYPES = [
    "milk",
    "bread",
    "eggs",
    "cheese",
    "butter",
    "yogurt",
    "apple",
    "banana",
    "orange",
    "tomato",
    "potato",
    "onion",
    "carrot",
    "chicken",
    "beef",
    "fish",
    "rice",
    "pasta",
    "beans",
    "cereal",
    "coffee",
]


def _load_trialbot_namespace() -> dict[str, Any]:
    source = RUN_NIGHTMARE_PATH.read_text(encoding="utf-8")
    marker = "asyncio.run(main())"
    if marker not in source:
        raise RuntimeError(f"Unable to find module entrypoint marker in {RUN_NIGHTMARE_PATH}")

    # Avoid websocket execution while reusing bot logic as-is.
    source = source.replace(marker, "", 1)
    os.environ.setdefault("GROCERY_BOT_TOKEN_NIGHTMARE", "offline-token")

    namespace: dict[str, Any] = {
        "__name__": "offline_run_nightmare",
        "__file__": str(RUN_NIGHTMARE_PATH),
    }
    exec(compile(source, str(RUN_NIGHTMARE_PATH), "exec"), namespace)
    return namespace


def _build_layout(width: int, height: int) -> tuple[list[list[int]], list[tuple[int, int]]]:
    walls: set[tuple[int, int]] = set()
    shelf_cells: list[tuple[int, int]] = []

    for x in range(width):
        walls.add((x, 0))
        walls.add((x, height - 1))
    for y in range(height):
        walls.add((0, y))
        walls.add((width - 1, y))

    shelf_columns: list[int] = []
    for aisle_idx in range(6):
        base = 2 + aisle_idx * 4
        shelf_columns.extend([base, base + 1])

    corridor_rows = {2, height // 2, height - 3}
    for y in range(1, height - 1):
        if y in corridor_rows:
            continue
        for x in shelf_columns:
            if 1 <= x < width - 1:
                walls.add((x, y))
                shelf_cells.append((x, y))

    walls_sorted = [[x, y] for x, y in sorted(walls)]
    return walls_sorted, shelf_cells


def _build_items(rng: random.Random, shelf_cells: list[tuple[int, int]]) -> list[dict[str, Any]]:
    if not shelf_cells:
        raise RuntimeError("No shelf cells available for synthetic nightmare state")

    items: list[dict[str, Any]] = []
    item_index = 0
    for item_type in ITEM_TYPES:
        for _ in range(2):
            pos = rng.choice(shelf_cells)
            items.append(
                {
                    "id": f"item_{item_index}",
                    "type": item_type,
                    "position": [pos[0], pos[1]],
                }
            )
            item_index += 1
    return items


def _build_orders(rng: random.Random) -> list[dict[str, Any]]:
    def one_order(order_id: str, status: str) -> dict[str, Any]:
        needed = [rng.choice(ITEM_TYPES) for _ in range(rng.randint(4, 6))]
        return {
            "id": order_id,
            "items_required": needed,
            "items_delivered": [],
            "complete": False,
            "status": status,
        }

    return [one_order("order_active", "active"), one_order("order_preview", "preview")]


def _build_bots(
    rng: random.Random,
    width: int,
    height: int,
    walls: set[tuple[int, int]],
    count: int = 20,
) -> list[dict[str, Any]]:
    spawn_candidates: list[tuple[int, int]] = []
    for y in range(max(1, height - 6), height - 1):
        for x in range(max(1, width - 8), width - 1):
            if (x, y) not in walls:
                spawn_candidates.append((x, y))
    if len(spawn_candidates) < count:
        raise RuntimeError("Not enough spawn candidates to place 20 bots")

    chosen = rng.sample(spawn_candidates, count)
    return [
        {"id": bot_id, "position": [chosen[bot_id][0], chosen[bot_id][1]], "inventory": []}
        for bot_id in range(count)
    ]


def build_synthetic_nightmare_state(seed: int) -> tuple[dict[str, Any], set[tuple[int, int]], dict[str, str]]:
    rng = random.Random(seed)
    width = 30
    height = 18
    walls_list, shelf_cells = _build_layout(width=width, height=height)
    walls_set = {tuple(w) for w in walls_list}
    items = _build_items(rng, shelf_cells)
    item_type_by_id = {item["id"]: item["type"] for item in items}
    bots = _build_bots(rng, width=width, height=height, walls=walls_set, count=20)
    drop_off_zones = [[1, height - 2], [width - 2, height - 2], [width // 2, 1]]

    state = {
        "type": "game_state",
        "round": 0,
        "max_rounds": 500,
        "grid": {
            "width": width,
            "height": height,
            "walls": walls_list,
        },
        "bots": bots,
        "items": items,
        "orders": _build_orders(rng),
        "drop_off": drop_off_zones[0],
        "drop_off_zones": drop_off_zones,
        "score": 0,
        "active_order_index": 0,
        "total_orders": 999,
    }
    return state, walls_set, item_type_by_id


def _validate_actions(state: dict[str, Any], actions: list[dict[str, Any]]) -> None:
    expected_bot_ids = {int(bot["id"]) for bot in state["bots"]}
    seen_bot_ids: set[int] = set()

    if len(actions) != len(expected_bot_ids):
        raise RuntimeError(f"Expected {len(expected_bot_ids)} actions, got {len(actions)}")

    for action in actions:
        bot_id = action.get("bot")
        name = action.get("action")
        if not isinstance(bot_id, int):
            raise RuntimeError(f"Action missing int bot id: {action}")
        if bot_id in seen_bot_ids:
            raise RuntimeError(f"Duplicate action for bot {bot_id}")
        seen_bot_ids.add(bot_id)
        if bot_id not in expected_bot_ids:
            raise RuntimeError(f"Unknown bot id in action: {bot_id}")
        if name not in VALID_ACTIONS:
            raise RuntimeError(f"Invalid action name: {name}")
        if name == "pick_up":
            item_id = action.get("item_id")
            if not isinstance(item_id, str) or not item_id:
                raise RuntimeError(f"pick_up missing item_id: {action}")


def _apply_actions(
    state: dict[str, Any],
    actions: list[dict[str, Any]],
    walls: set[tuple[int, int]],
    item_type_by_id: dict[str, str],
) -> None:
    width = int(state["grid"]["width"])
    height = int(state["grid"]["height"])
    drop_zones = {tuple(z) for z in state.get("drop_off_zones", [])}
    if not drop_zones and state.get("drop_off") is not None:
        drop_zones = {tuple(state["drop_off"])}
    item_pos_by_id = {item["id"]: tuple(item["position"]) for item in state["items"]}

    bots = sorted(state["bots"], key=lambda b: b["id"])
    action_by_id = {int(a["bot"]): a for a in actions}
    occupied = {tuple(bot["position"]) for bot in bots}

    for bot in bots:
        bot_id = int(bot["id"])
        action = action_by_id.get(bot_id, {"bot": bot_id, "action": "wait"})
        name = action["action"]
        pos = tuple(bot["position"])

        if name in MOVE_DELTAS:
            dx, dy = MOVE_DELTAS[name]
            nxt = (pos[0] + dx, pos[1] + dy)
            if (
                0 <= nxt[0] < width
                and 0 <= nxt[1] < height
                and nxt not in walls
                and nxt not in occupied
            ):
                occupied.remove(pos)
                occupied.add(nxt)
                bot["position"] = [nxt[0], nxt[1]]
            continue

        if name == "pick_up":
            if len(bot["inventory"]) >= 3:
                continue
            item_id = action.get("item_id")
            if item_id not in item_pos_by_id:
                continue
            item_pos = item_pos_by_id[item_id]
            if abs(item_pos[0] - pos[0]) + abs(item_pos[1] - pos[1]) == 1:
                bot["inventory"].append(item_type_by_id[item_id])
            continue

        if name == "drop_off":
            if pos in drop_zones:
                bot["inventory"] = []


def _percentile(values: list[float], pct: float) -> float:
    if not values:
        return 0.0
    idx = int((len(values) - 1) * pct)
    return sorted(values)[idx]


def run_smoke(rounds: int, seed: int, progress_every: int) -> int:
    namespace = _load_trialbot_namespace()
    trial_bot_cls = namespace["TrialBot"]
    sanitize_actions = namespace["sanitize_actions"]
    nightmare_shape_summary = namespace.get("nightmare_shape_summary")

    state, walls, item_type_by_id = build_synthetic_nightmare_state(seed=seed)
    if callable(nightmare_shape_summary):
        print(f"Synthetic state summary: {nightmare_shape_summary(state)}")

    bot = trial_bot_cls()
    timings_ms: list[float] = []

    print(
        f"Nightmare smoke start: rounds={rounds}, bots={len(state['bots'])}, "
        f"grid={state['grid']['width']}x{state['grid']['height']}, seed={seed}"
    )

    for rnd in range(rounds):
        state["round"] = rnd
        t0 = time.perf_counter()
        planned = bot.decide(state)
        dt_ms = (time.perf_counter() - t0) * 1000.0
        timings_ms.append(dt_ms)

        safe_actions = sanitize_actions(state, planned)
        _validate_actions(state, safe_actions)
        _apply_actions(state, safe_actions, walls=walls, item_type_by_id=item_type_by_id)

        if progress_every > 0 and (rnd % progress_every == 0 or rnd == rounds - 1):
            print(f"Round {rnd:3d} | plan_ms={dt_ms:.2f}")

    max_ms = max(timings_ms)
    avg_ms = statistics.fmean(timings_ms)
    p95_ms = _percentile(timings_ms, 0.95)
    print("")
    print(
        f"Smoke result: rounds={rounds}, avg_ms={avg_ms:.2f}, "
        f"p95_ms={p95_ms:.2f}, max_ms={max_ms:.2f}"
    )
    if max_ms > 1800.0:
        print("WARNING: planner exceeded 1800ms in smoke test")
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Offline nightmare smoke test for run_nightmare TrialBot."
    )
    parser.add_argument(
        "--rounds",
        type=int,
        default=40,
        help="Number of synthetic rounds to simulate.",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=42,
        help="Random seed for deterministic synthetic state.",
    )
    parser.add_argument(
        "--progress-every",
        type=int,
        default=10,
        help="Print progress every N rounds (0 disables periodic output).",
    )
    args = parser.parse_args()
    run_smoke(
        rounds=max(1, int(args.rounds)),
        seed=int(args.seed),
        progress_every=max(0, int(args.progress_every)),
    )


if __name__ == "__main__":
    main()
