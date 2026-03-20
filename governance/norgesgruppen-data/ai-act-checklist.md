# AI Act Checklist — NorgesGruppen Data: Object Detection

Challenge: NorgesGruppen Data
Owner: Chris
Date: 2026-03-19

---

## System Definition

- [x] **Purpose:** Train and deploy a computer vision object detection model on Norwegian grocery shelf images. Given images, output bounding boxes + product category IDs. Scored on detection mAP@0.5 and classification mAP@0.5.
- [x] **Intended users:** NM i AI competition judges (automated scoring). Operator: Chris. All team members review before submission.

---

## EU AI Act Risk Classification

**Classification: Minimal Risk**

Rationale:
- System detects and classifies grocery products on retail shelf images — no consequential decisions affecting natural persons.
- No personal data involved. Images contain grocery products; no facial recognition or biometric processing.
- Not used in employment, credit, law enforcement, or critical infrastructure contexts.
- EU AI Act Annex III high-risk categories: not applicable.
- **Caveat:** If any training/test images incidentally contain people (staff, customers in background), this is assessed as not the primary subject — product detection system, not person detection. No biometric processing.

---

## Risk and Control

- [x] Key risks identified and logged in `governance/risk-register.md` (R-010 through R-013).
- [x] Controls assigned: Chris owns all NorgesGruppen risks.
- [x] Residual risk accepted: Submission limit (R-012) — 3/day is a hard constraint; residual risk of wasted submissions accepted, mitigated by mandatory local eval gate.

---

## Data Governance

- [x] **Data sources:** NM i AI competition dataset — `NM_NGD_coco_dataset.zip` (~864 MB, 254 shelf images, ~22,300 COCO annotations). Product reference images — `NM_NGD_product_images.zip` (~60 MB, 327 products × 7 angles). Both downloaded from `app.ainm.no` (login required).
- [x] **Usage basis:** NM i AI competition rules. Dataset licensed for competition use. Product reference images are competition-provided and explicitly permitted as supplementary training data (confirmed by competition hosts 2026-03-19).
- [x] **PII:** Shelf images may incidentally include people in the background. Assessment: product detection system — persons are not the subject of detection or classification. No biometric extraction. Risk: Minimal.
- [x] Sensitive data controls: Images not redistributed; used only for competition model training.

---

## Transparency and Traceability

- [x] Model card created: `governance/norgesgruppen-data/model-card.md`
- [x] Data card created: `governance/norgesgruppen-data/data-card.md`
- [ ] Decision log updated in `ops/decision-log.md` — ongoing during competition

---

## Security and Robustness

- [x] **Code scanner rejection risk:** Sandbox rejects `import os`, `import subprocess`, `import socket`, `import ctypes`, `import builtins`, `eval()`, `exec()`, `compile()`, `__import__()`. Mitigation: use `pathlib` exclusively; grep for banned imports before packaging.
- [x] **Version mismatch risk:** Package versions in training environment must match sandbox exactly. Mismatch causes silent load failure. See risk R-011.
- [x] **Timeout risk:** Inference must complete within 300 seconds on NVIDIA L4. Mitigated by benchmarking locally on RTX 5090 Mobile (same 24 GB VRAM).
- [x] **Abuse / misuse:** Not applicable — grocery product detection has no identified abuse vector.
- [ ] Edge-case tests: local COCO eval run before every submission (mandatory gate)

---

## Human Oversight

- [x] **Human owner:** Chris — go/no-go authority for model training decisions and submissions.
- [x] **Escalation path:** Chris → Andrew (governance, submission gate) → KO. Signal for Patrick.
- [x] **Mandatory two-person review:** Per submission runbook — Andrew + Christopher minimum for final submission. Every submission treated as a production deploy given 3/day hard limit.
