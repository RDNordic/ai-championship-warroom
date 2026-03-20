"""Hyperparameters and constants for the experimental Bayesian approach."""
from __future__ import annotations

NUM_CLASSES = 6
CLASS_NAMES = ["empty", "settlement", "port", "ruin", "forest", "mountain"]

# --- Regime model ---
REGIMES = ["collapse", "dynamic"]
REGIME_PRIOR: dict[str, float] = {"collapse": 0.20, "dynamic": 0.80}

# Expected dynamic rate (classes 1,2,3) per regime for Bayes factor
REGIME_DYNAMIC_RATE: dict[str, float] = {"collapse": 0.02, "dynamic": 0.18}

# --- Feature buckets ---
NEAR_SETTLEMENT_DIST = 3

# --- Dirichlet priors per regime per bucket ---
# Alpha vectors: [empty, settlement, port, ruin, forest, mountain]
# Prior strength = sum(alpha) controls how much prior dominates over observations
DIRICHLET_PRIORS: dict[str, dict[str, list[float]]] = {
    "dynamic": {
        "mountain":      [0.1, 0.05, 0.05, 0.05, 0.1, 5.0],
        "forest":        [0.3, 0.2, 0.05, 0.15, 4.5, 0.15],
        "settlement":    [0.6, 2.5, 0.6, 0.6, 0.25, 0.1],
        "port":          [0.6, 0.6, 2.5, 0.6, 0.25, 0.1],
        "ruin":          [0.4, 0.4, 0.15, 2.5, 0.25, 0.1],
        "plains_near":   [2.5, 0.8, 0.2, 0.3, 0.5, 0.1],
        "plains_remote": [4.0, 0.2, 0.05, 0.15, 0.5, 0.1],
    },
    "collapse": {
        "mountain":      [0.1, 0.02, 0.02, 0.02, 0.1, 6.0],
        "forest":        [0.5, 0.05, 0.02, 0.1, 5.5, 0.15],
        "settlement":    [2.5, 0.2, 0.1, 0.8, 0.4, 0.05],
        "port":          [2.5, 0.1, 0.2, 0.8, 0.4, 0.05],
        "ruin":          [1.5, 0.1, 0.05, 2.0, 0.4, 0.1],
        "plains_near":   [5.0, 0.1, 0.03, 0.15, 0.8, 0.05],
        "plains_remote": [6.0, 0.05, 0.02, 0.08, 0.6, 0.05],
    },
}

# --- Submission ---
PROB_FLOOR = 0.01

# --- Query strategy ---
COVERAGE_VIEWPORTS = [
    {"x": 0,  "y": 0,  "w": 15, "h": 15},
    {"x": 15, "y": 0,  "w": 15, "h": 15},
    {"x": 25, "y": 0,  "w": 15, "h": 15},
    {"x": 0,  "y": 15, "w": 15, "h": 15},
    {"x": 15, "y": 15, "w": 15, "h": 15},
    {"x": 25, "y": 15, "w": 15, "h": 15},
    {"x": 0,  "y": 25, "w": 15, "h": 15},
    {"x": 15, "y": 25, "w": 15, "h": 15},
    {"x": 25, "y": 25, "w": 15, "h": 15},
]

TOTAL_BUDGET = 50
SENTINEL_BUDGET = 10
REFINEMENT_BUDGET = 5
