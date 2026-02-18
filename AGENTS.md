# AGENTS.md

This file defines agent roles and handoff contracts for competition execution.

## Operating Model
- One owner per challenge.
- Daily sync on blockers, metrics, and risks.
- Any high-risk submission requires owner + governance sign-off.

## Agent Roster

## Team Assignments (Current)
- Team member: Patrick
- Shift coverage: Solo coverage (all active competition hours)
- Role mapping:
  - `solver-agent`: Patrick
  - `eval-agent`: Patrick
  - `redteam-agent`: Patrick
  - `governance-agent`: Patrick
  - `submission-agent`: Patrick

### 1) `solver-agent`
Scope:
- Implements baseline and advanced approaches.
- Optimizes data processing, modeling, and inference.

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

## Handoff Contract
Every handoff must include:
- Current objective.
- Exact commit or artifact reference.
- What is proven.
- What is assumed.
- Next highest-priority task.

## Priority Rules
1. Validity over novelty.
2. Reproducibility over one-off wins.
3. Compliance blockers override speed.
