"""
Challenge 3 — Object Detection inference script.

Runs YOLOv8 on grocery shelf images and outputs COCO-format predictions.
Post-processing: uses store-section priors to penalize misclassified predictions.

Usage:
    python run.py --input /data/images --output /output/predictions.json
"""

import argparse
import functools
import json
from collections import Counter
from pathlib import Path

import torch

# ultralytics 8.1.0 calls torch.load() without weights_only=False,
# but torch 2.6.0 defaults weights_only=True. Patch to restore compat.
_original_torch_load = torch.load
torch.load = functools.partial(_original_torch_load, weights_only=False)

from ultralytics import YOLO

# ---------------------------------------------------------------------------
# Store-section mapping derived from training data co-occurrence analysis.
# 4 sections: 1=Knekkebrød, 2=Frokost, 3=Egg, 4=Varmedrikker
# Each category belongs to one or more sections. 343/356 are single-section.
# ---------------------------------------------------------------------------
SECTION_CATS = {
    1: {0, 2, 3, 5, 8, 11, 12, 13, 17, 21, 26, 29, 33, 36, 38, 39, 42, 44, 52, 53, 57, 59, 60, 62, 66, 68, 69, 70, 73, 76, 82, 84, 86, 91, 92, 96, 97, 101, 109, 113, 120, 123, 131, 132, 140, 143, 149, 150, 152, 154, 157, 158, 166, 170, 183, 188, 204, 207, 208, 209, 212, 217, 221, 223, 226, 227, 228, 230, 231, 233, 234, 235, 236, 239, 241, 242, 243, 244, 246, 250, 251, 257, 258, 264, 265, 270, 271, 274, 276, 278, 279, 280, 284, 290, 291, 293, 294, 296, 300, 303, 307, 311, 315, 316, 317, 321, 323, 327, 328, 329, 331, 333, 335, 338, 343, 345, 346, 349, 354, 355},
    2: {7, 14, 15, 22, 23, 29, 30, 34, 35, 36, 47, 50, 53, 61, 75, 78, 85, 90, 93, 94, 97, 108, 116, 117, 121, 129, 130, 145, 148, 156, 161, 162, 164, 170, 180, 181, 186, 187, 191, 194, 197, 201, 205, 211, 214, 218, 221, 223, 231, 240, 260, 261, 262, 263, 264, 268, 277, 289, 303, 305, 308, 315, 328, 330, 336, 342, 355},
    3: {4, 6, 10, 18, 41, 43, 48, 51, 67, 72, 79, 80, 88, 95, 102, 104, 105, 110, 119, 128, 135, 138, 139, 155, 159, 163, 168, 175, 176, 185, 193, 195, 213, 216, 220, 224, 232, 237, 253, 254, 267, 269, 273, 275, 283, 285, 286, 288, 295, 301, 302, 312, 313, 318, 322, 326, 351},
    4: {1, 9, 16, 19, 20, 24, 25, 27, 28, 31, 32, 37, 40, 45, 46, 49, 54, 55, 56, 58, 63, 64, 65, 71, 74, 77, 81, 83, 87, 89, 98, 99, 100, 103, 106, 107, 111, 112, 114, 115, 118, 122, 124, 125, 126, 127, 133, 134, 136, 137, 141, 142, 144, 146, 147, 151, 153, 160, 165, 167, 169, 171, 172, 173, 174, 177, 178, 179, 182, 184, 189, 190, 192, 196, 198, 199, 200, 202, 203, 206, 210, 215, 219, 222, 225, 229, 238, 245, 247, 248, 249, 252, 255, 256, 259, 266, 272, 281, 282, 287, 292, 297, 298, 299, 304, 306, 309, 310, 314, 319, 320, 324, 325, 332, 334, 337, 339, 340, 341, 344, 347, 348, 350, 352, 353, 355},
}

