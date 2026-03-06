from __future__ import annotations

import argparse
import os
import random
import sys
from pathlib import Path
from typing import Any


BASE_DIR = Path(__file__).resolve().parent
SIM_DIR = BASE_DIR.parent / "grocerybot-simulator"
DEFAULT_REPLAY = BASE_DIR / "logs" / "game_hard_99_20260301_223438.jsonl"


def _load_simulator_modules() -> tuple[Any, Any, Any]:
    if not SIM_DIR.exists():
        raise RuntimeError(f"Simulator directory not found: {SIM_DIR}")
    if str(SIM_DIR) not in sys.path:
        sys.path.insert(0, str(SIM_DIR))

    from parser import parse_replay  # type: ignore
    from engine import create_initial_state, step  # type: ignore

    return parse_replay, create_initial_state, step


def _load_trialbot_namespace() -> dict[str, Any]:
    run_hard_path = BASE_DIR / "run_hard.py"
    source = run_hard_path.read_text(encoding="utf-8")
    marker = "asyncio.run(main())"
    if marker not in source:
        raise RuntimeError(f"Unable to find module entrypoint marker in {run_hard_path}")

    # Prevent network run at import time while reusing bot logic verbatim.
    source = source.replace(marker, "", 1)
    os.environ.setdefault("GROCERY_BOT_TOKEN_HARD", "offline-token")

    namespace: dict[str, Any] = {
        "__name__": "offline_run_hard",
        "__file__": str(run_hard_path),
    }
    exec(compile(source, str(run_hard_path), "exec"), namespace)
    return namespace


def _orders_for_bot_view(state: Any) -> list[dict[str, Any]]:
    orders: list[dict[str, Any]] = []
    idx = int(state.active_order_index)

    if 0 <= idx < len(state.orders):
        active = state.orders[idx]
        orders.append(
            {
                "id": active.id,
                "items_required": list(active.items_required),
                "items_delivered": list(active.items_delivered),
                "complete": bool(active.complete),
                "status": "active",
            }
        )

    if 0 <= idx + 1 < len(state.orders):
        preview = state.orders[idx + 1]
        orders.append(
            {
                "id": preview.id,
                "items_required": list(preview.items_required),
                "items_delivered": list(preview.items_delivered),
                "complete": bool(preview.complete),
                "status": "preview",
            }
        )

    return orders


def _state_for_bot(state: Any, max_rounds: int, total_orders: int) -> dict[str, Any]:
    walls_sorted = [[x, y] for (x, y) in sorted(state.config.walls)]
    bots_sorted = sorted(state.bots, key=lambda b: b.id)

    return {
        "type": "game_state",
        "round": int(state.round),
        "max_rounds": int(max_rounds),
        "grid": {
            "width": int(state.config.width),
            "height": int(state.config.height),
            "walls": walls_sorted,
        },
        "bots": [
            {
                "id": int(bot.id),
                "position": [int(bot.position[0]), int(bot.position[1])],
                "inventory": list(bot.inventory),
            }
            for bot in bots_sorted
        ],
        "items": [
            {
                "id": item["id"],
                "type": item["type"],
                "position": [int(item["position"][0]), int(item["position"][1])],
            }
            for item in state.config.items
        ],
        "orders": _orders_for_bot_view(state),
        "drop_off": [int(state.config.drop_off[0]), int(state.config.drop_off[1])],
        "score": int(state.score),
        "active_order_index": int(state.active_order_index),
        "total_orders": int(total_orders),
    }


def run_offline(
    replay_path: Path,
    seed: int | None,
    progress_every: int,
    compare_actions: bool,
) -> int:
    parse_replay, create_initial_state, step = _load_simulator_modules()
    game = parse_replay(replay_path)

    namespace = _load_trialbot_namespace()
    trial_bot_cls = namespace["TrialBot"]
    sanitize_actions = namespace["sanitize_actions"]
    all_wait_actions = namespace["all_wait_actions"]

    if seed is not None:
        random.seed(seed)
        namespace_random = namespace.get("random")
        if namespace_random is not None and hasattr(namespace_random, "seed"):
            namespace_random.seed(seed)

    inv_cap = max(3, int(game.max_inventory_observed or 0))
    state = create_initial_state(game.config, game.orders_seen, inventory_cap=inv_cap)
    bot = trial_bot_cls()

    rounds = min(int(game.config.max_rounds), len(game.rounds))
    total_items_delivered = 0
    total_orders_completed = 0
    action_mismatch_rounds = 0
    first_action_mismatches: list[tuple[int, list[dict], list[dict]]] = []

    print(f"Replay source: {replay_path}")
    print(
        f"Offline run config: rounds={rounds}, bots={game.config.num_bots}, "
        f"orders_seen={len(game.orders_seen)}, seed={seed}"
    )

    for rnd in range(rounds):
        bot_state = _state_for_bot(
            state=state,
            max_rounds=game.config.max_rounds,
            total_orders=game.config.total_orders,
        )

        try:
            planned_actions = bot.decide(bot_state)
        except Exception as exc:
            print(f"Round {rnd}: planner error ({exc}); falling back to all wait actions")
            planned_actions = all_wait_actions(bot_state)

        safe_actions = sanitize_actions(bot_state, planned_actions)

        if compare_actions:
            logged_actions = game.rounds[rnd].actions
            if safe_actions != logged_actions:
                action_mismatch_rounds += 1
                if len(first_action_mismatches) < 5:
                    first_action_mismatches.append((rnd, logged_actions, safe_actions))

        state, results = step(state, safe_actions)
        total_items_delivered += sum(int(r.get("items_delivered", 0)) for r in results)
        total_orders_completed += sum(int(r.get("orders_completed", 0)) for r in results)

        if progress_every > 0 and (rnd % progress_every == 0 or rnd == rounds - 1):
            print(f"Round {rnd:3d} | score={state.score}")

    print("")
    print("Final comparison:")
    print(
        f"  Offline: score={state.score}, items={total_items_delivered}, "
        f"orders={total_orders_completed}"
    )
    print(
        f"  Logged : score={game.final_score}, items={game.items_delivered}, "
        f"orders={game.orders_completed}"
    )
    print(f"  Delta  : score={state.score - game.final_score}")

    if compare_actions:
        print(f"  Action mismatch rounds: {action_mismatch_rounds} / {rounds}")
        for rnd, logged_actions, offline_actions in first_action_mismatches:
            print(f"    Round {rnd}:")
            print(f"      logged : {logged_actions}")
            print(f"      offline: {offline_actions}")

    return int(state.score)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Offline harness: run run_hard TrialBot against local simulator engine."
    )
    parser.add_argument(
        "--replay",
        type=Path,
        default=DEFAULT_REPLAY,
        help="Replay JSONL used to extract map + order sequence.",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=42,
        help="Random seed for reproducible nudge behavior. Use -1 to disable seeding.",
    )
    parser.add_argument(
        "--progress-every",
        type=int,
        default=25,
        help="Print score every N rounds (use 1 for per-round output).",
    )
    parser.add_argument(
        "--compare-actions",
        action="store_true",
        help="Compare offline actions to logged replay actions round-by-round.",
    )
    args = parser.parse_args()

    replay_path = args.replay.resolve()
    if not replay_path.exists():
        raise SystemExit(f"Replay not found: {replay_path}")

    seed = None if args.seed == -1 else args.seed
    run_offline(
        replay_path=replay_path,
        seed=seed,
        progress_every=max(0, int(args.progress_every)),
        compare_actions=bool(args.compare_actions),
    )


if __name__ == "__main__":
    main()
