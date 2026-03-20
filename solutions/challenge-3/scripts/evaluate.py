"""
Local evaluation script for Challenge 3.

Runs the model on training images, then computes:
  - Detection mAP@0.5 (useCats=0) — worth 0.7
  - Classification mAP@0.5 (useCats=1) — worth 0.3
  - Weighted score

Usage:
    python scripts/evaluate.py [--model-size s] [--confidence 0.25] [--imgsz 1280]
"""

import argparse
import json
import subprocess
import sys
from pathlib import Path

import numpy as np
from pycocotools.coco import COCO
from pycocotools.cocoeval import COCOeval


def run_model(
    input_dir: Path,
    output_path: Path,
    model_size: str,
    confidence: float,
    imgsz: int,
) -> None:
    """Run submission/run.py as a subprocess."""
    run_py = Path(__file__).resolve().parent.parent / "submission" / "run.py"
    cmd = [
        sys.executable, str(run_py),
        "--input", str(input_dir),
        "--output", str(output_path),
        "--model-size", model_size,
        "--confidence", str(confidence),
        "--imgsz", str(imgsz),
    ]
    print(f"Running: {' '.join(cmd)}")
    subprocess.run(cmd, check=True)


def compute_map_at_iou(coco_gt, coco_dt, use_cats: int, iou_thr: float = 0.5) -> float:
    """Compute mAP at a single IoU threshold using COCOeval.

    We keep the default iouThrs array so summarize() works, then extract
    the mAP@0.5 value (index 1 in the 12-element stats array).
    """
    coco_eval = COCOeval(coco_gt, coco_dt, "bbox")
    coco_eval.params.useCats = use_cats
    coco_eval.evaluate()
    coco_eval.accumulate()
    coco_eval.summarize()
    # stats[1] = AP @ IoU=0.50
    return float(coco_eval.stats[1])


def evaluate_predictions(annotations_path: Path, predictions_path: Path) -> dict:
    """Compute detection and classification mAP@0.5."""
    coco_gt = COCO(str(annotations_path))

    predictions = json.loads(predictions_path.read_text())
    if not predictions:
        print("No predictions found!")
        return {"detection_map": 0.0, "classification_map": 0.0, "weighted_score": 0.0}

    coco_dt = coco_gt.loadRes(predictions)

    results = {}

    # Detection mAP (useCats=0 — ignores category labels)
    print("\n--- Detection mAP (category-agnostic) ---")
    results["detection_map"] = compute_map_at_iou(coco_gt, coco_dt, use_cats=0)

    # Classification mAP (useCats=1 — requires correct category)
    print("\n--- Classification mAP (category-aware) ---")
    results["classification_map"] = compute_map_at_iou(coco_gt, coco_dt, use_cats=1)

    # Weighted score
    results["weighted_score"] = (
        0.7 * results["detection_map"] + 0.3 * results["classification_map"]
    )

    return results


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate Challenge 3 model locally")
    parser.add_argument("--model-size", type=str, default="s", choices=["n", "s", "m", "l", "x"])
    parser.add_argument("--confidence", type=float, default=0.25)
    parser.add_argument("--imgsz", type=int, default=1280)
    parser.add_argument("--predictions", type=str, default=None,
                        help="Path to existing predictions.json (skip inference)")
    args = parser.parse_args()

    project_dir = Path(__file__).resolve().parent.parent
    annotations_path = project_dir / "data" / "train" / "annotations.json"
    images_dir = project_dir / "data" / "train" / "images"

    if not annotations_path.exists():
        print(f"ERROR: Annotations not found at {annotations_path}", file=sys.stderr)
        sys.exit(1)

    if args.predictions:
        predictions_path = Path(args.predictions)
    else:
        # Run inference to temp file
        predictions_path = project_dir / "predictions.json"
        run_model(images_dir, predictions_path, args.model_size, args.confidence, args.imgsz)

    results = evaluate_predictions(annotations_path, predictions_path)

    print("\n" + "=" * 50)
    print(f"Detection mAP@0.5:       {results['detection_map']:.4f}")
    print(f"Classification mAP@0.5:  {results['classification_map']:.4f}")
    print(f"Weighted Score:          {results['weighted_score']:.4f}")
    print("=" * 50)


if __name__ == "__main__":
    main()
