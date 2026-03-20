# NorgesGruppen Data — Object Detection Submission

## Entry Point

```bash
python run.py --input /data/images --output /output/predictions.json
```

## Model

- **Weights:** `best.pt` (YOLOv8, ~85 MB)
- **Inference size:** 1280px
- **Confidence threshold:** 0.25

## Output Format

COCO-format JSON array:

```json
[{"image_id": 42, "category_id": 7, "bbox": [x, y, w, h], "score": 0.91}]
```

- `image_id`: extracted from filename (`img_00042.jpg` -> `42`)
- `category_id`: model-predicted class (0-355)
- `bbox`: COCO format [x, y, width, height]
- `score`: confidence (0-1)

## Compliance Check (2026-03-20)

| Rule | Status |
|------|--------|
| `run.py` at zip root | PASS |
| Entry point `--input` / `--output` | PASS |
| Output JSON format | PASS |
| No blocked imports (`sys`, `os`, `subprocess`, etc.) | PASS |
| Uses `pathlib` (not `os`) | PASS |
| No `eval`/`exec`/`__import__` | PASS |
| Max 10 .py files | PASS (1) |
| Max 3 weight files | PASS (1: best.pt) |
| Max 420 MB uncompressed | PASS (~85 MB) |
| Allowed file types only (.py, .pt) | PASS |
| COCO bbox [x, y, w, h] | PASS |
| category_id from model prediction | PASS |

## Scoring

```
Score = 0.7 x detection_mAP@0.5 + 0.3 x classification_mAP@0.5
```

## Build Submission

```bash
uv run python scripts/prepare_submission.py
```
