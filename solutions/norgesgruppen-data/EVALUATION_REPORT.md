# Evaluation Report — Hybrid Tiled Class Correction

## Scores

### Variant A: Class correction, keep original confidence

| Metric | Baseline (no tiles) | Hybrid (class correction) | Delta |
|--------|---:|---:|---:|
| Detection mAP@0.5 | 0.8120 | 0.8227 | **+0.0107** |
| Classification mAP@0.5 | 0.7570 | 0.7341 | -0.0229 |
| **Weighted Score** | **0.7955** | **0.7961** | **+0.0006** |

Weighted score essentially flat (+0.0006). Detection improved, classification dropped — nearly cancel out.

### Variant B: Class correction + confidence boost (+0.5 or tile conf)

| Metric | Baseline (no tiles) | Hybrid (boosted conf) | Delta |
|--------|---:|---:|---:|
| Detection mAP@0.5 | 0.8120 | 0.6950 | -0.1170 |
| Classification mAP@0.5 | 0.7570 | 0.6824 | -0.0746 |
| **Weighted Score** | **0.7955** | **0.6912** | **-0.1043** |

Confidence boost made things much worse. The ~10% incorrect corrections (~582 predictions) become high-confidence false positives at conf ~0.5, poisoning the precision-recall curve.

**Conclusion: Variant A (keep original confidence) is the right approach. Variant B is discarded.**

## Pipeline Statistics (248 images)

| Stage | Count |
|-------|------:|
| Total predictions (full-image pass) | 67,359 |
| Images requiring tiling (both dims > 1280) | 200 / 248 |
| Tile detections (before NMS) | 53,951 |
| **Classes corrected by tile model** | **9,293** (13.8% of all predictions) |
| Section prior applied to images | 248 / 248 |
| **Predictions penalized by section prior** | **4,677** (6.9% of all predictions) |

## Confidence Distribution (Variant A — no boost)

| Confidence Range | Count | % |
|-----------------|------:|---:|
| [0.00, 0.01) | 4,286 | 6.4% |
| [0.01, 0.05) | 24,436 | 36.3% |
| [0.05, 0.10) | 5,911 | 8.8% |
| [0.10, 0.30) | 6,610 | 9.8% |
| [0.30, 0.50) | 2,779 | 4.1% |
| [0.50, 0.70) | 2,487 | 3.7% |
| [0.70, 0.90) | 7,700 | 11.4% |
| [0.90, 1.00] | 13,150 | 19.5% |

51.5% of predictions are below 0.1 confidence — these are the candidates for class correction.

## Class Correction Accuracy (sampled 20 images, verified against GT)

| Metric | Count |
|--------|------:|
| Low-confidence predictions (conf < 0.1) | 3,003 |
| With overlapping tile match (IoU >= 0.3) | 2,216 |
| Class actually changed | 681 |
| **Helped (wrong → correct)** | **436 (90.3%)** |
| **Hurt (correct → wrong)** | **47 (9.7%)** |
| Neither (both wrong / no GT match) | 198 |

Extrapolated to 248 images: ~8,444 corrections, ~5,406 helped, ~582 hurt.

## Why Score Is Flat (Variant A) and Why Boosting Hurts (Variant B)

All corrections happen on predictions with conf < 0.1. These sit at the bottom of the confidence-sorted ranking. mAP computes precision at each recall level, walking predictions from highest to lowest confidence. By the time it reaches conf < 0.1, the precision-recall curve is largely determined. So:

- **Variant A (keep conf):** Corrections are invisible to mAP. Both helped and hurt cases are at conf < 0.1 — equally irrelevant. Score is flat.

- **Variant B (boost conf to ~0.5):** The ~90% correct corrections move up the ranking and help mAP slightly. But the ~10% incorrect corrections (~582 predictions) also move up and become high-confidence false positives. A wrong prediction at conf 0.5 does far more damage than a correct prediction at conf 0.5 does good — because false positives at high confidence suppress precision across all recall levels below them. Net effect: score drops 10%.

**Key insight: you cannot boost confidence of a correction unless you are ~100% sure it is correct. At 90% accuracy, the 10% errors at high confidence destroy the gains.**

## Per-Image Stats

- Images: 248
- Predictions per image: min=46, max=760, mean=271.6
- Unique classes predicted: 295 / 356
- Classes with 0 predictions: 61

## Timing

- Full-image pass (with TTA): ~46s
- Tiled pass (200 images): ~320s
- **Total: ~370s** (exceeds 300s sandbox limit)

## Conclusion

The class correction logic is sound (90% accurate per-instance) but does not improve the weighted mAP score. Two fundamental issues:

1. **Without confidence boost:** corrections are at conf < 0.1 and invisible to mAP.
2. **With confidence boost:** the 10% incorrect corrections become toxic high-confidence false positives.

For tiled class correction to help, we would need either:
- **Near-perfect correction accuracy (>99%)** to safely boost confidence
- **A scoring metric that counts low-confidence predictions** (mAP does not)
- **Correcting higher-confidence predictions** (conf 0.1–0.5 range) where corrections would actually register in mAP — but the full-image model is more reliable at those confidence levels
