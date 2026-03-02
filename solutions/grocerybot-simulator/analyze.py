"""Analyze a game replay: board visualization, per-order efficiency, gap analysis.

Usage:
    python analyze.py <path_to_jsonl>
"""

import sys
from pathlib import Path
from parser import parse_replay
from pathfinding import bfs_distance_map, bfs_to_adjacent, precompute_distances


def render_board(game):
    """Render ASCII grid showing walls, items, drop-off, bot start."""
    config = game.config
    grid = []
    for y in range(config.height):
        row = []
        for x in range(config.width):
            if (x, y) in config.walls:
                row.append("##")
            else:
                row.append("  ")
        grid.append(row)

    # Place items
    for item in config.items:
        x, y = item["position"]
        label = item["type"][:2].upper()
        grid[y][x] = label

    # Place drop-off
    dx, dy = config.drop_off
    grid[dy][dx] = "DD"

    # Place bot starts
    for i, pos in enumerate(config.bot_start_positions):
        bx, by = pos
        grid[by][bx] = f"B{i}"

    print("Board layout:")
    print("  " + "".join(f"{x:2d}" for x in range(config.width)))
    for y in range(config.height):
        print(f"{y:2d} " + " ".join(grid[y]))
    print()
    print("Legend: ## = wall, DD = drop-off, B0/B1/... = bot start")
    print("Item codes: CH=cheese, BU=butter, YO=yogurt, MI=milk, "
          "EG=eggs, PA=pasta, BR=bread, CR=cream, RI=rice")


def analyze_orders(game):
    """Per-order breakdown: rounds spent, items, theoretical minimum rounds."""
    config = game.config
    distances = precompute_distances(config)
    drop_dist = distances["drop_off_distances"]
    item_adj_dist = distances["item_adj_distances"]

    # Build item type -> list of item_ids
    type_to_items = {}
    for item in config.items:
        type_to_items.setdefault(item["type"], []).append(item)

    # Track when each order was completed from the replay
    order_completions = {}
    prev_idx = 0
    for rnd in game.rounds:
        idx = rnd.game_state["active_order_index"]
        if idx > prev_idx:
            # Orders prev_idx..idx-1 were completed this round
            for oi in range(prev_idx, idx):
                order_completions[oi] = rnd.round
            prev_idx = idx

    print(f"\n{'='*70}")
    print(f"Order Analysis ({len(game.orders_seen)} orders seen, "
          f"{game.orders_completed} completed in {game.rounds_used} rounds)")
    print(f"{'='*70}")
    print(f"{'Order':<10} {'Items':<30} {'Done@Round':<12} {'Rounds':<8} {'Min*':<6} {'Gap'}")
    print(f"{'-'*10} {'-'*30} {'-'*12} {'-'*8} {'-'*6} {'-'*6}")

    total_actual = 0
    total_min = 0
    prev_done_round = 0

    for i, order in enumerate(game.orders_seen):
        items_str = ", ".join(order.items_required)
        if len(items_str) > 28:
            items_str = items_str[:25] + "..."

        if i in order_completions:
            done_round = order_completions[i]
            rounds_spent = done_round - prev_done_round

            # Estimate theoretical minimum rounds for this order
            # This is a lower bound: optimal pickup route + delivery
            min_rounds = estimate_min_rounds(
                config, order.items_required, type_to_items,
                item_adj_dist, drop_dist,
                start_pos=config.drop_off,  # assume starting from drop-off
                inv_cap=game.max_inventory_observed or 3,
            )

            gap = rounds_spent - min_rounds
            total_actual += rounds_spent
            total_min += min_rounds
            prev_done_round = done_round

            print(f"order_{i:<4} {items_str:<30} {done_round:<12} "
                  f"{rounds_spent:<8} {min_rounds:<6} {'+' + str(gap) if gap >= 0 else str(gap)}")
        else:
            print(f"order_{i:<4} {items_str:<30} {'(not done)':<12}")

    if total_min > 0:
        print(f"\n  Total rounds used on completed orders: {total_actual}")
        print(f"  Theoretical minimum (lower bound):     {total_min}")
        print(f"  Efficiency: {total_min/total_actual*100:.1f}% "
              f"(gap = {total_actual - total_min} rounds)")
        remaining = game.config.max_rounds - total_min
        print(f"  If perfect routing, ~{remaining} rounds available "
              f"-> potential for more orders")


