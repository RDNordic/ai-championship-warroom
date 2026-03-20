# Challenge 3 — NorgesGruppen Data: Object Detection

**Sponsor:** NorgesGruppen Data
**Status:** In progress
**Owner:** Chris (training/modelling) — all team members review before each submission

---

## What We're Building

Train an object detection model on Norwegian grocery shelf images, package it into a `.zip`, and upload it. Their server runs it on a GPU and scores the output. No hosted endpoint — upload-once model inference.

---

## The Dataset

| | |
|---|---|
| **Training images** | 254 shelf JPEG images (~2000×1500px) |
| **Annotations** | ~22,300 bounding boxes, COCO format |
| **Categories** | 357 product classes (IDs 0–356); `id: 356` = `unknown_product` |
| **Store sections** | Egg, Frokost, Knekkebrod, Varmedrikker |
| **Annotation file** | `annotations.json` — COCO format, `bbox` = [x, y, w, h] |
| **COCO dataset zip** | `NM_NGD_coco_dataset.zip` ~864 MB |
| **Product reference images** | `NM_NGD_product_images.zip` ~60 MB — 327 products, 7 angles each |

Download both from the **Submit** page at `app.ainm.no` (login required). Do this immediately.

### Product Reference Images

327 products × 7 angles (main, front, back, left, right, top, bottom) = 2,289 images.
Organised by barcode: `{product_code}/main.jpg`
Includes `metadata.json` with product names and annotation counts.

These are a competitive advantage for classification. Most teams will ignore them.

---

## Scoring

```
Score = 0.7 × detection_mAP@0.5  +  0.3 × classification_mAP@0.5
```

| Component | What it checks | Weight |
|---|---|---|
| **Detection mAP@0.5** | Did you find the product? IoU ≥ 0.5, category ignored | 70% |
| **Classification mAP@0.5** | IoU ≥ 0.5 AND correct `category_id` | 30% |

- Score range: **0.0 – 1.0**
- Detection-only baseline (all `category_id: 0`) scores up to **0.70**
- Public leaderboard = public test set. Final ranking = private test set (never revealed). Don't over-fit to the public score.

---

## The Critical Constraint: 3 Submissions Per Day