CAT_SECTION = {
    0: 1, 1: 4, 2: 1, 3: 1, 4: 3, 5: 1, 6: 3, 7: 2, 8: 1, 9: 4,
    10: 3, 11: 1, 12: 1, 13: 1, 14: 2, 15: 2, 16: 4, 17: 1, 18: 3, 19: 4,
    20: 4, 21: 1, 22: 2, 23: 2, 24: 4, 25: 4, 26: 1, 27: 4, 28: 4, 29: [1, 2],
    30: 2, 31: 4, 32: 4, 33: 1, 34: 2, 35: 2, 36: [1, 2], 37: 4, 38: 1, 39: 1,
    40: 4, 41: 3, 42: 1, 43: 3, 44: 1, 45: 4, 46: 4, 47: 2, 48: 3, 49: 4,
    50: 2, 51: 3, 52: 1, 53: [1, 2], 54: 4, 55: 4, 56: 4, 57: 1, 58: 4, 59: 1,
    60: 1, 61: 2, 62: 1, 63: 4, 64: 4, 65: 4, 66: 1, 67: 3, 68: 1, 69: 1,
    70: 1, 71: 4, 72: 3, 73: 1, 74: 4, 75: 2, 76: 1, 77: 4, 78: 2, 79: 3,
    80: 3, 81: 4, 82: 1, 83: 4, 84: 1, 85: 2, 86: 1, 87: 4, 88: 3, 89: 4,
    90: 2, 91: 1, 92: 1, 93: 2, 94: 2, 95: 3, 96: 1, 97: [1, 2], 98: 4, 99: 4,
    100: 4, 101: 1, 102: 3, 103: 4, 104: 3, 105: 3, 106: 4, 107: 4, 108: 2, 109: 1,
    110: 3, 111: 4, 112: 4, 113: 1, 114: 4, 115: 4, 116: 2, 117: 2, 118: 4, 119: 3,
    120: 1, 121: 2, 122: 4, 123: 1, 124: 4, 125: 4, 126: 4, 127: 4, 128: 3, 129: 2,
    130: 2, 131: 1, 132: 1, 133: 4, 134: 4, 135: 3, 136: 4, 137: 4, 138: 3, 139: 3,
    140: 1, 141: 4, 142: 4, 143: 1, 144: 4, 145: 2, 146: 4, 147: 4, 148: 2, 149: 1,
    150: 1, 151: 4, 152: 1, 153: 4, 154: 1, 155: 3, 156: 2, 157: 1, 158: 1, 159: 3,
    160: 4, 161: 2, 162: 2, 163: 3, 164: 2, 165: 4, 166: 1, 167: 4, 168: 3, 169: 4,
    170: [1, 2], 171: 4, 172: 4, 173: 4, 174: 4, 175: 3, 176: 3, 177: 4, 178: 4, 179: 4,
    180: 2, 181: 2, 182: 4, 183: 1, 184: 4, 185: 3, 186: 2, 187: 2, 188: 1, 189: 4,
    190: 4, 191: 2, 192: 4, 193: 3, 194: 2, 195: 3, 196: 4, 197: 2, 198: 4, 199: 4,
    200: 4, 201: 2, 202: 4, 203: 4, 204: 1, 205: 2, 206: 4, 207: 1, 208: 1, 209: 1,
    210: 4, 211: 2, 212: 1, 213: 3, 214: 2, 215: 4, 216: 3, 217: 1, 218: 2, 219: 4,
    220: 3, 221: [1, 2], 222: 4, 223: [1, 2], 224: 3, 225: 4, 226: 1, 227: 1, 228: 1, 229: 4,
    230: 1, 231: [1, 2], 232: 3, 233: 1, 234: 1, 235: 1, 236: 1, 237: 3, 238: 4, 239: 1,
    240: 2, 241: 1, 242: 1, 243: 1, 244: 1, 245: 4, 246: 1, 247: 4, 248: 4, 249: 4,
    250: 1, 251: 1, 252: 4, 253: 3, 254: 3, 255: 4, 256: 4, 257: 1, 258: 1, 259: 4,
    260: 2, 261: 2, 262: 2, 263: 2, 264: [1, 2], 265: 1, 266: 4, 267: 3, 268: 2, 269: 3,
    270: 1, 271: 1, 272: 4, 273: 3, 274: 1, 275: 3, 276: 1, 277: 2, 278: 1, 279: 1,
    280: 1, 281: 4, 282: 4, 283: 3, 284: 1, 285: 3, 286: 3, 287: 4, 288: 3, 289: 2,
    290: 1, 291: 1, 292: 4, 293: 1, 294: 1, 295: 3, 296: 1, 297: 4, 298: 4, 299: 4,
    300: 1, 301: 3, 302: 3, 303: [1, 2], 304: 4, 305: 2, 306: 4, 307: 1, 308: 2, 309: 4,
    310: 4, 311: 1, 312: 3, 313: 3, 314: 4, 315: [1, 2], 316: 1, 317: 1, 318: 3, 319: 4,
    320: 4, 321: 1, 322: 3, 323: 1, 324: 4, 325: 4, 326: 3, 327: 1, 328: [1, 2], 329: 1,
    330: 2, 331: 1, 332: 4, 333: 1, 334: 4, 335: 1, 336: 2, 337: 4, 338: 1, 339: 4,
    340: 4, 341: 4, 342: 2, 343: 1, 344: 4, 345: 1, 346: 1, 347: 4, 348: 4, 349: 1,
    350: 4, 351: 3, 352: 4, 353: 4, 354: 1, 355: [1, 2, 4],
}

