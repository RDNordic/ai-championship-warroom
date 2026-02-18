# Submission Runbook

## Pre-Submission Checklist
- [ ] Repro command succeeds from clean environment.
- [ ] Dependencies pinned.
- [ ] Metric report attached.
- [ ] Failure modes documented.
- [ ] Governance checklist complete.
- [ ] Two-person review complete.

## Packaging
- Include only required files.
- Add `README` with run instructions.
- Include model and data card references.

## Final Gate
- [ ] No policy/compliance blockers.
- [ ] No unresolved high-severity robustness issue.
- [ ] Rollback candidate preserved.

## Post-Submission
- Log result in `ops/decision-log.md`.
- Capture lessons in `ops/postmortem-template.md`.
