# Challenge Intake Playbook

Use this within the first 60-90 minutes after challenge release.

## Kickoff Trigger (Captain-Owned)
- Captain posts official challenge GitHub link in `README.md` under `Challenge Kickoff (Captain Action)`.
- Record challenge repo URL in `ops/decision-log.md`.
- Confirm challenge identifier (`challenge-1`, `challenge-2`, or `challenge-3`).

## Step 1: Parse Challenge
- Objective function and scoring metric.
- Input/output constraints.
- API limits and runtime budget.
- Explicit and implicit rules.

## Step 2: Define Win Strategy
- Baseline approach (deliverable in 2-4 hours).
- Stretch approach (higher upside, higher risk).
- Kill criteria for dead-end experiments.

## Step 3: Build Work Breakdown
- Data prep owner.
- Model owner.
- Eval owner.
- Governance owner.

## Step 4: Risk and Compliance Scan
- Data rights and permitted usage.
- Sensitive data presence.
- Security implications (prompt injection, unsafe outputs, leakage).

## Step 5: Commit Initial Plan
- Record in `ops/decision-log.md`.
- Open challenge branch and assign owners.
