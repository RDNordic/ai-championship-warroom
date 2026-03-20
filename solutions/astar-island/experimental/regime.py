"""Bayesian regime detection via Bayes factor computation."""
from __future__ import annotations

import math
from typing import Any

from .config import REGIME_DYNAMIC_RATE, REGIME_PRIOR, REGIMES
from .pooling import compute_dynamic_counts


def _log_binomial_likelihood(k: int, n: int, p: float) -> float:
    """Log-likelihood of k successes in n trials with rate p (up to constant)."""
    if p <= 0:
        return -float("inf") if k > 0 else 0.0
    if p >= 1:
        return -float("inf") if k < n else 0.0
    return k * math.log(p) + (n - k) * math.log(1 - p)


def regime_posterior(
    observations: list[dict[str, Any]],
    prior: dict[str, float] | None = None,
) -> dict[str, float]:
    """
    Compute posterior probability of each regime given observations.
    Uses a Binomial model for dynamic vs non-dynamic cell counts.
    """
    if prior is None:
        prior = dict(REGIME_PRIOR)

    dynamic_count, total_count = compute_dynamic_counts(observations)

    if total_count == 0:
        return dict(prior)

    log_posteriors: dict[str, float] = {}
    for regime in REGIMES:
        rate = REGIME_DYNAMIC_RATE[regime]
        log_prior = math.log(max(prior.get(regime, 0.01), 1e-10))
        log_lik = _log_binomial_likelihood(dynamic_count, total_count, rate)
        log_posteriors[regime] = log_prior + log_lik

    # Normalize in log space
    max_log = max(log_posteriors.values())
    posteriors: dict[str, float] = {}
    denom = 0.0
    for regime in REGIMES:
        posteriors[regime] = math.exp(log_posteriors[regime] - max_log)
        denom += posteriors[regime]

    for regime in REGIMES:
        posteriors[regime] /= denom

    return posteriors


def is_collapse(regime_post: dict[str, float], threshold: float = 0.7) -> bool:
    """Check if the collapse regime is dominant."""
    return regime_post.get("collapse", 0.0) > threshold
