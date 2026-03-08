"""Greedy assignment — extracted from run_hard.py.

Uses distance-sorted candidates with lock awareness.
Hard variant: simple sort-and-claim.
Expert variant: regret-based (picks the bot with highest "regret" first).
"""

from __future__ import annotations

from collections import Counter
from typing import Callable, Optional

from core.types import Coord

from .base import Assigner


class GreedyAssigner(Assigner):
    """
    Greedy multi-stage assignment.
    Sorts (distance, bot_id, item_id) candidates and claims greedily.
    Extracted from run_hard.py _build_greedy_assignments.
    """

    def __init__(self, use_delivery_penalty: bool = True) -> None:
        self._use_delivery_penalty = use_delivery_penalty

    def assign(
        self,
        bots: list[dict],
        items: list[dict],
        needed: Counter,
        distance_fn: Callable[[Coord, Coord], int],
        excluded_bots: set[int] = frozenset(),
        excluded_items: set[str] = frozenset(),
        delivery_bots: set[int] = frozenset(),
        bot_locks: dict[int, str] | None = None,
    ) -> dict[int, str]:
        if bot_locks is None:
            bot_locks = {}

        assignments: dict[int, str] = {}
        needed_left = Counter(needed)

        # Resolve lock types for deduplication
        lock_type_by_bot: dict[int, str] = {}
        for lock_bot_id, item_id in bot_locks.items():
            for item in items:
                if item["id"] == item_id:
                    lock_type_by_bot[lock_bot_id] = item["type"]
                    break

        candidates: list[tuple[int, int, str]] = []
        for bot in bots:
            bot_id = bot["id"]
            if bot_id in excluded_bots:
                continue
            if len(bot["inventory"]) >= 3:
                continue

            # Per-bot needed: subtract locks held by OTHER bots
            bot_needed = Counter(needed_left)
            for other_id, item_type in lock_type_by_bot.items():
                if other_id == bot_id:
                    continue
                if bot_needed[item_type] > 0:
                    bot_needed[item_type] -= 1

            is_delivering = bot_id in delivery_bots
            bot_pos = tuple(bot["position"])

            for item in items:
                item_id = item["id"]
                if item_id in excluded_items:
                    continue
                if bot_needed[item["type"]] <= 0:
                    continue

                dist = distance_fn(bot_pos, tuple(item["position"]))

                # Delivery bots get a distance penalty to discourage
                # them from detouring far from dropoff
                if is_delivering and self._use_delivery_penalty:
                    dist += max(3, dist // 3)

                candidates.append((dist, bot_id, item_id))

        candidates.sort(key=lambda x: x[0])

        used_bots: set[int] = set()
        used_items: set[str] = set()
        for _, bot_id, item_id in candidates:
            if bot_id in used_bots or item_id in used_items:
                continue
            item = next((it for it in items if it["id"] == item_id), None)
            if item is None:
                continue
            if needed_left[item["type"]] <= 0:
                continue
            assignments[bot_id] = item_id
            used_bots.add(bot_id)
            used_items.add(item_id)
            needed_left[item["type"]] -= 1

        return assignments


class RegretGreedyAssigner(Assigner):
    """
    Regret-based greedy assignment.
    Picks the bot with the highest "regret" (gap between best and 2nd-best
    option) first, ensuring bots with fewer choices get priority.
    Extracted from run_expert.py _build_greedy_assignments.
    """

    def __init__(self, use_delivery_penalty: bool = True) -> None:
        self._use_delivery_penalty = use_delivery_penalty

    def assign(
        self,
        bots: list[dict],
        items: list[dict],
        needed: Counter,
        distance_fn: Callable[[Coord, Coord], int],
        excluded_bots: set[int] = frozenset(),
        excluded_items: set[str] = frozenset(),
        delivery_bots: set[int] = frozenset(),
        bot_locks: dict[int, str] | None = None,
    ) -> dict[int, str]:
        if bot_locks is None:
            bot_locks = {}

        assignments: dict[int, str] = {}
        needed_left = Counter(needed)

        lock_type_by_bot: dict[int, str] = {}
        for lock_bot_id, item_id in bot_locks.items():
            for item in items:
                if item["id"] == item_id:
                    lock_type_by_bot[lock_bot_id] = item["type"]
                    break

        available_bots: dict[int, dict] = {}
        for bot in bots:
            if bot["id"] in excluded_bots:
                continue
            if len(bot["inventory"]) >= 3:
                continue
            available_bots[bot["id"]] = bot

        used_items: set[str] = set()

        while available_bots:
            chosen: Optional[tuple[int, int, str, str]] = None
            chosen_regret = -1
            chosen_best_dist = 9999

            for bot_id, bot in available_bots.items():
                bot_needed = Counter(needed_left)
                for other_id, item_type in lock_type_by_bot.items():
                    if other_id == bot_id:
                        continue
                    if bot_needed[item_type] > 0:
                        bot_needed[item_type] -= 1

                is_delivering = bot_id in delivery_bots
                options: list[tuple[int, str, str]] = []

                for item in items:
                    item_id = item["id"]
                    if item_id in used_items or item_id in excluded_items:
                        continue
                    if bot_needed[item["type"]] <= 0:
                        continue
                    dist = distance_fn(tuple(bot["position"]), tuple(item["position"]))
                    if is_delivering and self._use_delivery_penalty:
                        dist += max(3, dist // 3)
                    options.append((dist, item_id, item["type"]))

                if not options:
                    continue

                options.sort(key=lambda t: (t[0], t[1]))
                best_dist, best_item_id, best_item_type = options[0]
                second_dist = options[1][0] if len(options) > 1 else (best_dist + 8)
                regret = second_dist - best_dist

                if regret > chosen_regret or (
                    regret == chosen_regret and best_dist < chosen_best_dist
                ):
                    chosen_regret = regret
                    chosen_best_dist = best_dist
                    chosen = (bot_id, best_dist, best_item_id, best_item_type)

            if chosen is None:
                break

            bot_id, _, item_id, item_type = chosen
            if needed_left[item_type] <= 0:
                available_bots.pop(bot_id, None)
                continue

            assignments[bot_id] = item_id
            available_bots.pop(bot_id, None)
            used_items.add(item_id)
            needed_left[item_type] -= 1

        return assignments
