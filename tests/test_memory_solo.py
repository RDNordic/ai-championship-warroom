"""Tests for memory_solo.py strategy."""

from __future__ import annotations

from typing import Any
from unittest.mock import patch

import pytest

from grocerybot.daily_memory import DailySnapshot, OrderRecord
from grocerybot.grid import PassableGrid, adjacent_walkable
from grocerybot.models import GameState, PickUpAction
from grocerybot.strategies.memory_solo import (
    MemorySoloStrategy,
    _get_active_order,
    _get_preview_order,
    _remaining_needed,
)


@pytest.fixture()
def easy_state(easy_game_state_data: dict[str, Any]) -> GameState:
    return GameState.model_validate(easy_game_state_data)


@pytest.fixture()
def grid(easy_state: GameState) -> PassableGrid:
    return PassableGrid(easy_state)


@pytest.fixture()
def today_snapshot(easy_state: GameState) -> DailySnapshot:
    """A snapshot that matches today's date (mocked)."""
    from grocerybot.daily_memory import build_snapshot_from_state

    snap = build_snapshot_from_state(easy_state, "easy")
    return snap.model_copy(
        update={
            "orders": [
                OrderRecord(
                    id="order_0",
                    items_required=["milk", "bread", "eggs"],
                ),
                OrderRecord(
                    id="order_1",
                    items_required=["juice", "milk", "bread"],
                ),
            ],
        },
    )


class TestHelpers:
    def test_get_active_order(self, easy_state: GameState) -> None:
        active = _get_active_order(easy_state)
        assert active is not None
        assert active.status == "active"

    def test_get_preview_order(self, easy_state: GameState) -> None:
        preview = _get_preview_order(easy_state)
        assert preview is not None
        assert preview.status == "preview"

    def test_remaining_needed_basic(self, easy_state: GameState) -> None:
        active = _get_active_order(easy_state)
        assert active is not None
        needed = _remaining_needed(active, [])
        assert sorted(needed) == sorted(active.items_required)

    def test_remaining_needed_with_inventory(
        self, easy_state: GameState,
    ) -> None:
        active = _get_active_order(easy_state)
        assert active is not None
        needed = _remaining_needed(active, ["milk"])
        assert "milk" not in needed

    def test_remaining_needed_with_delivered(
        self, easy_state: GameState,
    ) -> None:
        active = _get_active_order(easy_state)
        assert active is not None
        # The easy example has items_delivered = [], so needed == required
        needed = _remaining_needed(active, [])
        assert len(needed) == len(active.items_required)


class TestDiscoveryMode:
    def test_no_memory_file(self, easy_state: GameState) -> None:
        strategy = MemorySoloStrategy(level="easy")
        with patch(
            "grocerybot.strategies.memory_solo.load_snapshot",
            return_value=None,
        ):
            strategy.on_game_start(easy_state)
        assert not strategy._has_memory

    def test_accumulates_orders(self, easy_state: GameState) -> None:
        strategy = MemorySoloStrategy(level="easy")
        with patch(
            "grocerybot.strategies.memory_solo.load_snapshot",
            return_value=None,
        ):
            strategy.on_game_start(easy_state)
        assert len(strategy._seen_orders) == 2  # active + preview


class TestOptimizedMode:
    def test_has_memory(
        self,
        easy_state: GameState,
        today_snapshot: DailySnapshot,
    ) -> None:
        strategy = MemorySoloStrategy(level="easy")
        with patch(
            "grocerybot.strategies.memory_solo.load_snapshot",
            return_value=today_snapshot,
        ):
            strategy.on_game_start(easy_state)
        assert strategy._has_memory


class TestPlanTrip:
    def test_respects_inventory_cap(
        self,
        easy_state: GameState,
        grid: PassableGrid,
    ) -> None:
        strategy = MemorySoloStrategy(level="easy")
        with patch(
            "grocerybot.strategies.memory_solo.load_snapshot",
            return_value=None,
        ):
            strategy.on_game_start(easy_state)

        trip = strategy._plan_trip(
            (5, 4),
            ["existing1", "existing2"],  # 2 items in inventory
            ["milk", "bread"],  # need 2 active
            [],
            grid,
        )
        assert len(trip) <= 1  # only 1 space left

    def test_adds_preview_if_space(
        self,
        easy_state: GameState,
        grid: PassableGrid,
    ) -> None:
        strategy = MemorySoloStrategy(level="easy")
        with patch(
            "grocerybot.strategies.memory_solo.load_snapshot",
            return_value=None,
        ):
            strategy.on_game_start(easy_state)

        trip = strategy._plan_trip(
            (5, 4),
            [],  # empty inventory
            ["milk"],  # 1 active needed
            ["bread"],  # 1 preview available
            grid,
        )
        assert len(trip) == 2  # 1 active + 1 preview


class TestOpportunisticPick:
    def test_pick_when_adjacent(
        self, easy_state: GameState, grid: PassableGrid,
    ) -> None:
        strategy = MemorySoloStrategy(level="easy")
        # Find an item and an adjacent walkable cell
        item = easy_state.items[0]
        adj = adjacent_walkable(item.position, grid)
        assert len(adj) > 0

        action = strategy._opportunistic_pick(
            easy_state, 0, adj[0], [item.type], grid,
        )
        assert action is not None
        assert isinstance(action, PickUpAction)
        assert action.item_id == item.id

    def test_no_pick_when_not_adjacent(
        self, easy_state: GameState, grid: PassableGrid,
    ) -> None:
        strategy = MemorySoloStrategy(level="easy")
        # Use a position far from any item
        action = strategy._opportunistic_pick(
            easy_state, 0, (5, 8), ["milk"], grid,
        )
        assert action is None
