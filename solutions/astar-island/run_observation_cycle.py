from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from astar_api import ROOT, api_get, api_post, dump_json, get_active_round
from model import DYNAMIC_CODES, build_prior_prediction, map_code_to_class_index, normalize_cell, validate_prediction


VIEWPORTS = [
    {"viewport_x": 0, "viewport_y": 0, "viewport_w": 15, "viewport_h": 15},
    {"viewport_x": 15, "viewport_y": 0, "viewport_w": 15, "viewport_h": 15},
    {"viewport_x": 25, "viewport_y": 0, "viewport_w": 15, "viewport_h": 15},
    {"viewport_x": 0, "viewport_y": 15, "viewport_w": 15, "viewport_h": 15},
    {"viewport_x": 15, "viewport_y": 15, "viewport_w": 15, "viewport_h": 15},
    {"viewport_x": 25, "viewport_y": 15, "viewport_w": 15, "viewport_h": 15},
    {"viewport_x": 0, "viewport_y": 25, "viewport_w": 15, "viewport_h": 15},
    {"viewport_x": 15, "viewport_y": 25, "viewport_w": 15, "viewport_h": 15},
    {"viewport_x": 25, "viewport_y": 25, "viewport_w": 15, "viewport_h": 15},
]

REPEAT_QUERIES = 3
PRIOR_STRENGTH = 4.0
OBSERVATION_CLASS_WEIGHTS = [1.0, 0.45, 0.45, 0.45, 1.0, 1.0]
COLLAPSE_DYNAMIC_RATE_THRESHOLD = 0.01
COLLAPSE_DYNAMIC_SCALE = 0.12
COLLAPSE_REALLOCATION = {0: 0.85, 4: 0.15}
COLLAPSE_OBSERVATION_CLASS_WEIGHTS = [1.0, 0.10, 0.10, 0.10, 1.0, 1.0]


def round_artifact_dir(round_id: str) -> Path:
    return ROOT / "artifacts" / f"round_{round_id}"


def canonical_viewport(viewport: dict[str, int]) -> dict[str, int]:
    if "x" in viewport and "y" in viewport and "w" in viewport and "h" in viewport:
        return {
            "x": viewport["x"],
            "y": viewport["y"],
            "w": viewport["w"],
            "h": viewport["h"],
        }
    return {
        "x": viewport["viewport_x"],
        "y": viewport["viewport_y"],
        "w": viewport["viewport_w"],
        "h": viewport["viewport_h"],
    }


def simulate_payload(round_id: str, seed_index: int, viewport: dict[str, int]) -> dict[str, int | str]:
    canonical = canonical_viewport(viewport)
    return {
        "round_id": round_id,
        "seed_index": seed_index,
        "viewport_x": canonical["x"],
        "viewport_y": canonical["y"],
        "viewport_w": canonical["w"],
        "viewport_h": canonical["h"],
    }


def observation_path(round_id: str, seed_index: int, viewport: dict[str, int], repeat_index: int = 0) -> Path:
    canonical = canonical_viewport(viewport)
    x = canonical["x"]
    y = canonical["y"]
    w = canonical["w"]
    h = canonical["h"]
    suffix = f"_repeat{repeat_index}" if repeat_index else ""
    name = (
        f"seed_{seed_index}_x{x}_y{y}"
        f"_w{w}_h{h}{suffix}.json"
    )
    return round_artifact_dir(round_id) / "simulate" / name


def fetch_or_load_simulation(
    round_id: str, seed_index: int, viewport: dict[str, int], repeat_index: int = 0
) -> dict[str, Any]:
    path = observation_path(round_id, seed_index, viewport, repeat_index=repeat_index)
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))

    payload = simulate_payload(round_id, seed_index, viewport)
    result = api_post("/simulate", payload, auth=True)
    dump_json(path, result)
    time.sleep(0.25)
    return result


def coverage_observations(round_id: str, seeds_count: int) -> list[dict[str, Any]]:
    observations: list[dict[str, Any]] = []
    for seed_index in range(seeds_count):
        for viewport in VIEWPORTS:
            result = fetch_or_load_simulation(round_id, seed_index, viewport)
            requested_viewport = canonical_viewport(viewport)
            observations.append(
                {
                    "seed_index": seed_index,
                    "viewport": requested_viewport,
                    "grid": result["grid"],
                    "settlements": result.get("settlements", []),
                    "repeat_index": 0,
                }
            )
    return observations


def observation_stats(observations: list[dict[str, Any]]) -> dict[str, Any]:
    terrain_counts: dict[int, int] = {}
    total_cells = 0
    dynamic_cells = 0

    for obs in observations:
        for row in obs["grid"]:
            for code in row:
                terrain_counts[code] = terrain_counts.get(code, 0) + 1
                total_cells += 1
                if code in DYNAMIC_CODES:
                    dynamic_cells += 1

    dynamic_rate = (dynamic_cells / total_cells) if total_cells else 0.0
    return {
        "total_cells": total_cells,
        "dynamic_cells": dynamic_cells,
        "dynamic_rate": dynamic_rate,
        "terrain_counts": terrain_counts,
    }


def collapse_mode_for_stats(stats: dict[str, Any]) -> bool:
    return stats["dynamic_rate"] <= COLLAPSE_DYNAMIC_RATE_THRESHOLD


