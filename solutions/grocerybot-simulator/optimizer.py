"""Offline optimizer: find the theoretical maximum score for a game replay.

Given complete knowledge of the board and all orders (from a replay log),
compute the optimal action sequence for a single bot (Easy difficulty).

Usage:
    python optimizer.py <path_to_jsonl>
"""

from __future__ import annotations
import sys
from itertools import permutations, product
from pathlib import Path
from parser import parse_replay, ParsedGame
from pathfinding import bfs_distance_map, bfs_path, bfs_to_adjacent
from engine import ITEM_SCORE, ORDER_BONUS


def precompute_all_distances(game: ParsedGame) -> dict[tuple, dict[tuple, int]]:
    """Precompute BFS distance from every walkable cell to every other.

    Returns dist_map[src] = {dst: distance}.
    Only computes from key locations (item adjacency cells + drop-off).
    """
    config = game.config

    # Collect key locations: drop-off + all walkable cells adjacent to items
    key_cells = {config.drop_off}
    for item in config.items:
        ix, iy = item["position"]
        for dx, dy in [(0, -1), (0, 1), (-1, 0), (1, 0)]:
            ax, ay = ix + dx, iy + dy
            if 0 <= ax < config.width and 0 <= ay < config.height:
                if (ax, ay) not in config.walls:
                    key_cells.add((ax, ay))

    # Also add bot start positions
    for pos in config.bot_start_positions:
        key_cells.add(pos)

    dist_map = {}
    for cell in key_cells:
        dist_map[cell] = bfs_distance_map(config, cell)

    return dist_map


def get_item_sources(game: ParsedGame) -> dict[str, list[dict]]:
    """Map item_type -> list of item dicts (each with adjacent pickup cells)."""
    config = game.config
    type_sources = {}
    for item in config.items:
        itype = item["type"]
        ix, iy = item["position"]
        adj_cells = []
        for dx, dy in [(0, -1), (0, 1), (-1, 0), (1, 0)]:
            ax, ay = ix + dx, iy + dy
            if 0 <= ax < config.width and 0 <= ay < config.height:
                if (ax, ay) not in config.walls:
                    adj_cells.append((ax, ay))
        entry = {"id": item["id"], "type": itype,
                 "position": item["position"], "adj_cells": adj_cells}
        type_sources.setdefault(itype, []).append(entry)
    return type_sources


def dist_between(dist_map, a, b):
    """Get distance between two key cells, with fallback."""
    if a == b:
        return 0
    if a in dist_map:
        return dist_map[a].get(b, 9999)
    return 9999


def best_adj_cell(dist_map, from_pos, item_source):
    """Find the best adjacent cell to reach an item source from from_pos."""
    best_d = 9999
    best_cell = None
    for ac in item_source["adj_cells"]:
        d = dist_between(dist_map, from_pos, ac)
        if d < best_d:
            best_d = d
            best_cell = ac
    return best_cell, best_d


def plan_trip(dist_map, start_pos, pickup_sources, drop_off):
    """Plan a single trip: start -> pick up items -> drop off.

    pickup_sources: list of (item_source_dict) in pickup order.
    Returns (total_rounds, end_pos, path_detail).

    total_rounds includes movement + 1 pick_up action per item + 1 drop_off.
    """
    pos = start_pos
    total = 0
    detail = []

    for src in pickup_sources:
        cell, d = best_adj_cell(dist_map, pos, src)
        if cell is None:
            return 9999, pos, detail
        total += d  # movement
        total += 1  # pick_up action
        pos = cell
        detail.append(f"  pickup {src['type']} at {src['position']} (adj {cell}, +{d+1} rounds)")

    # Go to drop-off
    d = dist_between(dist_map, pos, drop_off)
    total += d  # movement to drop-off
    total += 1  # drop_off action
    detail.append(f"  drop_off at {drop_off} (+{d+1} rounds)")

    return total, drop_off, detail


