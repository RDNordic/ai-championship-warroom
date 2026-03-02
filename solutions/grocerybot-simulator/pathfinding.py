"""BFS shortest-path utilities for the grocery grid."""

from __future__ import annotations
from collections import deque
from parser import GameConfig

DIRECTIONS = [(0, -1), (0, 1), (-1, 0), (1, 0)]
DIR_NAMES = {(0, -1): "move_up", (0, 1): "move_down",
             (-1, 0): "move_left", (1, 0): "move_right"}


def bfs_distance_map(config: GameConfig, start: tuple[int, int]) -> dict[tuple[int, int], int]:
    """BFS from start, return {cell: distance} for all reachable cells."""
    dist = {start: 0}
    queue = deque([start])
    while queue:
        x, y = queue.popleft()
        d = dist[(x, y)]
        for dx, dy in DIRECTIONS:
            nx, ny = x + dx, y + dy
            if (nx, ny) not in dist:
                if 0 <= nx < config.width and 0 <= ny < config.height:
                    if (nx, ny) not in config.walls:
                        dist[(nx, ny)] = d + 1
                        queue.append((nx, ny))
    return dist


def bfs_path(config: GameConfig, start: tuple[int, int],
             goal: tuple[int, int]) -> list[str] | None:
    """Return shortest action sequence from start to goal, or None if unreachable."""
    if start == goal:
        return []
    parent = {start: None}
    queue = deque([start])
    while queue:
        x, y = queue.popleft()
        for dx, dy in DIRECTIONS:
            nx, ny = x + dx, y + dy
            if (nx, ny) not in parent:
                if 0 <= nx < config.width and 0 <= ny < config.height:
                    if (nx, ny) not in config.walls:
                        parent[(nx, ny)] = ((x, y), (dx, dy))
                        if (nx, ny) == goal:
                            # Reconstruct
                            actions = []
                            cur = goal
                            while parent[cur] is not None:
                                prev_pos, direction = parent[cur]
                                actions.append(DIR_NAMES[direction])
                                cur = prev_pos
                            actions.reverse()
                            return actions
                        queue.append((nx, ny))
    return None


def bfs_to_adjacent(config: GameConfig, start: tuple[int, int],
                    target: tuple[int, int]) -> list[str] | None:
    """Return shortest action sequence to reach a cell adjacent to target.

    Items require adjacency (Manhattan dist 1) for pickup.
    Returns the path to the best adjacent cell.
    """
    tx, ty = target
    # Find all walkable cells adjacent to target
    adjacent_cells = []
    for dx, dy in DIRECTIONS:
        ax, ay = tx + dx, ty + dy
        if 0 <= ax < config.width and 0 <= ay < config.height:
            if (ax, ay) not in config.walls:
                adjacent_cells.append((ax, ay))

    if not adjacent_cells:
        return None

    # Check if already adjacent
    if start in adjacent_cells:
        return []

    # BFS from start, stop at first adjacent cell hit
    best_path = None
    for cell in adjacent_cells:
        path = bfs_path(config, start, cell)
        if path is not None:
            if best_path is None or len(path) < len(best_path):
                best_path = path

    return best_path


def precompute_distances(config: GameConfig) -> dict:
    """Precompute BFS distances between all key locations.

    Returns a dict with:
      - item_distances[item_id] = {cell: distance_to_adjacent}
      - drop_off_distances = {cell: distance_to_drop_off}
    """
    # Distance from every cell to drop-off
    drop_off_dist = bfs_distance_map(config, config.drop_off)

    # For each item, compute distance from every cell to nearest adjacent cell
    item_adj_distances = {}
    for item in config.items:
        ipos = item["position"]
        ix, iy = ipos
        # Find walkable adjacent cells
        adj_cells = []
        for dx, dy in DIRECTIONS:
            ax, ay = ix + dx, iy + dy
            if 0 <= ax < config.width and 0 <= ay < config.height:
                if (ax, ay) not in config.walls:
                    adj_cells.append((ax, ay))

        # BFS from each adjacent cell, take min distance per cell
        min_dist = {}
        for ac in adj_cells:
            dmap = bfs_distance_map(config, ac)
            for cell, d in dmap.items():
                if cell not in min_dist or d < min_dist[cell]:
                    min_dist[cell] = d

        item_adj_distances[item["id"]] = min_dist

    return {
        "drop_off_distances": drop_off_dist,
        "item_adj_distances": item_adj_distances,
    }
