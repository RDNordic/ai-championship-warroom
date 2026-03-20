"""End-to-end live runner for the experimental Bayesian approach."""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

import astar_api
from astar_api import ROOT, api_get, api_post, dump_json, get_active_round

from .config import REFINEMENT_BUDGET, SENTINEL_BUDGET, TOTAL_BUDGET
from .predictor import predict_all_seeds
from .query_planner import (
    select_coverage_queries,
    select_refinement_queries,
    select_sentinel_queries,
)
from .regime import regime_posterior
from .submission import format_prediction, validate_prediction


def _artifact_dir(round_id: str) -> Path:
    return ROOT / "artifacts" / f"round_{round_id}"


def _simulate(round_id: str, seed_index: int, viewport: dict[str, int], label: str = "") -> dict[str, Any]:
    """Call /simulate and save the result."""
    payload = {
        "round_id": round_id,
        "seed_index": seed_index,
        "viewport_x": viewport["x"],
        "viewport_y": viewport["y"],
        "viewport_w": viewport["w"],
        "viewport_h": viewport["h"],
    }
    result = api_post("/simulate", payload, auth=True)

    suffix = f"_{label}" if label else ""
    name = (
        f"seed_{seed_index}_x{viewport['x']}_y{viewport['y']}"
        f"_w{viewport['w']}_h{viewport['h']}{suffix}.json"
    )
    path = _artifact_dir(round_id) / "simulate_bayesian" / name
    dump_json(path, result)

    time.sleep(0.25)
    return result


def _obs_from_result(
    seed_index: int, viewport: dict[str, int], result: dict[str, Any], repeat_index: int = 0
) -> dict[str, Any]:
    return {
        "seed_index": seed_index,
        "viewport": viewport,
        "grid": result["grid"],
        "settlements": result.get("settlements", []),
        "repeat_index": repeat_index,
    }


def main() -> None:
    rounds = api_get("/rounds", auth=False)
    active_round = get_active_round(rounds)
    if not active_round:
        raise SystemExit("No active round found.")

    round_id = active_round["id"]
    detail = api_get(f"/rounds/{round_id}", auth=False)
    budget = api_get("/budget", auth=True)

    if not budget.get("active"):
        raise SystemExit("No active budget.")

    queries_used = budget.get("queries_used", 0)
    queries_max = budget.get("queries_max", TOTAL_BUDGET)
    budget_remaining = queries_max - queries_used

    if budget_remaining <= 0:
        raise SystemExit(f"No queries remaining ({queries_used}/{queries_max}).")

    initial_states = detail["initial_states"]
    seeds_count = detail["seeds_count"]
    height = detail["map_height"]
    width = detail["map_width"]

    print(f"Round {detail.get('round_number', '?')}: {round_id}")
    print(f"Budget: {queries_used}/{queries_max} used, {budget_remaining} remaining")
    print(f"Seeds: {seeds_count}, Map: {width}x{height}")

    all_observations: list[dict[str, Any]] = []

    # Phase 1: Sentinel queries
    sentinel_budget = min(SENTINEL_BUDGET, budget_remaining)
    sentinel_queries = select_sentinel_queries(initial_states, max_queries=sentinel_budget)
    print(f"\nPhase 1: {len(sentinel_queries)} sentinel queries")

    for q in sentinel_queries:
        result = _simulate(round_id, q["seed_index"], q["viewport"], label="sentinel")
        all_observations.append(_obs_from_result(q["seed_index"], q["viewport"], result))
        budget_remaining -= 1

    regime_post = regime_posterior(all_observations)
    print(f"Regime after sentinels: {regime_post}")

    # Phase 2: Coverage
    coverage_budget = max(0, budget_remaining - REFINEMENT_BUDGET)
    coverage_queries = select_coverage_queries(initial_states, all_observations, coverage_budget)
    print(f"\nPhase 2: {len(coverage_queries)} coverage queries")

    for q in coverage_queries:
        result = _simulate(round_id, q["seed_index"], q["viewport"], label="coverage")
        all_observations.append(_obs_from_result(q["seed_index"], q["viewport"], result))
        budget_remaining -= 1

    regime_post = regime_posterior(all_observations)
    print(f"Regime after coverage: {regime_post}")

    # Phase 3: Refinement
    refinement_queries = select_refinement_queries(all_observations, budget_remaining)
    print(f"\nPhase 3: {len(refinement_queries)} refinement queries")

    for i, q in enumerate(refinement_queries):
        result = _simulate(round_id, q["seed_index"], q["viewport"], label=f"refine_{i}")
        all_observations.append(_obs_from_result(q["seed_index"], q["viewport"], result, repeat_index=i + 1))
        budget_remaining -= 1

    # Generate predictions
    print(f"\nGenerating predictions ({len(all_observations)} total observations)...")
    predictions = predict_all_seeds(initial_states, all_observations)

    for seed_index in range(len(predictions)):
        predictions[seed_index] = format_prediction(predictions[seed_index])
        validate_prediction(predictions[seed_index], height, width)

    # Save predictions
    out_dir = _artifact_dir(round_id)
    for seed_index, pred in enumerate(predictions):
        dump_json(out_dir / f"bayesian_prediction_seed_{seed_index}.json", pred)

    # Submit
    print("\nSubmitting predictions...")
    submit_results: list[dict[str, Any]] = []
    for seed_index, pred in enumerate(predictions):
        response = api_post(
            "/submit",
            {"round_id": round_id, "seed_index": seed_index, "prediction": pred},
            auth=True,
        )
        submit_results.append(response)
        print(f"  Seed {seed_index}: submitted")

    summary = {
        "round_id": round_id,
        "approach": "experimental_bayesian",
        "total_observations": len(all_observations),
        "regime_posterior": regime_post,
        "queries_used": queries_max - budget_remaining,
        "submit_results": submit_results,
    }
    dump_json(out_dir / "bayesian_cycle_summary.json", summary)
    print(f"\nDone. {json.dumps(summary, indent=2)}")
