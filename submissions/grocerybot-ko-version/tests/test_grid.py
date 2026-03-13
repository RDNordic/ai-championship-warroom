"""Tests for grid.py — PassableGrid, BFS, A*, distance maps, adjacency."""

from __future__ import annotations

from typing import Any

import pytest

from grocerybot.grid import (
    PassableGrid,
    adjacent_walkable,
    astar,
    bfs,
    bfs_distance_map,
    direction_for_move,
)
from grocerybot.models import GameState

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def easy_state(easy_game_state_data: dict[str, Any]) -> GameState:
    return GameState.model_validate(easy_game_state_data)


@pytest.fixture()
def grid(easy_state: GameState) -> PassableGrid:
    return PassableGrid(easy_state)


# ---------------------------------------------------------------------------
# PassableGrid construction
# ---------------------------------------------------------------------------


class TestPassableGrid:
    def test_dimensions(self, grid: PassableGrid) -> None:
        assert grid.width == 12
        assert grid.height == 10

    def test_border_walls_impassable(self, grid: PassableGrid) -> None:
        # Top row is all walls
        for x in range(12):
            assert not grid.is_passable((x, 0))
        # Bottom row is all walls
        for x in range(12):
            assert not grid.is_passable((x, 9))
        # Left column
        for y in range(10):
            assert not grid.is_passable((0, y))
        # Right column
        for y in range(10):
            assert not grid.is_passable((11, y))

    def test_shelves_impassable(self, grid: PassableGrid, easy_state: GameState) -> None:
        # All item positions should be impassable (they are shelves)
        for item in easy_state.items:
            assert not grid.is_passable(item.position), (
                f"Shelf at {item.position} should be impassable"
            )

    def test_drop_off_passable(self, grid: PassableGrid) -> None:
        assert grid.is_passable(grid.drop_off)

    def test_bot_spawn_passable(self, grid: PassableGrid, easy_state: GameState) -> None:
        for bot in easy_state.bots:
            assert grid.is_passable(bot.position)

    def test_out_of_bounds(self, grid: PassableGrid) -> None:
        assert not grid.is_passable((-1, 0))
        assert not grid.is_passable((0, -1))
        assert not grid.is_passable((12, 5))
        assert not grid.is_passable((5, 10))

    def test_interior_floor_passable(self, grid: PassableGrid) -> None:
        # (1, 1) is interior — not a wall, not a shelf in the easy map
        # Check if it's in walls or shelves
        if (1, 1) not in grid.walls and (1, 1) not in grid.shelves:
            assert grid.is_passable((1, 1))

    def test_neighbors_returns_only_passable(self, grid: PassableGrid) -> None:
        nbs = grid.neighbors((5, 4))  # bot position in easy map
        for nb in nbs:
            assert grid.is_passable(nb)
        # Should have 2-4 neighbors
        assert 1 <= len(nbs) <= 4


# ---------------------------------------------------------------------------
# BFS
# ---------------------------------------------------------------------------


class TestBFS:
    def test_same_start_goal(self, grid: PassableGrid) -> None:
        path = bfs((5, 4), (5, 4), grid)
        assert path == [(5, 4)]

    def test_path_to_drop_off(self, grid: PassableGrid) -> None:
        path = bfs((5, 4), (9, 8), grid)
        assert len(path) > 0
        assert path[0] == (5, 4)
        assert path[-1] == (9, 8)

    def test_path_avoids_walls(self, grid: PassableGrid) -> None:
        path = bfs((5, 4), (9, 8), grid)
        for pos in path:
            assert grid.is_passable(pos), f"Path goes through impassable {pos}"

    def test_path_is_connected(self, grid: PassableGrid) -> None:
        path = bfs((5, 4), (9, 8), grid)
        for i in range(len(path) - 1):
            dx = abs(path[i][0] - path[i + 1][0])
            dy = abs(path[i][1] - path[i + 1][1])
            assert dx + dy == 1, f"Non-adjacent step: {path[i]} -> {path[i+1]}"

    def test_unreachable_returns_empty(self, grid: PassableGrid) -> None:
        # Wall cell as goal
        path = bfs((5, 4), (0, 0), grid)
        assert path == []

    def test_unreachable_start(self, grid: PassableGrid) -> None:
        path = bfs((0, 0), (5, 4), grid)
        assert path == []


# ---------------------------------------------------------------------------
# A*
# ---------------------------------------------------------------------------


