"""Medium strategy: replay simulated offline v4 plan, fallback to medium_v4."""

from __future__ import annotations

import json
import os
from collections import Counter, defaultdict
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Literal, cast

from grocerybot.daily_memory import load_snapshot, snapshot_path
from grocerybot.grid import PassableGrid, adjacent_walkable
from grocerybot.models import (
    BotAction,
    DropOffAction,
    GameOver,
    GameState,
    MoveAction,
    PickUpAction,
    WaitAction,
)
from grocerybot.strategies.base import Strategy
from grocerybot.strategies.medium_v4 import MediumV4Strategy

if TYPE_CHECKING:
    from grocerybot.models import Bot

Position = tuple[int, int]
NUM_BOTS = 3
MOVE_DELTAS: dict[str, Position] = {
    "move_up": (0, -1),
    "move_down": (0, 1),
    "move_left": (-1, 0),
    "move_right": (1, 0),
}


class OptimizedMediumV4Strategy(Strategy):
    """Replay robust offline plan prefix for medium, then use medium_v4."""

    MAX_CONSECUTIVE_SKIPS = 6

    def __init__(
        self,
        level: str = "medium",
        plan_path: Path | None = None,
        fallback: Strategy | None = None,
    ) -> None:
        self._level = level
        self._plan_path_override = plan_path
        self._fallback = fallback if fallback is not None else MediumV4Strategy()
        self._grid: PassableGrid | None = None
        self._actions_by_round: dict[int, dict[int, dict[str, object]]] = {}
        self._checkpoints_by_round: dict[int, dict[str, object]] = {}
        self._max_round_exclusive = 0
        self._plan_enabled = False
        self._bot_skips: list[int] = [0] * NUM_BOTS

    def on_game_start(self, state: GameState) -> None:
        self._grid = PassableGrid(state)
        self._fallback.on_game_start(state)
        self._load_plan()

    def on_game_over(self, result: GameOver) -> None:
        self._fallback.on_game_over(result)

    def decide(self, state: GameState) -> list[BotAction]:
        fallback_actions = self._fallback.decide(state)
        if not self._plan_enabled:
            return fallback_actions
        if state.round >= self._max_round_exclusive:
            self._plan_enabled = False
            return fallback_actions

        checkpoint = self._checkpoints_by_round.get(state.round)
        planned_round = self._actions_by_round.get(state.round)
        if planned_round is None:
            self._plan_enabled = False
            return fallback_actions
        checkpoint_ok = checkpoint is not None and self._checkpoint_matches(state, checkpoint)

        actions: list[BotAction] = []
        for bot in sorted(state.bots, key=lambda b: b.id):
            action_data = planned_round.get(bot.id, {"bot": bot.id, "action": "wait"})
            resolved = self._resolve_action(state, bot, action_data)
            if resolved is None:
                if self._can_skip_plan_entry(state, bot, action_data):
                    actions.append(WaitAction(bot=bot.id))
                    self._bot_skips[bot.id] = 0
                else:
                    actions.append(WaitAction(bot=bot.id))
                    self._bot_skips[bot.id] += 1
            else:
                actions.append(resolved)
                self._bot_skips[bot.id] = 0

        if any(skips >= self.MAX_CONSECUTIVE_SKIPS for skips in self._bot_skips):
            self._plan_enabled = False
            return fallback_actions

        # Treat checkpoint mismatch as advisory; only disable when we are both
        # mismatched and making no useful progress (all waits).
        if not checkpoint_ok and all(a.action == "wait" for a in actions):
            self._plan_enabled = False
            return fallback_actions
        return actions

    def _resolve_plan_path(self) -> Path:
        if self._plan_path_override is not None:
            return self._plan_path_override
        env_path = os.environ.get("GROCERY_BOT_PLAN_PATH")
        if env_path:
            return Path(env_path)
        snap = load_snapshot(self._level)
        if snap is not None:
            date = snap.date
        else:
            date = datetime.now(tz=UTC).strftime("%Y-%m-%d")
        snap_p = snapshot_path(self._level, date)
        return snap_p.with_name(f"{self._level}_{date}_plan_v4.json")

    def _load_plan(self) -> None:
        plan_path = self._resolve_plan_path()
        self._plan_enabled = False
        self._actions_by_round = {}
        self._checkpoints_by_round = {}
        self._max_round_exclusive = 0
        if not plan_path.exists():
            return
        raw = json.loads(plan_path.read_text(encoding="utf-8"))
        raw_actions = raw.get("actions")
        raw_checkpoints = raw.get("checkpoints")
        summary = raw.get("summary")
        if not isinstance(raw_actions, list) or not isinstance(raw_checkpoints, list):
            return

        actions_by_round: dict[int, dict[int, dict[str, object]]] = defaultdict(dict)
        max_round = -1
        for entry in raw_actions:
            if not isinstance(entry, dict):
                continue
            rnd = entry.get("round")
            bot = entry.get("bot")
            if not isinstance(rnd, int) or not isinstance(bot, int):
                continue
            if 0 <= bot < NUM_BOTS:
                actions_by_round[rnd][bot] = entry
                if rnd > max_round:
                    max_round = rnd

        checkpoints_by_round: dict[int, dict[str, object]] = {}
        for cp in raw_checkpoints:
            if not isinstance(cp, dict):
                continue
            rnd = cp.get("round")
            if isinstance(rnd, int):
                checkpoints_by_round[rnd] = cp

        max_round_exclusive = max_round + 1
        if isinstance(summary, dict):
            planned_rounds = summary.get("optimal_rounds")
            if isinstance(planned_rounds, int) and planned_rounds > 0:
                max_round_exclusive = planned_rounds

        if not actions_by_round or not checkpoints_by_round:
            return
        self._actions_by_round = dict(actions_by_round)
        self._checkpoints_by_round = checkpoints_by_round
        self._max_round_exclusive = max_round_exclusive
        self._bot_skips = [0] * NUM_BOTS
        self._plan_enabled = True

    def _checkpoint_matches(
        self,
        state: GameState,
        checkpoint: dict[str, object],
    ) -> bool:
        bots_raw = checkpoint.get("bots")
        if not isinstance(bots_raw, list):
            return False
        cp_bots: dict[int, tuple[Position, Counter[str]]] = {}
        for bot in bots_raw:
            if not isinstance(bot, dict):
                return False
            bid = bot.get("id")
            pos = bot.get("position")
            inv = bot.get("inventory")
            if (
                not isinstance(bid, int)
                or not isinstance(pos, list)
                or len(pos) != 2
                or not all(isinstance(v, int) for v in pos)
                or not isinstance(inv, list)
                or not all(isinstance(v, str) for v in inv)
            ):
                return False
            cp_bots[bid] = ((pos[0], pos[1]), Counter(inv))

        for bot in state.bots:
            cp = cp_bots.get(bot.id)
            if cp is None:
                return False
            cp_pos, cp_inv = cp
            if bot.position != cp_pos:
                return False
            if Counter(bot.inventory) != cp_inv:
                return False

        cp_active_id = checkpoint.get("active_order_id")
        cp_active_needed = checkpoint.get("active_needed")
        active = next((o for o in state.orders if o.status == "active"), None)
        if active is None:
            return cp_active_id is None
        if cp_active_id != active.id:
            return False
        if not isinstance(cp_active_needed, list) or not all(
            isinstance(v, str) for v in cp_active_needed
        ):
            return False
        remaining = Counter(active.items_required)
        remaining.subtract(active.items_delivered)
        remaining = Counter({k: v for k, v in remaining.items() if v > 0})
        return remaining == Counter(cp_active_needed)

    def _resolve_action(
        self,
        state: GameState,
        bot: Bot,
        action_data: dict[str, object],
    ) -> BotAction | None:
        grid = self._grid
        assert grid is not None

        action_name = action_data.get("action")
        if not isinstance(action_name, str):
            return None

        if action_name in MOVE_DELTAS:
            dx, dy = MOVE_DELTAS[action_name]
            nxt = (bot.position[0] + dx, bot.position[1] + dy)
            if not grid.is_passable(nxt):
                return None
            return MoveAction(
                bot=bot.id,
                action=cast(
                    Literal["move_up", "move_down", "move_left", "move_right"],
                    action_name,
                ),
            )

        if action_name == "drop_off":
            if bot.position != state.drop_off:
                return None
            active = next((o for o in state.orders if o.status == "active"), None)
            if active is None:
                return None
            needed = Counter(active.items_required)
            needed.subtract(active.items_delivered)
            needed = Counter({k: v for k, v in needed.items() if v > 0})
            if not any(needed[item] > 0 for item in bot.inventory):
                return None
            return DropOffAction(bot=bot.id, action="drop_off")

        if action_name == "pick_up":
            if len(bot.inventory) >= 3:
                return None
            item_type = action_data.get("item_type")
            if not isinstance(item_type, str):
                return None
            item_id = self._find_adjacent_item(state, bot.position, item_type)
            if item_id is None:
                return None
            return PickUpAction(bot=bot.id, action="pick_up", item_id=item_id)

        if action_name == "wait":
            return WaitAction(bot=bot.id)
        return None

    def _can_skip_plan_entry(
        self,
        state: GameState,
        bot: Bot,
        action_data: dict[str, object],
    ) -> bool:
        action_name = action_data.get("action")
        if action_name == "wait":
            return True
        if action_name == "drop_off":
            return bot.position == state.drop_off
        if action_name == "pick_up":
            return len(bot.inventory) >= 3
        return False

    def _find_adjacent_item(
        self,
        state: GameState,
        pos: Position,
        item_type: str,
    ) -> str | None:
        grid = self._grid
        assert grid is not None
        candidates: list[str] = []
        for item in state.items:
            if item.type != item_type:
                continue
            if pos in adjacent_walkable(item.position, grid):
                candidates.append(item.id)
        if not candidates:
            return None
        return sorted(candidates)[0]
