"""Dirichlet-multinomial conjugate model for cell-level prediction."""
from __future__ import annotations

from .config import NUM_CLASSES, PROB_FLOOR


def posterior_alpha(prior_alpha: list[float], counts: list[int]) -> list[float]:
    """Compute posterior Dirichlet alpha = prior + observed counts."""
    return [a + n for a, n in zip(prior_alpha, counts)]


def posterior_mean(alpha: list[float]) -> list[float]:
    """Posterior mean of a Dirichlet distribution."""
    total = sum(alpha)
    if total <= 0:
        return [1.0 / NUM_CLASSES] * NUM_CLASSES
    return [a / total for a in alpha]


def normalize_with_floor(probs: list[float], floor: float = PROB_FLOOR) -> list[float]:
    """Normalize probabilities with a minimum floor (never submit 0.0)."""
    floored = [max(p, floor) for p in probs]
    total = sum(floored)
    return [p / total for p in floored]
