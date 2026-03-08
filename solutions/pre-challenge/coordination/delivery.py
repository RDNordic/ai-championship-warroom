"""Delivery coordination — dropoff queue, slot allocation, staging.

Extracted from run_hard.py and run_expert.py.
"""

from __future__ import annotations

from collections import Counter
from typing import Optional

from core.types import Coord, Grid, manhattan, neighbors


class DeliveryCoordinator:
    """
    Manages delivery logistics:
    - Allocate which bot delivers which item types
    - Dropoff queue leadership (who goes to dropoff first)
    - Dropoff clearance (move idle bots off the dropoff cell)
    - Staging near dropoff for pipeline delivery
    """

    def __init__(self, max_queue_leaders: int = 2) -> None:
        self._max_queue_leaders = max_queue_leaders

    def allocate_delivery_slots(
        self,
        bots: list[dict],
        remaining_needed: Counter,
    ) -> tuple[dict[int, Counter], Counter]:
        """
        Pre-assign which bot delivers which item types based on inventory.
        Lower bot IDs claim slots first.

        Returns (alloc, leftover) where:
        - alloc: dict[bot_id -> Counter of item_type -> count]
        - leftover: Counter of still-unmatched needed items
        """
        left = Counter(remaining_needed)
        alloc: dict[int, Counter] = {}
        for bot in bots:
            reserved = Counter()
            for item_type in bot["inventory"]:
                if left[item_type] > 0:
                    reserved[item_type] += 1
                    left[item_type] -= 1
            alloc[bot["id"]] = reserved
        return alloc, left

    def select_queue_leaders(
        self,
        bots: list[dict],
        drop_off: Coord,
        delivery_alloc: dict[int, Counter],
    ) -> set[int]:
        """Select top N closest deliverers as queue leaders."""
        deliverers = [
            b for b in bots
            if delivery_count(delivery_alloc.get(b["id"], Counter())) > 0
        ]
        if not deliverers:
            return set()
        ranked = sorted(
            deliverers,
            key=lambda b: (
                0 if tuple(b["position"]) == drop_off else 1,
                manhattan(tuple(b["position"]), drop_off),
                b["id"],
            ),
        )
        return {b["id"] for b in ranked[: self._max_queue_leaders]}

    def select_queue_primary(
        self,
        queue_ids: set[int],
        bots: list[dict],
        drop_off: Coord,
    ) -> Optional[int]:
        """Select the single primary deliverer from the queue."""
        if not queue_ids:
            return None
        candidates = [b for b in bots if b["id"] in queue_ids]
        if not candidates:
            return None
        on_dropoff = [b for b in candidates if tuple(b["position"]) == drop_off]
        if on_dropoff:
            return min(b["id"] for b in on_dropoff)
        leader = min(
            candidates,
            key=lambda b: (manhattan(tuple(b["position"]), drop_off), b["id"]),
        )
        return leader["id"]

    def dropoff_clearance_bots(
        self,
        bots: list[dict],
        drop_off: Coord,
        delivery_alloc: dict[int, Counter],
    ) -> set[int]:
        """Identify bots idling on dropoff that should move out of the way."""
        waiting_deliveries = any(
            tuple(b["position"]) != drop_off
            and delivery_count(delivery_alloc.get(b["id"], Counter())) > 0
            for b in bots
        )
        if not waiting_deliveries:
            return set()
        return {
            b["id"]
            for b in bots
            if tuple(b["position"]) == drop_off
            and delivery_count(delivery_alloc.get(b["id"], Counter())) == 0
        }

    def is_near_delivery_path(
        self,
        pos: Coord,
        drop_off: Coord,
        item_pos: Coord,
        max_detour: int = 5,
        max_item_dist: int = 8,
    ) -> bool:
        """Check if picking an item is a small detour on the way to dropoff."""
        direct = manhattan(pos, drop_off)
        via_item = manhattan(pos, item_pos) + manhattan(item_pos, drop_off)
        return via_item <= direct + max_detour and manhattan(pos, item_pos) <= max_item_dist


def delivery_count(alloc: Counter) -> int:
    """Total items allocated for delivery."""
    return int(sum(alloc.values()))