class TestAStar:
    def test_same_start_goal(self, grid: PassableGrid) -> None:
        path = astar((5, 4), (5, 4), grid)
        assert path == [(5, 4)]

    def test_path_to_drop_off(self, grid: PassableGrid) -> None:
        path = astar((5, 4), (9, 8), grid)
        assert len(path) > 0
        assert path[0] == (5, 4)
        assert path[-1] == (9, 8)

    def test_path_optimal(self, grid: PassableGrid) -> None:
        """A* path should be same length as BFS (both optimal on unit-cost grid)."""
        path_astar = astar((5, 4), (9, 8), grid)
        path_bfs = bfs((5, 4), (9, 8), grid)
        assert len(path_astar) == len(path_bfs)

    def test_avoids_blocked_cells(self, grid: PassableGrid) -> None:
        # Block an intermediate cell
        path_normal = astar((5, 4), (9, 8), grid)
        assert len(path_normal) > 2

        # Block a cell on the normal path
        block_pos = path_normal[1]
        path_blocked = astar((5, 4), (9, 8), grid, blocked=frozenset({block_pos}))
        # Should still find a path (just longer or different)
        if path_blocked:
            assert block_pos not in path_blocked

    def test_path_avoids_shelves(
        self, grid: PassableGrid, easy_state: GameState
    ) -> None:
        path = astar((5, 4), (9, 8), grid)
        shelf_positions = {item.position for item in easy_state.items}
        for pos in path:
            assert pos not in shelf_positions, f"Path goes through shelf at {pos}"

    def test_unreachable(self, grid: PassableGrid) -> None:
        path = astar((5, 4), (0, 0), grid)
        assert path == []


# ---------------------------------------------------------------------------
# Distance map
# ---------------------------------------------------------------------------


class TestDistanceMap:
    def test_goal_has_zero_distance(self, grid: PassableGrid) -> None:
        dist = bfs_distance_map((9, 8), grid)
        assert dist[(9, 8)] == 0

    def test_adjacent_has_distance_one(self, grid: PassableGrid) -> None:
        dist = bfs_distance_map((9, 8), grid)
        nbs = grid.neighbors((9, 8))
        for nb in nbs:
            assert dist[nb] == 1

    def test_matches_bfs_path_length(self, grid: PassableGrid) -> None:
        dist = bfs_distance_map((9, 8), grid)
        path = bfs((5, 4), (9, 8), grid)
        assert len(path) > 0
        # Distance = number of steps = len(path) - 1
        assert dist[(5, 4)] == len(path) - 1

    def test_walls_not_in_map(self, grid: PassableGrid) -> None:
        dist = bfs_distance_map((9, 8), grid)
        assert (0, 0) not in dist  # wall


# ---------------------------------------------------------------------------
# Adjacent walkable
# ---------------------------------------------------------------------------


class TestAdjacentWalkable:
    def test_shelf_has_adjacent_walkable(
        self, grid: PassableGrid, easy_state: GameState
    ) -> None:
        # Every shelf should have at least one adjacent walkable cell
        for item in easy_state.items:
            adj = adjacent_walkable(item.position, grid)
            assert len(adj) >= 1, (
                f"Shelf at {item.position} has no adjacent walkable cells"
            )

    def test_adjacent_cells_are_passable(
        self, grid: PassableGrid, easy_state: GameState
    ) -> None:
        for item in easy_state.items:
            for a in adjacent_walkable(item.position, grid):
                assert grid.is_passable(a)

    def test_adjacent_cells_are_distance_one(
        self, grid: PassableGrid, easy_state: GameState
    ) -> None:
        for item in easy_state.items:
            for a in adjacent_walkable(item.position, grid):
                dx = abs(a[0] - item.position[0])
                dy = abs(a[1] - item.position[1])
                assert dx + dy == 1


# ---------------------------------------------------------------------------
# direction_for_move
# ---------------------------------------------------------------------------


class TestDirectionForMove:
    def test_move_right(self) -> None:
        assert direction_for_move((1, 1), (2, 1)) == "move_right"

    def test_move_left(self) -> None:
        assert direction_for_move((2, 1), (1, 1)) == "move_left"

    def test_move_down(self) -> None:
        assert direction_for_move((1, 1), (1, 2)) == "move_down"

    def test_move_up(self) -> None:
        assert direction_for_move((1, 1), (1, 0)) == "move_up"

    def test_invalid_raises(self) -> None:
        with pytest.raises(ValueError, match="Not a single-step move"):
            direction_for_move((1, 1), (3, 3))

    def test_same_position_raises(self) -> None:
        with pytest.raises(ValueError, match="Not a single-step move"):
            direction_for_move((1, 1), (1, 1))
