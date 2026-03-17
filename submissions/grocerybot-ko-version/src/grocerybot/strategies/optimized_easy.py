"""Easy-mode strategy: replay offline optimized plan, then fallback to heuristics."""

from __future__ import annotations

import json
import os
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
from grocerybot.strategies.memory_solo import MemorySoloStrategy

if TYPE_CHECKING:
    from grocerybot.models import Bot

Position = tuple[int, int]
MOVE_DELTAS: dict[str, Position] = {
    "move_up": (0, -1),
    "move_down": (0, 1),
    "move_left": (-1, 0),
    "move_right": (1, 0),
}


class OptimizedEasyStrategy(Strategy):
    """Replay precomputed plan actions on Easy, then fallback to memory_solo."""

    def __init__(
        self,
        level: str = "easy",
        plan_path: Path | None = None,
        fallback: Strategy | None = None,
    ) -> None:
        self._level = level
        self._plan_path_override = plan_path
        self._fallback = fallback if fallback is not None else MemorySoloStrategy(level=level)
        self._grid: PassableGrid | None = None
        self._plan_actions: dict[int, dict[str, object]] = {}
        self._ordered_plan_actions: list[dict[str, object]] = []
        self._max_round: int = -1
        self._plan_cursor: int = 0
        self._plan_enabled = False

    def on_game_start(self, state: GameState) -> None:
        self._grid = PassableGrid(state)
        self._fallback.on_game_start(state)
        self._load_plan_actions()

    def on_game_over(self, result: GameOver) -> None:
        self._fallback.on_game_over(result)

    def decide(self, state: GameState) -> list[BotAction]:
        fallback_action = self._fallback.decide(state)[0]
        if not self._plan_enabled:
            return [fallback_action]

        # Keep cursor aligned with wall-clock round when possible.
        while self._plan_cursor < len(self._ordered_plan_actions):
            round_raw = self._ordered_plan_actions[self._plan_cursor].get("round")
            if isinstance(round_raw, int) and round_raw < state.round:
                self._plan_cursor += 1
            else:
                break

        skip_budget = 3
        while self._plan_cursor < len(self._ordered_plan_actions):
            plan_entry = self._ordered_plan_actions[self._plan_cursor]
            planned = self._planned_action_for_state(state, plan_entry)
            if planned is not None:
                self._plan_cursor += 1
                return [planned]
            if self._can_skip_plan_entry(state, plan_entry) and skip_budget > 0:
                self._plan_cursor += 1
                skip_budget -= 1
                continue
            self._plan_enabled = False
            return [fallback_action]

        self._plan_enabled = False
        return [fallback_action]

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
        snap_path = snapshot_path(self._level, date)
        return snap_path.with_name(f"{self._level}_{date}_plan.json")

    def _load_plan_actions(self) -> None:
        plan_path = self._resolve_plan_path()
        if not plan_path.exists():
            self._plan_enabled = False
            self._plan_actions = {}
            self._ordered_plan_actions = []
            self._max_round = -1
            self._plan_cursor = 0
            return

        raw = json.loads(plan_path.read_text(encoding="utf-8"))
        round_limit_exclusive: int | None = None
        summary = raw.get("summary")
        if isinstance(summary, dict):
            from_summary = summary.get("optimal_rounds_for_current_run_orders")
            if isinstance(from_summary, int) and from_summary > 0:
                round_limit_exclusive = from_summary

        raw_actions = raw.get("actions")
        if not isinstance(raw_actions, list):
            self._plan_enabled = False
            self._plan_actions = {}
            self._ordered_plan_actions = []
            self._max_round = -1
            self._plan_cursor = 0
            return

        plan_actions: dict[int, dict[str, object]] = {}
        ordered: list[tuple[int, dict[str, object]]] = []
        max_round = -1
        for idx, action in enumerate(raw_actions):
            if not isinstance(action, dict):
                continue
            round_raw = action.get("round", idx)
            if not isinstance(round_raw, int):
                continue
            if round_limit_exclusive is not None and round_raw >= round_limit_exclusive:
                continue
            plan_actions[round_raw] = action
            ordered.append((round_raw, action))
            if round_raw > max_round:
                max_round = round_raw

        self._plan_actions = plan_actions
        self._ordered_plan_actions = [action for _, action in sorted(ordered)]
        self._max_round = max_round
        self._plan_cursor = 0
        self._plan_enabled = bool(plan_actions)

    def _planned_action_for_state(
        self,
        state: GameState,
        action_data: dict[str, object],
    ) -> BotAction | None:
        grid = self._grid
        assert grid is not None

        bot = self._single_bot(state)
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
                if self._is_pickable_item_id(state, bot.position, by_id):
                    return PickUpAction(bot=bot.id, action="pick_up", item_id=by_id)
                return None
            by_type = action_data.get("item_type")
            if isinstance(by_type, str):
                item_id = self._pick_adjacent_item_id_for_type(state, bot.position, by_type)
                if item_id is None:
                    return None
                return PickUpAction(bot=bot.id, action="pick_up", item_id=item_id)
            return None

        if action_name == "wait":
            return WaitAction(bot=bot.id)

        return None

    def _can_skip_plan_entry(
        self,
        state: GameState,
        action_data: dict[str, object],
    ) -> bool:
        bot = self._single_bot(state)
        action_name = action_data.get("action")
        if action_name == "drop_off":
            return bot.position == state.drop_off and not bot.inventory
        return False

    def _single_bot(self, state: GameState) -> Bot:
        return state.bots[0]

    def _is_pickable_item_id(
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

    def _pick_adjacent_item_id_for_type(
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
