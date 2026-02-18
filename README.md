# AI Championship War Room

Private prep repo for the Norwegian AI Championship (March 19-22, 2026).

## Purpose
- Ship high-performing challenge solutions fast.
- Maintain compliance, risk control, and traceability by default.
- Run a repeatable team workflow under competition pressure.

## Repo Layout
- `CLAUDE.md`: Operating rules for AI coding assistants.
- `AGENTS.md`: Team agent roles, contracts, and handoffs.
- `playbooks/`: Execution runbooks for intake, submission, and incidents.
- `governance/`: Compliance and governance templates.
- `evals/`: Evaluation harness and red-team test guidance.
- `solutions/`: Per-challenge implementation folders.
- `ops/`: Decision log, assumptions, and postmortems.

## Quick Start
1. Fill `AGENTS.md` with your real team members and shift coverage.
2. Create branch naming + PR rules in GitHub settings.
3. Before kickoff, run one full dry-run using `playbooks/submission-runbook.md`.
4. For each challenge, copy governance templates and complete minimum fields.

## Challenge Kickoff (Captain Action)
When organizers release the challenge repository, paste the link here and start intake.

- Captain: Greybeards of Governance
- Challenge Repo URL: `PASTE_URL_HERE`
- Kickoff command set:
  - Clone or add remote to local workspace.
  - Create challenge branch (`challenge-1/*`, `challenge-2/*`, or `challenge-3/*`).
  - Execute `playbooks/challenge-intake.md` immediately.

## Suggested Branch Strategy
- `main`: stable, releasable baseline.
- `challenge-1/*`, `challenge-2/*`, `challenge-3/*`: challenge-specific work.
- `hotfix/*`: urgent leaderboard or reliability fixes.

## Minimum Evidence Before Any Submission
- Repro command and pinned dependencies.
- Metrics + known failure modes.
- Risk and compliance checklist completed.
- Named owner and rollback strategy.
