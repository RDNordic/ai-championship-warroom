"""Tests for optimized_easy strategy plan replay + heuristic fallback."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from grocerybot.models import Bot, GameOver, GameState, MoveAction, PickUpAction, WaitAction
from grocerybot.strategies.base import Strategy
from grocerybot.strategies.optimized_easy import OptimizedEasyStrategy


@pytest.fixture()
def easy_state(easy_game_state_data: dict[str, Any]) -> GameState:
    return GameState.model_validate(easy_game_state_data)


class _FakeFallback(Strategy):
    def __init__(self) -> None:
        self.started = False
        self.decide_calls = 0
        self.game_over_called = False

    def on_game_start(self, state: GameState) -> None:
        self.started = True

    def decide(self, state: GameState) -> list[WaitAction]:
        self.decide_calls += 1
        return [WaitAction(bot=state.bots[0].id)]

    def on_game_over(self, result: GameOver) -> None:
        self.game_over_called = True


def _write_plan(path: Path, actions: list[dict[str, object]]) -> None:
    payload = {
        "meta": {"level": "easy", "date": "2026-03-02"},
        "actions": actions,
    }
    path.write_text(json.dumps(payload), encoding="utf-8")


class TestOptimizedEasyStrategy:
    def test_replays_planned_move_action(
        self,
        easy_state: GameState,
        tmp_path: Path,
    ) -> None:
        plan_path = tmp_path / "easy_plan.json"
        _write_plan(
            plan_path,
            [{"round": easy_state.round, "bot": 0, "action": "move_left"}],
        )
        fallback = _FakeFallback()
        strategy = OptimizedEasyStrategy(plan_path=plan_path, fallback=fallback)
        strategy.on_game_start(easy_state)

        action = strategy.decide(easy_state)[0]
        assert isinstance(action, MoveAction)
        assert action.action == "move_left"
        assert fallback.decide_calls == 1

    def test_falls_back_after_plan_exhausted(
        self,
        easy_state: GameState,
        tmp_path: Path,
    ) -> None:
        plan_path = tmp_path / "easy_plan.json"
        _write_plan(
            plan_path,
            [{"round": easy_state.round, "bot": 0, "action": "wait"}],
        )
        fallback = _FakeFallback()
        strategy = OptimizedEasyStrategy(plan_path=plan_path, fallback=fallback)
        strategy.on_game_start(easy_state)

        a0 = strategy.decide(easy_state)[0]
        assert isinstance(a0, WaitAction)

        next_state = easy_state.model_copy(update={"round": easy_state.round + 1})
        a1 = strategy.decide(next_state)[0]
        assert isinstance(a1, WaitAction)
        assert fallback.decide_calls == 2

    def test_pickup_item_type_resolves_to_item_id(
        self,
        easy_state: GameState,
        tmp_path: Path,
    ) -> None:
        plan_path = tmp_path / "easy_plan.json"
        _write_plan(
            plan_path,
            [{"round": 0, "bot": 0, "action": "pick_up", "item_type": "milk"}],
        )
        fallback = _FakeFallback()
        custom = easy_state.model_copy(
            update={
                "round": 0,
                "bots": [Bot(id=0, position=(3, 1), inventory=[])],
            },
        )
        strategy = OptimizedEasyStrategy(plan_path=plan_path, fallback=fallback)
        strategy.on_game_start(custom)

        action = strategy.decide(custom)[0]
        assert isinstance(action, PickUpAction)
        assert action.item_id == "item_0"

    def test_invalid_planned_action_disables_plan_and_uses_fallback(
        self,
        easy_state: GameState,
        tmp_path: Path,
    ) -> None:
        plan_path = tmp_path / "easy_plan.json"
        _write_plan(
            plan_path,
            [
                {"round": easy_state.round, "bot": 0, "action": "drop_off"},
                {"round": easy_state.round + 1, "bot": 0, "action": "move_left"},
            ],
        )
        fallback = _FakeFallback()
        strategy = OptimizedEasyStrategy(plan_path=plan_path, fallback=fallback)
        strategy.on_game_start(easy_state)

        first = strategy.decide(easy_state)[0]
        assert isinstance(first, WaitAction)

        next_state = easy_state.model_copy(update={"round": easy_state.round + 1})
        second = strategy.decide(next_state)[0]
        assert isinstance(second, WaitAction)
        assert fallback.decide_calls == 2

    def test_skips_empty_dropoff_and_continues_plan(
        self,
        easy_state: GameState,
        tmp_path: Path,
    ) -> None:
        plan_path = tmp_path / "easy_plan.json"
        _write_plan(
            plan_path,
            [
                {"round": easy_state.round, "bot": 0, "action": "drop_off"},
                {"round": easy_state.round + 1, "bot": 0, "action": "move_left"},
            ],
        )
        fallback = _FakeFallback()
        at_drop_empty = easy_state.model_copy(
            update={
                "bots": [Bot(id=0, position=easy_state.drop_off, inventory=[])],
            },
        )
        strategy = OptimizedEasyStrategy(plan_path=plan_path, fallback=fallback)
        strategy.on_game_start(at_drop_empty)

        action = strategy.decide(at_drop_empty)[0]
        assert isinstance(action, MoveAction)
        assert action.action == "move_left"

    def test_summary_round_limit_caps_plan_replay(
        self,
        easy_state: GameState,
        tmp_path: Path,
    ) -> None:
        plan_path = tmp_path / "easy_plan.json"
        payload = {
            "summary": {"optimal_rounds_for_current_run_orders": easy_state.round + 1},
            "actions": [
                {"round": easy_state.round, "bot": 0, "action": "move_left"},
                {"round": easy_state.round + 1, "bot": 0, "action": "move_right"},
            ],
        }
        plan_path.write_text(json.dumps(payload), encoding="utf-8")

        fallback = _FakeFallback()
        strategy = OptimizedEasyStrategy(plan_path=plan_path, fallback=fallback)
        strategy.on_game_start(easy_state)

        first = strategy.decide(easy_state)[0]
        assert isinstance(first, MoveAction)
        assert first.action == "move_left"

        next_state = easy_state.model_copy(update={"round": easy_state.round + 1})
        second = strategy.decide(next_state)[0]
        assert isinstance(second, WaitAction)
        assert fallback.decide_calls == 2

    def test_delegates_game_over_to_fallback(
        self,
        easy_state: GameState,
        tmp_path: Path,
    ) -> None:
        plan_path = tmp_path / "easy_plan.json"
        _write_plan(plan_path, [])
        fallback = _FakeFallback()
        strategy = OptimizedEasyStrategy(plan_path=plan_path, fallback=fallback)
        strategy.on_game_start(easy_state)
        strategy.on_game_over(
            GameOver(
                type="game_over",
                score=0,
                rounds_used=300,
                items_delivered=0,
                orders_completed=0,
            ),
        )
        assert fallback.game_over_called
