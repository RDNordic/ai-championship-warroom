# CLAUDE.md

This file defines how AI assistants should operate in this repository.

## Mission
Produce competition-ready solutions that are:
- Strong on leaderboard metrics.
- Reproducible.
- Security and privacy aware.
- Clearly documented for rapid handoff.

## Core Rules
1. Prefer small, testable changes over broad rewrites.
2. Never submit code without an explicit evaluation result.
3. Every model change must include:
   - Intended effect.
   - Observed metric change.
   - Potential regression risk.
4. Keep a clear audit trail in `ops/decision-log.md`.
5. If uncertain about data rights, pause and log in `governance/risk-register.md`.

## Required Output Format For AI Assistants
When proposing or making a change, include:
- `What changed`
- `Why it helps`
- `How to run`
- `Validation evidence`
- `Risks and mitigations`

## Engineering Defaults
- Pin package versions.
- Use deterministic seeds where possible.
- Separate experimental notebooks from production scripts.
- Prefer scripts over manual steps.

## Governance Defaults
- Complete `governance/ai-act-checklist.md` for each challenge solution.
- Maintain a model card and data card for each final submission.
- Run abuse/misuse checks from `evals/red-team-tests.md`.

## Submission Gate
No final submission without:
- Passing runbook in `playbooks/submission-runbook.md`.
- Completed compliance checklist.
- Two-person review for critical changes.