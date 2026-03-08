"""Tests for daily_memory.py — snapshot persistence."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

from grocerybot.daily_memory import (
    DailySnapshot,
    OrderRecord,
    build_snapshot_from_state,
    load_snapshot,
    merge_orders,
    save_snapshot,
    snapshot_path,
)
from grocerybot.models import GameState


@pytest.fixture()
def easy_state(easy_game_state_data: dict[str, Any]) -> GameState:
    return GameState.model_validate(easy_game_state_data)


@pytest.fixture()
def sample_snapshot() -> DailySnapshot:
    return DailySnapshot(
        date="2026-03-01",
        level="easy",
        grid_width=12,
        grid_height=10,
        walls=[[0, 0], [1, 0]],
        drop_off=[9, 8],
        item_type_to_positions={
            "milk": [[3, 2], [7, 2]],
            "bread": [[3, 4]],
        },
        orders=[
            OrderRecord(id="order_0", items_required=["milk", "bread", "milk"]),
        ],
    )


class TestSnapshotPath:
    def test_format(self) -> None:
        p = snapshot_path("easy", "2026-03-01")
        assert p.name == "easy_2026-03-01.json"
        assert p.parent.name == "data"

    def test_different_levels(self) -> None:
        assert snapshot_path("easy", "2026-03-01") != snapshot_path(
            "medium", "2026-03-01",
        )


class TestBuildSnapshotFromState:
    def test_captures_items(self, easy_state: GameState) -> None:
        snap = build_snapshot_from_state(easy_state, "easy")
        assert snap.level == "easy"
        assert snap.grid_width == 12
        assert snap.grid_height == 10
        assert len(snap.item_type_to_positions) > 0
        assert snap.orders == []

    def test_item_types_correct(self, easy_state: GameState) -> None:
        snap = build_snapshot_from_state(easy_state, "easy")
        types = set(snap.item_type_to_positions.keys())
        state_types = {item.type for item in easy_state.items}
        assert types == state_types


class TestLoadSnapshot:
    def test_missing_returns_none(self) -> None:
        # data/ dir likely doesn't have a file for this level/date
        with patch(
            "grocerybot.daily_memory.DATA_DIR",
            Path("/nonexistent/path"),
        ):
            assert load_snapshot("easy") is None

    def test_stale_date_returns_none(self, tmp_path: Path) -> None:
        snap = DailySnapshot(
            date="2020-01-01",  # stale
            level="easy",
            grid_width=12,
            grid_height=10,
            walls=[],
            drop_off=[1, 8],
            item_type_to_positions={},
            orders=[],
        )
        today = datetime.now(tz=UTC).strftime("%Y-%m-%d")
        path = tmp_path / f"easy_{today}.json"
        path.write_text(snap.model_dump_json(), encoding="utf-8")

        with patch("grocerybot.daily_memory.DATA_DIR", tmp_path):
            result = load_snapshot("easy")
        assert result is None

    def test_valid_roundtrip(
        self, tmp_path: Path, sample_snapshot: DailySnapshot,
    ) -> None:
        today = datetime.now(tz=UTC).strftime("%Y-%m-%d")
        snap = sample_snapshot.model_copy(update={"date": today})

        with patch("grocerybot.daily_memory.DATA_DIR", tmp_path):
            save_snapshot(snap)
            loaded = load_snapshot("easy")

        assert loaded is not None
        assert loaded.level == "easy"
        assert loaded.grid_width == 12
        assert len(loaded.orders) == 1


class TestMergeOrders:
    def test_adds_new_orders(self, sample_snapshot: DailySnapshot) -> None:
        new = [OrderRecord(id="order_1", items_required=["eggs"])]
        merged = merge_orders(sample_snapshot, new)
        assert len(merged.orders) == 2
        assert merged.orders[1].id == "order_1"

    def test_deduplicates(self, sample_snapshot: DailySnapshot) -> None:
        dup = [OrderRecord(id="order_0", items_required=["milk"])]
        merged = merge_orders(sample_snapshot, dup)
        assert len(merged.orders) == 1

    def test_no_change_returns_same(
        self, sample_snapshot: DailySnapshot,
    ) -> None:
        merged = merge_orders(sample_snapshot, [])
        assert merged is sample_snapshot  # identity — no copy needed


class TestSaveSnapshot:
    def test_creates_dir(self, tmp_path: Path) -> None:
        data_dir = tmp_path / "data"
        snap = DailySnapshot(
            date="2026-03-01",
            level="easy",
            grid_width=12,
            grid_height=10,
            walls=[],
            drop_off=[1, 8],
            item_type_to_positions={},
            orders=[],
        )
        with patch("grocerybot.daily_memory.DATA_DIR", data_dir):
            save_snapshot(snap)
        assert (data_dir / "easy_2026-03-01.json").exists()

    def test_json_valid(
        self, tmp_path: Path, sample_snapshot: DailySnapshot,
    ) -> None:
        with patch("grocerybot.daily_memory.DATA_DIR", tmp_path):
            save_snapshot(sample_snapshot)
        path = tmp_path / "easy_2026-03-01.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        assert data["level"] == "easy"
        assert len(data["orders"]) == 1
