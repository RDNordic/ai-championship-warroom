"""Tests for planner.py (M3 multi-bot coordination primitives)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from grocerybot.grid import PassableGrid
from grocerybot.models import (
    Bot,
    GameState,
    MoveAction,
    Order,
    WaitAction,
)
from grocerybot.planner import (
    CollisionResolver,
    LocalTripPlanner,
    OrderSnapshot,
    OrderTracker,
    TaskAssigner,
)


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


def _state_with_bots(
    state: GameState,
    bots: list[Bot],
) -> GameState:
    return state.model_copy(update={"bots": bots})


class TestOrderTracker:
    def test_snapshot_accounts_for_delivered_and_inventory(
        self, medium_state: GameState,
    ) -> None:
        tracker = OrderTracker()
        snap = tracker.snapshot(medium_state)
        assert snap is not None
        assert snap.active_needed == ["bread", "eggs", "cheese"]
        assert sorted(snap.preview_needed) == ["butter", "pasta", "rice"]

    def test_preview_consumes_only_leftover_inventory(
        self, medium_state: GameState,
    ) -> None:
        tracker = OrderTracker()
        custom = medium_state.model_copy(
            update={
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
                        items_required=["milk"],
                        items_delivered=[],
                        complete=False,
                        status="preview",
                    ),
                ],
                "bots": [
                    Bot(id=0, position=(3, 7), inventory=["milk"]),
                    Bot(id=1, position=(7, 3), inventory=[]),
                    Bot(id=2, position=(11, 9), inventory=[]),
                ],
            },
        )
        snap = tracker.snapshot(custom)
        assert snap is not None
        assert snap.active_needed == ["milk"]
        assert snap.preview_needed == ["milk"]


class TestTaskAssigner:
    def test_assigns_one_task_per_bot(
        self, medium_state: GameState,
    ) -> None:
        tracker = OrderTracker()
        snap = tracker.snapshot(medium_state)
        assert snap is not None
        planner = LocalTripPlanner(medium_state, PassableGrid(medium_state))
        assigner = TaskAssigner()

        tasks = assigner.assign(medium_state, snap, planner)
        assert sorted(tasks.keys()) == [0, 1, 2]

    def test_full_inventory_bot_gets_dropoff(
        self, medium_state: GameState,
    ) -> None:
        tracker = OrderTracker()
        planner = LocalTripPlanner(medium_state, PassableGrid(medium_state))
        assigner = TaskAssigner()

        custom = _state_with_bots(
            medium_state,
            [
                Bot(id=0, position=(3, 7), inventory=["milk", "bread", "eggs"]),
                Bot(id=1, position=(7, 3), inventory=[]),
                Bot(id=2, position=(11, 9), inventory=[]),
            ],
        )
        snap = tracker.snapshot(custom)
        assert snap is not None
        tasks = assigner.assign(custom, snap, planner)
        assert tasks[0].kind == "drop_off"

    def test_full_inventory_without_active_match_goes_to_dropoff(
        self, medium_state: GameState,
    ) -> None:
        tracker = OrderTracker()
        planner = LocalTripPlanner(medium_state, PassableGrid(medium_state))
        assigner = TaskAssigner()

        custom = medium_state.model_copy(
            update={
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
                        items_required=["butter"],
                        items_delivered=[],
                        complete=False,
                        status="preview",
                    ),
                ],
                "bots": [
                    Bot(id=0, position=(3, 7), inventory=["bread", "eggs", "cheese"]),
                    Bot(id=1, position=(7, 3), inventory=[]),
                    Bot(id=2, position=(11, 9), inventory=[]),
                ],
            },
        )
        snap = tracker.snapshot(custom)
        assert snap is not None
        tasks = assigner.assign(custom, snap, planner)
        assert tasks[0].kind == "drop_off"

    def test_no_over_assignment_of_active_multiplicity(
        self, medium_state: GameState,
    ) -> None:
        tracker = OrderTracker()
        planner = LocalTripPlanner(medium_state, PassableGrid(medium_state))
        assigner = TaskAssigner()

        custom = medium_state.model_copy(
            update={
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
                "bots": [
                    Bot(id=0, position=(5, 5), inventory=[]),
                    Bot(id=1, position=(5, 6), inventory=[]),
                    Bot(id=2, position=(6, 5), inventory=[]),
                ],
            },
        )
        snap = tracker.snapshot(custom)
        assert snap is not None
        tasks = assigner.assign(custom, snap, planner)
        assigned_active = sum(task.pickups.count("cheese") for task in tasks.values())
        assert assigned_active <= 1

    def test_preview_not_assigned_to_first_bot_when_active_unmet(
        self, medium_state: GameState,
    ) -> None:
        tracker = OrderTracker()
        snap = tracker.snapshot(medium_state)
        assert snap is not None
        planner = LocalTripPlanner(medium_state, PassableGrid(medium_state))
        assigner = TaskAssigner()

        tasks = assigner.assign(medium_state, snap, planner)
        first = tasks[0]
        if first.kind == "pick":
            assert "cheese" in first.pickups

    def test_carried_active_items_get_dropoff_regardless_of_id(
        self, medium_state: GameState,
    ) -> None:
        """Bot 2 carrying active items should get drop_off.

        This should hold even if Bot 0/1 are processed first.
        """
        tracker = OrderTracker()
        planner = LocalTripPlanner(medium_state, PassableGrid(medium_state))
        assigner = TaskAssigner()

        custom = medium_state.model_copy(
            update={
                "orders": [
                    Order(
                        id="a0",
                        items_required=["cream", "cream", "milk"],
                        items_delivered=["milk"],
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
                "bots": [
                    Bot(id=0, position=(5, 5), inventory=[]),
                    Bot(id=1, position=(5, 6), inventory=[]),
                    Bot(id=2, position=(3, 9), inventory=["cream", "cream", "cream"]),
                ],
            },
        )
        snap = tracker.snapshot(custom)
        assert snap is not None
        assert snap.active_needed == ["cream", "cream"]
        tasks = assigner.assign(custom, snap, planner)
        # Bot 2 has matching items → must be assigned drop_off
        assert tasks[2].kind == "drop_off"
        # Empty bots should not steal active items via pickup of active needs
        assert tasks[0].kind != "drop_off"
        assert tasks[1].kind != "drop_off"


class TestCollisionResolver:
    def test_same_non_dropoff_target_lower_id_wins(
        self, medium_state: GameState,
    ) -> None:
        resolver = CollisionResolver()
        custom = _state_with_bots(
            medium_state,
            [
                Bot(id=0, position=(5, 5), inventory=[]),
                Bot(id=1, position=(5, 7), inventory=[]),
                Bot(id=2, position=(11, 9), inventory=[]),
            ],
        )
        proposed = {
            0: MoveAction(bot=0, action="move_down"),
            1: MoveAction(bot=1, action="move_up"),
            2: WaitAction(bot=2),
        }
        actions = resolver.resolve(custom, proposed)
        assert isinstance(actions[0], MoveAction)
        assert isinstance(actions[1], WaitAction)

    def test_move_into_lower_id_stationary_cell_is_blocked(
        self, medium_state: GameState,
    ) -> None:
        resolver = CollisionResolver()
        custom = _state_with_bots(
            medium_state,
            [
                Bot(id=0, position=(5, 5), inventory=[]),
                Bot(id=1, position=(5, 6), inventory=[]),
                Bot(id=2, position=(11, 9), inventory=[]),
            ],
        )
        proposed = {
            0: WaitAction(bot=0),
            1: MoveAction(bot=1, action="move_up"),
            2: WaitAction(bot=2),
        }
        actions = resolver.resolve(custom, proposed)
        assert isinstance(actions[0], WaitAction)
        assert isinstance(actions[1], WaitAction)

    def test_lower_id_cannot_move_into_higher_id_current_cell(
        self, medium_state: GameState,
    ) -> None:
        resolver = CollisionResolver()
        custom = _state_with_bots(
            medium_state,
            [
                Bot(id=0, position=(13, 9), inventory=[]),
                Bot(id=1, position=(12, 9), inventory=[]),
                Bot(id=2, position=(11, 9), inventory=[]),
            ],
        )
        proposed = {
            0: MoveAction(bot=0, action="move_left"),
            1: WaitAction(bot=1),
            2: WaitAction(bot=2),
        }
        actions = resolver.resolve(custom, proposed)
        assert isinstance(actions[0], WaitAction)
        assert isinstance(actions[1], WaitAction)
        assert isinstance(actions[2], WaitAction)

    def test_multiple_bots_targeting_dropoff_lower_id_wins(
        self, medium_state: GameState,
    ) -> None:
        resolver = CollisionResolver()
        custom = medium_state.model_copy(
            update={
                "drop_off": (5, 5),
                "bots": [
                    Bot(id=0, position=(5, 6), inventory=[]),
                    Bot(id=1, position=(5, 4), inventory=[]),
                    Bot(id=2, position=(11, 9), inventory=[]),
                ],
            },
        )
        proposed = {
            0: MoveAction(bot=0, action="move_up"),
            1: MoveAction(bot=1, action="move_down"),
            2: WaitAction(bot=2),
        }
        actions = resolver.resolve(custom, proposed)
        assert isinstance(actions[0], MoveAction)
        assert isinstance(actions[1], WaitAction)

    def test_higher_id_can_follow_into_vacated_lower_id_cell(
        self, medium_state: GameState,
    ) -> None:
        resolver = CollisionResolver()
        custom = _state_with_bots(
            medium_state.model_copy(update={"round": 10}),
            [
                Bot(id=0, position=(5, 5), inventory=[]),
                Bot(id=1, position=(5, 6), inventory=[]),
                Bot(id=2, position=(11, 9), inventory=[]),
            ],
        )
        proposed = {
            0: MoveAction(bot=0, action="move_up"),
            1: MoveAction(bot=1, action="move_up"),
            2: WaitAction(bot=2),
        }
        actions = resolver.resolve(custom, proposed)
        assert isinstance(actions[0], MoveAction)
        assert isinstance(actions[1], MoveAction)

    def test_spawn_not_exempt_after_round_zero(
        self, medium_state: GameState,
    ) -> None:
        resolver = CollisionResolver()
        spawn = (medium_state.grid.width - 2, medium_state.grid.height - 2)
        custom = medium_state.model_copy(
            update={
                "round": 5,
                "bots": [
                    Bot(id=0, position=(spawn[0] - 1, spawn[1]), inventory=[]),
                    Bot(id=1, position=spawn, inventory=[]),
                    Bot(id=2, position=(11, 9), inventory=[]),
                ],
            },
        )
        proposed = {
            0: MoveAction(bot=0, action="move_right"),
            1: WaitAction(bot=1),
            2: WaitAction(bot=2),
        }
        actions = resolver.resolve(custom, proposed)
        assert isinstance(actions[0], WaitAction)

    def test_conflict_tie_break_rotates_by_round(
        self, medium_state: GameState,
    ) -> None:
        resolver = CollisionResolver()
        base = medium_state.model_copy(
            update={
                "bots": [
                    Bot(id=0, position=(5, 5), inventory=[]),
                    Bot(id=1, position=(7, 5), inventory=[]),
                    Bot(id=2, position=(11, 9), inventory=[]),
                ],
            },
        )
        proposed = {
            0: MoveAction(bot=0, action="move_right"),
            1: MoveAction(bot=1, action="move_left"),
            2: WaitAction(bot=2),
        }

        round0 = base.model_copy(update={"round": 0})
        actions0 = resolver.resolve(round0, proposed)
        assert isinstance(actions0[0], MoveAction)
        assert isinstance(actions0[1], WaitAction)

        round1 = base.model_copy(update={"round": 1})
        actions1 = resolver.resolve(round1, proposed)
        assert isinstance(actions1[0], WaitAction)
        assert isinstance(actions1[1], MoveAction)


def test_snapshot_type(medium_state: GameState) -> None:
    tracker = OrderTracker()
    snap = tracker.snapshot(medium_state)
    assert snap is not None
    assert isinstance(snap, OrderSnapshot)
