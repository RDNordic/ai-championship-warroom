"""Compare CELL_CONCENTRATION values across all rounds with replay data."""
import sys, json, math
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from experimental.config import NUM_CLASSES, DIRICHLET_PRIORS, REGIMES, PROB_FLOOR
from experimental.dirichlet import normalize_with_floor, posterior_alpha, posterior_mean
from experimental.features import build_feature_map
from experimental.pooling import map_code_to_class, pool_observations
from experimental.regime import regime_posterior

ARTIFACTS = Path(__file__).resolve().parent / "artifacts"

ROUNDS = {
    1: "71451d74-be9f-471f-aacd-a41f3b68a9cd",
    2: "76909e29-f664-4b2f-b16b-61b7507277e9",
    3: "f1dac9a9-5cf1-49a9-8f17-d6cb5d5ba5cb",
    5: "fd3c92ff-3178-4dc9-8d9b-acf389b3982b",
    6: "ae78003a-4efe-425a-881a-d16a39bca0ad",
    7: "36e581f1-73f8-453f-ab98-cbe3052b701b",
    8: "c5cdf100-a876-4fb7-b5d8-757162c97989",
}

CONCENTRATIONS = [10, 15, 20, 25, 30, 40]


def load_json(p):
    return json.loads(p.read_text(encoding="utf-8"))


def load_observations(round_id):
    obs = []
    for sim_dir_name in ["simulate_bayesian", "simulate"]:
        sim_dir = ARTIFACTS / f"round_{round_id}" / sim_dir_name
        if not sim_dir.exists():
            continue
        for path in sorted(sim_dir.glob("*.json")):
            data = load_json(path)
            name = path.stem
            parts = name.split("_")
            seed_index = int(parts[1])
            vp = {}
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
            if len(vp) == 4:
                obs.append({
                    "seed_index": seed_index,
                    "viewport": vp,
                    "grid": data["grid"],
                    "settlements": data.get("settlements", []),
                    "repeat_index": repeat,
                })
        if obs:
            break
    return obs


def predict_with_concentration(initial_states, observations, cell_concentration):
    feature_maps = [build_feature_map(state) for state in initial_states]
    bucket_counts = pool_observations(observations, feature_maps)
    regime_post = regime_posterior(observations)

    predictions = []
    for seed_index, initial_state in enumerate(initial_states):
        # Build cell counts
        h, w = 40, 40
        counts = [[[0] * NUM_CLASSES for _ in range(w)] for _ in range(h)]
        for obs_item in observations:
            if obs_item["seed_index"] != seed_index:
                continue
            vp = obs_item["viewport"]
            for dy, row in enumerate(obs_item["grid"]):
                for dx, code in enumerate(row):
                    y = vp["y"] + dy
                    x = vp["x"] + dx
                    if 0 <= y < h and 0 <= x < w:
                        counts[y][x][map_code_to_class(code)] += 1

        prediction = []
        for y in range(h):
            row = []
            for x in range(w):
                bucket = feature_maps[seed_index][y][x]
                cell_obs = counts[y][x]
                cell_total = sum(cell_obs)
                mixed = [0.0] * NUM_CLASSES
                for regime in REGIMES:
                    weight = regime_post.get(regime, 0.0)
                    if weight < 1e-8:
                        continue
                    bucket_prior = DIRICHLET_PRIORS[regime].get(bucket, [1.0] * NUM_CLASSES)
                    b_counts = bucket_counts.get(bucket, [0] * NUM_CLASSES)
                    bucket_alpha = posterior_alpha(bucket_prior, b_counts)
                    bucket_mean_val = posterior_mean(bucket_alpha)
                    if cell_total > 0:
                        cell_prior = [m * cell_concentration for m in bucket_mean_val]
                        cell_alpha = posterior_alpha(cell_prior, cell_obs)
                        cell_mean = posterior_mean(cell_alpha)
                    else:
                        cell_mean = bucket_mean_val
                    for k in range(NUM_CLASSES):
                        mixed[k] += weight * cell_mean[k]
                row.append(normalize_with_floor(mixed))
            prediction.append(row)
        predictions.append(prediction)
    return predictions, regime_post


def score_prediction(prediction, ground_truth):
    """Competition-style scoring (entropy-weighted KL)."""
    max_entropy = math.log(NUM_CLASSES)
    total = 0.0
    for y in range(len(ground_truth)):
        for x in range(len(ground_truth[y])):
            p = ground_truth[y][x]
            q = prediction[y][x]
            w = 0.0
            for pk in p:
                if pk > 1e-15:
                    w -= pk * math.log(pk)
            w /= max_entropy if max_entropy > 0 else 1.0
            kl = 0.0
            for pk, qk in zip(p, q):
                if pk > 1e-15:
                    kl += pk * math.log(pk / max(qk, 1e-15))
            total += w * kl
    return total


def main():
    print(f"{'Round':>5} | {'Regime':>8} | ", end="")
    for c in CONCENTRATIONS:
        print(f"{'C='+str(c):>8}", end=" | ")
    print("Best")
    print("-" * (20 + 11 * len(CONCENTRATIONS) + 6))

    overall = {c: 0.0 for c in CONCENTRATIONS}
    n_seeds = 0

    for rnd, round_id in sorted(ROUNDS.items()):
        detail_path = ARTIFACTS / f"round_{round_id}" / "round_detail.json"
        if not detail_path.exists():
            continue

        detail = load_json(detail_path)
        observations = load_observations(round_id)
        if not observations:
            print(f"R{rnd:>4} | skipped (no observations)")
            continue

        seeds_count = detail.get("seeds_count", 5)
        analysis_dir = ARTIFACTS / f"round_{round_id}" / "analysis"

        analyses = []
        for s in range(seeds_count):
            ap = analysis_dir / f"seed_{s}.json"
            if not ap.exists():
                break
            analyses.append(load_json(ap))
        if len(analyses) != seeds_count:
            print(f"R{rnd:>4} | skipped (incomplete analysis)")
            continue

        # Detect regime once
        regime_post = regime_posterior(observations)
        regime = "collapse" if regime_post.get("collapse", 0) > 0.5 else "dynamic"

        scores = {c: [] for c in CONCENTRATIONS}
        for c in CONCENTRATIONS:
            preds, _ = predict_with_concentration(detail["initial_states"], observations, c)
            for s in range(seeds_count):
                kl = score_prediction(preds[s], analyses[s]["ground_truth"])
                scores[c].append(kl)

        # Print per-round mean KL (lower is better)
        means = {c: sum(scores[c]) / seeds_count for c in CONCENTRATIONS}
        best_c = min(means, key=means.get)

        print(f"R{rnd:>4} | {regime:>8} | ", end="")
        for c in CONCENTRATIONS:
            marker = " *" if c == best_c else "  "
            print(f"{means[c]:>6.3f}{marker}", end=" | ")
        print(f"C={best_c}")

        for c in CONCENTRATIONS:
            overall[c] += sum(scores[c])
        n_seeds += seeds_count

    print("-" * (20 + 11 * len(CONCENTRATIONS) + 6))
    print(f"{'TOTAL':>5} | {'':>8} | ", end="")
    best_overall = min(overall, key=overall.get)
    for c in CONCENTRATIONS:
        avg = overall[c] / n_seeds if n_seeds > 0 else 0
        marker = " *" if c == best_overall else "  "
        print(f"{avg:>6.3f}{marker}", end=" | ")
    print(f"C={best_overall}")


if __name__ == "__main__":
    main()
