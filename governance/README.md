# Governance

This folder contains EU AI Act and GDPR compliance documentation for each challenge submitted to the NM i AI Championship (March 2026).

## Structure

```
governance/
├── README.md                        ← this file
├── risk-register.md                 ← all risks across all challenges (updated 2026-03-22)
├── ai-act-checklist.md              ← blank template (see challenge-level folders below)
├── model-card-template.md           ← blank template
├── data-card-template.md            ← blank template
├── privacy-security-checklist.md    ← blank template
│
├── tripletex/                       ← Tripletex: AI Accounting Agent
│   ├── ai-act-checklist.md          ← EU AI Act classification + controls
│   ├── model-card.md                ← model overview, performance, safety, repro
│   ├── data-card.md                 ← data sources, composition, privacy controls
│   └── privacy-security-checklist.md ← GDPR + security checklist (fully completed)
│
├── astar-island/                    ← Astar Island: Viking World Prediction
│   ├── ai-act-checklist.md
│   ├── model-card.md
│   ├── data-card.md
│   └── privacy-security-checklist.md
│
└── norgesgruppen-data/              ← NorgesGruppen Data: Object Detection
    ├── ai-act-checklist.md
    ├── model-card.md
    ├── data-card.md
    └── privacy-security-checklist.md
```

> **Note:** The root-level `ai-act-checklist.md`, `model-card-template.md`, `data-card-template.md`, and `privacy-security-checklist.md` are blank templates provided for reference. The filled-in, challenge-specific documents are in each challenge subfolder.

---

## EU AI Act Classifications

| Challenge | Classification | Rationale |
|-----------|---------------|-----------|
| Tripletex — AI Accounting Agent | **Limited Risk** (competition context) — would be **High Risk** in production | Autonomous financial agent modifying ledgers and employee records. In production, Annex III obligations would apply. Competition context: sandboxed, synthetic data, no real subjects. |
| Astar Island — Viking World Prediction | **Minimal Risk** | Pure read/predict pipeline on synthetic simulation data. No consequential decisions, no personal data. |
| NorgesGruppen Data — Object Detection | **Minimal Risk** | Grocery product detection on retail shelf images. No biometric processing, no consequential decisions affecting persons. |

---

## GDPR Posture

All three challenges apply GDPR principles by default, even where data is synthetic:

- **Purpose limitation** — data used only for competition task completion.
- **Data minimisation** — only fields required for task extracted/used.
- **Storage limitation** — no persistent storage of prompt content or credentials; retention policies documented per challenge.
- **Integrity and confidentiality** — secrets managed outside source code; HTTPS enforced; no credentials in git.

---

## Key Documents (non-governance)

| Document | Location |
|----------|----------|
| Risk Register | `governance/risk-register.md` |
| Decision Log | `ops/decision-log.md` |
| Red Team Tests | `evals/red-team-tests.md` |
| Submission Runbook | `playbooks/submission-runbook.md` |
