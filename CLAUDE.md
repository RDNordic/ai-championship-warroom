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

## Verification Ladder
Every significant change follows: **extract → draft → review**.
1. Extract: gather data, read code, understand the problem.
2. Draft: implement the change with repro command and metrics.
3. Review: challenge the change before merging or submitting.

Review prompts to use at step 3:
- "Grill me on these changes" — force justification of every decision.
- "Prove to me this works" — demand evidence, not assertions.
- "Knowing everything you know now, scrap this" — check if the approach is still the best one.

## Data Handling Defaults
- Don't blanket-ban personal data — allow with lawful basis, flag what you see.
- Apply GDPR principles by default: purpose limitation, data minimisation, storage limitation.
- Flag EU AI Act risk categories when relevant.
- When in doubt, ask — don't silently proceed and don't silently refuse.
- Log any data rights uncertainty in `governance/risk-register.md`.

## Subagent and AI Tool Principles
- Give each agent the minimum tools it needs (reader agents don't need edit/bash).
- Hardcode actual repo paths, not template placeholders.
- Don't build automation prematurely — wait until a workflow repeats 3+ times.
- Use slash commands as the intermediate step before full skill development.

## Challenge-Level CLAUDE.md
Each `solutions/challenge-N/` folder may contain its own `CLAUDE.md` with challenge-specific rules that inherit from and extend this file.

## Submission Gate
No final submission without:
- Passing runbook in `playbooks/submission-runbook.md`.
- Completed compliance checklist.
- Two-person review for critical changes (Andrew + Christopher minimum).