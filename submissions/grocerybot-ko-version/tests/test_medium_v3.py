"""Tests for medium_v3 strategy wiring and collision-safe outputs."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from grocerybot.models import Bot, BotAction, GameState, Order
from grocerybot.planner import BotIntent, next_position_for_action
from grocerybot.strategies.medium_v3 import MediumV3Strategy


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


class TestMediumV3:
    def test_returns_exactly_three_actions(self, medium_state: GameState) -> None:
        strategy = MediumV3Strategy()
        strategy.on_game_start(medium_state)
        actions = strategy.decide(medium_state)
        assert len(actions) == 3
        assert sorted(a.bot for a in actions) == [0, 1, 2]

    def test_no_duplicate_non_dropoff_positions_after_decide(
        self, medium_state: GameState,
    ) -> None:
        strategy = MediumV3Strategy()
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
        strategy = MediumV3Strategy()
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
        strategy = MediumV3Strategy()
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
        strategy = MediumV3Strategy()
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

    def test_non_deliver_vacates_dropoff_when_delivery_pending(
        self, medium_state: GameState,
    ) -> None:
        strategy = MediumV3Strategy()
        custom = medium_state.model_copy(
            update={
                "drop_off": (1, 10),
                "bots": [
                    Bot(id=0, position=(2, 10), inventory=["milk"]),
                    Bot(id=1, position=(1, 10), inventory=[]),
                    Bot(id=2, position=(4, 10), inventory=[]),
                ],
                "orders": [
                    Order(
                        id="a0",
                        items_required=["milk"],
                        items_delivered=[],
                        complete=False,
                        status="active",
                    ),
                    Order(
                        id="p0",
                        items_required=["bread", "eggs", "butter"],
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

        # Bot 1 is not a deliverer and should clear drop-off lane.
        assert by_bot[1].action in {"move_up", "move_down", "move_left", "move_right"}

    def test_dropoff_clearance_not_applied_to_pick_intent(
        self, medium_state: GameState,
    ) -> None:
        strategy = MediumV3Strategy()
        custom = medium_state.model_copy(
            update={
                "drop_off": (1, 10),
                "bots": [
                    Bot(id=0, position=(1, 7), inventory=[]),
                    Bot(id=1, position=(2, 10), inventory=["milk"]),
                    Bot(id=2, position=(4, 10), inventory=[]),
                ],
                "orders": [
                    Order(
                        id="a0",
                        items_required=["milk"],
                        items_delivered=[],
                        complete=False,
                        status="active",
                    ),
                    Order(
                        id="p0",
                        items_required=["bread"],
                        items_delivered=[],
                        complete=False,
                        status="preview",
                    ),
                ],
            },
        )
        strategy.on_game_start(custom)
        strategy._intents.set(0, BotIntent(kind="pick", pickups=("bread",), order_id="a0"))
        strategy._intents.set(1, BotIntent(kind="deliver", target=custom.drop_off, order_id="a0"))
        bot0 = next(b for b in custom.bots if b.id == 0)
        must_clear = strategy._must_clear_dropoff_lane(
            state=custom,
            bot=bot0,
            delivery_bots={1},
        )
        assert must_clear is False
