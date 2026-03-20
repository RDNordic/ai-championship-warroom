"""Cell feature extraction for Bayesian bucket assignment."""
from __future__ import annotations

from typing import Any

from .config import NEAR_SETTLEMENT_DIST


def _settlement_positions(initial_state: dict[str, Any]) -> list[tuple[int, int]]:
    """Extract (x, y) positions of all initial settlements."""
    return [(s["x"], s["y"]) for s in initial_state.get("settlements", [])]


def _distance_to_nearest(x: int, y: int, positions: list[tuple[int, int]]) -> float:
    """Chebyshev distance to the nearest position in the list."""
    if not positions:
        return float("inf")
    return min(max(abs(x - sx), abs(y - sy)) for sx, sy in positions)


def _code_to_bucket(code: int, dist_to_settlement: float) -> str:
    """Map initial terrain code + distance to feature bucket name."""
    if code == 5:
        return "mountain"
    if code == 4:
        return "forest"
    if code == 1:
        return "settlement"
    if code == 2:
        return "port"
    if code == 3:
        return "ruin"
    # Codes 0, 10, 11 are all plains/empty variants
    if dist_to_settlement <= NEAR_SETTLEMENT_DIST:
        return "plains_near"
    return "plains_remote"


def build_feature_map(initial_state: dict[str, Any]) -> list[list[str]]:
    """Build a height x width grid of feature bucket names from the initial state."""
    grid = initial_state["grid"]
    height = len(grid)
    width = len(grid[0]) if height else 0
    settlements = _settlement_positions(initial_state)

    feature_map: list[list[str]] = []
    for y in range(height):
        row: list[str] = []
        for x in range(width):
            dist = _distance_to_nearest(x, y, settlements)
            row.append(_code_to_bucket(grid[y][x], dist))
        feature_map.append(row)
    return feature_map
