"""Pick-fail cooldown tracker.

Extracted from run_hard.py / run_expert.py _update_pick_retry_state.
Prevents bots from repeatedly trying to pick unreachable items.
"""

from __future__ import annotations


class PickCooldownTracker:
    """
    Tracks failed pick attempts per item.
    After N consecutive failures, blocks the item for a cooldown period.
    """

    def __init__(self, max_cooldown: int = 18, base_cooldown: int = 4, step: int = 2) -> None:
        self._max_cooldown = max_cooldown
        self._base_cooldown = base_cooldown
        self._step = step

        self.pick_fail_streak: dict[str, int] = {}
        self.pick_block_until_round: dict[str, int] = {}

        # Per-bot state for detecting failed picks
        self._last_action: dict[int, str] = {}
        self._last_pick_item: dict[int, str] = {}
        self._last_inventory_size: dict[int, int] = {}

    def update(
        self,
        bots: list[dict],
        round_number: int,
        bot_targets: dict[int, str],
    ) -> None:
        """Call at the start of each round to detect pick failures."""
        active_ids = {b["id"] for b in bots}

        for bot in bots:
            bot_id = bot["id"]
            prev_action = self._last_action.get(bot_id)
            prev_size = self._last_inventory_size.get(bot_id)
            current_size = len(bot["inventory"])

            if prev_action == "pick_up":
                attempted_item_id = self._last_pick_item.get(bot_id)
                if attempted_item_id and prev_size is not None:
                    if current_size <= prev_size:
                        # Pick failed
                        streak = self.pick_fail_streak.get(attempted_item_id, 0) + 1
                        self.pick_fail_streak[attempted_item_id] = streak
                        cooldown = min(
                            self._max_cooldown,
                            self._base_cooldown + ((streak - 1) * self._step),
                        )
                        until = round_number + cooldown
                        self.pick_block_until_round[attempted_item_id] = max(
                            self.pick_block_until_round.get(attempted_item_id, -1),
                            until,
                        )
                        # Clear targets for this item
                        for target_bot_id, target_item_id in list(bot_targets.items()):
                            if target_item_id == attempted_item_id:
                                bot_targets.pop(target_bot_id, None)
                    else:
                        # Pick succeeded — reset
                        self.pick_fail_streak.pop(attempted_item_id, None)
                        self.pick_block_until_round.pop(attempted_item_id, None)

            self._last_inventory_size[bot_id] = current_size

        # Cleanup departed bots
        for bot_id in list(self._last_inventory_size.keys()):
            if bot_id not in active_ids:
                self._last_inventory_size.pop(bot_id, None)
                self._last_pick_item.pop(bot_id, None)

        # Expire old cooldowns
        for item_id, until in list(self.pick_block_until_round.items()):
            if until < round_number:
                self.pick_block_until_round.pop(item_id, None)
                self.pick_fail_streak.pop(item_id, None)

    def is_blocked(self, item_id: str, round_number: int) -> bool:
        until = self.pick_block_until_round.get(item_id)
        return until is not None and round_number <= until

    def record_action(self, bot_id: int, action: dict) -> None:
        """Call after deciding an action to track pick attempts."""
        action_name = action.get("action", "wait")
        self._last_action[bot_id] = action_name
        if action_name == "pick_up":
            item_id = action.get("item_id")
            if isinstance(item_id, str) and item_id:
                self._last_pick_item[bot_id] = item_id
            else:
                self._last_pick_item.pop(bot_id, None)
        else:
            self._last_pick_item.pop(bot_id, None)
