from __future__ import annotations

from typing import Any


EMPTY_PRIOR = [0.92, 0.02, 0.02, 0.02, 0.02, 0.02]
# Round-2 analysis showed that plains and settlement-adjacent cells were too settlement-heavy.
PLAINS_REMOTE_PRIOR = [0.8155, 0.0485, 0.0194, 0.0291, 0.0680, 0.0194]
PLAINS_NEAR_SETTLEMENT_PRIOR = [0.67, 0.16, 0.03, 0.05, 0.07, 0.02]
SETTLEMENT_PRIOR = [0.1538, 0.5128, 0.1282, 0.1282, 0.0513, 0.0256]
PORT_PRIOR = [0.1538, 0.1282, 0.5128, 0.1282, 0.0513, 0.0256]
RUIN_PRIOR = [0.05, 0.10, 0.05, 0.75, 0.03, 0.02]
FOREST_PRIOR = [0.05, 0.05, 0.02, 0.05, 0.80, 0.03]
MOUNTAIN_PRIOR = [0.02, 0.02, 0.02, 0.02, 0.02, 0.90]

DYNAMIC_CODES = {1, 2, 3}


def normalize_cell(probs: list[float]) -> list[float]:
    floored = [max(p, 0.01) for p in probs]
    total = sum(floored)
    return [p / total for p in floored]


def map_code_to_class_index(code: int) -> int:
    if code in (0, 10, 11):
        return 0
    if code == 1:
        return 1
    if code == 2:
        return 2
    if code == 3:
        return 3
    if code == 4:
        return 4
    if code == 5:
        return 5
    raise ValueError(f"Unsupported terrain code: {code}")


def mark_settlement_cells(initial_state: dict[str, Any]) -> dict[tuple[int, int], list[float]]:
    overrides: dict[tuple[int, int], list[float]] = {}
    for settlement in initial_state.get("settlements", []):
        x = settlement["x"]
        y = settlement["y"]
        overrides[(x, y)] = PORT_PRIOR if settlement.get("has_port") else SETTLEMENT_PRIOR
    return overrides


def settlement_neighbor_cells(
    width: int, height: int, settlement_cells: set[tuple[int, int]]
) -> set[tuple[int, int]]:
    neighbors: set[tuple[int, int]] = set()
    for x, y in settlement_cells:
        for dy in (-1, 0, 1):
            for dx in (-1, 0, 1):
                nx = x + dx
                ny = y + dy
                if 0 <= nx < width and 0 <= ny < height:
                    neighbors.add((nx, ny))
    return neighbors


def base_prior_for_code(code: int) -> list[float]:
    if code == 5:
        return MOUNTAIN_PRIOR[:]
    if code in (10, 0):
        return EMPTY_PRIOR[:]
    if code == 4:
        return FOREST_PRIOR[:]
    if code == 3:
        return RUIN_PRIOR[:]
    if code == 2:
        return PORT_PRIOR[:]
    if code == 1:
        return SETTLEMENT_PRIOR[:]
    return PLAINS_REMOTE_PRIOR[:]


def build_prior_prediction(initial_state: dict[str, Any]) -> list[list[list[float]]]:
    grid = initial_state["grid"]
    height = len(grid)
    width = len(grid[0]) if height else 0

    overrides = mark_settlement_cells(initial_state)
    settlement_cells = set(overrides.keys())
    near_settlements = settlement_neighbor_cells(width, height, settlement_cells)

    prediction: list[list[list[float]]] = []
    for y, row in enumerate(grid):
        pred_row: list[list[float]] = []
        for x, code in enumerate(row):
            probs = overrides.get((x, y))
            if probs is None:
                if code == 11 and (x, y) in near_settlements:
                    probs = PLAINS_NEAR_SETTLEMENT_PRIOR[:]
                else:
                    probs = base_prior_for_code(code)
            pred_row.append(normalize_cell(probs))
        prediction.append(pred_row)

    return prediction


def validate_prediction(prediction: list[list[list[float]]], height: int, width: int) -> None:
    if len(prediction) != height:
        raise SystemExit(f"Expected {height} rows, got {len(prediction)}")

    for y, row in enumerate(prediction):
        if len(row) != width:
            raise SystemExit(f"Row {y}: expected {width} cols, got {len(row)}")
        for x, cell in enumerate(row):
            if len(cell) != 6:
                raise SystemExit(f"Cell ({y},{x}): expected 6 probs, got {len(cell)}")
            if any(p < 0 for p in cell):
                raise SystemExit(f"Cell ({y},{x}): negative probability")
            total = sum(cell)
            if abs(total - 1.0) > 0.01:
                raise SystemExit(f"Cell ({y},{x}): probs sum to {total}, expected 1.0")
