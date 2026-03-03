"""Tests for optimized_medium strategy: 3-bot plan replay + fallback."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from grocerybot.models import Bot, GameOver, GameState, MoveAction, WaitAction
from grocerybot.strategies.base import Strategy
from grocerybot.strategies.optimized_medium import OptimizedMediumStrategy


@pytest.fixture()
def medium_state_data() -> dict[str, Any]:
    path = (
        Path(__file__).resolve().parent.parent
        / "spec" / "examples" / "medium" / "game_state.json"
    )
    with open(path, encoding="utf-8") as f:
        return json.load(f)


@pytest.fixture()
def medium_state(medium_state_data: dict[str, Any]) -> GameState:
    return GameState.model_validate(medium_state_data)


class _FakeFallback(Strategy):
    def __init__(self) -> None:
        self.started = False
        self.decide_calls = 0
        self.game_over_called = False

    def on_game_start(self, state: GameState) -> None:
        self.started = True

    def decide(self, state: GameState) -> list[WaitAction]:
        self.decide_calls += 1
        return [WaitAction(bot=b.id) for b in state.bots]

    def on_game_over(self, result: GameOver) -> None:
        self.game_over_called = True


def _write_plan(path: Path, actions: list[dict[str, object]]) -> None:
    payload = {
        "meta": {"level": "medium", "date": "2026-03-02"},
        "actions": actions,
    }
    path.write_text(json.dumps(payload), encoding="utf-8")


class TestOptimizedMediumStrategy:
    def test_replays_3bot_planned_actions(
        self,
        medium_state: GameState,
        tmp_path: Path,
    ) -> None:
        plan_path = tmp_path / "medium_plan.json"
        rnd = medium_state.round
        _write_plan(
            plan_path,
            [
                {"round": rnd, "bot": 0, "action": "move_left"},
                {"round": rnd, "bot": 1, "action": "move_up"},
                {"round": rnd, "bot": 2, "action": "wait"},
            ],
        )
        fallback = _FakeFallback()
        strategy = OptimizedMediumStrategy(plan_path=plan_path, fallback=fallback)
        strategy.on_game_start(medium_state)

        actions = strategy.decide(medium_state)
        assert len(actions) == 3
        assert isinstance(actions[0], MoveAction)
        assert actions[0].action == "move_left"
        assert isinstance(actions[1], MoveAction)
        assert actions[1].action == "move_up"
        assert isinstance(actions[2], WaitAction)

    def test_falls_back_when_plan_exhausted(
        self,
        medium_state: GameState,
        tmp_path: Path,
    ) -> None:
        plan_path = tmp_path / "medium_plan.json"
        rnd = medium_state.round
        _write_plan(
            plan_path,
            [
                {"round": rnd, "bot": 0, "action": "wait"},
                {"round": rnd, "bot": 1, "action": "wait"},
                {"round": rnd, "bot": 2, "action": "wait"},
            ],
        )
        fallback = _FakeFallback()
        strategy = OptimizedMediumStrategy(plan_path=plan_path, fallback=fallback)
        strategy.on_game_start(medium_state)

        strategy.decide(medium_state)
        next_state = medium_state.model_copy(update={"round": rnd + 1})
        actions = strategy.decide(next_state)
        assert len(actions) == 3
        assert fallback.decide_calls == 2  # called both rounds (for fallback prep)

    def test_invalid_action_waits_per_bot_not_global_disable(
        self,
        medium_state: GameState,
        tmp_path: Path,
    ) -> None:
        plan_path = tmp_path / "medium_plan.json"
        rnd = medium_state.round
        # Bot 0 at (3,7) — drop_off at (13,10), so drop_off is invalid
        _write_plan(
            plan_path,
            [
                {"round": rnd, "bot": 0, "action": "drop_off"},
                {"round": rnd, "bot": 1, "action": "move_up"},
                {"round": rnd, "bot": 2, "action": "wait"},
            ],
        )
        fallback = _FakeFallback()
        strategy = OptimizedMediumStrategy(plan_path=plan_path, fallback=fallback)
        strategy.on_game_start(medium_state)

        actions = strategy.decide(medium_state)
        assert len(actions) == 3
        # Bot 0 invalid → waits, bot 1 follows plan, bot 2 follows plan
        assert isinstance(actions[0], WaitAction)  # bot 0 skipped
        assert isinstance(actions[1], MoveAction)   # bot 1 plan ok
        assert actions[1].action == "move_up"
        assert isinstance(actions[2], WaitAction)    # bot 2 plan was wait

    def test_missing_plan_file_uses_fallback(
        self,
        medium_state: GameState,
        tmp_path: Path,
    ) -> None:
        plan_path = tmp_path / "nonexistent.json"
        fallback = _FakeFallback()
        strategy = OptimizedMediumStrategy(plan_path=plan_path, fallback=fallback)
        strategy.on_game_start(medium_state)

        actions = strategy.decide(medium_state)
        assert len(actions) == 3
        assert fallback.decide_calls == 1

    def test_delegates_game_over_to_fallback(
        self,
        medium_state: GameState,
        tmp_path: Path,
    ) -> None:
        plan_path = tmp_path / "medium_plan.json"
        _write_plan(plan_path, [])
        fallback = _FakeFallback()
        strategy = OptimizedMediumStrategy(plan_path=plan_path, fallback=fallback)
        strategy.on_game_start(medium_state)
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

    def test_plan_grouped_by_round_correctly(
        self,
        medium_state: GameState,
        tmp_path: Path,
    ) -> None:
        plan_path = tmp_path / "medium_plan.json"
        rnd = medium_state.round
        _write_plan(
            plan_path,
            [
                {"round": rnd, "bot": 0, "action": "move_left"},
                {"round": rnd, "bot": 1, "action": "move_up"},
                {"round": rnd, "bot": 2, "action": "wait"},
                {"round": rnd + 1, "bot": 0, "action": "move_left"},
                {"round": rnd + 1, "bot": 1, "action": "move_up"},
                {"round": rnd + 1, "bot": 2, "action": "move_left"},
            ],
        )
        fallback = _FakeFallback()
        strategy = OptimizedMediumStrategy(plan_path=plan_path, fallback=fallback)
        strategy.on_game_start(medium_state)

        # Round 1
        a1 = strategy.decide(medium_state)
        assert len(a1) == 3
        assert isinstance(a1[0], MoveAction)

        # Round 2
        next_state = medium_state.model_copy(
            update={
                "round": rnd + 1,
                "bots": [
                    Bot(id=0, position=(2, 7), inventory=["milk"]),
                    Bot(id=1, position=(7, 2), inventory=[]),
                    Bot(id=2, position=(11, 9), inventory=["bread", "eggs"]),
                ],
            },
        )
        a2 = strategy.decide(next_state)
        assert len(a2) == 3
        assert isinstance(a2[2], MoveAction)
        assert a2[2].action == "move_left"
