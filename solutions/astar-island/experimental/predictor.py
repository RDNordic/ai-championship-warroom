"""Full prediction pipeline: regime -> pooling -> per-cell Dirichlet posterior."""
from __future__ import annotations

from typing import Any

from .config import DIRICHLET_PRIORS, NUM_CLASSES, REGIMES
from .dirichlet import normalize_with_floor, posterior_alpha, posterior_mean
from .features import build_feature_map
from .pooling import map_code_to_class, pool_observations
from .regime import regime_posterior


def _build_cell_counts(
    observations: list[dict[str, Any]],
    seed_index: int,
    height: int = 40,
    width: int = 40,
) -> list[list[list[int]]]:
    """Build per-cell observation count vectors for a single seed."""
    counts = [[[0] * NUM_CLASSES for _ in range(width)] for _ in range(height)]

    for obs in observations:
        if obs["seed_index"] != seed_index:
            continue
        vp = obs["viewport"]
        for dy, row in enumerate(obs["grid"]):
            for dx, code in enumerate(row):
                y = vp["y"] + dy
                x = vp["x"] + dx
                if 0 <= y < height and 0 <= x < width:
                    counts[y][x][map_code_to_class(code)] += 1

    return counts


def predict_seed(
    initial_state: dict[str, Any],
    seed_index: int,
    observations: list[dict[str, Any]],
    feature_map: list[list[str]],
    bucket_counts: dict[str, list[int]],
    regime_post: dict[str, float],
    height: int = 40,
    width: int = 40,
) -> list[list[list[float]]]:
    """
    Generate a height x width x NUM_CLASSES prediction tensor for one seed.

    Two-level Dirichlet model:
      Level 1: bucket prior + pooled cross-seed counts -> bucket posterior
      Level 2: bucket posterior + this cell's own observations -> cell posterior

    Final prediction is a regime-weighted mixture.
    """
    cell_counts = _build_cell_counts(observations, seed_index, height, width)

    prediction: list[list[list[float]]] = []
    for y in range(height):
        row: list[list[float]] = []
        for x in range(width):
            bucket = feature_map[y][x]
            cell_obs = cell_counts[y][x]
            cell_total = sum(cell_obs)

            mixed = [0.0] * NUM_CLASSES
            for regime in REGIMES:
                weight = regime_post.get(regime, 0.0)
                if weight < 1e-8:
                    continue

                bucket_prior = DIRICHLET_PRIORS[regime].get(
                    bucket, [1.0] * NUM_CLASSES
                )
                b_counts = bucket_counts.get(bucket, [0] * NUM_CLASSES)
                bucket_alpha = posterior_alpha(bucket_prior, b_counts)

                if cell_total > 0:
                    # Cell-level: start from bucket posterior, add own observations
                    cell_alpha = posterior_alpha(bucket_alpha, cell_obs)
                    cell_mean = posterior_mean(cell_alpha)
                else:
                    cell_mean = posterior_mean(bucket_alpha)

                for k in range(NUM_CLASSES):
                    mixed[k] += weight * cell_mean[k]

            row.append(normalize_with_floor(mixed))
        prediction.append(row)

    return prediction


def predict_all_seeds(
    initial_states: list[dict[str, Any]],
    observations: list[dict[str, Any]],
) -> list[list[list[list[float]]]]:
    """
    Full prediction pipeline for all seeds in a round.

    1. Build feature maps for all seeds
    2. Pool observations across seeds into bucket counts
    3. Compute regime posterior from all observations
    4. Generate per-seed predictions as regime-weighted Dirichlet posteriors
    """
    feature_maps = [build_feature_map(state) for state in initial_states]
    bucket_counts = pool_observations(observations, feature_maps)
    regime_post = regime_posterior(observations)

    predictions: list[list[list[list[float]]]] = []
    for seed_index, initial_state in enumerate(initial_states):
        pred = predict_seed(
            initial_state,
            seed_index,
            observations,
            feature_maps[seed_index],
            bucket_counts,
            regime_post,
        )
        predictions.append(pred)

    return predictions
