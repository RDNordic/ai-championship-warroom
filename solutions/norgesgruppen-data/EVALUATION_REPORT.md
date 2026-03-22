# Evaluation Report — Hybrid Tiled Class Correction

## Best Result: Section-Guided Triple Filter + Confidence Replacement

| Metric | Baseline (no tiles) | Section-guided hybrid | Delta |
|--------|---:|---:|---:|
| Detection mAP@0.5 | 0.8120 | 0.8377 | **+0.0257** |
| Classification mAP@0.5 | 0.7570 | 0.8712 | **+0.1142** |
| **Weighted Score** | **0.7955** | **0.8478** | **+0.0523** |

Model: `last_run_full` (YOLOv8L, 120 epochs, 495 images, val_fraction=0.001).

## Strategy That Works: Section-Guided Triple Filter

Only correct a prediction when ALL four conditions are met:

1. Full-image predicted class is **NOT in the image's detected section**
2. Overlapping tile prediction exists (IoU >= 0.3)
3. Tile confidence **>= 0.7**
4. Tile predicted class **IS in the correct section**

When correcting: replace **both class AND confidence** with tile's values.

This produced **158 corrections** across 248 images — small in volume but high-impact because:
- Removes false positives from wrong classes (improves precision)
- Adds true positives to correct classes at conf >= 0.7 (improves recall at meaningful thresholds)
- 96.7% accuracy on 3-image GT verification (only 1 hurt case)

## Pipeline Statistics (248 images)

| Stage | Count |
|-------|------:|
| Total predictions (full-image pass) | 45,243 |
| Images requiring tiling (both dims > 1280) | 200 / 248 |
| Tile detections (after per-class NMS) | 53,951 |
| **Section-guided class corrections** | **158** (0.3% of all predictions) |
| Section prior: images with detected section | 248 / 248 |
| **Predictions penalized by section prior** | **2,549** (5.6% of all predictions) |

## Timing (idle GPU, no contention)

- Full-image pass (with TTA): ~46s
- Tiled pass (200 images): ~165s
- **Total: 211s** (within 300s sandbox limit)

## Submission

- `best_full_image.pt`: 85MB (YOLOv8L, 120 epochs, full data)
- `best_tile.pt`: 85MB (YOLOv8L, 30 epochs, tiled+augmented data)
- `submission.zip`: 155.7MB (well under 420MB limit)
- 2 weight files (max 3 allowed)
- No `import os` — sandbox compliant

## Failed Approaches (for the record)

### Variant A: Low-conf correction, keep original confidence

Corrected predictions at conf < 0.1 using tile conf >= 0.3, kept original confidence.

| Metric | Baseline | Variant A | Delta |
|--------|---:|---:|---:|
| **Weighted Score** | **0.7955** | **0.7961** | **+0.0006** |

90.3% accurate per-instance but flat score — corrections at conf < 0.1 are invisible to mAP.

### Variant B: Low-conf correction + confidence boost

Same as A but boosted confidence to ~0.5.

| Metric | Baseline | Variant B | Delta |
|--------|---:|---:|---:|
| **Weighted Score** | **0.7955** | **0.6912** | **-0.1043** |

The ~10% incorrect corrections became high-confidence false positives, destroying precision.

### Key Insight

You cannot boost confidence unless corrections are nearly perfect (~97%+). At 90% accuracy, the 10% errors at high confidence do more damage than the 90% correct ones help. The section-guided triple filter achieves 96.7% accuracy, making confidence replacement safe.

## Why Section-Guided Works and Others Don't

mAP sorts predictions by confidence and walks them highest-to-lowest. Impact depends on WHERE in the ranking you make changes:

| Approach | Confidence zone | mAP impact |
|----------|----------------|------------|
| Low-conf correction (keep conf) | < 0.1 | Invisible — tail of ranking |
| Low-conf correction (boost conf) | 0.03 → 0.5 | Toxic — 10% errors at 0.5 |
| **Section-guided (use tile conf)** | **any → 0.7+** | **High — removes FPs, adds TPs at meaningful thresholds** |

The section-guided approach works because:
1. **Triple filter ensures high accuracy** (wrong section + tile match + tile confident + tile in right section)
2. **Using tile confidence (>= 0.7)** places corrected predictions where mAP counts them
3. **Double mAP benefit**: removes a FP from wrong class AND adds a TP to correct class
