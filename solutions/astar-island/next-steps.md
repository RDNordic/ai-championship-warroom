# Astar Island - Next Steps

> Historical round checklists, facts, and artifact references archived in [round-history.md](round-history.md).

## Current Status

- [x] Round 7 submitted using Bayesian pipeline (all 5 seeds accepted)
- [ ] Round 7 scoring — export `/analysis` when available
- [ ] Round 7 score comparison against round 6 (`73.59`)
- [ ] Round 8+ — run `python solutions/astar-island/run_bayesian.py` when active
- [ ] Optional: calibrate Dirichlet priors in `config.py` from round 6+7 analysis data
- [ ] Optional: implement entropy-weighted submission (currently using plain posterior mean)

## Score History

| Round | Score | Approach | Notes |
|-------|-------|----------|-------|
| 1 | 42.62 | Baseline | Hand-tuned priors |
| 2 | 40.81 | Baseline | Over-predicted dynamic mass (534 vs 155) |
| 3 | 29.24 | Baseline | Collapse round — missed regime |
| 4 | null | Missed | — |
| 5 | 54.60 | Baseline v2 | Conservative prior + collapse detector |
| **6** | **73.59** | **Bayesian** | **Cross-seed pooling + Dirichlet + regime detection** |

## Working Rules

- Never submit any `0.0` probabilities
- Missing a seed means `0` for that seed
- Hidden parameters are shared across all 5 seeds
- Full-map tiling costs 9 queries per seed with `15x15` viewports
- Every `/simulate` call spends 1 of 50 total queries; `GET` endpoints are free
- Treat `/submit` as overwrite-per-seed — coordinate before replacing team work
- Do not use the website UI for queries — scripted workflow only

## Round 6 Facts (Latest Completed)

- Round 6 ID: `ae78003a-4efe-425a-881a-d16a39bca0ad`
- Round 6 approach: `experimental_bayesian`
- Round 6 regime posterior: `P(dynamic) = 1.0`
- Round 6 query budget: `50 / 50` used (5 sentinel + 40 coverage + 5 refinement)
- Round 6 final score: `73.5851`
- Round 6 seed scores: `74.0113, 72.5254, 71.3368, 74.9609, 75.0909`
- Round 6 artifacts: `solutions/astar-island/artifacts/round_ae78003a-4efe-425a-881a-d16a39bca0ad/`
- Round 6 exported analysis: `solutions/astar-island/artifacts/round_ae78003a-4efe-425a-881a-d16a39bca0ad/analysis/`

## Bayesian Pipeline

Branch: `experimental/bayesian-astar` (now the primary approach; baseline on `main` is the fallback).
Formulation: `solutions/astar-island/astar_island_bayesian_formulation.md`

Key advantages over baseline:
1. **Cross-seed pooling** — shares signal across all 5 seeds
2. **Early regime detection** — collapse detected after 5 sentinel queries, not after all 45
3. **Proper Dirichlet-multinomial** conjugate updates
4. **Adaptive query strategy** — 5 sentinel + 40 coverage + 5 refinement (adapts to regime)

Code: `solutions/astar-island/experimental/` — see files on disk for details.

## Fresh Context Start Prompt

```text
Read only these files first:
1. solutions/astar-island/next-steps.md
2. solutions/astar-island/TOKEN_WORKFLOW.md
3. solutions/astar-island/run_bayesian.py
4. solutions/astar-island/experimental/config.py

Task: resume the Astar Island challenge from the current handoff state. Do not use the website UI. Use the local token workflow in solutions/astar-island/.token. First verify current round status, budget, my predictions, and whether /analysis is available. Then continue with the highest-priority unfinished item in next-steps.md and update that file before stopping.
```

## Fresh Context End Prompt

```text
Before stopping:
1. Update solutions/astar-island/next-steps.md with current status, exact round state, what is proven, what is assumed, and the next highest-priority task.
2. List every file changed.
3. List every command run that matters.
4. Record whether queries were spent, submissions were overwritten, or analysis endpoints were checked.
5. If a new artifact folder or summary file was created, add its exact path to next-steps.md.
Then give a concise handoff summary.
```

## Handoff Contract

- Current objective: continue using the Bayesian pipeline for round 7+. Consider calibrating Dirichlet priors from round 6 analysis data for further gains.
- Current branch: `experimental/bayesian-astar`
- Exact artifact reference: `solutions/astar-island/artifacts/round_ae78003a-4efe-425a-881a-d16a39bca0ad/`
- What is proven: the Bayesian pipeline scored `73.59` on round 6, a 35% improvement over the round 5 baseline (`54.60`); replay validation showed 20/20 seeds improved across all 4 historic rounds; regime detection correctly identified dynamic (rounds 1,2,5,6) and collapse (round 3).
- What is assumed: Dirichlet priors in `config.py` are reasonable defaults but not yet calibrated from analysis data; further gains possible from prior calibration and entropy-weighted submission.
- Next highest-priority task: export round 7 analysis when scoring completes, then run Bayesian pipeline on round 8+.
- Fallback: baseline code on `main` branch remains intact. Switch back with `git checkout main` and use `run_observation_cycle.py`.
- Live deployment command: `python solutions/astar-island/run_bayesian.py`
- Replay validation command: `python solutions/astar-island/replay_bayesian.py`
