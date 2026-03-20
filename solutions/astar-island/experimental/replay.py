"""Offline replay validation against saved artifacts."""
from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

from .config import NUM_CLASSES
from .predictor import predict_all_seeds

ROUND_IDS = {
    1: "71451d74-be9f-471f-aacd-a41f3b68a9cd",
    2: "76909e29-f664-4b2f-b16b-61b7507277e9",
    3: "f1dac9a9-5cf1-49a9-8f17-d6cb5d5ba5cb",
    5: "fd3c92ff-3178-4dc9-8d9b-acf389b3982b",
}

ARTIFACTS_ROOT = Path(__file__).resolve().parent.parent / "artifacts"


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _load_round_detail(round_id: str) -> dict[str, Any]:
    return _load_json(ARTIFACTS_ROOT / f"round_{round_id}" / "round_detail.json")


def _load_observations(round_id: str) -> list[dict[str, Any]]:
    """Load all saved simulation results for a round."""
    sim_dir = ARTIFACTS_ROOT / f"round_{round_id}" / "simulate"
    if not sim_dir.exists():
        return []

    observations: list[dict[str, Any]] = []
    for path in sorted(sim_dir.glob("*.json")):
        data = _load_json(path)
        name = path.stem
        parts = name.split("_")
        seed_index = int(parts[1])

        vp: dict[str, int] = {}
        repeat = 0
        for p in parts[2:]:
            if p.startswith("x") and len(p) > 1 and p[1:].isdigit():
                vp["x"] = int(p[1:])
            elif p.startswith("y") and len(p) > 1 and p[1:].isdigit():
                vp["y"] = int(p[1:])
            elif p.startswith("w") and len(p) > 1 and p[1:].isdigit():
                vp["w"] = int(p[1:])
            elif p.startswith("h") and len(p) > 1 and p[1:].isdigit():
                vp["h"] = int(p[1:])
            elif p.startswith("repeat") and len(p) > 6 and p[6:].isdigit():
                repeat = int(p[6:])

        if len(vp) == 4:
            observations.append({
                "seed_index": seed_index,
                "viewport": vp,
                "grid": data["grid"],
                "settlements": data.get("settlements", []),
                "repeat_index": repeat,
            })

    return observations


def _load_analysis(round_id: str, seed_index: int) -> dict[str, Any] | None:
    path = ARTIFACTS_ROOT / f"round_{round_id}" / "analysis" / f"seed_{seed_index}.json"
    if not path.exists():
        return None
    return _load_json(path)


def _kl_divergence(p: list[float], q: list[float]) -> float:
    """KL(p || q)."""
    kl = 0.0
    for pk, qk in zip(p, q):
        if pk > 1e-15:
            kl += pk * math.log(pk / max(qk, 1e-15))
    return kl


def _entropy(p: list[float]) -> float:
    h = 0.0
    for pk in p:
        if pk > 1e-15:
            h -= pk * math.log(pk)
    return h


def score_prediction(
    prediction: list[list[list[float]]],
    ground_truth: list[list[list[float]]],
) -> float:
    """Compute entropy-weighted KL divergence (lower = better)."""
    max_entropy = math.log(NUM_CLASSES)
    total = 0.0
    for y in range(len(ground_truth)):
        for x in range(len(ground_truth[y])):
            p = ground_truth[y][x]
            q = prediction[y][x]
            w = _entropy(p) / max_entropy if max_entropy > 0 else 0.0
            total += w * _kl_divergence(p, q)
    return total


def replay_round(round_number: int) -> dict[str, Any] | None:
    """Replay a completed round through the Bayesian pipeline and compare."""
    round_id = ROUND_IDS.get(round_number)
    if not round_id:
        print(f"  No round ID for round {round_number}")
        return None

    try:
        detail = _load_round_detail(round_id)
    except FileNotFoundError:
        print(f"  No round detail for round {round_number}")
        return None

    observations = _load_observations(round_id)
    if not observations:
        print(f"  No observations for round {round_number}")
        return None

    seeds_count = detail.get("seeds_count", 5)
    analyses = []
    for seed in range(seeds_count):
        analysis = _load_analysis(round_id, seed)
        if analysis is None:
            print(f"  No analysis for round {round_number} seed {seed}")
            return None
        analyses.append(analysis)

    # Run new pipeline
    new_predictions = predict_all_seeds(detail["initial_states"], observations)

    # Compute regime posterior for reporting
    from .regime import regime_posterior
    regime_post = regime_posterior(observations)

    results: dict[str, Any] = {
        "round_number": round_number,
        "round_id": round_id,
        "observations_count": len(observations),
        "regime_posterior": {k: round(v, 4) for k, v in regime_post.items()},
        "seeds": [],
    }

    for seed in range(seeds_count):
        gt = analyses[seed]["ground_truth"]
        baseline_pred = analyses[seed]["prediction"]
        baseline_api_score = analyses[seed]["score"]
        new_pred = new_predictions[seed]

        baseline_kl = score_prediction(baseline_pred, gt)
        new_kl = score_prediction(new_pred, gt)

        results["seeds"].append({
            "seed": seed,
            "baseline_api_score": baseline_api_score,
            "baseline_weighted_kl": round(baseline_kl, 4),
            "new_weighted_kl": round(new_kl, 4),
            "improvement": round(baseline_kl - new_kl, 4),
            "better": new_kl < baseline_kl,
        })

    baseline_mean = sum(s["baseline_weighted_kl"] for s in results["seeds"]) / seeds_count
    new_mean = sum(s["new_weighted_kl"] for s in results["seeds"]) / seeds_count
    wins = sum(1 for s in results["seeds"] if s["better"])

    results["baseline_mean_kl"] = round(baseline_mean, 4)
    results["new_mean_kl"] = round(new_mean, 4)
    results["mean_improvement"] = round(baseline_mean - new_mean, 4)
    results["wins"] = f"{wins}/{seeds_count}"
    results["verdict"] = "BETTER" if new_mean < baseline_mean else "WORSE"

    return results


def main() -> None:
    print("=" * 60)
    print("BAYESIAN REPLAY VALIDATION")
    print("=" * 60)

    all_results = []
    for round_num in sorted(ROUND_IDS.keys()):
        print(f"\n--- Round {round_num} ---")
        result = replay_round(round_num)
        if result:
            all_results.append(result)
            print(f"  Regime: {result['regime_posterior']}")
            for s in result["seeds"]:
                marker = "+" if s["better"] else "-"
                print(
                    f"  Seed {s['seed']}: baseline_kl={s['baseline_weighted_kl']:.4f} "
                    f"new_kl={s['new_weighted_kl']:.4f} [{marker}] "
                    f"(API score: {s['baseline_api_score']:.2f})"
                )
            print(
                f"  Round: baseline={result['baseline_mean_kl']:.4f} "
                f"new={result['new_mean_kl']:.4f} "
                f"wins={result['wins']} -> {result['verdict']}"
            )

    if all_results:
        round_wins = sum(1 for r in all_results if r["verdict"] == "BETTER")
        print(f"\n{'=' * 60}")
        print(f"OVERALL: {round_wins}/{len(all_results)} rounds improved")
        if round_wins >= 3:
            print("RECOMMENDATION: Deploy experimental approach")
        else:
            print("RECOMMENDATION: Keep baseline, investigate failures")
        print(f"{'=' * 60}")