SECTION_MISMATCH_PENALTY = 0.15
SECTION_VOTE_CONF = 0.3
SECTION_MIN_DOMINANCE = 0.6


def _get_cat_sections(cat_id):
    s = CAT_SECTION.get(cat_id)
    if s is None:
        return {1, 2, 3, 4}
    if isinstance(s, list):
        return set(s)
    return {s}


def _detect_image_section(preds):
    section_scores = Counter()
    total_score = 0.0
    for p in preds:
        if p["score"] < SECTION_VOTE_CONF:
            continue
        for s in _get_cat_sections(p["category_id"]):
            section_scores[s] += p["score"]
            total_score += p["score"]
    if not section_scores or total_score == 0:
        return None
    best_section, best_score = section_scores.most_common(1)[0]
    if best_score / total_score < SECTION_MIN_DOMINANCE:
        return None
    return best_section


def apply_section_prior(predictions):
    by_image = {}
    for p in predictions:
        by_image.setdefault(p["image_id"], []).append(p)

    corrected = []
    total_penalized = 0
    images_with_section = 0
    for image_id, preds in by_image.items():
        section = _detect_image_section(preds)
        if section is None:
            corrected.extend(preds)
            continue

        images_with_section += 1
        allowed_cats = SECTION_CATS[section]
        for p in preds:
            if p["category_id"] not in allowed_cats and p["score"] < 0.3:
                p["score"] = round(p["score"] * SECTION_MISMATCH_PENALTY, 4)
                total_penalized += 1
            corrected.append(p)

    print(f"Section prior: {images_with_section}/{len(by_image)} images assigned a section, "
          f"penalized {total_penalized}/{len(predictions)} predictions")
    return corrected


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
            max_det=1000,
            augment=True,
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

    # Apply store-section prior to penalize cross-section misclassifications
    predictions = apply_section_prior(predictions)

    # Write output
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(predictions, indent=2))
    print(f"Wrote {len(predictions)} predictions to {output_path}")


def main() -> None:
    parser = argparse.ArgumentParser(description="YOLOv8 grocery shelf detection")
    parser.add_argument("--input", type=str, required=True, help="Input image directory")
    parser.add_argument("--output", type=str, required=True, help="Output predictions JSON path")
    parser.add_argument("--confidence", type=float, default=0.01, help="Confidence threshold")
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
