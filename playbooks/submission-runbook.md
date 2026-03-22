# Submission Runbook

## Pre-Submission Checklist
- [x] Repro command succeeds from clean environment — verified per challenge (see model cards for repro commands).
- [x] Dependencies pinned — requirements.txt pinned for Tripletex; sandbox versions pinned for NorgesGruppen.
- [x] Metric report attached — Tripletex score 53.2; NorgesGruppen score 0.8329; Astar Island 14 rounds completed.
- [x] Failure modes documented — see model cards and risk register for all three challenges.
- [x] Governance checklist complete — AI Act checklists, model cards, data cards, and privacy-security checklists completed for all three challenges.
- [x] Two-person review complete — Andrew + Christopher reviewed final submission state.

## Packaging
- Include only required files.
- Add `README` with run instructions.
- Include model and data card references.

## Final Gate
- [x] No policy/compliance blockers — all risks mitigated or explicitly accepted; see risk-register.md.
- [x] No unresolved high-severity robustness issue — all 13 risks resolved; see updated risk-register.md.
- [x] Rollback candidate preserved — all working states tagged in git history.

## Post-Submission
- Log result in `ops/decision-log.md`.
- Capture lessons in `ops/postmortem-template.md`.
