"""Submission formatting and validation."""
from __future__ import annotations

from .config import NUM_CLASSES
from .dirichlet import normalize_with_floor


def format_prediction(prediction: list[list[list[float]]]) -> list[list[list[float]]]:
    """Ensure prediction is properly normalized with floor."""
    return [
        [normalize_with_floor(cell) for cell in row]
        for row in prediction
    ]


def validate_prediction(prediction: list[list[list[float]]], height: int, width: int) -> None:
    """Validate prediction tensor shape and constraints."""
    if len(prediction) != height:
        raise ValueError(f"Expected {height} rows, got {len(prediction)}")
    for y, row in enumerate(prediction):
        if len(row) != width:
            raise ValueError(f"Row {y}: expected {width} cols, got {len(row)}")
        for x, cell in enumerate(row):
            if len(cell) != NUM_CLASSES:
                raise ValueError(f"Cell ({y},{x}): expected {NUM_CLASSES} probs, got {len(cell)}")
            if any(p < 0 for p in cell):
                raise ValueError(f"Cell ({y},{x}): negative probability")
            total = sum(cell)
            if abs(total - 1.0) > 0.02:
                raise ValueError(f"Cell ({y},{x}): probs sum to {total}")