| Limit | Value |
|---|---|
| Submissions in-flight | 2 per team |
| **Submissions per day** | **3 per team** |
| Infrastructure failure freebies | 2/day (don't count against limit) |
| Reset | Midnight UTC |

With ~3 competition days, we have roughly **9 real submissions total**. Every upload must be deliberate. **Local eval is mandatory before any submission** — treat each upload like a production deploy.

---

## Submission Contract

Script executed as:
```bash
python run.py --input /data/images --output /output/predictions.json
```

### Output Format

```json
[
  {
    "image_id": 42,
    "category_id": 15,
    "bbox": [120.5, 45.0, 80.0, 110.0],
    "score": 0.923
  }
]
```

| Field | Type | Description |
|---|---|---|
| `image_id` | int | Numeric ID from filename: `img_00042.jpg` → `42` |
| `category_id` | int | Product class ID 0–356 from `annotations.json` |
| `bbox` | [x, y, w, h] | Bounding box in COCO pixel format |
| `score` | float | Confidence 0–1 |

---

## Zip Structure & Limits

```
submission.zip
├── run.py              ← MUST be at root (not in a subfolder — most common error)
├── model.pt            ← weights
└── utils.py            ← optional helpers
```

| Limit | Value |
|---|---|
| Max zip (uncompressed) | 420 MB |
| Max weight files | 3 |
| Max weight total | 420 MB |
| Max Python files | 10 |
| Allowed weight formats | `.pt` `.pth` `.onnx` `.safetensors` `.npy` |
| Allowed code formats | `.py` `.json` `.yaml` `.yml` `.cfg` |

**Verify the zip before uploading:**
```bash
unzip -l submission.zip | head -10
# Must show run.py at root, not inside a subfolder
```

**Windows (PowerShell):**
```powershell
cd my_submission
Compress-Archive -Path .\* -DestinationPath ..\submission.zip
```

Do NOT use right-click → Compress — it nests files in a subfolder.

---

## Sandbox Environment

| Resource | Value |
|---|---|
| **GPU** | NVIDIA L4, 24 GB VRAM |
| CUDA | 12.4 |
| Python | 3.11 |
| CPU | 4 vCPU |
| RAM | 8 GB system |
| Network | **None — fully offline** |
| Timeout | **300 seconds** |

**KO's RTX 5090 Mobile = 24 GB VRAM** — same VRAM as the sandbox L4. Local benchmarks are directly representative of sandbox performance. No surprises.

### Pre-installed Packages (use without bundling)

| Package | Version |
|---|---|
| ultralytics | 8.1.0 |
| torch | 2.6.0+cu124 |
| torchvision | 0.21.0+cu124 |
| onnxruntime-gpu | 1.20.0 |
| opencv-python-headless | 4.9.0.80 |
| albumentations | 1.3.1 |
| timm | 0.9.12 |
| ensemble-boxes | 1.0.9 |
| pycocotools | 2.0.7 |
| Pillow | 10.2.0 |
| numpy | 1.26.4 |
| scipy | 1.12.0 |
| scikit-learn | 1.4.0 |
| safetensors | 0.4.2 |
| supervision | 0.18.0 |

No `pip install` at runtime — everything must be bundled or pre-installed above.

### Security Restrictions (Code Scanner)

These will cause rejection:
- `import os` → use `pathlib` instead
- `import subprocess`, `import socket`, `import ctypes`, `import builtins`
- `eval()`, `exec()`, `compile()`, `__import__()`

---

## Version Pinning (Mismatch = Silent Load Failure)

| Train with | Sandbox has | Risk if mismatched |
|---|---|---|
| `ultralytics==8.1.0` | 8.1.0 | 8.2+ changes model class → load fails |
| `torch==2.6.0` | 2.6.0 | 2.7+ full-model save may fail |
| `timm==0.9.12` | 0.9.12 | 1.0+ layer names changed → load fails |
| ONNX opset ≤ 20 | onnxruntime 1.20.0 | opset 21+ not supported |

**Safest path: export to ONNX.** Universal, version-independent, GPU-accelerated via CUDAExecutionProvider.

---

## Training Setup (KO's Machine)

```bash
# Match sandbox versions exactly
pip install ultralytics==8.1.0
pip install torch==2.6.0 torchvision==0.21.0 --index-url https://download.pytorch.org/whl/cu124
```

### Dataset YAML

```yaml
# norgesgruppen.yaml
path: /path/to/NM_NGD_coco_dataset
train: images/train
val: images/val
nc: 357
names:
  0: VESTLANDSLEFSA TØRRE 10STK 360G
  1: COFFEE MATE 180G NESTLE
  # ... (generate from annotations.json categories)
  356: unknown_product
```

### Train YOLOv8m

```bash
yolo detect train \
  data=norgesgruppen.yaml \
  model=yolov8m.pt \
  epochs=50 \
  imgsz=640 \
  batch=16 \
  seed=42
```

### Weight Export

```python
# Option A: state_dict (ultralytics 8.1.0 only)
torch.save(model.state_dict(), "model.pt")

# Option B: ONNX FP16 (recommended — universal)
model.export(format="onnx", opset=17, half=True)
# Use CUDAExecutionProvider in run.py
```

FP16 is recommended for L4: faster inference and smaller file size.

---

## Model Strategy

### Phase 1 — Detection-only baseline (submission 1, score target: 0.60–0.70)

- Use pretrained YOLOv8s/m, no fine-tuning
- Set all `category_id: 0` in output
- Validate locally first with pycocotools
- Establishes a real leaderboard score with zero training cost

### Phase 2 — Fine-tuned full model (submission 2–3, score target: 0.75–0.88)

- Fine-tune YOLOv8m (or YOLOv8l if VRAM permits) on their COCO data, `nc=357`
- Full classification head outputs correct `category_id`
- Local eval both mAPs separately before upload
- Export ONNX FP16

### Phase 3 — Reference image boost (submission 4+, score target: 0.88+)

- 327 products × 7 angles — augment training data with reference images
- Or: use as a template/few-shot classifier on top of YOLOv8 detections
- Investigate whether any product IDs in reference images align with annotation `product_code` field

---

## Local Evaluation (Mandatory Before Every Submission)

```python
from pycocotools.coco import COCO
from pycocotools.cocoeval import COCOeval
import json

coco_gt = COCO("annotations.json")
coco_dt = coco_gt.loadRes("predictions.json")

# Detection mAP (category ignored)
eval_det = COCOeval(coco_gt, coco_dt, "bbox")
eval_det.params.useCats = 0
eval_det.evaluate()
eval_det.accumulate()
eval_det.summarize()
det_map = eval_det.stats[0]

# Classification mAP (category must match)
eval_cls = COCOeval(coco_gt, coco_dt, "bbox")
eval_cls.params.useCats = 1
eval_cls.evaluate()
eval_cls.accumulate()
eval_cls.summarize()
cls_map = eval_cls.stats[0]

final_score = 0.7 * det_map + 0.3 * cls_map
print(f"Detection mAP: {det_map:.4f}")
print(f"Classification mAP: {cls_map:.4f}")
print(f"Final score: {final_score:.4f}")
```

---

## run.py Template

```python
import argparse
import json
from pathlib import Path

import torch
import numpy as np
from ultralytics import YOLO

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    input_dir = Path(args.input)
    output_path = Path(args.output)

    model = YOLO("model.pt")  # or load ONNX via onnxruntime
    device = "cuda" if torch.cuda.is_available() else "cpu"

    predictions = []
    for img_path in sorted(input_dir.glob("*.jpg")):
        # Parse image_id from filename: img_00042.jpg → 42
        image_id = int(img_path.stem.split("_")[1])

        results = model(str(img_path), device=device, verbose=False)
        for result in results:
            for box in result.boxes:
                x1, y1, x2, y2 = box.xyxy[0].tolist()
                w, h = x2 - x1, y2 - y1
                predictions.append({
                    "image_id": image_id,
                    "category_id": int(box.cls[0]),
                    "bbox": [x1, y1, w, h],
                    "score": float(box.conf[0]),
                })

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(predictions))

if __name__ == "__main__":
    main()
```

---

## Strategy Notes

1. **3 subs/day is the binding constraint** — treat every submission like a production deploy. Local eval first, always.
2. **Detection-only first** — gets up to 0.70 score with no training risk. De-risks day 1.
3. **YOLOv8 is the path of least resistance** — pre-installed at 8.1.0, no ONNX conversion needed for straightforward workflow.
4. **Reference images are underexploited** — 7-angle product photos. Most teams won't use them.
5. **KO's GPU matches sandbox exactly** — 24GB VRAM on both. Benchmark inference time locally; if it runs in <300s on KO's machine it'll pass the sandbox timeout.
6. **254 images is small** — 80/20 split = 203 train / 51 val. Use aggressive augmentation. Consider cross-validation.
7. **Private test set divergence** — don't sacrifice generalisation chasing public leaderboard decimal points.
8. **FP16 everywhere** — faster on L4, smaller weights, stays under 420 MB.

---

## Training Runs

### Run Summary Table

| Run | Model | Data | Epochs | Val mAP50 | Val cls_loss | Det mAP@0.5 | Cls mAP@0.5 | **Score** | Still improving? |
|-----|-------|------|--------|-----------|-------------|-------------|-------------|-----------|------------------|
| 1 — Baseline | YOLOv8L | Original (248 img) | 50 | 0.646 | 1.002 | 0.781 | 0.570 | **0.7175** | Yes |
| 2 — Augmented | YOLOv8L | Augmented (496 img) | 50 | 0.799 | 0.726 | — | — | **0.8329** | Yes |

> Scores in the table use inference tweaks: `conf=0.01`, `augment=True` (TTA), `max_det=1000`.
> Run 1 baseline without inference tweaks scored 0.7039.

### Run 1 — Baseline (2026-03-20)

- **Config:** YOLOv8L, 50 epochs, batch 4, imgsz 1280, original 248 images (80/20 split)
- **Final val metrics:** mAP50=0.646, mAP50-95=0.446, cls_loss=1.002
- **Local eval (with inference tweaks):** det_mAP=0.781, cls_mAP=0.570, score=**0.7175**
- **Observation:** Model still improving at epoch 50 — losses and mAP both trending favourably
- **Weights:** `runs/detect/train/weights/best.pt`

```bash
uv run python scripts/train.py --model-size l --epochs 50 --batch 4 --imgsz 1280
```

### Run 2 — Copy-Paste Augmented (2026-03-20)

- **Config:** YOLOv8L, 50 epochs, batch 4, imgsz 1280, augmented 496 images (248 original + 248 synthetic)
- **Final val metrics:** mAP50=0.799, mAP50-95=0.594, cls_loss=0.726
- **Local eval (with inference tweaks):** score=**0.8329**
- **Observation:** Significant improvement over Run 1 on all val metrics. cls_loss dropped from 1.002 to 0.726 (+27%), mAP50 jumped from 0.646 to 0.799 (+24%). Model still improving at epoch 50.
- **Weights:** `runs/detect/train_aug/weights/best.pt`

**What changed from Run 1:**
- Added offline copy-paste augmentation using 320 individual product reference images (from `data/individ/`)
- GrabCut foreground extraction + alpha-blended pasting onto shelf images
- Inverse-frequency sampling: rare categories (74 with <5 annotations) pasted more often
- 10 products pasted per augmented image, sized to match real annotation bbox distribution

```bash
# Step 1: Generate augmented data
uv run python scripts/augment_copypaste.py --num-augmented 248 --pastes-per-image 10

# Step 2: Train on augmented data
uv run python scripts/train.py --augmented --model-size l --epochs 50 --batch 4 --imgsz 1280 --name train_aug
```

### Inference Tweaks (applied to all runs at eval time)

Applied in `submission/run.py`, these improved Run 1 from 0.7039 to 0.7175:

| Tweak | Before | After | Effect |
|-------|--------|-------|--------|
| `conf` | 0.25 | 0.01 | Let COCOeval do its own thresholding — main driver of improvement |
| `augment` (TTA) | False | True | Multi-scale + flip inference ensemble — small cls boost |
| `max_det` | 300 | 1000 | Handle dense shelves (avg 92 products/image, max 235) |

---

## Open Questions

- [ ] **Who downloads the data?** Needs `app.ainm.no` login. ~924 MB total. Do this now.
- [ ] Are product reference images allowed as additional training data? (Check competition rules.)
- [ ] How many test images are there? Need to benchmark inference time locally to avoid timeout.
- [ ] Train/val split strategy — random split or stratified by section (Egg/Frokost/Knekkebrod/Varmedrikker)?
