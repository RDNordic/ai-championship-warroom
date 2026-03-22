# Privacy and Security Checklist — NorgesGruppen Data: Object Detection

Challenge: NorgesGruppen Data
Owner: Chris (primary), Andrew (governance escalation)
Date: 2026-03-22

---

## Data Inventory

- [x] **Data sources listed:** NM i AI competition dataset — `NM_NGD_coco_dataset.zip` (~864 MB, 254 shelf images, ~22,300 COCO annotations). Product reference images — `NM_NGD_product_images.zip` (~60 MB, 327 products × 7 angles). Both downloaded from `app.ainm.no` (login required).
- [x] **Lawful basis:** NM i AI competition rules. Dataset licensed for competition use only. Product reference images explicitly permitted as supplementary training data (confirmed by competition hosts 2026-03-19).
- [x] **Personal data identified:** Grocery shelf images may incidentally contain people (staff, customers in background). Assessment: product detection system — persons are not the subject of detection or classification. No biometric extraction or person-identification capability. No facial recognition. Risk: Minimal.
- [x] **Sensitive attributes:** None intentionally present. No health, biometric, ethnic, or political data. Product labels may incidentally contain nutritional/allergen information — this is publicly available retail data, not sensitive personal data.
- [x] **Third-party data compliance:** All data sourced from NorgesGruppen via NM i AI competition platform. YOLOv8 pretrained COCO weights used as model initialisation — COCO dataset is publicly licensed for research use.

---

## GDPR Principles (Apply By Default)

- [x] **Purpose limitation:** Data used solely for training and evaluating a grocery product detection model within the competition. Not used for person detection, profiling, surveillance, or any secondary purpose.
- [x] **Data minimisation:** Only competition-provided images and annotations used. No additional scraping, crawling, or external data collection. Model detects product bounding boxes only — no person-related features extracted.
- [x] **Storage limitation:** Raw images retained locally through competition end (March 22, 2026). Post-competition: assess whether competition rules allow retention for research. If unclear, delete raw images; keep only trained model artifacts (weights contain no recoverable PII).
- [x] **Accuracy:** Dataset quality accepted as-is from NorgesGruppen. Known limitation: 254 images for 357 classes — severe class imbalance. `unknown_product` (class 356) is semantically noisy. These are data quality issues, not GDPR accuracy concerns (no personal data involved).
- [x] **Integrity and confidentiality:** Images stored locally only. Not redistributed or uploaded to any service beyond the competition submission endpoint. Access limited to team members.

---

## Security

- [x] **Secrets management:** Competition platform login credentials managed per-user (browser session). No API keys or credentials stored in source code. No `.env` files in the NorgesGruppen solution directory.
- [x] **Dependency review:** `ultralytics` 8.1.0, `torch` 2.6.0, `torchvision` 0.21.0, `onnxruntime-gpu` 1.20.0, `opencv-python-headless` 4.9.0.80, `numpy` 1.26.4, `pycocotools` 2.0.7. All pinned to sandbox-matching versions. No known CVEs at time of writing.
- [x] **Prompt injection checks:** Not applicable — no LLM component. Model processes images only. No natural language input.
- [x] **Output filtering:** Model outputs COCO-format predictions JSON (bounding boxes, category IDs, confidence scores). No capability to leak training data, PII, or credentials through inference output.
- [x] **Code scanner compliance:** Sandbox rejects `import os`, `import subprocess`, `import socket`, `import ctypes`, `import builtins`, `eval()`, `exec()`, `compile()`, `__import__()`. Mitigation: use `pathlib` exclusively throughout `run.py`. Grep for banned imports before every packaging step. See risk R-010.

---

## Operational

- [x] **Incident owner:** Chris — primary. Andrew for governance escalation.
- [x] **Escalation contacts:** Chris → Andrew (governance, submission gate) → KO. Patrick on Signal for awareness.
- [x] **Backup / rollback:** If fine-tuned model regresses, revert to detection-only baseline (`category_id: 0` for all detections) — scores up to 0.70. Per commit-before-run protocol: each working submission tagged in git. Previous submission scores retained by competition platform (bad runs never lower score).
- [x] **Competition data handling rules checked:** 3 submissions per day hard limit. Local COCO eval mandatory before every submission (prevents wasted quota). Images not to be redistributed outside team. Submission zip must have `run.py` at root level.

---

## Decision Rule

When in doubt about data rights or privacy: **pause, log in risk-register.md, and ask** — don't silently proceed and don't silently refuse.
