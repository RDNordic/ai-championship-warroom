from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from astar_api import ROOT, api_get, api_post, dump_json, get_active_round
from model import build_prior_prediction, validate_prediction


def artifact_dir(round_id: str) -> Path:
    return ROOT / "artifacts" / f"round_{round_id}"


def save_artifacts(round_id: str, detail: dict[str, Any], predictions: list[list[list[list[float]]]]) -> Path:
    out_dir = artifact_dir(round_id)
    dump_json(out_dir / "round_detail.json", detail)

    for seed_index, prediction in enumerate(predictions):
        dump_json(out_dir / f"prediction_seed_{seed_index}.json", prediction)

    summary = {
        "round_id": round_id,
        "seeds_count": len(predictions),
        "artifact_dir": str(out_dir),
    }
    dump_json(out_dir / "summary.json", summary)
    return out_dir


def main() -> None:
    parser = argparse.ArgumentParser(description="Build and optionally submit a prior-only baseline.")
    parser.add_argument(
        "--submit",
        action="store_true",
        help="Submit the generated baseline for all seeds in the active round.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Allow submission even if the team already has predictions on file.",
    )
    args = parser.parse_args()

    rounds = api_get("/rounds", auth=False)
    active_round = get_active_round(rounds)
    if not active_round:
        raise SystemExit("No active round found.")

    round_id = active_round["id"]
    detail = api_get(f"/rounds/{round_id}", auth=False)
    predictions_on_file = api_get(f"/my-predictions/{round_id}", auth=True)

    if predictions_on_file and not args.force:
        raise SystemExit(
            "Team already has predictions on file. Re-run with --force only if you intend to overwrite them."
        )

    initial_states = detail["initial_states"]
    height = detail["map_height"]
    width = detail["map_width"]

    predictions: list[list[list[list[float]]]] = []
    for initial_state in initial_states:
        prediction = build_prior_prediction(initial_state)
        validate_prediction(prediction, height, width)
        predictions.append(prediction)

    out_dir = save_artifacts(round_id, detail, predictions)

    if not args.submit:
        print(
            json.dumps(
                {
                    "status": "built",
                    "round_id": round_id,
                    "artifact_dir": str(out_dir),
                    "seeds_count": len(predictions),
                },
                indent=2,
            )
        )
        return

    results: list[dict[str, Any]] = []
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
        results.append(response)

    dump_json(out_dir / "submit_results.json", results)
    print(
        json.dumps(
            {
                "status": "submitted",
                "round_id": round_id,
                "artifact_dir": str(out_dir),
                "results": results,
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
