"""Tests for optimized_medium_v4 strategy: checkpointed plan replay + fallback."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from uuid import uuid4

import pytest

from grocerybot.models import Bot, GameOver, GameState, MoveAction, WaitAction
from grocerybot.strategies.base import Strategy
from grocerybot.strategies.optimized_medium_v4 import OptimizedMediumV4Strategy


@pytest.fixture()
def medium_state_data() -> dict[str, Any]:
    path = (
        Path(__file__).resolve().parent.parent
        / "spec"
        / "examples"
        / "medium"
        / "game_state.json"
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


def _active_needed(state: GameState) -> list[str]:
    active = next(order for order in state.orders if order.status == "active")
    needed = list(active.items_required)
    for delivered in active.items_delivered:
        if delivered in needed:
            needed.remove(delivered)
    return sorted(needed)


def _checkpoint_for_state(state: GameState, round_no: int | None = None) -> dict[str, object]:
    return {
        "round": state.round if round_no is None else round_no,
        "active_order_id": next(order for order in state.orders if order.status == "active").id,
        "active_needed": _active_needed(state),
        "orders_completed": 0,
        "score": state.score,
        "bots": [
            {
                "id": bot.id,
                "position": [bot.position[0], bot.position[1]],
                "inventory": sorted(bot.inventory),
            }
            for bot in state.bots
        ],
    }


def _write_plan(path: Path, state: GameState, actions: list[dict[str, object]]) -> None:
    checkpoint = _checkpoint_for_state(state, round_no=state.round)
    payload = {
        "meta": {"level": "medium", "date": "2026-03-02"},
        "summary": {"optimal_rounds": state.round + 1},
        "checkpoints": [checkpoint],
        "actions": actions,
    }
    path.write_text(json.dumps(payload), encoding="utf-8")


def _temp_plan_path() -> Path:
    return Path.cwd() / f"_tmp_medium_plan_v4_{uuid4().hex}.json"


class TestOptimizedMediumV4Strategy:
    def test_replays_checkpointed_actions(
        self,
        medium_state: GameState,
    ) -> None:
        plan_path = _temp_plan_path()
        try:
            _write_plan(
                plan_path,
                medium_state,
                [
                    {"round": medium_state.round, "bot": 0, "action": "wait"},
                    {"round": medium_state.round, "bot": 1, "action": "wait"},
                    {"round": medium_state.round, "bot": 2, "action": "wait"},
                ],
            )
            fallback = _FakeFallback()
            strategy = OptimizedMediumV4Strategy(plan_path=plan_path, fallback=fallback)
            strategy.on_game_start(medium_state)

            actions = strategy.decide(medium_state)
            assert len(actions) == 3
            assert all(isinstance(a, WaitAction) for a in actions)
            assert fallback.decide_calls == 0
        finally:
            plan_path.unlink(missing_ok=True)

    def test_falls_back_on_checkpoint_mismatch(
        self,
        medium_state: GameState,
    ) -> None:
        plan_path = _temp_plan_path()
        try:
            _write_plan(
                plan_path,
                medium_state,
                [
                    {"round": medium_state.round, "bot": 0, "action": "wait"},
                    {"round": medium_state.round, "bot": 1, "action": "wait"},
                    {"round": medium_state.round, "bot": 2, "action": "wait"},
                ],
            )
            mismatch = medium_state.model_copy(
                update={
                    "bots": [
                        Bot(id=0, position=(4, 7), inventory=["milk"]),
                        medium_state.bots[1],
                        medium_state.bots[2],
                    ],
                },
            )
            fallback = _FakeFallback()
            strategy = OptimizedMediumV4Strategy(plan_path=plan_path, fallback=fallback)
            strategy.on_game_start(medium_state)

            actions = strategy.decide(mismatch)
            assert len(actions) == 3
            assert fallback.decide_calls == 1
            assert all(isinstance(a, WaitAction) for a in actions)
        finally:
            plan_path.unlink(missing_ok=True)

    def test_falls_back_after_plan_round_limit(
        self,
        medium_state: GameState,
    ) -> None:
        plan_path = _temp_plan_path()
        try:
            _write_plan(
                plan_path,
                medium_state,
                [
                    {"round": medium_state.round, "bot": 0, "action": "wait"},
                    {"round": medium_state.round, "bot": 1, "action": "wait"},
                    {"round": medium_state.round, "bot": 2, "action": "wait"},
                ],
            )
            fallback = _FakeFallback()
            strategy = OptimizedMediumV4Strategy(plan_path=plan_path, fallback=fallback)
            strategy.on_game_start(medium_state)

            strategy.decide(medium_state)
            next_state = medium_state.model_copy(
                update={
                    "round": medium_state.round
                    + OptimizedMediumV4Strategy.RESYNC_BACK_WINDOW
                    + 2,
                },
            )
            actions = strategy.decide(next_state)
            assert len(actions) == 3
            assert fallback.decide_calls == 1
            assert all(isinstance(a, WaitAction) for a in actions)
        finally:
            plan_path.unlink(missing_ok=True)

    def test_delegates_game_over_to_fallback(
        self,
        medium_state: GameState,
    ) -> None:
        plan_path = _temp_plan_path()
        try:
            _write_plan(
                plan_path,
                medium_state,
                [
                    {"round": medium_state.round, "bot": 0, "action": "wait"},
                    {"round": medium_state.round, "bot": 1, "action": "wait"},
                    {"round": medium_state.round, "bot": 2, "action": "wait"},
                ],
            )
            fallback = _FakeFallback()
            strategy = OptimizedMediumV4Strategy(plan_path=plan_path, fallback=fallback)
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
        finally:
            plan_path.unlink(missing_ok=True)

    def test_resyncs_after_one_tick_drift(
        self,
        medium_state: GameState,
    ) -> None:
        plan_path = _temp_plan_path()
        try:
            rnd = medium_state.round
            moved_state = medium_state.model_copy(
                update={
                    "round": rnd + 1,
                    "bots": [
                        Bot(
                            id=0,
                            position=(
                                medium_state.bots[0].position[0] - 1,
                                medium_state.bots[0].position[1],
                            ),
                            inventory=list(medium_state.bots[0].inventory),
                        ),
                        medium_state.bots[1],
                        medium_state.bots[2],
                    ],
                },
            )
            payload = {
                "meta": {"level": "medium", "date": "2026-03-02"},
                "summary": {"optimal_rounds": rnd + 2},
                "checkpoints": [
                    _checkpoint_for_state(medium_state, round_no=rnd),
                    _checkpoint_for_state(moved_state, round_no=rnd + 1),
                ],
                "actions": [
                    {"round": rnd, "bot": 0, "action": "move_left"},
                    {"round": rnd, "bot": 1, "action": "wait"},
                    {"round": rnd, "bot": 2, "action": "wait"},
                    {"round": rnd + 1, "bot": 0, "action": "wait"},
                    {"round": rnd + 1, "bot": 1, "action": "wait"},
                    {"round": rnd + 1, "bot": 2, "action": "wait"},
                ],
            }
            plan_path.write_text(json.dumps(payload), encoding="utf-8")

            # Simulate one-tick lag: round advanced, but bot0 did not move yet.
            drifted = medium_state.model_copy(update={"round": rnd + 1})
            fallback = _FakeFallback()
            strategy = OptimizedMediumV4Strategy(plan_path=plan_path, fallback=fallback)
            strategy.on_game_start(medium_state)

            actions = strategy.decide(drifted)
            assert len(actions) == 3
            assert isinstance(actions[0], MoveAction)
            assert actions[0].action == "move_left"
        finally:
            plan_path.unlink(missing_ok=True)

    def test_recovers_after_transient_checkpoint_mismatch(
        self,
        medium_state: GameState,
    ) -> None:
        plan_path = _temp_plan_path()
        try:
            rnd = medium_state.round
            next_state = medium_state.model_copy(update={"round": rnd + 1})
            payload = {
                "meta": {"level": "medium", "date": "2026-03-02"},
                "summary": {"optimal_rounds": rnd + 2},
                "checkpoints": [
                    _checkpoint_for_state(medium_state, round_no=rnd),
                    _checkpoint_for_state(next_state, round_no=rnd + 1),
                ],
                "actions": [
                    {"round": rnd, "bot": 0, "action": "wait"},
                    {"round": rnd, "bot": 1, "action": "wait"},
                    {"round": rnd, "bot": 2, "action": "wait"},
                    {"round": rnd + 1, "bot": 0, "action": "wait"},
                    {"round": rnd + 1, "bot": 1, "action": "wait"},
                    {"round": rnd + 1, "bot": 2, "action": "wait"},
                ],
            }
            plan_path.write_text(json.dumps(payload), encoding="utf-8")

            mismatch = medium_state.model_copy(
                update={
                    "bots": [
                        Bot(
                            id=0,
                            position=(
                                medium_state.bots[0].position[0] + 1,
                                medium_state.bots[0].position[1],
                            ),
                            inventory=list(medium_state.bots[0].inventory),
                        ),
                        medium_state.bots[1],
                        medium_state.bots[2],
                    ],
                },
            )

            fallback = _FakeFallback()
            strategy = OptimizedMediumV4Strategy(plan_path=plan_path, fallback=fallback)
            strategy.on_game_start(medium_state)

            first = strategy.decide(mismatch)
            assert len(first) == 3
            assert fallback.decide_calls == 1
            assert all(isinstance(a, WaitAction) for a in first)

            second = strategy.decide(next_state)
            assert len(second) == 3
            assert fallback.decide_calls == 1
            assert all(isinstance(a, WaitAction) for a in second)

            diag = strategy.replay_diagnostics(next_state, second, timed_out=False)
            assert diag["plan_enabled"] is True
            assert diag["transient_mismatches"] == 1
            assert diag["hard_divergences"] == 0
            assert diag["checkpoint_miss_streak"] == 0
        finally:
            plan_path.unlink(missing_ok=True)

    def test_disables_after_sustained_checkpoint_mismatch_window(
        self,
        medium_state: GameState,
    ) -> None:
        plan_path = _temp_plan_path()
        try:
            _write_plan(
                plan_path,
                medium_state,
                [
                    {"round": medium_state.round, "bot": 0, "action": "wait"},
                    {"round": medium_state.round, "bot": 1, "action": "wait"},
                    {"round": medium_state.round, "bot": 2, "action": "wait"},
                ],
            )
            mismatch = medium_state.model_copy(
                update={
                    "bots": [
                        Bot(
                            id=0,
                            position=(
                                medium_state.bots[0].position[0] + 1,
                                medium_state.bots[0].position[1],
                            ),
                            inventory=list(medium_state.bots[0].inventory),
                        ),
                        medium_state.bots[1],
                        medium_state.bots[2],
                    ],
                },
            )
            fallback = _FakeFallback()
            strategy = OptimizedMediumV4Strategy(plan_path=plan_path, fallback=fallback)
            strategy.on_game_start(medium_state)

            disable_at = OptimizedMediumV4Strategy.MAX_HARD_DIVERGENCE_STREAK
            last_state = mismatch
            last_actions = []
            for step in range(disable_at - 1):
                last_state = mismatch.model_copy(update={"round": medium_state.round + step})
                last_actions = strategy.decide(last_state)
            pre_disable = strategy.replay_diagnostics(last_state, last_actions, timed_out=False)
            assert pre_disable["plan_enabled"] is True

            last_state = mismatch.model_copy(
                update={"round": medium_state.round + disable_at - 1},
            )
            last_actions = strategy.decide(last_state)
            post_disable = strategy.replay_diagnostics(last_state, last_actions, timed_out=False)
            assert post_disable["plan_enabled"] is False
            assert post_disable["hard_divergences"] >= 1
            assert post_disable["checkpoint_miss_streak"] >= disable_at
            assert fallback.decide_calls == disable_at
            assert all(isinstance(a, WaitAction) for a in last_actions)
        finally:
            plan_path.unlink(missing_ok=True)
