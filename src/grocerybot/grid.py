"""Spatial data structures: passable grid, BFS, A*, distance maps.

Built once from round-0 GameState. Grid never changes within a game.
"""

from __future__ import annotations

import heapq
from collections import deque
from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:
    from grocerybot.models import GameState

Position = tuple[int, int]

DIRECTIONS: list[tuple[int, int]] = [(0, -1), (0, 1), (-1, 0), (1, 0)]


class PassableGrid:
    """Immutable grid recording which cells are walkable.

    Built once from round-0 GameState. Shelf cells (item positions) are
    permanently impassable even after items are picked up.
    """

    __slots__ = ("width", "height", "walls", "shelves", "drop_off", "_passable")

    def __init__(self, state: GameState) -> None:
        self.width = state.grid.width
        self.height = state.grid.height
        self.walls: frozenset[Position] = frozenset(state.grid.walls)
        self.shelves: frozenset[Position] = frozenset(
            item.position for item in state.items
        )
        self.drop_off: Position = state.drop_off

        blocked = self.walls | self.shelves
        self._passable: list[list[bool]] = [
            [
                (x, y) not in blocked
                for y in range(self.height)
            ]
            for x in range(self.width)
        ]

    def is_passable(self, pos: Position) -> bool:
        """Check if a cell is walkable (within bounds and not blocked)."""
        x, y = pos
        if 0 <= x < self.width and 0 <= y < self.height:
            return self._passable[x][y]
        return False

    def neighbors(self, pos: Position) -> list[Position]:
        """Return walkable neighbors of pos (4-connected)."""
        x, y = pos
        result: list[Position] = []
        for dx, dy in DIRECTIONS:
            nx, ny = x + dx, y + dy
            if 0 <= nx < self.width and 0 <= ny < self.height and self._passable[nx][ny]:
                result.append((nx, ny))
        return result


def bfs(start: Position, goal: Position, grid: PassableGrid) -> list[Position]:
    """BFS shortest path from start to goal. Returns path (inclusive) or []."""
    if start == goal:
        return [start]
    if not grid.is_passable(start) or not grid.is_passable(goal):
        return []

    queue: deque[Position] = deque([start])
    came_from: dict[Position, Position] = {start: start}

    while queue:
        current = queue.popleft()
        for nb in grid.neighbors(current):
            if nb not in came_from:
                came_from[nb] = current
                if nb == goal:
                    # Reconstruct path
                    path: list[Position] = []
                    node = goal
                    while node != start:
                        path.append(node)
                        node = came_from[node]
                    path.append(start)
                    path.reverse()
                    return path
                queue.append(nb)
    return []


def _manhattan(a: Position, b: Position) -> int:
    return abs(a[0] - b[0]) + abs(a[1] - b[1])


def astar(
    start: Position,
    goal: Position,
    grid: PassableGrid,
    blocked: frozenset[Position] | None = None,
) -> list[Position]:
    """A* shortest path with Manhattan heuristic.

    Args:
        start: Start position.
        goal: Goal position.
        grid: The passable grid.
        blocked: Additional positions to treat as impassable (e.g. reservations).

    Returns:
        Path from start to goal (inclusive), or [] if unreachable.
    """
    if start == goal:
        return [start]
    if not grid.is_passable(goal):
        return []
    if blocked and start in blocked:
        return []

    g_score: dict[Position, int] = {start: 0}
    f_score = _manhattan(start, goal)
    counter = 0
    open_set: list[tuple[int, int, Position]] = [(f_score, counter, start)]
    came_from: dict[Position, Position] = {}
    closed: set[Position] = set()

    while open_set:
        _, _, current = heapq.heappop(open_set)
        if current == goal:
            path: list[Position] = []
            node = current
            while node in came_from:
                path.append(node)
                node = came_from[node]
            path.append(start)
            path.reverse()
            return path

        if current in closed:
            continue
        closed.add(current)

        current_g = g_score[current]
        for nb in grid.neighbors(current):
            if nb in closed:
                continue
            if blocked and nb in blocked:
                continue
            tentative_g = current_g + 1
            if nb not in g_score or tentative_g < g_score[nb]:
                g_score[nb] = tentative_g
                came_from[nb] = current
                f = tentative_g + _manhattan(nb, goal)
                counter += 1
                heapq.heappush(open_set, (f, counter, nb))

    return []


def bfs_distance_map(goal: Position, grid: PassableGrid) -> dict[Position, int]:
    """BFS from goal outward. Returns distance from every reachable cell to goal.

    Use as a perfect heuristic for A* or for nearest-item selection.
    """
    if not grid.is_passable(goal):
        return {}

    dist: dict[Position, int] = {goal: 0}
    queue: deque[Position] = deque([goal])

    while queue:
        current = queue.popleft()
        d = dist[current] + 1
        for nb in grid.neighbors(current):
            if nb not in dist:
                dist[nb] = d
                queue.append(nb)
    return dist


def adjacent_walkable(shelf_pos: Position, grid: PassableGrid) -> list[Position]:
    """Return walkable cells adjacent (Manhattan dist 1) to a shelf position.

    Used to find where a bot must stand to pick up an item from a shelf.
    """
    x, y = shelf_pos
    result: list[Position] = []
    for dx, dy in DIRECTIONS:
        nx, ny = x + dx, y + dy
        if grid.is_passable((nx, ny)):
            result.append((nx, ny))
    return result


MoveDirection = Literal["move_up", "move_down", "move_left", "move_right"]


def direction_for_move(from_pos: Position, to_pos: Position) -> MoveDirection:
    """Return the move action string for a single-step move."""
    dx = to_pos[0] - from_pos[0]
    dy = to_pos[1] - from_pos[1]
    if dx == 1:
        return "move_right"
    if dx == -1:
        return "move_left"
    if dy == 1:
        return "move_down"
    if dy == -1:
        return "move_up"
    msg = f"Not a single-step move: {from_pos} -> {to_pos}"
    raise ValueError(msg)