def optimize_order(dist_map, type_sources, start_pos, order_items, drop_off, inv_cap):
    """Find the fastest way to complete one order.

    Tries all permutations of pickup order and source choices.
    For 4-item orders with inv_cap=3, plans 2 trips.

    Returns (total_rounds, end_pos, plan_detail).
    """
    # Split into trips based on inventory cap
    trips_items = []
    remaining = list(order_items)
    while remaining:
        trip = remaining[:inv_cap]
        remaining = remaining[inv_cap:]
        trips_items.append(trip)

    best_total = 9999
    best_detail = []
    best_end = start_pos

    # For each trip, try permutations of pickup order × source choices
    def solve_trips(trip_idx, pos, total_so_far, detail_so_far):
        nonlocal best_total, best_detail, best_end

        if trip_idx >= len(trips_items):
            if total_so_far < best_total:
                best_total = total_so_far
                best_detail = list(detail_so_far)
                best_end = pos
            return

        trip = trips_items[trip_idx]

        # Get all source options for each item type in this trip
        source_options = []
        for item_type in trip:
            sources = type_sources.get(item_type, [])
            if not sources:
                return  # impossible
            source_options.append(sources)

        # Try all permutations of pickup order
        indices = list(range(len(trip)))
        for perm in set(permutations(indices)):
            # Try all source combinations
            perm_sources = [source_options[i] for i in perm]

            # For each position in permuted order, try each source
            for combo in product(*perm_sources):
                cost, end_pos, detail = plan_trip(
                    dist_map, pos, list(combo), drop_off
                )
                new_total = total_so_far + cost
                if new_total < best_total:
                    new_detail = detail_so_far + [f"Trip {trip_idx + 1}:"] + detail
                    solve_trips(trip_idx + 1, end_pos, new_total, new_detail)

    solve_trips(0, start_pos, 0, [])
    return best_total, best_end, best_detail


def optimize_game(game: ParsedGame, verbose: bool = False) -> dict:
    """Find the theoretical maximum score for a complete game.

    Processes orders greedily (must complete in sequence).
    For each order, finds the fastest completion route.
    Stops when 300 rounds are exhausted.
    """
    config = game.config
    inv_cap = game.max_inventory_observed or 3

    print("Precomputing distances...")
    dist_map = precompute_all_distances(game)
    type_sources = get_item_sources(game)

    pos = config.bot_start_positions[0]
    total_rounds = 0
    score = 0
    orders_completed = 0
    items_delivered = 0

    print(f"Optimizing {len(game.orders_seen)} orders (max {config.max_rounds} rounds)...\n")

    for i, order in enumerate(game.orders_seen):
        cost, new_pos, detail = optimize_order(
            dist_map, type_sources, pos, order.items_required,
            config.drop_off, inv_cap
        )

        if total_rounds + cost > config.max_rounds:
            if verbose:
                print(f"order_{i}: {order.items_required} — SKIP (need {cost} rounds, "
                      f"only {config.max_rounds - total_rounds} left)")
            break

        total_rounds += cost
        pos = new_pos
        n_items = len(order.items_required)
        order_score = n_items * ITEM_SCORE + ORDER_BONUS
        score += order_score
        orders_completed += 1
        items_delivered += n_items

        if verbose:
            print(f"order_{i}: {order.items_required} — {cost} rounds "
                  f"(+{order_score} pts, total={score}, round={total_rounds})")
            for line in detail:
                print(f"    {line}")

    remaining_rounds = config.max_rounds - total_rounds

    print(f"\n{'='*50}")
    print(f"THEORETICAL MAXIMUM (greedy sequential):")
    print(f"  Orders completed: {orders_completed}")
    print(f"  Items delivered:  {items_delivered}")
    print(f"  Score:            {score}")
    print(f"  Rounds used:      {total_rounds} / {config.max_rounds}")
    print(f"  Rounds remaining: {remaining_rounds}")
    print(f"\nACTUAL BOT RESULT:")
    print(f"  Orders completed: {game.orders_completed}")
    print(f"  Items delivered:  {game.items_delivered}")
    print(f"  Score:            {game.final_score}")
    print(f"\nGAP:")
    print(f"  Score gap: {score - game.final_score} "
          f"(theoretical {score} vs actual {game.final_score})")
    if game.final_score > 0:
        print(f"  Bot efficiency: {game.final_score / score * 100:.1f}% of theoretical max")

    return {
        "theoretical_score": score,
        "theoretical_orders": orders_completed,
        "theoretical_items": items_delivered,
        "rounds_used": total_rounds,
        "actual_score": game.final_score,
        "gap": score - game.final_score,
    }


def main():
    if len(sys.argv) < 2:
        print("Usage: python optimizer.py <path_to_jsonl>")
        sys.exit(1)

    path = sys.argv[1]
    verbose = "--verbose" in sys.argv or "-v" in sys.argv
    game = parse_replay(path)

    print(f"Replay: {path}")
    print(f"Grid: {game.config.width}x{game.config.height}, "
          f"{game.config.num_bots} bot(s), {len(game.config.items)} items")
    print(f"Actual result: score={game.final_score}\n")

    optimize_game(game, verbose=verbose)


if __name__ == "__main__":
    main()
