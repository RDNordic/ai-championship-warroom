"""Smoke tests for optimized_medium_v5 strategy."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from uuid import uuid4

import pytest

from grocerybot.models import GameOver, GameState, WaitAction
from grocerybot.strategies.base import Strategy
from grocerybot.strategies.optimized_medium_v5 import OptimizedMediumV5Strategy
from scripts.optimize import load_snapshot
from scripts.optimize_medium_v5 import (
    MOVE_DELTAS,
    SimBot,
    SimOrder,
    _apply_boundary_carryover,
    plan_medium_v5,
)


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
        self.decide_calls = 0
        self.game_over_called = False

    def on_game_start(self, state: GameState) -> None:
        return

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


def _temp_plan_path() -> Path:
    return Path.cwd() / f"_tmp_medium_plan_v5_{uuid4().hex}.json"


def _write_wait_plan(path: Path, state: GameState) -> None:
    payload = {
        "meta": {"level": "medium", "date": "2026-03-02"},
        "summary": {"optimal_rounds": state.round + 1},
        "checkpoints": [
            {
                "round": state.round,
                "active_order_id": next(
                    order.id for order in state.orders if order.status == "active"
                ),
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
            },
        ],
        "actions": [
            {"round": state.round, "bot": 0, "action": "wait"},
            {"round": state.round, "bot": 1, "action": "wait"},
            {"round": state.round, "bot": 2, "action": "wait"},
        ],
    }
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_replays_wait_plan(medium_state: GameState) -> None:
    plan_path = _temp_plan_path()
    try:
        _write_wait_plan(plan_path, medium_state)
        fallback = _FakeFallback()
        strategy = OptimizedMediumV5Strategy(plan_path=plan_path, fallback=fallback)
        strategy.on_game_start(medium_state)
        actions = strategy.decide(medium_state)
        assert len(actions) == 3
        assert all(isinstance(a, WaitAction) for a in actions)
        assert fallback.decide_calls == 0
    finally:
        plan_path.unlink(missing_ok=True)


def test_delegates_game_over(medium_state: GameState) -> None:
    plan_path = _temp_plan_path()
    try:
        _write_wait_plan(plan_path, medium_state)
        fallback = _FakeFallback()
        strategy = OptimizedMediumV5Strategy(plan_path=plan_path, fallback=fallback)
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


def test_planner_blocks_move_into_occupied_drop_off() -> None:
    snapshot = load_snapshot(Path("data/medium_2026-03-03.json"))
    sim = plan_medium_v5(
        snapshot=snapshot,
        spawns=[(14, 10), (14, 10), (14, 10)],
        max_orders=12,
        round_cap=120,
    )
    actions_raw = sim.get("actions")
    checkpoints_raw = sim.get("checkpoints")
    assert isinstance(actions_raw, list)
    assert isinstance(checkpoints_raw, list)
    actions_by_round: dict[int, list[dict[str, object]]] = {}
    for entry in actions_raw:
        assert isinstance(entry, dict)
        round_no = entry.get("round")
        assert isinstance(round_no, int)
        actions_by_round.setdefault(round_no, []).append(entry)

    for checkpoint in checkpoints_raw:
        assert isinstance(checkpoint, dict)
        round_no = checkpoint.get("round")
        bots_raw = checkpoint.get("bots")
        assert isinstance(round_no, int)
        assert isinstance(bots_raw, list)
        positions: dict[int, tuple[int, int]] = {}
        counts: dict[tuple[int, int], int] = {}
        for bot in bots_raw:
            assert isinstance(bot, dict)
            bot_id = bot.get("id")
            pos = bot.get("position")
            assert isinstance(bot_id, int)
            assert isinstance(pos, list) and len(pos) == 2
            assert isinstance(pos[0], int) and isinstance(pos[1], int)
            cur = (pos[0], pos[1])
            positions[bot_id] = cur
            counts[cur] = counts.get(cur, 0) + 1

        by_bot = {
            int(a["bot"]): str(a["action"])
            for a in actions_by_round.get(round_no, [])
            if isinstance(a, dict) and isinstance(a.get("bot"), int)
        }
        for bot_id in sorted(positions):
            action_name = by_bot.get(bot_id, "wait")
            if action_name not in MOVE_DELTAS:
                continue
            start = positions[bot_id]
            dx, dy = MOVE_DELTAS[action_name]
            nxt = (start[0] + dx, start[1] + dy)
            assert (
                counts.get(nxt, 0) <= 0
            ), f"round {round_no}: bot {bot_id} moved into occupied {nxt}"
            counts[start] -= 1
            if counts[start] == 0:
                counts.pop(start, None)
            counts[nxt] = counts.get(nxt, 0) + 1
            positions[bot_id] = nxt


def test_boundary_carryover_consumes_new_active_items() -> None:
    order = SimOrder(
        id="next",
        required=["cream", "yogurt", "cheese"],
        delivered=[],
    )
    bots = [
        SimBot(id=0, pos=(1, 10), inventory=["cream", "milk"]),
        SimBot(id=1, pos=(1, 9), inventory=["yogurt"]),
        SimBot(id=2, pos=(1, 10), inventory=["bread", "yogurt"]),
    ]

    delivered = _apply_boundary_carryover(order, bots, drop_off=(1, 10))

    assert delivered == 2
    assert sorted(order.delivered) == ["cream", "yogurt"]
    assert bots[0].inventory == ["milk"]
    assert bots[1].inventory == ["yogurt"]
    assert bots[2].inventory == ["bread"]
