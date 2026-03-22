# CLAUDE.md

This file defines how AI assistants should operate in this repository.

---

## Competition Status

**NM i AI Championship — ACTIVE**
- Kickoff: March 19, 2026 at 18:00 CET
- Deadline: March 22, 2026
- Three challenges running in parallel

| Challenge | Owner | Solution folder |
|-----------|-------|----------------|
| Tripletex — AI Accounting Agent | KO | `solutions/tripletex/` |
| Astar Island — Viking World Prediction | AD (Andrew) | `solutions/astar-island/` |
| NorgesGruppen Data — Object Detection | Chris | `solutions/norgesgruppen-data/` |

Patrick participating remotely during competition week.

**When starting a new session:** Read the challenge-local handoff first (`solutions/<challenge>/next-steps.md` when it exists). For Astar Island, start with `solutions/astar-island/next-steps.md`. Use root `next-steps.md` only for repo-wide coordination, then read the relevant `solutions/<challenge>/README.md` for technical detail.

---

## Mission

Produce competition-ready solutions that are:
- Strong on leaderboard metrics.
- Reproducible.
- Security and privacy aware.
- Clearly documented for rapid handoff.

---

## Core Rules

1. Prefer small, testable changes over broad rewrites.
2. Never submit code without an explicit evaluation result.
3. Every model change must include:
   - Intended effect.
   - Observed metric change.
   - Potential regression risk.
4. Keep a clear audit trail in `ops/decision-log.md`.
5. If uncertain about data rights, pause and log in `governance/risk-register.md`.

---

## Required Output Format For AI Assistants

When proposing or making a change, include:
- `What changed`
- `Why it helps`
- `How to run`
- `Validation evidence`
- `Risks and mitigations`

---

## Engineering Defaults

- Pin package versions.
- Use deterministic seeds where possible (`random.seed(42)`).
- Separate experimental notebooks from production scripts.
- Prefer scripts over manual steps.

---

## Governance Defaults

- Complete `governance/ai-act-checklist.md` for each challenge solution.
- Maintain a model card and data card for each final submission.
- Run abuse/misuse checks from `evals/red-team-tests.md`.

---

## Verification Ladder

Every significant change follows: **extract → draft → review**.

1. **Extract:** gather data, read code, understand the problem.
2. **Draft:** implement the change with repro command and metrics.
3. **Review:** challenge the change before merging or submitting.

Review prompts to use at step 3:
- "Grill me on these changes" — force justification of every decision.
- "Prove to me this works" — demand evidence, not assertions.
- "Knowing everything you know now, scrap this" — check if the approach is still the best one.

---

## Data Handling Defaults

- Don't blanket-ban personal data — allow with lawful basis, flag what you see.
- Apply GDPR principles by default: purpose limitation, data minimisation, storage limitation.
- Flag EU AI Act risk categories when relevant.
- When in doubt, ask — don't silently proceed and don't silently refuse.
- Log any data rights uncertainty in `governance/risk-register.md`.

---

## Subagent and AI Tool Principles

- Give each agent the minimum tools it needs (reader agents don't need edit/bash).
- Hardcode actual repo paths, not template placeholders.
- Don't build automation prematurely — wait until a workflow repeats 3+ times.
- Use slash commands as the intermediate step before full skill development.

---

## Commit-Before-Run / Revert-On-Regression Protocol

For any iterative scoring challenge, follow this discipline:

1. **Commit before every run.** Use descriptive messages, e.g.:
   - `tripletex: score=2.4, added invoice creation flow`
   - `astar-island: score=58, tiling complete + parameter inference`
   - `norgesgruppen: det_mAP=0.61, yolov8m fine-tuned epoch50`
2. **One change per commit.** Makes it trivial to bisect which change helped vs. hurt.
3. **Run after each change.** Compare score against the current best.
4. **Revert immediately if score drops.** `git checkout -- <file>` — do not rationalize regressions.
5. **Tag new high-water marks.** After any new best: `git tag tripletex-best-2.4 HEAD`
6. **Never iterate on uncommitted code.** If a change doesn't improve, revert before trying the next idea.
7. **Median over 3 runs for noisy challenges.** If variance is high, compare medians not single runs.
8. **Time-box tuning.** If no improvement in 30 min on a difficulty, move to the next one.
9. **Add `random.seed(42)` early** to eliminate variance, making A/B testing reliable.

---

## Challenge-Level CLAUDE.md

Each `solutions/<challenge>/` folder may contain its own `CLAUDE.md` with challenge-specific rules that inherit from and extend this file:
- `solutions/tripletex/CLAUDE.md`
- `solutions/astar-island/CLAUDE.md`
- `solutions/norgesgruppen-data/CLAUDE.md`

---

## Submission Gate

No final submission without:
- Passing runbook in `playbooks/submission-runbook.md`.
- Completed compliance checklist.
- Two-person review for critical changes (Andrew + Christopher minimum).
