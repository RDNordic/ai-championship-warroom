"""Tests for greedy strategy wiring and collision-safe outputs."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from grocerybot.models import Bot, BotAction, GameState, Order
from grocerybot.planner import next_position_for_action
from grocerybot.strategies.greedy import GreedyStrategy


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


class TestGreedyStrategy:
    def test_returns_exactly_three_actions(self, medium_state: GameState) -> None:
        strategy = GreedyStrategy()
        strategy.on_game_start(medium_state)
        actions = strategy.decide(medium_state)
        assert len(actions) == 3
        assert sorted(a.bot for a in actions) == [0, 1, 2]

    def test_no_duplicate_non_dropoff_positions_after_decide(
        self, medium_state: GameState,
    ) -> None:
        strategy = GreedyStrategy()
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
                        items_required=["cheese"],
                        items_delivered=[],
                        complete=False,
                        status="active",
                    ),
                    Order(
                        id="p0",
                        items_required=["butter"],
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

    def test_shared_spawn_does_not_force_all_wait(
        self, medium_state: GameState,
    ) -> None:
        strategy = GreedyStrategy()
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
        assert any(a.action != "wait" for a in actions)

    def test_dropoff_blockers_step_aside_when_delivery_is_pending(
        self, medium_state: GameState,
    ) -> None:
        strategy = GreedyStrategy()
        custom = medium_state.model_copy(
            update={
                "drop_off": (1, 10),
                "bots": [
                    Bot(id=0, position=(1, 9), inventory=["milk", "cream"]),
                    Bot(id=1, position=(1, 10), inventory=["eggs"]),
                    Bot(id=2, position=(2, 10), inventory=["yogurt", "cream"]),
                ],
                "orders": [
                    Order(
                        id="a0",
                        items_required=["cream", "pasta", "cream", "milk"],
                        items_delivered=["pasta", "cream"],
                        complete=False,
                        status="active",
                    ),
                    Order(
                        id="p0",
                        items_required=["yogurt", "eggs", "cream"],
                        items_delivered=[],
                        complete=False,
                        status="preview",
                    ),
                ],
            },
        )
        strategy.on_game_start(custom)
        actions = strategy.decide(custom)
        by_bot = {a.bot: a for a in actions}

        assert by_bot[1].action == "move_up"
        assert by_bot[0].action in {"move_right", "move_up", "wait"}
        assert by_bot[2].action in {"move_up", "wait"}
