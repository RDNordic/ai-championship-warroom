from __future__ import annotations

import argparse
import json
from pathlib import Path

from astar_api import ROOT, api_get, dump_json


def export_round(round_id: str, seeds_count: int) -> Path:
    out_dir = ROOT / "artifacts" / f"round_{round_id}" / "analysis"
    out_dir.mkdir(parents=True, exist_ok=True)

    summary: dict[str, object] = {
        "round_id": round_id,
        "seeds_count": seeds_count,
        "seed_scores": {},
    }

    for seed_index in range(seeds_count):
        data = api_get(f"/analysis/{round_id}/{seed_index}", auth=True)
        dump_json(out_dir / f"seed_{seed_index}.json", data)
        summary["seed_scores"][str(seed_index)] = data.get("score")

    dump_json(out_dir / "summary.json", summary)
    return out_dir


def main() -> None:
    parser = argparse.ArgumentParser(description="Export Astar round analysis for all seeds.")
    parser.add_argument("--round-id", required=True, help="Round UUID")
    parser.add_argument("--seeds", type=int, default=5, help="Number of seeds to export")
    args = parser.parse_args()

    out_dir = export_round(args.round_id, args.seeds)
    print(
        json.dumps(
            {
                "status": "exported",
                "round_id": args.round_id,
                "seeds": args.seeds,
                "artifact_dir": str(out_dir),
            },
            indent=2,
            ensure_ascii=True,
        )
    )


if __name__ == "__main__":
    main()
