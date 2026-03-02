"""Tests for medium_v4 strategy wiring and collision-safe outputs."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from grocerybot.models import Bot, BotAction, GameState, Order
from grocerybot.planner import next_position_for_action
from grocerybot.strategies.medium_v4 import MediumV4Strategy


@pytest.fixture()
def medium_state() -> GameState:
    path = (
        Path(__file__).resolve().parent.parent
        / "spec"
        / "examples"
        / "medium"
        / "game_state.json"
    )
    data: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    return GameState.model_validate(data)


def _non_dropoff_final_positions(
    state: GameState,
    actions: list[BotAction],
) -> list[tuple[int, int]]:
    by_id = {bot.id: bot for bot in state.bots}
    finals: list[tuple[int, int]] = []
    for action in actions:
        bot = by_id[action.bot]
        pos = next_position_for_action(bot.position, action)
        if pos != state.drop_off:
            finals.append(pos)
    return finals


class TestMediumV4:
    def test_returns_exactly_three_actions(self, medium_state: GameState) -> None:
        strategy = MediumV4Strategy()
        strategy.on_game_start(medium_state)
        actions = strategy.decide(medium_state)
        assert len(actions) == 3
        assert sorted(a.bot for a in actions) == [0, 1, 2]

    def test_no_duplicate_non_dropoff_positions_after_decide(
        self, medium_state: GameState,
    ) -> None:
        strategy = MediumV4Strategy()
        custom = medium_state.model_copy(
            update={
                "bots": [
                    Bot(id=0, position=(5, 5), inventory=[]),
                    Bot(id=1, position=(5, 7), inventory=[]),
                    Bot(id=2, position=(6, 7), inventory=[]),
                ],
                "orders": [
                    Order(
                        id="a0",
                        items_required=["cheese", "milk", "eggs"],
                        items_delivered=[],
                        complete=False,
                        status="active",
                    ),
                    Order(
                        id="p0",
                        items_required=["butter", "rice", "pasta"],
                        items_delivered=[],
                        complete=False,
                        status="preview",
                    ),
                ],
            },
        )
        strategy.on_game_start(custom)
        actions = strategy.decide(custom)
        finals = _non_dropoff_final_positions(custom, actions)
        assert len(finals) == len(set(finals))

    def test_shared_spawn_produces_non_wait_action(
        self, medium_state: GameState,
    ) -> None:
        strategy = MediumV4Strategy()
        custom = medium_state.model_copy(
            update={
                "round": 0,
                "bots": [
                    Bot(id=0, position=(14, 10), inventory=[]),
                    Bot(id=1, position=(14, 10), inventory=[]),
                    Bot(id=2, position=(14, 10), inventory=[]),
                ],
                "drop_off": (1, 10),
                "orders": [
                    Order(
                        id="a0",
                        items_required=["milk", "eggs", "bread", "milk"],
                        items_delivered=[],
                        complete=False,
                        status="active",
                    ),
                    Order(
                        id="p0",
                        items_required=["butter", "pasta", "rice"],
                        items_delivered=[],
                        complete=False,
                        status="preview",
                    ),
                ],
            },
        )
        strategy.on_game_start(custom)
        actions = strategy.decide(custom)
        assert any(action.action != "wait" for action in actions)

    def test_replay_diagnostics_payload(
        self, medium_state: GameState,
    ) -> None:
        strategy = MediumV4Strategy()
        strategy.on_game_start(medium_state)
        actions = strategy.decide(medium_state)
        diag = strategy.replay_diagnostics(
            state=medium_state,
            actions=actions,
            timed_out=False,
        )
        assert isinstance(diag, dict)
        assert "traffic_blocks" in diag
        assert "blocked_moves" in diag
        assert "greedy_assignments" in diag
        assert "per_bot" in diag
        per_bot = diag["per_bot"]
        assert isinstance(per_bot, dict)
        assert set(per_bot.keys()) == {"0", "1", "2"}
        for payload in per_bot.values():
            assert isinstance(payload, dict)
            assert "intent" in payload
            assert "blocked_ticks" in payload
            assert "primary_action" in payload
            assert "final_action" in payload
            assert "wait_reason" in payload

    def test_replay_diagnostics_marks_timeout(
        self, medium_state: GameState,
    ) -> None:
        strategy = MediumV4Strategy()
        strategy.on_game_start(medium_state)
        actions = strategy.decide(medium_state)
        diag = strategy.replay_diagnostics(
            state=medium_state,
            actions=actions,
            timed_out=True,
        )
        assert isinstance(diag, dict)
        assert diag.get("timed_out") is True
        per_bot = diag["per_bot"]
        assert isinstance(per_bot, dict)
        for payload in per_bot.values():
            assert isinstance(payload, dict)
            assert payload.get("final_action") == "wait"
            assert payload.get("wait_reason") == "time_budget_exceeded"
