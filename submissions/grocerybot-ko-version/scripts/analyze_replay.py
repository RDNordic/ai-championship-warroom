"""Analyze a replay .jsonl for per-bot utilization and stall patterns."""

import json
import sys
from collections import Counter
from pathlib import Path


def analyze(path: Path) -> None:
    lines = path.read_text(encoding="utf-8").strip().splitlines()

    states: list[dict] = []
    responses: list[dict] = []
    strategy_diags: dict[int, dict] = {}
    game_over: dict | None = None

    for line in lines:
        obj = json.loads(line)
        if obj.get("type") == "game_state":
            states.append(obj)
        elif obj.get("type") == "game_over":
            game_over = obj
        elif obj.get("type") == "strategy_diagnostics":
            rnd = obj.get("round")
            if isinstance(rnd, int):
                strategy_diags[rnd] = obj
        elif "actions" in obj:
            responses.append(obj)

    if not states:
        print("No game_state entries found.")
        return

    num_bots = len(states[0]["bots"])
    total_rounds = len(states)
    print(f"=== Replay Analysis: {path.name} ===")
    print(f"Rounds: {total_rounds}, Bots: {num_bots}")
    if game_over:
        print(f"Final score: {game_over.get('score')}")
        print(f"Items delivered: {game_over.get('items_delivered')}")
        print(f"Orders completed: {game_over.get('orders_completed')}")
    print()

    # Track per-bot: actions sent, positions, waits, moves, pickups, dropoffs
    bot_actions: dict[int, Counter] = {i: Counter() for i in range(num_bots)}
    bot_positions: dict[int, list[tuple[int, int]]] = {i: [] for i in range(num_bots)}
    bot_stuck_streaks: dict[int, list[int]] = {i: [] for i in range(num_bots)}

    # Track positions from states
    for state in states:
        for bot in state["bots"]:
            bid = bot["id"]
            pos = tuple(bot["position"])
            bot_positions[bid].append(pos)

    # Track actions from responses
    for resp in responses:
        for act in resp.get("actions", []):
            bid = act.get("bot", 0)
            action_type = act.get("action", "wait")
            bot_actions[bid][action_type] += 1

    # Compute stuck streaks from positions (didn't actually move)
    for bid in range(num_bots):
        positions = bot_positions[bid]
        streak = 0
        for i in range(1, len(positions)):
            if positions[i] == positions[i - 1]:
                streak += 1
            else:
                if streak > 0:
                    bot_stuck_streaks[bid].append(streak)
                streak = 0
        if streak > 0:
            bot_stuck_streaks[bid].append(streak)

    # Per-bot summary
    print("--- Per-Bot Action Summary (from responses sent) ---")
    for bid in range(num_bots):
        acts = bot_actions[bid]
        total = sum(acts.values())
        waits = acts.get("wait", 0)
        moves = sum(v for k, v in acts.items() if k.startswith("move_"))
        picks = acts.get("pick_up", 0)
        drops = acts.get("drop_off", 0)
        wait_pct = (waits / total * 100) if total else 0
        print(f"  Bot {bid}: total={total}, wait={waits} ({wait_pct:.0f}%), "
              f"move={moves}, pick_up={picks}, drop_off={drops}")
    print()

    # Actual movement (position changed between rounds)
    print("--- Per-Bot Actual Movement (position changed) ---")
    for bid in range(num_bots):
        positions = bot_positions[bid]
        moved = sum(1 for i in range(1, len(positions)) if positions[i] != positions[i - 1])
        stationary = len(positions) - 1 - moved
        pct_stationary = (stationary / max(len(positions) - 1, 1)) * 100
        print(f"  Bot {bid}: moved={moved}, stationary={stationary} ({pct_stationary:.0f}%)")
    print()

    # Stuck streaks
    print("--- Per-Bot Stuck Streaks (consecutive rounds at same position) ---")
    for bid in range(num_bots):
        streaks = bot_stuck_streaks[bid]
        if not streaks:
            print(f"  Bot {bid}: no stuck streaks")
            continue
        print(f"  Bot {bid}: count={len(streaks)}, "
              f"max={max(streaks)}, avg={sum(streaks)/len(streaks):.1f}, "
              f"streaks>5: {sum(1 for s in streaks if s > 5)}, "
              f"streaks>10: {sum(1 for s in streaks if s > 10)}")
    print()

    # When do stuck streaks happen? Find round ranges for long streaks
    print("--- Long Stuck Streaks (>10 rounds) with round ranges ---")
    for bid in range(num_bots):
        positions = bot_positions[bid]
        streak_start = 0
        streak_len = 0
        for i in range(1, len(positions)):
            if positions[i] == positions[i - 1]:
                if streak_len == 0:
                    streak_start = i - 1
                streak_len += 1
            else:
                if streak_len > 10:
                    pos = positions[streak_start]
                    print(f"  Bot {bid}: rounds {streak_start}-{streak_start + streak_len} "
                          f"({streak_len} rounds) stuck at {pos}")
                streak_len = 0
        if streak_len > 10:
            pos = positions[streak_start]
            print(f"  Bot {bid}: rounds {streak_start}-{streak_start + streak_len} "
                  f"({streak_len} rounds) stuck at {pos}")
    print()

    # Score progression: when did score increase?
    print("--- Score Progression ---")
    prev_score = 0
    for state in states:
        score = state.get("score", 0)
        rnd = state.get("round", 0)
        if score != prev_score:
            print(f"  Round {rnd}: score {prev_score} -> {score}")
            prev_score = score
    print()

    # Order tracking
    print("--- Order Transitions ---")
    prev_active_id = None
    for state in states:
        rnd = state.get("round", 0)
        for order in state.get("orders", []):
            if order["status"] == "active" and order["id"] != prev_active_id:
                items = order["items_required"]
                delivered = order["items_delivered"]
                print(f"  Round {rnd}: new active order '{order['id']}' "
                      f"needs={items} delivered={delivered}")
                prev_active_id = order["id"]

    # Drop-off position
    drop_off = tuple(states[0]["drop_off"])
    print(f"\nDrop-off at: {drop_off}")

    # How often are bots near drop-off?
    print("\n--- Bot Proximity to Drop-off ---")
    for bid in range(num_bots):
        near = sum(1 for p in bot_positions[bid]
                   if abs(p[0] - drop_off[0]) + abs(p[1] - drop_off[1]) <= 2)
        pct = near / len(bot_positions[bid]) * 100
        print(f"  Bot {bid}: within 2 of drop-off for {near}/{len(bot_positions[bid])} "
              f"rounds ({pct:.0f}%)")

    # Inventory tracking: when do bots carry items vs empty?
    print("\n--- Inventory Utilization ---")
    for bid in range(num_bots):
        carrying = sum(1 for s in states if any(
            b["id"] == bid and len(b["inventory"]) > 0 for b in s["bots"]
        ))
        pct = carrying / len(states) * 100
        print(f"  Bot {bid}: carrying items {carrying}/{len(states)} rounds ({pct:.0f}%)")

    if strategy_diags:
        print("\n--- Strategy Diagnostics (if recorded) ---")
        strategies = Counter(
            str(entry.get("strategy", "unknown"))
            for entry in strategy_diags.values()
        )
        print(
            "  Diagnostics entries: "
            f"{len(strategy_diags)} (strategies={dict(strategies)})",
        )

        wait_reasons: dict[int, Counter] = {i: Counter() for i in range(num_bots)}
        blocked_ticks: dict[int, list[int]] = {i: [] for i in range(num_bots)}
        timed_out_rounds = 0
        traffic_block_rounds = 0
        traffic_block_total = 0
        hotspots: list[tuple[int, int]] = []

        for rnd, entry in sorted(strategy_diags.items()):
            diag = entry.get("diagnostics", {})
            if not isinstance(diag, dict):
                continue
            if bool(diag.get("timed_out")):
                timed_out_rounds += 1

            traffic_blocks = diag.get("traffic_blocks", 0)
            if isinstance(traffic_blocks, int):
                traffic_block_total += traffic_blocks
                if traffic_blocks > 0:
                    traffic_block_rounds += 1
                    hotspots.append((rnd, traffic_blocks))

            per_bot = diag.get("per_bot", {})
            if not isinstance(per_bot, dict):
                continue
            for bid_raw, payload in per_bot.items():
                if not isinstance(payload, dict):
                    continue
                try:
                    bid = int(bid_raw)
                except (TypeError, ValueError):
                    continue
                if bid not in wait_reasons:
                    wait_reasons[bid] = Counter()
                    blocked_ticks[bid] = []

                reason = payload.get("wait_reason")
                if isinstance(reason, str):
                    wait_reasons[bid][reason] += 1

                ticks = payload.get("blocked_ticks")
                if isinstance(ticks, int):
                    blocked_ticks[bid].append(ticks)

        print(
            f"  Timed-out rounds: {timed_out_rounds}"
            f" | rounds with traffic blocks: {traffic_block_rounds}"
            f" | total traffic blocks: {traffic_block_total}",
        )

        print("\n  Per-bot wait reasons:")
        for bid in sorted(wait_reasons):
            reasons = wait_reasons[bid]
            if not reasons:
                print(f"    Bot {bid}: none")
                continue
            top = ", ".join(
                f"{reason}={count}" for reason, count in reasons.most_common(5)
            )
            print(f"    Bot {bid}: {top}")

        print("\n  Per-bot blocked-ticks summary:")
        for bid in sorted(blocked_ticks):
            ticks = blocked_ticks[bid]
            if not ticks:
                print(f"    Bot {bid}: no samples")
                continue
            avg_ticks = sum(ticks) / len(ticks)
            print(
                f"    Bot {bid}: avg={avg_ticks:.2f}, max={max(ticks)}, "
                f">=3 ticks={sum(1 for t in ticks if t >= 3)}",
            )

        if hotspots:
            hotspots.sort(key=lambda x: (-x[1], x[0]))
            print("\n  Traffic block hotspots (top 10):")
            for rnd, count in hotspots[:10]:
                print(f"    Round {rnd}: traffic_blocks={count}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python scripts/analyze_replay.py <replay.jsonl>")
        sys.exit(1)
    analyze(Path(sys.argv[1]))