def estimate_min_rounds(config, items_required, type_to_items,
                        item_adj_dist, drop_dist, start_pos, inv_cap):
    """Greedy lower-bound estimate: min rounds to complete one order.

    Assumes starting and ending at start_pos (typically drop-off).
    Uses nearest-item greedy for each pickup trip.
    """
    remaining = list(items_required)
    pos = start_pos
    total_rounds = 0

    while remaining:
        # Plan a trip: pick up to inv_cap items, then return to drop-off
        trip_items = remaining[:inv_cap]
        remaining = remaining[inv_cap:]

        # Greedy nearest-item routing for this trip
        trip_pos = pos
        trip_rounds = 0

        for item_type in trip_items:
            # Find nearest source of this item type
            sources = type_to_items.get(item_type, [])
            best_dist = float("inf")
            best_item = None
            for src in sources:
                d = item_adj_dist[src["id"]].get(trip_pos, float("inf"))
                if d < best_dist:
                    best_dist = d
                    best_item = src

            if best_item is not None:
                trip_rounds += best_dist  # move to adjacent
                trip_rounds += 1  # pick_up action
                # Update position to adjacent cell of item
                # (approximate: use item position's adjacent cell nearest to current)
                ix, iy = best_item["position"]
                for dx, dy in [(0, -1), (0, 1), (-1, 0), (1, 0)]:
                    ax, ay = ix + dx, iy + dy
                    if (ax, ay) not in config.walls:
                        if 0 <= ax < config.width and 0 <= ay < config.height:
                            d = item_adj_dist[best_item["id"]].get(trip_pos, float("inf"))
                            trip_pos = (ax, ay)
                            break

        # Return to drop-off
        trip_rounds += drop_dist.get(trip_pos, 999)
        trip_rounds += 1  # drop_off action

        total_rounds += trip_rounds
        pos = config.drop_off  # after drop-off, bot is at drop-off

    return total_rounds


def action_breakdown(game):
    """Show action distribution and idle time."""
    counts = {}
    for rnd in game.rounds:
        for action in rnd.actions:
            act = action["action"]
            counts[act] = counts.get(act, 0) + 1

    total = sum(counts.values())
    print(f"\nAction breakdown ({total} total actions across {game.config.num_bots} bot(s)):")
    for act in sorted(counts, key=counts.get, reverse=True):
        pct = counts[act] / total * 100
        print(f"  {act:<14} {counts[act]:>5}  ({pct:.1f}%)")

    wait_pct = counts.get("wait", 0) / total * 100
    if wait_pct > 5:
        print(f"\n  WARNING: {wait_pct:.1f}% wait actions — significant idle time")


def score_timeline(game):
    """Show score progression over time."""
    print(f"\nScore timeline:")
    prev_score = 0
    milestones = [25, 50, 75, 100, 125, 150, 175, 200, 225, 250, 275, 300]
    mi = 0

    for rnd in game.rounds:
        score = rnd.game_state["score"]
        while mi < len(milestones) and rnd.round >= milestones[mi]:
            print(f"  Round {milestones[mi]:>3}: score = {prev_score}")
            mi += 1
        prev_score = score

    print(f"  Round 300: score = {game.final_score}")


def main():
    if len(sys.argv) < 2:
        print("Usage: python analyze.py <path_to_jsonl>")
        sys.exit(1)

    path = sys.argv[1]
    game = parse_replay(path)

    print(f"Replay: {path}")
    print(f"Difficulty seed: {game.config.width}x{game.config.height} grid, "
          f"{game.config.num_bots} bot(s), {len(game.config.items)} items")
    print(f"Result: score={game.final_score}, orders={game.orders_completed}/{game.config.total_orders}, "
          f"items={game.items_delivered}")
    print()

    render_board(game)
    analyze_orders(game)
    action_breakdown(game)
    score_timeline(game)


if __name__ == "__main__":
    main()
