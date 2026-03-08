"""Order tracking and preview prefetching logic.

Extracted from run_hard.py and run_expert.py.
"""

from __future__ import annotations

from collections import Counter
from typing import Optional

from core.types import Coord, manhattan


class OrderManager:
    """
    Manages order-related state:
    - Track which items are needed for active/preview orders
    - Preview duty assignment (which bots are fetching preview items)
    - Preview item identification
    """

    def __init__(self, preview_duty_cap_offset: int = 1) -> None:
        # How many bots to subtract from total to get preview cap
        # Hard uses 1, Expert uses 2
        self._preview_duty_cap_offset = preview_duty_cap_offset

    def preview_item_ids(
        self,
        items: list[dict],
        preview_needed: Counter,
    ) -> set[str]:
        """Identify item IDs on the map that match preview order needs."""
        if sum(preview_needed.values()) <= 0:
            return set()
        return {item["id"] for item in items if preview_needed[item["type"]] > 0}

    def current_preview_duty_bots(
        self,
        preview_item_ids: set[str],
        bots: list[dict],
        bot_targets: dict[int, str],
    ) -> set[int]:
        """Which bots are already committed to fetching preview items."""
        if not preview_item_ids:
            return set()
        bot_ids = {b["id"] for b in bots}
        return {
            bot_id
            for bot_id, target_item_id in bot_targets.items()
            if bot_id in bot_ids and target_item_id in preview_item_ids
        }

    def preview_duty_cap(self, num_bots: int) -> int:
        """Max bots allowed to work on preview items."""
        return max(0, num_bots - self._preview_duty_cap_offset)

    def select_target_item(
        self,
        pos: Coord,
        items: list[dict],
        needed: Counter,
        reserved_items: set[str],
        distance_fn,
        round_number: int = -1,
        pick_blocked_fn=None,
    ) -> Optional[dict]:
        """Select the nearest needed item not reserved or blocked."""
        best_item = None
        best_dist = 9999
        for item in items:
            if item["id"] in reserved_items:
                continue
            if needed[item["type"]] <= 0:
                continue
            if pick_blocked_fn and pick_blocked_fn(item["id"], round_number):
                continue
            dist = distance_fn(pos, tuple(item["position"]))
            if dist < best_dist:
                best_dist = dist
                best_item = item
        return best_item

    def pick_if_adjacent(
        self,
        bot: dict,
        items: list[dict],
        needed: Counter,
        reserved_items: set[str],
        round_number: int = -1,
        pick_blocked_fn=None,
    ) -> Optional[dict]:
        """Pick up a needed item if adjacent (Manhattan distance 1)."""
        pos = tuple(bot["position"])
        if len(bot["inventory"]) >= 3:
            return None

        candidates: list[dict] = []
        for item in items:
            if item["id"] in reserved_items:
                continue
            if needed[item["type"]] <= 0:
                continue
            if pick_blocked_fn and pick_blocked_fn(item["id"], round_number):
                continue
            if manhattan(pos, tuple(item["position"])) == 1:
                candidates.append(item)

        if not candidates:
            return None

        chosen = candidates[0]
        reserved_items.add(chosen["id"])
        needed[chosen["type"]] -= 1
        return {"bot": bot["id"], "action": "pick_up", "item_id": chosen["id"]}
