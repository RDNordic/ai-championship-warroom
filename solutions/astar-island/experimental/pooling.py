"""Cross-seed evidence aggregation."""
from __future__ import annotations

from typing import Any

from .config import NUM_CLASSES

# Map raw terrain codes from /simulate response to class index 0-5
_CODE_TO_CLASS = {0: 0, 10: 0, 11: 0, 1: 1, 2: 2, 3: 3, 4: 4, 5: 5}


def map_code_to_class(code: int) -> int:
    """Map a terrain code from simulation to class index 0-5."""
    return _CODE_TO_CLASS.get(code, 0)


def pool_observations(
    observations: list[dict[str, Any]],
    feature_maps: list[list[list[str]]],
) -> dict[str, list[int]]:
    """
    Pool observed class counts by feature bucket across all seeds.

    Returns dict mapping bucket name -> count vector of length NUM_CLASSES.
    """
    counts: dict[str, list[int]] = {}

    for obs in observations:
        seed = obs["seed_index"]
        vp = obs["viewport"]
        grid = obs["grid"]
        fm = feature_maps[seed]

        for dy, row in enumerate(grid):
            for dx, code in enumerate(row):
                y = vp["y"] + dy
                x = vp["x"] + dx
                if 0 <= y < len(fm) and 0 <= x < len(fm[0]):
                    bucket = fm[y][x]
                    cls = map_code_to_class(code)
                    if bucket not in counts:
                        counts[bucket] = [0] * NUM_CLASSES
                    counts[bucket][cls] += 1

    return counts


def compute_dynamic_counts(observations: list[dict[str, Any]]) -> tuple[int, int]:
    """
    Count dynamic cells (classes 1,2,3) vs total observed cells across all observations.
    Returns (dynamic_count, total_count).
    """
    dynamic = 0
    total = 0
    for obs in observations:
        for row in obs["grid"]:
            for code in row:
                total += 1
                if map_code_to_class(code) in (1, 2, 3):
                    dynamic += 1
    return dynamic, total
