"""Deep replay analysis: per-round inventory + action detail around stall points."""

import json
import sys
from pathlib import Path


def analyze(path: Path) -> None:
    lines = path.read_text(encoding="utf-8").strip().splitlines()

    states: list[dict] = []
    responses: list[dict] = []

    for line in lines:
        obj = json.loads(line)
        if obj.get("type") == "game_state":
            states.append(obj)
        elif "actions" in obj:
            responses.append(obj)

    num_bots = len(states[0]["bots"])

    # Build per-round data: (round, bot_positions, bot_inventories, actions_sent, orders)
    print("=== Detailed Round-by-Round (stall-relevant rounds) ===\n")

    # Find score changes to identify interesting ranges
    score_changes: list[int] = []
    prev_score = 0
    for s in states:
        if s["score"] != prev_score:
            score_changes.append(s["round"])
            prev_score = s["score"]
    last_score_round = score_changes[-1] if score_changes else 0

    # Show rounds around last score change and the stall
    interesting = set()
    for sc in score_changes:
        for r in range(max(0, sc - 2), min(len(states), sc + 5)):
            interesting.add(r)
    # Also show first 5 rounds of stall + a few samples
    for r in range(last_score_round, min(len(states), last_score_round + 15)):
        interesting.add(r)
    # Sample every 50 rounds during stall
    for r in range(last_score_round + 50, len(states), 50):
        interesting.add(r)

    for rnd in sorted(interesting):
        if rnd >= len(states) or rnd >= len(responses):
            continue
        state = states[rnd]
        resp = responses[rnd]
        actions = resp.get("actions", [])
        action_map = {a["bot"]: a for a in actions}

        active_order = None
        preview_order = None
        for order in state["orders"]:
            if order["status"] == "active":
                active_order = order
            elif order["status"] == "preview":
                preview_order = order

        print(f"--- Round {state['round']} (score={state['score']}) ---")
        if active_order:
            remaining = list(active_order["items_required"])
            for d in active_order["items_delivered"]:
                if d in remaining:
                    remaining.remove(d)
            print(f"  Active order '{active_order['id']}': "
                  f"need={remaining} delivered={active_order['items_delivered']}")
        if preview_order:
            remaining = list(preview_order["items_required"])
            for d in preview_order["items_delivered"]:
                if d in remaining:
                    remaining.remove(d)
            print(f"  Preview order '{preview_order['id']}': need={remaining}")

        for bot in sorted(state["bots"], key=lambda b: b["id"]):
            bid = bot["id"]
            pos = tuple(bot["position"])
            inv = bot["inventory"]
            act = action_map.get(bid, {})
            act_str = act.get("action", "?")
            extra = ""
            if "item_id" in act:
                extra = f" (item_id={act['item_id']})"
            print(f"  Bot {bid}: pos={pos} inv={inv} -> {act_str}{extra}")
        print()


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python scripts/analyze_deep.py <replay.jsonl>")
        sys.exit(1)
    analyze(Path(sys.argv[1]))
