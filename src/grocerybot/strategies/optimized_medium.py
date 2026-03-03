"""Medium-mode strategy: replay offline optimized 3-bot plan, fallback to medium_v3."""

from __future__ import annotations

import json
import os
from collections import defaultdict
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
from grocerybot.strategies.medium_v3 import MediumV3Strategy

if TYPE_CHECKING:
    from grocerybot.models import Bot

Position = tuple[int, int]
MOVE_DELTAS: dict[str, Position] = {
    "move_up": (0, -1),
    "move_down": (0, 1),
    "move_left": (-1, 0),
    "move_right": (1, 0),
}
NUM_BOTS = 3


class OptimizedMediumStrategy(Strategy):
    """Replay precomputed 3-bot plan on Medium, fallback to medium_v3."""

    # If a bot accumulates this many consecutive skip rounds, disable plan entirely
    MAX_CONSECUTIVE_SKIPS = 5

    def __init__(
        self,
        level: str = "medium",
        plan_path: Path | None = None,
        fallback: Strategy | None = None,
    ) -> None:
        self._level = level
        self._plan_path_override = plan_path
        self._fallback = fallback if fallback is not None else MediumV3Strategy(level=level)
        self._grid: PassableGrid | None = None
        self._plan_by_round: dict[int, list[dict[str, object]]] = {}
        self._max_round: int = -1
        self._plan_enabled = False
        # Per-bot consecutive skip counters for resilience
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

        if state.round > self._max_round:
            self._plan_enabled = False
            return fallback_actions

        planned = self._plan_by_round.get(state.round)
        if planned is None:
            # Gap in plan — disable
            self._plan_enabled = False
            return fallback_actions

        # Per-bot resilience: each bot either follows plan or waits
        actions: list[BotAction] = []
        for bot_id in range(NUM_BOTS):
            bot = state.bots[bot_id]
            action_data = planned[bot_id] if bot_id < len(planned) else None
            if action_data is None:
                actions.append(WaitAction(bot=bot.id))
                self._bot_skips[bot_id] += 1
                continue

            resolved = self._resolve_action(state, bot, action_data)
            if resolved is not None:
                actions.append(resolved)
                self._bot_skips[bot_id] = 0
            elif self._can_skip(state, bot, action_data):
                actions.append(WaitAction(bot=bot.id))
                self._bot_skips[bot_id] = 0
            else:
                # Bot blocked (collision, unexpected state) — wait this round
                actions.append(WaitAction(bot=bot.id))
                self._bot_skips[bot_id] += 1

        # If any bot has too many consecutive skips, plan is diverged — abandon
        if any(s >= self.MAX_CONSECUTIVE_SKIPS for s in self._bot_skips):
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
        return snap_p.with_name(f"{self._level}_{date}_plan.json")

    def _load_plan(self) -> None:
        plan_path = self._resolve_plan_path()
        if not plan_path.exists():
            self._plan_enabled = False
            return

        raw = json.loads(plan_path.read_text(encoding="utf-8"))
        raw_actions = raw.get("actions")
        if not isinstance(raw_actions, list):
            self._plan_enabled = False
            return

        # Group actions by round, then by bot_id within each round
        by_round: dict[int, dict[int, dict[str, object]]] = defaultdict(dict)
        max_round = -1

        for action in raw_actions:
            if not isinstance(action, dict):
                continue
            round_raw = action.get("round")
            bot_raw = action.get("bot")
            if not isinstance(round_raw, int) or not isinstance(bot_raw, int):
                continue
            if 0 <= bot_raw < NUM_BOTS:
                by_round[round_raw][bot_raw] = action
                if round_raw > max_round:
                    max_round = round_raw

        # Convert to list[dict] per round (indexed by bot_id)
        plan_by_round: dict[int, list[dict[str, object]]] = {}
        for rnd, bot_actions in by_round.items():
            ordered: list[dict[str, object]] = []
            for bot_id in range(NUM_BOTS):
                if bot_id in bot_actions:
                    ordered.append(bot_actions[bot_id])
                else:
                    ordered.append({"bot": bot_id, "action": "wait"})
            plan_by_round[rnd] = ordered

        self._plan_by_round = plan_by_round
        self._max_round = max_round
        self._plan_enabled = bool(plan_by_round)

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
            if bot.position != state.drop_off or not bot.inventory:
                return None
            return DropOffAction(bot=bot.id, action="drop_off")

        if action_name == "pick_up":
            if len(bot.inventory) >= 3:
                return None
            by_id = action_data.get("item_id")
            if isinstance(by_id, str):
                if self._is_pickable(state, bot.position, by_id):
                    return PickUpAction(bot=bot.id, action="pick_up", item_id=by_id)
                return None
            by_type = action_data.get("item_type")
            if isinstance(by_type, str):
                item_id = self._find_adjacent_item(state, bot.position, by_type)
                if item_id is None:
                    return None
                return PickUpAction(bot=bot.id, action="pick_up", item_id=item_id)
            return None

        if action_name == "wait":
            return WaitAction(bot=bot.id)

        return None

    def _can_skip(
        self,
        state: GameState,
        bot: Bot,
        action_data: dict[str, object],
    ) -> bool:
        action_name = action_data.get("action")
        if action_name == "drop_off":
            return bot.position == state.drop_off and not bot.inventory
        if action_name == "wait":
            return True
        return False

    def _is_pickable(
        self,
        state: GameState,
        pos: Position,
        item_id: str,
    ) -> bool:
        grid = self._grid
        assert grid is not None
        for item in state.items:
            if item.id == item_id:
                return pos in adjacent_walkable(item.position, grid)
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
        candidates.sort()
        return candidates[0]
