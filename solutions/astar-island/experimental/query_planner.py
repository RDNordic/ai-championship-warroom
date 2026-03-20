"""Adaptive 3-phase query strategy."""
from __future__ import annotations

from typing import Any

from .config import COVERAGE_VIEWPORTS, REFINEMENT_BUDGET, SENTINEL_BUDGET
from .pooling import map_code_to_class


def _settlement_centroid(initial_state: dict[str, Any]) -> tuple[int, int]:
    """Find centroid of initial settlements, or map centre as fallback."""
    settlements = initial_state.get("settlements", [])
    if not settlements:
        return (20, 20)
    cx = sum(s["x"] for s in settlements) / len(settlements)
    cy = sum(s["y"] for s in settlements) / len(settlements)
    return (int(cx), int(cy))


def _viewport_around(cx: int, cy: int, map_w: int = 40, map_h: int = 40) -> dict[str, int]:
    """Create a 15x15 viewport centred on (cx, cy), clamped to map bounds."""
    x = max(0, min(cx - 7, map_w - 15))
    y = max(0, min(cy - 7, map_h - 15))
    return {"x": x, "y": y, "w": 15, "h": 15}


def _viewport_key(seed: int, vp: dict[str, int]) -> str:
    return f"{seed}_{vp['x']}_{vp['y']}_{vp['w']}_{vp['h']}"


def select_sentinel_queries(
    initial_states: list[dict[str, Any]],
    max_queries: int | None = None,
) -> list[dict[str, Any]]:
    """Phase 1: One sentinel per seed, centred on settlement cluster."""
    if max_queries is None:
        max_queries = SENTINEL_BUDGET

    queries: list[dict[str, Any]] = []
    for seed_index, state in enumerate(initial_states):
        if len(queries) >= max_queries:
            break
        cx, cy = _settlement_centroid(state)
        queries.append({"seed_index": seed_index, "viewport": _viewport_around(cx, cy)})
    return queries


def select_coverage_queries(
    initial_states: list[dict[str, Any]],
    existing_observations: list[dict[str, Any]],
    budget_remaining: int,
) -> list[dict[str, Any]]:
    """Phase 2: Standard tile coverage, skipping already-observed viewports."""
    covered: set[str] = set()
    for obs in existing_observations:
        covered.add(_viewport_key(obs["seed_index"], obs["viewport"]))

    queries: list[dict[str, Any]] = []
    for seed_index in range(len(initial_states)):
        for viewport in COVERAGE_VIEWPORTS:
            if len(queries) >= budget_remaining:
                return queries
            if _viewport_key(seed_index, viewport) not in covered:
                queries.append({"seed_index": seed_index, "viewport": dict(viewport)})
    return queries


def select_refinement_queries(
    observations: list[dict[str, Any]],
    budget_remaining: int,
) -> list[dict[str, Any]]:
    """Phase 3: Repeat the highest-dynamic-density viewports."""
    if budget_remaining <= 0:
        return []

    def dynamic_score(obs: dict[str, Any]) -> int:
        return sum(
            1 for row in obs["grid"] for code in row
            if map_code_to_class(code) in (1, 2, 3)
        )

    ranked = sorted(observations, key=dynamic_score, reverse=True)

    seen: set[str] = set()
    queries: list[dict[str, Any]] = []
    for obs in ranked:
        if len(queries) >= budget_remaining:
            break
        key = _viewport_key(obs["seed_index"], obs["viewport"])
        if key not in seen:
            seen.add(key)
            queries.append({"seed_index": obs["seed_index"], "viewport": dict(obs["viewport"])})
    return queries
