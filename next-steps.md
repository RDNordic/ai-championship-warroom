# NM i AI Championship — Final Handoff

**Competition deadline: March 22, 2026 at 15:00 CET**
**Repo link deadline: 15:15 CET (15 min grace after close)**

---

## Current Status (as of 2026-03-22 ~14:15 CET)

| Challenge | Owner | Status | Score |
|-----------|-------|--------|-------|
| Tripletex — AI Accounting Agent | KO | Endpoint live on Cloud Run | 53.2 |
| NorgesGruppen — Object Detection | Chris | Model submitted | 0.8329 |
| Astar Island — Viking World Prediction | AD | Round 23 active (50/50 queries used, 5/5 seeds submitted) | Best: 88.1 (R8) |

**`main` is clean, up to date, and security-verified. All governance documentation complete.**

---

## FINAL ACTIONS — T-45 MIN

### 1. At ~14:58 — Make repo public
- Go to: `https://github.com/RDNordic/ai-championship-warroom/settings`
- **Danger Zone → Change repository visibility → Make public**
- Do this as late as safely possible to avoid competitors scanning the repo

### 2. Immediately after — Submit repo link at `app.ainm.no/finals`
- URL: `https://github.com/RDNordic/ai-championship-warroom`
- Label: All three challenges — Tripletex, Astar Island, NorgesGruppen
- Notes: Full EU AI Act + GDPR governance documentation included (`governance/`)
- Deadline: **15:15 CET** (hard lock)

### 3. Confirm all three challenge submissions are registered
- Tripletex: `https://captains-tripletex-339414168231.europe-north1.run.app/solve` registered at `app.ainm.no/submit/tripletex` ✓
- NorgesGruppen: latest zip uploaded at `app.ainm.no` ✓
- Astar Island: 5/5 seeds submitted for all rounds ✓

### 4. Astar Island scoring note
- Leaderboard score = **best (round_score × round_weight)** across all rounds
- Round weight = `1.05^round_number` — later rounds worth more
- Round 23 still active — if AD gets a strong score it will likely be the best weighted result
- Do not skip submitting Round 23 even if the raw score looks modest

---

## Submission Compliance Rules (READ BEFORE ANY LAST-MINUTE CHANGES)

These rules must be satisfied for submission to count. **Do not bypass.**

### Governance (completed — do not break)
- All 3 challenges have completed AI Act checklists, model cards, data cards, and privacy-security checklists in `governance/`
- Risk register updated — all 13 risks mitigated, closed, or explicitly accepted
- Decision log has 5 key competition decisions recorded in `ops/decision-log.md`
- Red team tests completed for all 3 challenges in `evals/red-team-tests.md`

### Code submission rules
- **NorgesGruppen `run.py`:** must NOT contain `import os`, `import subprocess`, `import socket`, `import ctypes`, `import builtins`, `eval()`, `exec()`, `compile()`, `__import__()` — sandbox will reject. Use `pathlib` only.
- **NorgesGruppen zip:** `run.py` must be at the **root** of the zip, not in a subfolder. Verify with `unzip -l submission.zip`.
- **Tripletex endpoint:** must return `{"status": "completed"}` within 300 seconds. Session token must never be logged.
- **Astar Island predictions:** every cell in the H×W×6 tensor must have values summing to 1.0 (±0.01). Apply `np.maximum(prediction, 0.01)` + renormalise before every submit — zero probability causes KL divergence → ∞.
- All 5 seeds must be submitted for every Astar round — missing seed = score 0 for that seed.

### Repository rules
- Repo must be **public** by 15:00 CET for prize eligibility
- `main` branch must contain the final submission state
- No secrets, API keys, or credentials committed — verified via `.gitignore`
- MIT licence present (`LICENSE` file) ✓

### Score discipline
- Per `CLAUDE.md`: commit before every run, revert on regression, one change per commit
- Do NOT make last-minute speculative changes without a local eval result
- NorgesGruppen: only 3 submissions/day — do not upload without local COCO eval confirming improvement

---

## Team

| Member | Role | Challenge |
|--------|------|-----------|
| AD (Andrew/John) | PM / Governance | Astar Island |
| Chris (Christopher) | Solver / Eval | NorgesGruppen Object Detection |
| KO (Oddar) | Infra / Agent | Tripletex |
| Patrick | Advisory (Signal only) | — |

---

## Key File Locations

| What | Where |
|------|-------|
| Governance overview | `governance/README.md` |
| Risk register | `governance/risk-register.md` |
| Submission runbook | `playbooks/submission-runbook.md` |
| Decision log | `ops/decision-log.md` |
| Red team tests | `evals/red-team-tests.md` |
| Tripletex handoff | `solutions/tripletex/SESSION_HANDOFF.md` |
| Astar Island handoff | `solutions/astar-island/next-steps.md` |
| NorgesGruppen README | `solutions/norgesgruppen-data/README.md` |

---

## Session Log

- **2026-03-22 ~14:15:** Repo tidied for public release. README, next-steps, Tripletex live endpoint URL documented. Security scan clean. Awaiting 14:58 to make public and submit repo link.
- **2026-03-22 morning:** Final governance review complete. All 3 challenges have full EU AI Act + GDPR documentation. PRs merged to main. Repo clean.
- **2026-03-21:** Tripletex iterative hardening: score 22 → 42.2 → 53.2 (23+ fixes).
- **2026-03-20:** NorgesGruppen Run 2: score 0.8329. Governance docs created for all challenges.
- **2026-03-19:** Competition began 18:00 CET. All 3 challenges read and ownership assigned. Baselines established.