def viewport_dynamic_score(obs: dict[str, Any]) -> float:
    grid = obs["grid"]
    dynamic_cells = sum(1 for row in grid for code in row if code in DYNAMIC_CODES)
    ports = sum(1 for s in obs["settlements"] if s.get("has_port"))
    ruins = sum(1 for row in grid for code in row if code == 3)
    return dynamic_cells + (2 * len(obs["settlements"])) + ports + ruins


def choose_repeat_targets(observations: list[dict[str, Any]], max_targets: int) -> list[dict[str, Any]]:
    ranked = sorted(observations, key=viewport_dynamic_score, reverse=True)
    return ranked[:max_targets]


def repeat_observations(round_id: str, targets: list[dict[str, Any]]) -> list[dict[str, Any]]:
    repeats: list[dict[str, Any]] = []
    for repeat_index, target in enumerate(targets, start=1):
        result = fetch_or_load_simulation(
            round_id,
            target["seed_index"],
            target["viewport"],
            repeat_index=repeat_index,
        )
        requested_viewport = canonical_viewport(target["viewport"])
        repeats.append(
            {
                "seed_index": target["seed_index"],
                "viewport": requested_viewport,
                "grid": result["grid"],
                "settlements": result.get("settlements", []),
                "repeat_index": repeat_index,
            }
        )
    return repeats


def apply_collapse_damping(prediction: list[list[list[float]]]) -> list[list[list[float]]]:
    for y, row in enumerate(prediction):
        for x, cell in enumerate(row):
            updated = cell[:]
            removed_mass = 0.0
            for class_index in (1, 2, 3):
                original = updated[class_index]
                updated[class_index] = original * COLLAPSE_DYNAMIC_SCALE
                removed_mass += original - updated[class_index]

            for class_index, share in COLLAPSE_REALLOCATION.items():
                updated[class_index] += removed_mass * share

            prediction[y][x] = normalize_cell(updated)

    return prediction


def combine_prior_with_observations(
    initial_state: dict[str, Any],
    observations: list[dict[str, Any]],
    collapse_mode: bool = False,
) -> list[list[list[float]]]:
    prediction = build_prior_prediction(initial_state)
    observation_weights = OBSERVATION_CLASS_WEIGHTS

    if collapse_mode:
        prediction = apply_collapse_damping(prediction)
        observation_weights = COLLAPSE_OBSERVATION_CLASS_WEIGHTS

    for obs in observations:
        viewport = obs["viewport"]
        grid = obs["grid"]
        for dy, row in enumerate(grid):
            for dx, code in enumerate(row):
                y = viewport["y"] + dy
                x = viewport["x"] + dx
                counts = [PRIOR_STRENGTH * p for p in prediction[y][x]]
                class_index = map_code_to_class_index(code)
                counts[class_index] += observation_weights[class_index]
                prediction[y][x] = normalize_cell(counts)

    return prediction


def summarize_cycle(
    round_id: str,
    coverage: list[dict[str, Any]],
    repeats: list[dict[str, Any]],
    coverage_stats: dict[str, Any],
    collapse_mode: bool,
    submit_results: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "round_id": round_id,
        "coverage_queries": len(coverage),
        "repeat_queries": len(repeats),
        "coverage_stats": coverage_stats,
        "collapse_mode": collapse_mode,
        "repeat_targets": [
            {
                "seed_index": item["seed_index"],
                "viewport": item["viewport"],
                "dynamic_score": viewport_dynamic_score(item),
            }
            for item in repeats
        ],
        "submit_results": submit_results,
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
        raise SystemExit("No active budget returned for this round.")

    seeds_count = detail["seeds_count"]
    coverage = coverage_observations(round_id, seeds_count)
    coverage_stats = observation_stats(coverage)
    collapse_mode = collapse_mode_for_stats(coverage_stats)
    repeat_targets = [] if collapse_mode else choose_repeat_targets(coverage, REPEAT_QUERIES)
    repeats = repeat_observations(round_id, repeat_targets)

    by_seed: dict[int, list[dict[str, Any]]] = {seed: [] for seed in range(seeds_count)}
    for item in coverage + repeats:
        by_seed[item["seed_index"]].append(item)

    predictions: list[list[list[list[float]]]] = []
    for seed_index, initial_state in enumerate(detail["initial_states"]):
        prediction = combine_prior_with_observations(
            initial_state,
            by_seed[seed_index],
            collapse_mode=collapse_mode,
        )
        validate_prediction(prediction, detail["map_height"], detail["map_width"])
        predictions.append(prediction)
        dump_json(round_artifact_dir(round_id) / f"improved_prediction_seed_{seed_index}.json", prediction)

    submit_results: list[dict[str, Any]] = []
    for seed_index, prediction in enumerate(predictions):
        response = api_post(
            "/submit",
            {
                "round_id": round_id,
                "seed_index": seed_index,
                "prediction": prediction,
            },
            auth=True,
        )
        submit_results.append(response)

    summary = summarize_cycle(round_id, coverage, repeats, coverage_stats, collapse_mode, submit_results)
    dump_json(round_artifact_dir(round_id) / "observation_cycle_summary.json", summary)
    print(json.dumps(summary, indent=2, ensure_ascii=True))


if __name__ == "__main__":
    main()
