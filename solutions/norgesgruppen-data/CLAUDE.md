# Challenge 3 — Object Detection (NorgesGruppen)

## Sandbox Constraints
- Python 3.11, NVIDIA L4 24GB, 300s timeout, no network, no `import os`
- Max 420MB uncompressed zip, max 3 weight files
- Entry point: `python run.py --input /data/images --output /output/predictions.json`

## Sandbox Packages (exact versions)
PyTorch 2.6.0+cu124, torchvision 0.21.0+cu124, ultralytics 8.1.0,
onnxruntime-gpu 1.20.0, opencv-python-headless 4.9.0.80, albumentations 1.3.1,
Pillow 10.2.0, numpy 1.26.4, scipy 1.12.0, scikit-learn 1.4.0,
pycocotools 2.0.7, ensemble-boxes 1.0.9, timm 0.9.12, supervision 0.18.0,
safetensors 0.4.2

## Scoring
```
Score = 0.7 × detection_mAP@0.5 + 0.3 × classification_mAP@0.5
```
Detection-only baseline (all `category_id: 0`) caps at 0.70.

## Data Facts (verified)
- 248 training images (~2000×1500px), 22731 annotations
- 356 categories (IDs 0-355), ID 355 = `unknown_product`
- 327 reference products × 7 angles in `individual_samples/`

## torch.load Compatibility
ultralytics 8.1.0 calls `torch.load()` without `weights_only=False`.
torch 2.6.0 defaults `weights_only=True`. Must monkey-patch in run.py:
```python
import functools, torch
torch.load = functools.partial(torch.load, weights_only=False)
```

## Local Eval
```bash
uv run python submission/run.py --input data/train/images --output /tmp/predictions.json
uv run python scripts/evaluate.py --predictions /tmp/predictions.json
```

## Submission
```bash
uv run python scripts/prepare_submission.py --model-size s
# Upload submission.zip to app.ainm.no
```

## Improvement Ways Not To Do

### RGB Channel Manipulation — Investigated, Not Worth Pursuing

The YOLOv8 image pipeline is:
```
Disk (JPEG) → cv2.imread() → BGR uint8
  → HSV augmentation (hsv_h=0.015, hsv_s=0.7, hsv_v=0.4)
  → [::-1] channel flip → RGB float32 (C,H,W)
  → /255.0 uniform scaling → [0.0, 1.0] range
  → Model input (3-ch Conv, pretrained on ImageNet RGB)
```

**Why changing channel handling doesn't help here:**
1. **Pretrained weights expect RGB /255** — changing normalization (e.g. ImageNet mean/std subtraction) or color space (LAB, HSV input) breaks transfer learning, which is the main performance driver on 248 images.
2. **No per-channel normalization is applied** — all channels divided by 255 identically (mean=0, std=1). This is standard for YOLO and matches pretrained weight expectations.
3. **Adding extra input channels** (edge maps, gradients, etc.) would require modifying the first conv layer and losing pretrained weights for that layer — net negative.
4. **HSV augmentation is already enabled** and is the standard approach for color robustness in YOLO.
5. **Reducing `hsv_s`** (from 0.7 to 0.3) was considered to preserve color cues for classification, but the augmented-data approach is a better lever for classification improvement.

## Next Steps

### Done

1. **Run 1 — Baseline YOLOv8L** (50 epochs, original 248 images): val mAP50=0.646, score=0.7039
2. **Inference tweaks** (`conf=0.01`, TTA `augment=True`, `max_det=1000`): score 0.7039 → **0.7175**
3. **Copy-paste augmentation script** (`scripts/augment_copypaste.py`): GrabCut foreground extraction from 320 individual product images, inverse-frequency sampling for rare categories, 248 synthetic images with 10 pastes each
4. **Run 2 — Augmented training** (50 epochs, 496 images): val mAP50=0.799, cls_loss=0.726 — large improvement over Run 1. Score=**0.8329**.
5. **RGB channel investigation**: concluded not worth changing (see above)

### To Do Next (priority order)

1. **Evaluate Run 2** — copy `runs/detect/train_aug/weights/best.pt` to `submission/best.pt`, run local eval, compare score to Run 1
2. **Train longer (100-150 epochs)** — both Run 1 and Run 2 were still improving at epoch 50. Training longer is the easiest next gain. Use the augmented dataset.
3. **Full-data retrain** — once best hyperparams are found, retrain on all 248 original images (val_fraction=0.0) + augmented images. Gives ~20% more real training data.
4. **Try YOLOv8X** — larger model, more parameters for 356-class classification. May need batch=2 at 1280px to fit in 24GB VRAM.
5. **More augmented images** — current run uses 248 synthetic images with 10 pastes. Could increase to 500+ synthetic images or 15-20 pastes per image to further boost rare categories.
6. **Augmentation tuning** — try `mixup=0.15`, `copy_paste=0.1` (YOLO's built-in), reduce `scale` from 0.5 to 0.3 to preserve small products.
7. **Color histogram post-processing** — use individual product reference images to re-rank/correct classification predictions by color similarity between detected crops and reference images. Acts as a classification refinement layer on top of YOLO output.
8. **Confidence threshold sweep** — systematic sweep of inference `conf` (0.001, 0.005, 0.01, 0.05) to find optimal value for the eval metric.
