"""
Challenge 3 — Object Detection inference script.

Runs YOLOv8 on grocery shelf images and outputs COCO-format predictions.
Phase 1: detection only, all category_id=0.

Usage:
    python run.py --input /data/images --output /output/predictions.json
"""

import argparse
import functools
import json
from pathlib import Path

import torch

# ultralytics 8.1.0 calls torch.load() without weights_only=False,
# but torch 2.6.0 defaults weights_only=True. Patch to restore compat.
_original_torch_load = torch.load
torch.load = functools.partial(_original_torch_load, weights_only=False)

from ultralytics import YOLO


def parse_image_id(filename: str) -> int:
    """Extract numeric image_id from filename like img_00042.jpg -> 42."""
    stem = Path(filename).stem
    # Remove 'img_' prefix and parse as int
    return int(stem.replace("img_", ""))


def run_inference(
    input_dir: Path,
    output_path: Path,
    confidence: float = 0.25,
    imgsz: int = 1280,
) -> None:
    """Run YOLOv8 on all images in input_dir, write COCO predictions."""
    # Load model from same directory as this script
    script_dir = Path(__file__).resolve().parent
    model_path = script_dir / "best.pt"

    if not model_path.exists():
        raise FileNotFoundError(f"Model not found at {model_path}")

    model = YOLO(str(model_path))

    # Collect image paths
    image_extensions = {".jpg", ".jpeg", ".png", ".bmp", ".tiff"}
    image_paths = sorted(
        p for p in input_dir.iterdir()
        if p.suffix.lower() in image_extensions
    )

    if not image_paths:
        print(f"WARNING: No images found in {input_dir}")
        output_path.write_text(json.dumps([]))
        return

    print(f"Running inference on {len(image_paths)} images with best.pt")

    predictions = []

    for img_path in image_paths:
        image_id = parse_image_id(img_path.name)

        results = model.predict(
            source=str(img_path),
            conf=confidence,
            imgsz=imgsz,
            verbose=False,
        )

        for result in results:
            boxes = result.boxes
            if boxes is None or len(boxes) == 0:
                continue

            for i in range(len(boxes)):
                # Get xyxy and convert to COCO [x, y, w, h]
                x1, y1, x2, y2 = boxes.xyxy[i].tolist()
                w = x2 - x1
                h = y2 - y1

                predictions.append({
                    "image_id": image_id,
                    "category_id": int(boxes.cls[i]),
                    "bbox": [round(x1, 2), round(y1, 2), round(w, 2), round(h, 2)],
                    "score": round(float(boxes.conf[i]), 4),
                })

    # Write output
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(predictions, indent=2))
    print(f"Wrote {len(predictions)} predictions to {output_path}")


def main() -> None:
    parser = argparse.ArgumentParser(description="YOLOv8 grocery shelf detection")
    parser.add_argument("--input", type=str, required=True, help="Input image directory")
    parser.add_argument("--output", type=str, required=True, help="Output predictions JSON path")
    parser.add_argument("--confidence", type=float, default=0.25, help="Confidence threshold")
    parser.add_argument("--imgsz", type=int, default=1280, help="Inference image size")
    args = parser.parse_args()

    run_inference(
        input_dir=Path(args.input),
        output_path=Path(args.output),
        confidence=args.confidence,
        imgsz=args.imgsz,
    )


if __name__ == "__main__":
    main()
