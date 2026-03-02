"""Replay a logged game through the engine and verify state matches at every round.

Usage:
    python validator.py [path_to_jsonl]

Defaults to the Easy 110 replay if no path given.
"""

import sys
from pathlib import Path
from parser import parse_replay
from engine import create_initial_state, step


def validate_replay(path: str | Path, verbose: bool = False) -> dict:
    """Replay a game log through the engine and compare states.

    Syncs engine state to logged state each round so timeout/lag events
    don't cascade into false mismatches.

    Returns a summary dict with:
      - match: bool (True if no logic mismatches)
      - rounds_checked: int
      - logic_mismatches: list of {round, field, expected, got}
      - timeout_rounds: list of int (rounds where server ignored all actions)
      - final_score_engine: int
      - final_score_logged: int
    """
    game = parse_replay(path)
    config = game.config

    # Determine inventory cap from observed data
    inv_cap = game.max_inventory_observed if game.max_inventory_observed > 0 else 3

    state = create_initial_state(config, game.orders_seen, inventory_cap=inv_cap)
    logic_mismatches = []
    timeout_rounds = []

    for rnd in game.rounds:
        logged = rnd.game_state
        rnd_num = rnd.round

        # --- Compare state BEFORE applying actions ---
        round_mismatches = []

        for i, bot in enumerate(state.bots):
            logged_pos = tuple(logged["bots"][i]["position"])
            if bot.position != logged_pos:
                round_mismatches.append({
                    "round": rnd_num,
                    "field": f"bot[{i}].position",
                    "expected": logged_pos,
                    "got": bot.position,
                })

        for i, bot in enumerate(state.bots):
            logged_inv = logged["bots"][i]["inventory"]
            if sorted(bot.inventory) != sorted(logged_inv):
                round_mismatches.append({
                    "round": rnd_num,
                    "field": f"bot[{i}].inventory",
                    "expected": logged_inv,
                    "got": bot.inventory,
                })

        logged_score = logged["score"]
        if state.score != logged_score:
            round_mismatches.append({
                "round": rnd_num,
                "field": "score",
                "expected": logged_score,
                "got": state.score,
            })

        logged_idx = logged["active_order_index"]
        if state.active_order_index != logged_idx:
            round_mismatches.append({
                "round": rnd_num,
                "field": "active_order_index",
                "expected": logged_idx,
                "got": state.active_order_index,
            })

        # Classify: timeout (all bots stayed put despite non-wait actions)
        # vs. logic error
        if round_mismatches:
            pos_only = all(m["field"].endswith(".position") for m in round_mismatches)
            all_stayed = all(
                tuple(logged["bots"][i]["position"]) ==
                tuple(game.rounds[rnd_num - 1].game_state["bots"][i]["position"])
                for i in range(len(state.bots))
            ) if rnd_num > 0 else False

            if pos_only and all_stayed:
                timeout_rounds.append(rnd_num)
            else:
                logic_mismatches.extend(round_mismatches)
                if verbose:
                    print(f"LOGIC MISMATCH at round {rnd_num}:")
                    for m in round_mismatches:
                        print(f"  {m['field']}: expected={m['expected']} got={m['got']}")

        # Sync engine state to logged state (prevents cascade)
        for i, bot in enumerate(state.bots):
            bot.position = tuple(logged["bots"][i]["position"])
            bot.inventory = list(logged["bots"][i]["inventory"])
        state.score = logged["score"]
        state.active_order_index = logged["active_order_index"]
        # Sync order delivery state
        for logged_order in logged["orders"]:
            for eng_order in state.orders:
                if eng_order.id == logged_order["id"]:
                    eng_order.items_delivered = list(logged_order["items_delivered"])
                    eng_order.complete = logged_order["complete"]
                    break

        # Apply actions
        if rnd.actions:
            state, _ = step(state, rnd.actions)

    return {
        "match": len(logic_mismatches) == 0,
        "rounds_checked": game.rounds[-1].round if game.rounds else 0,
        "logic_mismatches": logic_mismatches,
        "timeout_rounds": timeout_rounds,
        "final_score_engine": state.score,
        "final_score_logged": game.final_score,
    }


def main():
    default = "../grocerybot-trial-vs-code/logs/game_20260301_211903.jsonl"
    path = sys.argv[1] if len(sys.argv) > 1 else default
    verbose = "--verbose" in sys.argv or "-v" in sys.argv

    print(f"Validating: {path}")
    result = validate_replay(path, verbose=verbose)

    timeouts = result["timeout_rounds"]
    logic_errs = result["logic_mismatches"]

    if result["match"]:
        print(f"ENGINE LOGIC: ALL ROUNDS MATCH!")
    else:
        print(f"ENGINE LOGIC: {len(logic_errs)} mismatch(es)")
        for m in logic_errs[:10]:
            print(f"  Round {m['round']}: {m['field']} expected={m['expected']} got={m['got']}")

    if timeouts:
        print(f"TIMEOUT ROUNDS: {len(timeouts)} (server ignored actions)")
        if verbose:
            print(f"  Rounds: {timeouts}")

    print(f"  Rounds checked: {result['rounds_checked']}")
    print(f"  Final score (logged): {result['final_score_logged']}")


if __name__ == "__main__":
    main()
