# Competition Recon (2026 Prep)

Purpose: capture concrete lessons from prior AI Championship repos and convert them to immediate execution tasks.

## Verified From Prior Public Repos

Source: `https://github.com/amboltio/DM-i-AI-2025`
- Competition format was API-focused with baseline notebooks and one final submission deadline.
- Three use cases were included.
- Top teams were expected to share code/models for verification.

Source: `https://github.com/amboltio/DM-i-AI-2024`
- Structure appears similar: starter resources and challenge framing in a single repo.
- Public repo can be used to benchmark expected folder structure and onboarding speed.

Source: `https://github.com/vidocq/DM-i-AI-2022`
- Historical reference repo exists and is useful for pattern matching (task packaging, baseline flow, evaluation style).

## Verified From Nora 2025 Pages (Local Capture)

Source file: `past-championships-data/nora.ai-competitions-ai-championship-2025-about.txt`
- 2025 event timeline was explicitly defined:
  - Registration close: July 31, 2025 at 23:59
  - Kickoff and use-case reveal: August 1, 2025 at 10:00
  - Hackathon window: August 1-8, 2025
  - Final submission deadline: August 8, 2025 at 14:00
- Participants solved three assignments in a weeklong virtual format.
- Solo or team participation was allowed.
- Norway used the same challenges as Denmark, but Norway and Denmark were scored separately by country.

Source file: `past-championships-data/nora.ai-resources-faq.txt`
- Eligibility: bachelor/master students in Norway.
- Team size: no hard cap stated, recommendation was 2-5; solo explicitly allowed.
- Objective: solve 3 use cases, each worth one-third of total points.
- Technical target: end-to-end machine learning systems with API endpoints (not model-only delivery).
- Evaluation: primarily automated metric scoring; robustness considered if runtime/issues occur.
- External data: explicitly allowed and encouraged.
- Programming language: no explicit restriction.
- Compute: teams could apply for cloud/university compute (examples mentioned: Google, AWS, Azure).
- Prep-before-kickoff: infra/API preparation allowed; challenge-specific work not allowed before reveal.

## Practical Implications For 2026

1. Optimize for a valid end-to-end API submission first, not model sophistication.
2. Expect hard finalization rules: preserve full reproducibility (code, model artifacts, versions, seeds).
3. Prepare governance evidence during development, not at the end.
4. Treat each challenge as independent with fast branch isolation and clean handoffs.

## Solo-Team Setup (Patrick)

Single owner means role-cycling instead of parallel staffing:
- Solver block: implement and instrument.
- Eval block: run fixed seed regression and compare to prior checkpoint.
- Governance block: update risk/checklist before any high-risk change.
- Submission block: package and dry-run submission command.

Recommended cadence:
- 45m build
- 15m eval
- 10m governance update
- 10m decision log + next task

## Immediate Tasks (Do Today)

- [x] Add Team Assignments section in `AGENTS.md` naming Patrick as owner for all five agent roles.
- [ ] Pre-write one submission command template per challenge folder in `solutions/challenge-1/README.md`, `solutions/challenge-2/README.md`, and `solutions/challenge-3/README.md`.
- [ ] Add a reproducibility checklist item for model/code artifact retention in `playbooks/submission-runbook.md`.
- [ ] Create a single-command local eval entrypoint and store it in each challenge README.

## Still Unclear (Track As Assumptions)

- Submission cap/frequency (if multiple submissions were allowed before final lock).
- Exact timezone binding for deadlines (local Norway time vs explicit UTC).
- Explicit policy for third-party hosted inference APIs versus self-hosted endpoints.
- Code disclosure obligations beyond top-team verification.

## Note On `vast.ai`

`vast.ai` may be useful for burst GPU training, but only if competition rules explicitly allow:
- External cloud compute use.
- Third-party hosted models/services.
- Data transfer outside approved jurisdictions.
