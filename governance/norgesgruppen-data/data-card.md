# Data Card — NorgesGruppen Data: Object Detection

Challenge: NorgesGruppen Data
Owner: Chris
Date: 2026-03-22 (final submission)

---

## Dataset Overview

- **Name:** NM i AI NorgesGruppen Grocery Detection Dataset
- **Version:** Competition release (March 2026)
- **Source:** NorgesGruppen Data via NM i AI platform (`app.ainm.no`)
- **License / usage basis:** NM i AI competition rules. For competition use only. Product reference images are competition-provided and explicitly permitted as supplementary training data (confirmed by competition hosts).
- **Owner:** NorgesGruppen Data (provided to competition). Read-only for our team.

---

## Composition

- **Training images:** 254 grocery shelf JPEG images (~2000×1500 px each). Store sections: Egg, Frokost, Knekkebrod, Varmedrikker.
- **Annotations:** ~22,300 bounding boxes in COCO format (`bbox = [x, y, w, h]`). File: `annotations.json`.
- **Categories:** 357 product classes (IDs 0–356). `id: 356` = `unknown_product`.
- **Product reference images:** 327 products × 7 angles (main, front, back, left, right, top, bottom) = 2,289 images. Organised by barcode: `{product_code}/main.jpg`. Includes `metadata.json`.
- **Labeling method:** COCO format bounding box annotation. Labeling done by NorgesGruppen Data (provenance unknown — assumed manual or semi-automated).
- **Missingness:** 30 of 357 classes have no reference images (357 annotation classes vs. 327 reference products). `unknown_product` (class 356) likely appears in annotations but has no reference images.

---

## Collection and Processing

- **Collection method:** Real grocery shelf images captured by NorgesGruppen Data. Not synthetic. Represents actual retail store conditions.
- **Preprocessing steps planned:**
  1. Download and extract both zips (~924 MB total)
  2. Generate `norgesgruppen.yaml` from `annotations.json` categories
  3. Apply 80/20 train/val split (203 train / 51 val) — stratified by store section preferred
  4. Apply augmentation: horizontal flip, brightness/contrast, mosaic (YOLOv8 defaults)
  5. Export ONNX FP16 for submission
- **Filtering criteria:** None — use all 254 images. With only 254 images, excluding any is costly.

---

## Quality and Bias Notes

- **Known quality issues:** 254 training images is a small dataset for 357 classes — many classes will have very few examples. Long-tail class distribution expected.
- **Bias risks:**
  - Store section bias: if Egg/Frokost/Knekkebrod/Varmedrikker are represented unevenly, model generalisation across sections may be uneven.
  - Scale/lighting variation: retail shelf images vary in perspective, zoom, lighting. Augmentation partially mitigates.
  - `unknown_product` class (ID 356): catch-all for unlabeled products — may be frequent but semantically noisy.
- **Mitigation:**
  - Aggressive augmentation to compensate for small dataset.
  - Investigate class frequency distribution in `annotations.json` before training.
  - Consider class-weighted loss if extreme imbalance detected.

---

## Security and Privacy

- **Sensitive fields present:** Grocery shelf images may incidentally contain people (staff, customers in background). Not the subject of detection — product-only labeling confirms intent.
- **Protection controls:** Images used only for competition model training. Not redistributed. Not uploaded to any external service beyond competition submission endpoint.
- **Retention policy:** Retain through competition end (March 22, 2026) for training reproducibility. Post-competition: assess whether competition rules allow retention for research. If unclear, delete raw images; keep only trained model artifacts.
