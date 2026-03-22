# AGENTS.md

This file defines agent roles, team assignments, and handoff contracts for competition execution.

---

## Competition Status

**NM i AI — ACTIVE. March 19–22, 2026.**

| Challenge | Owner | Status | Docs |
|-----------|-------|--------|------|
| Tripletex — AI Accounting Agent | **KO** | Building | `solutions/tripletex/README.md` |
| Astar Island — Viking World Prediction | **AD (Andrew)** | Building | `solutions/astar-island/README.md` |
| NorgesGruppen Data — Object Detection | **Chris** | Building | `solutions/norgesgruppen-data/README.md` |

Patrick is not active during competition week.

---

## Operating Model

- One owner per challenge. They are the decision-maker for that challenge.
- Daily sync on blockers, metrics, and risks.
- Any high-risk submission requires owner + governance sign-off (AD minimum).
- **Zero on any challenge = catastrophic.** Baseline submission on all 3 before optimising any one.

---

## Team Roster

### Andrew Davidson (AD) — Team Captain / Astar Island Owner
- Owns Astar Island (probabilistic ML, query strategy, parameter inference). Governance gate on all final submissions.

### Christopher Coello (Chris) — NorgesGruppen Object Detection Owner
- Owns NorgesGruppen object detection. Trains YOLOv8, manages 3-submissions/day budget, local eval gating.

### Oddar / KO — Tripletex Accounting Agent Owner
- Owns Tripletex. Builds and maintains FastAPI `/solve` endpoint, LLM agent, Cloud Run deployment.

### Patrick Lundebye
- Not active during competition week.

---

## Team Assignments — Active

| Agent Role | Primary | Support |
|---|---|---|
| `solver-agent` (Tripletex) | KO | AD |
| `solver-agent` (Astar Island) | AD | Chris |
| `solver-agent` (NorgesGruppen) | Chris | KO |
| `eval-agent` | Chris (primary) | AD |
| `redteam-agent` | KO (primary) | AD |
| `governance-agent` | AD (primary) | — |
| `submission-agent` | AD (compliance gate) | Chris (technical gate) |

---

## Immediate Priorities Per Owner

### KO — Tripletex
1. Claim sandbox at `app.ainm.no` (Tripletex submission page)
2. Stand up FastAPI `/solve` endpoint + cloudflared HTTPS tunnel
3. Submit stub endpoint to get first score on board
4. Iterate: cover more of the 30 task types; drive down 4xx errors for efficiency bonus
5. Full spec: `solutions/tripletex/README.md`

### AD — Astar Island
1. Check `GET /astar-island/rounds` — is a new round active?
2. If active: submit a prior-only baseline for all 5 seeds before spending any queries
3. Use the corrected scripted workflow for the full coverage + repeat cycle; do not use the website UI
4. After scoring, export `/analysis/{round_id}/{seed_index}` for all 5 seeds and compare against the prior round
5. Adjust priors or observation weighting only when the analysis shows a clear, repeated bias
6. Full spec and live handoff: `solutions/astar-island/README.md` and `solutions/astar-island/next-steps.md`

### Chris — NorgesGruppen Object Detection
1. Download training data from `app.ainm.no` Submit page (~924 MB total)
2. `pip install ultralytics==8.1.0` — must pin to sandbox version
3. Build local eval script with `pycocotools` — mandatory before any upload
4. First submission: YOLOv8 zero-shot, all `category_id: 0` (scores up to 0.70)
5. Fine-tune YOLOv8m on their COCO data (`nc=357`) for classification
6. **3 submissions/day cap** — never upload without local eval result
7. Full spec: `solutions/norgesgruppen-data/README.md`

---

## Agent Role Definitions

### 1) `solver-agent`
Scope:
- Implements baseline and advanced approaches.
- Optimizes data processing, modelling, and inference.

Must output:
- Code changes.
- Repro command.
- Metric deltas.
- Known failure cases.

### 2) `eval-agent`
Scope:
- Builds and maintains the evaluation harness.
- Checks regression across datasets/seeds.

Must output:
- Eval report with metric table.
- Confidence notes and variance.
- Regression alert summary.

### 3) `redteam-agent`
Scope:
- Stress tests edge cases and abuse patterns.
- Probes robustness and reliability.

Must output:
- Test cases run.
- Failure severity.
- Suggested mitigations.

### 4) `governance-agent`
Scope:
- Tracks AI Act relevance, privacy, and security controls.
- Maintains risk register and compliance artifacts.

Must output:
- Updated risk register entries.
- Checklist completion status.
- Blocking issues (if any).

### 5) `submission-agent`
Scope:
- Packages final deliverable and metadata.
- Verifies final gate criteria.

Must output:
- Submission bundle manifest.
- Final gate checklist result.
- Rollback/fallback plan.

---

## Per-Challenge Eval Protocols

### Tripletex
- Score: sum of best per-task scores across 30 task types (max 6.0 per task)
- Local test: use sandbox account at `https://kkpqfuj-amager.tripletex.dev` to verify API calls before submitting endpoint
- Gate: confirm agent handles at least Tier 1 tasks with zero 4xx errors before targeting Tier 2/3
- Regression check: efficiency benchmarks recalculate every 12h — monitor score for unexpected drops

### Astar Island
- Score: entropy-weighted KL divergence → 0–100 (higher is better)
- Local test: validate prediction tensor shape (H×W×6), all values ≥ 0.01, rows sum to 1.0 (±0.01)
- Gate: always submit something for all 5 seeds — missing seed = 0 for that seed
- Cardinal rule: never submit 0.0 probability in any cell — use `np.maximum(pred, 0.01)` + renormalise

### NorgesGruppen Object Detection
- Score: `0.7 × detection_mAP@0.5 + 0.3 × classification_mAP@0.5`
- Local test: run `pycocotools` COCOeval on local val split before every upload — compute both mAPs separately
- Gate: **3 submissions/day hard cap** — never upload without local eval score in hand
- Regression check: public leaderboard = public test set; final ranking = private test set — don't over-fit to public score

---

## Handoff Contract

Every handoff must include:
- Current objective.
- Exact commit or artifact reference.
- What is proven.
- What is assumed.
- Next highest-priority task.

---

## Priority Rules

1. Validity over novelty.
2. Reproducibility over one-off wins.
3. Compliance blockers override speed.
4. Baseline on all 3 challenges before deep optimisation of any one.

---

## Repository Automation Agent (Codex / Claude Code)

- Scope: Implements requested repository changes, runs local verification, and reports concrete outcomes.
- Guardrails: Does not override governance decisions. Follows handoff contract and priority rules above.
- Must output:
  - Files changed.
  - Repro/test commands run.
  - Results and known limitations.
