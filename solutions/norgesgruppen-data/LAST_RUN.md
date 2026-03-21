# Final Run Plan — SAHI Tiled Training + Inference

## Current Run: `use_sahi` (validation run)

- **Purpose**: Test if tiled training improves mAP over augmented baseline
- **Config**: YOLOv8L, 50 epochs (stopping at ~15-16), batch 4, imgsz 1280, tiled+augmented data (4256 tiles)
- **Baseline**: `train_aug_v2` — 50 epochs, 496 images, mAP50=0.8144, score=0.8329
- **Results at epoch 8**: mAP50=0.7278 (steep climb), box loss already better than baseline best
- **Stop**: ~epoch 15-16 (~40min from epoch 11, each epoch ~9min)

## Final Run: `use_sahi_full`

```bash
uv run python scripts/train.py --tiled --augmented --model-size l --epochs 30 --imgsz 1280 --batch 4 --val-fraction 0.001 --name use_sahi_full
```

- **Data**: all tiled+augmented images (~4251 train / 5 val)
- **Epochs**: 30 (~4.5h overnight)
- **Rationale**: 30 epochs × 4256 tiles = ~128k image passes. More than enough. Going beyond risks overfitting on overlapping tile content.

## Inference: Tiled (SAHI-style)

`submission/run.py` updated with tiled inference:
1. Images where **both** dims > 1280 are tiled into overlapping 1280x1280 crops (20% overlap)
2. Images where only one dim > 1280 are sent whole (YOLO letterboxes)
3. Detections remapped from tile-local to full-image coordinates
4. Per-class NMS (IoU=0.5) merges duplicates from overlapping tiles
5. TTA disabled (`augment=False`) to stay within 300s sandbox timeout

**Estimated inference time**: ~150-200s for 248 images (within 300s limit)

## Timing test

After stopping `use_sahi`, run on free GPU:
```bash
uv run python submission/run.py --input data/train/images --output /tmp/predictions.json
```

## Monitor command

```bash
uv run python scripts/monitor_training.py --current runs/detect/use_sahi --baseline runs/detect/train_aug_v2
```

## Morning plan

1. Copy `use_sahi_full` best.pt to `submission/best.pt`
2. Run inference timing test
3. Evaluate: `uv run python scripts/evaluate.py --predictions /tmp/predictions.json`
4. If time allows, one more run with tweaked params (overlap, confidence sweep, etc.)
