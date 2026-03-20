# Model Card — NorgesGruppen Data: Object Detection

Challenge: NorgesGruppen Data
Owner: Chris
Version: v1 (competition)
Date: 2026-03-19

---

## Model Overview

- **Name:** NorgesGruppen Grocery Object Detection Model
- **Architecture:** YOLOv8m (or YOLOv8l if VRAM permits) — fine-tuned on NorgesGruppen COCO dataset. Export: ONNX FP16 (recommended) or PyTorch state_dict.
- **Owner:** Chris
- **Challenge:** NM i AI — NorgesGruppen Data
- **Date:** 2026-03-19

---

## Intended Use

- **Primary use:** Given a directory of grocery shelf images, detect all product bounding boxes and output category IDs with confidence scores. Formatted as COCO predictions JSON.
- **Users:** NM i AI automated scoring system (COCOeval mAP). Operator: Chris.
- **Environment:** Sandbox — NVIDIA L4 GPU, 24 GB VRAM, CUDA 12.4, Python 3.11, ultralytics 8.1.0. Fully offline (no network access at inference time). Timeout: 300 seconds.
- **Out of scope:** Not for production retail use. Not intended for person detection. Not intended for any use case beyond this competition.

---

## Data

- **Training sources:** NorgesGruppen COCO dataset (254 images, ~22,300 annotations, 357 classes) + YOLOv8 pretrained COCO weights as initialisation.
- **Optional supplementary data:** Product reference images (327 × 7 angles) — **confirmed permitted** by competition hosts. Use to augment training or as a few-shot/template classifier on top of YOLOv8 detections.
- **Validation sources:** 20% hold-out split from training images (~51 images). Evaluated with `pycocotools` COCOeval before every submission.
- **Data limitations:** 254 training images for 357 classes = severe class imbalance. Many low-frequency classes may not be reliably learnable.

---

## Performance

- **Primary metric:** `Score = 0.7 × detection_mAP@0.5 + 0.3 × classification_mAP@0.5`. Target: ≥ 0.75.
- **Secondary metrics:** Per-class AP, detection mAP independently (max 0.70), inference time (must be <300s on L4).
- **Phase targets:**
  - Phase 1 (detection-only baseline, `category_id: 0`): 0.60–0.70
  - Phase 2 (fine-tuned full model): 0.75–0.88
  - Phase 3 (reference image boost): 0.88+
- **Known weak spots:**
  - Rare classes (<5 training examples) — AP near 0.
  - `unknown_product` (class 356) — semantically undefined, hard to classify reliably.
  - Edge cases: partial occlusion, extreme shelf angles, reflective packaging.

---

## Safety and Risk

- **Abuse / misuse considerations:** Grocery product detection — no identified misuse risk.
- **Failure modes:**
  1. **Banned import (`import os`) triggers code scanner → submission rejected.** Mitigation: use `pathlib`; grep for banned imports before packaging.
  2. **Version mismatch → silent weight load failure.** Mitigation: pin ultralytics==8.1.0, torch==2.6.0; test ONNX loading in clean env.
  3. **`run.py` in wrong zip path → submission fails.** Mitigation: always package from within the submission directory; verify with `unzip -l`.
  4. **Inference timeout on large test set.** Mitigation: benchmark locally on RTX 5090 Mobile first.
  5. **Overfitting to public leaderboard.** Mitigation: do not chase public decimal points; final ranking is on private test set.
- **Mitigations:** See R-010 through R-013 in risk register.

---

## Operational Notes

- **Repro command:**
  ```bash
  # Training (KO's machine)
  yolo detect train data=norgesgruppen.yaml model=yolov8m.pt epochs=50 imgsz=640 batch=16 seed=42

  # Local evaluation (mandatory before submission)
  python solutions/norgesgruppen-data/eval_local.py

  # Package submission
  cd my_submission
  Compress-Archive -Path .\* -DestinationPath ..\submission.zip
  unzip -l ../submission.zip | head -5  # verify run.py at root
  ```
- **Dependencies (sandbox pre-installed, do not bundle):** ultralytics 8.1.0, torch 2.6.0+cu124, torchvision 0.21.0+cu124, onnxruntime-gpu 1.20.0, opencv-python-headless 4.9.0.80, numpy 1.26.4, pycocotools 2.0.7.
- **Rollback / fallback:** If fine-tuned model regresses, revert to detection-only baseline (0 for category_id) — still scores up to 0.70. Per commit-before-run protocol: tag each working submission with git tag.
- **Submission gate:** Two-person review (Andrew + Christopher) before every upload. Local COCO eval must show improvement over current best.
