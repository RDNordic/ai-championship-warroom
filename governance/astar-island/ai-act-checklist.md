# AI Act Checklist — Astar Island: Viking World Prediction

Challenge: Astar Island
Owner: AD (Andrew/John)
Date: 2026-03-22 (final submission)
Created: 2026-03-19

---

## System Definition

- [x] **Purpose:** Observe a stochastic Norse civilisation simulation via a viewport API, infer hidden world parameters, and submit a W×H×6 probability tensor predicting terrain distributions after 50 simulation years. Pure analytical/prediction system — no actions taken in any real-world system.
- [x] **Intended users:** NM i AI competition judges (automated scoring). Operator: AD.

---

## EU AI Act Risk Classification

**Classification: Minimal Risk**

Rationale:
- System operates entirely on synthetic simulation data. No real-world subjects, physical environments, or consequential decisions.
- Output is a probability distribution over a fictional grid — no downstream automated decision-making affecting natural persons.
- No personal data involved at any stage.
- EU AI Act Annex III high-risk categories: not applicable.

---

## Risk and Control

- [x] Key risks identified and logged in `governance/risk-register.md` (R-006 through R-009).
- [x] Controls assigned: AD owns all Astar Island risks.
- [x] Residual risk accepted: Query budget misallocation (R-008) — mitigated by upfront tile planning; residual accepted.

---

## Data Governance

- [x] **Data sources:** Astar Island API (`api.ainm.no/astar-island`) — simulation observations. Initial grid states from `/rounds/{round_id}`. All data is synthetic simulation output.
- [x] **Usage basis:** NM i AI competition rules. All data is competition-issued synthetic data with no personal data component.
- [x] **PII:** None. Grid cells represent terrain types (Empty, Settlement, Port, Ruin, Forest, Mountain). Settlement stats (population, food, wealth, defense) are simulation abstractions — not derived from real people.
- [x] Sensitive data: None present.

---

## Transparency and Traceability

- [x] Model card created: `governance/astar-island/model-card.md`
- [x] Data card created: `governance/astar-island/data-card.md`
- [x] Decision log updated in `ops/decision-log.md`

---

## Security and Robustness

- [x] **Critical failure mode — zero probability:** If `prediction[y][x][c] = 0` for any class that has nonzero ground truth probability, KL divergence → ∞. Mitigation: mandatory `np.maximum(prediction, 0.01)` + renormalise on every submission.
- [x] **Credential risk:** JWT access_token stored in `.token` file — must not be committed to git. `.gitignore` entry verified.
- [x] **Budget exhaustion:** 50 queries total for 5 seeds. Tile budget is 9 queries/seed. Over-querying one seed starves others. Mitigation: pre-planned budget allocation before any observation run.
- [x] Abuse/misuse considerations: None applicable — pure read/predict system with no external effects.

---

## Human Oversight

- [x] **Human owner:** AD — go/no-go authority for submissions and budget allocation decisions.
- [x] **Escalation path:** AD → Christopher (technical backup) → KO. Signal for Patrick.
- [x] **Oversight scope:** Human reviews tile plan and submission before each round. Budget decisions are irreversible — require explicit human approval.
