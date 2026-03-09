from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any


BASE_DIR = Path(__file__).resolve().parent
SIM_DIR = BASE_DIR.parent / "grocerybot-simulator"


def _load_parse_replay():
    if str(SIM_DIR) not in sys.path:
        sys.path.insert(0, str(SIM_DIR))
    from parser import parse_replay  # type: ignore

    return parse_replay


def _active_order(state: dict[str, Any]) -> dict[str, Any] | None:
    for order in state.get("orders", []):
        if order.get("status") == "active":
            return order
    return None


def _round_score(rounds: list[Any], target_round: int) -> int:
    score = 0
    for rnd in rounds:
        if int(rnd.round) > target_round:
            break
        score = int(rnd.game_state.get("score", score))
    return score


def analyze_replay(path: Path, early_round: int) -> dict[str, Any]:
    parse_replay = _load_parse_replay()
    game = parse_replay(path)

    orders_by_round = 0
    score_by_round = _round_score(game.rounds, early_round)
    orders_by_round = 0

    longest_starvation = 0
    current_starvation = 0
    starvation_start: int | None = None
    longest_starvation_start: int | None = None
    longest_starvation_end: int | None = None

    last_active_id: str | None = None
    last_active_progress = 0
    all_wait_rounds: list[int] = []
    progress_rounds: list[int] = []

    for rnd in game.rounds:
        state = rnd.game_state
        round_num = int(rnd.round)
        if round_num <= early_round:
            orders_by_round = max(orders_by_round, int(state.get("active_order_index", 0)))

        actions = rnd.actions or []
        if actions and all(a.get("action") == "wait" for a in actions):
            all_wait_rounds.append(round_num)

        active = _active_order(state)
        active_id = active.get("id") if active else None
        active_progress = len(active.get("items_delivered", [])) if active else 0

        progress = False
        if last_active_id is None:
            progress = True
        elif active_id != last_active_id:
            progress = True
        elif active_progress > last_active_progress:
            progress = True

        if progress:
            progress_rounds.append(round_num)
            if current_starvation > longest_starvation:
                longest_starvation = current_starvation
                longest_starvation_start = starvation_start
                longest_starvation_end = round_num - 1
            current_starvation = 0
            starvation_start = round_num + 1
        else:
            if starvation_start is None:
                starvation_start = round_num
            current_starvation += 1

        last_active_id = active_id
        last_active_progress = active_progress

    if current_starvation > longest_starvation:
        longest_starvation = current_starvation
        longest_starvation_start = starvation_start
        longest_starvation_end = game.rounds[-1].round if game.rounds else None

    return {
        "path": str(path),
        "final_score": int(game.final_score),
        "final_orders": int(game.orders_completed),
        "final_items": int(game.items_delivered),
        "score_round_100": score_by_round,
        "orders_round_100": orders_by_round,
        "longest_starvation": int(longest_starvation),
        "longest_starvation_start": longest_starvation_start,
        "longest_starvation_end": longest_starvation_end,
        "all_wait_rounds": all_wait_rounds,
        "all_wait_count": len(all_wait_rounds),
        "progress_rounds_sample": progress_rounds[:20],
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Analyze Expert replay tempo and starvation metrics."
    )
    parser.add_argument("replays", nargs="+", type=Path, help="Replay JSONL file(s) to analyze.")
    parser.add_argument(
        "--early-round",
        type=int,
        default=100,
        help="Round cutoff for early-tempo metrics (default: 100).",
    )
    args = parser.parse_args()

    for replay in args.replays:
        result = analyze_replay(replay.resolve(), int(args.early_round))
        print(f"Replay: {result['path']}")
        print(
            f"  Final: score={result['final_score']} orders={result['final_orders']} items={result['final_items']}"
        )
        print(
            f"  Round {args.early_round}: score={result['score_round_100']} "
            f"orders={result['orders_round_100']}"
        )
        print(
            f"  Longest active-order starvation: {result['longest_starvation']} rounds "
            f"({result['longest_starvation_start']} -> {result['longest_starvation_end']})"
        )
        print(f"  All-wait rounds: {result['all_wait_count']}")
        if result["all_wait_rounds"]:
            sample = result["all_wait_rounds"][:12]
            print(f"    sample: {sample}")
        print(f"  Progress rounds sample: {result['progress_rounds_sample']}")
        print("")


if __name__ == "__main__":
    main()
