# Astar Island - Next Steps

## Current Round

- [x] Browser `access_token` captured and stored in `solutions/astar-island/.token`
- [x] Local token-loading workflow created
- [x] Safe API connectivity verified
- [x] Active round confirmed
- [x] Team query budget checked
- [x] Check whether the team already has submissions for seeds 0-4
- [x] Prior-only baseline submitted for seeds 0-4
- [x] Full 45-query coverage pass completed across all 5 seeds
- [x] Final 3 repeat queries used on highest-dynamic viewport
- [x] Improved observation-based submission accepted for seeds 0-4
- [x] Read-only poller built and verified with one-shot check
- [x] Round 1 completed and scored
- [x] Round 1 full analysis exported locally for all 5 seeds
- [x] Round 2 baseline submitted for seeds 0-4
- [x] Round 2 full 45-query coverage pass completed across all 5 seeds
- [x] Round 2 final 3 repeat queries used with corrected viewport payloads
- [x] Round 2 improved observation-based submission accepted for seeds 0-4
- [x] Round 2 final 2 extra repeat queries spent on highest-value unrepeated hotspots
- [x] Round 2 final overwrite submitted after using the full `50 / 50` query budget
- [x] Round 2 completed and scored
- [x] Round 2 full analysis exported locally for all 5 seeds

## Immediate Priorities

- [x] If no team submissions exist yet: generate and submit prior-only baseline for all 5 seeds immediately
- [x] If submissions already exist: inspect status before overwriting anything
- [x] Save current round metadata and initial states locally for reproducible work
- [x] Build baseline tensor generator from initial terrain + visible settlements
- [x] Validate tensor shape, sums, and 0.01 floor before any submit
- [x] Treat reveals as stochastic samples of the 50-year end state, not ground truth
- [x] Plan the remaining 48-query observation strategy
- [x] Script `/simulate` data collection with artifact logging
- [x] Identify the highest-value repeat-query targets after first full coverage pass
- [x] Wait for scoring and capture round results
- [x] Pull `/analysis/{round_id}/{seed_index}` when available
- [ ] Convert round-1 findings into the next-round starting policy
- [x] Fix repeat-query payload handling so repeat `/simulate` calls target the intended viewport
- [x] Run the read-only poller through scoring / next-round transition
- [ ] Convert round-2 analysis into concrete prior and observation-weight updates before the next active round

## Query Discipline

- [x] Stop using the website UI for map reveal/query
- [x] Preserve remaining query budget for scripted use only
- [x] Use `GET` endpoints freely; only `/simulate` spends queries
- [x] Treat `/submit` as overwrite-per-seed and coordinate before replacing team work

## Round Facts

- Round 1 ID: `71451d74-be9f-471f-aacd-a41f3b68a9cd`
- Round 1 status: `completed`
- Seeds: `5`
- Map: `40x40`
- Query budget at first scripted check: `2 / 50` used
- Remaining query budget after improved submission: `0`
- Round 1 deadline: `2026-03-19 21:42:19 CET`
- Round 1 final score: `42.623`
- Round 1 seed scores: `42.3687, 41.5476, 44.6877, 41.6614, 42.8494`
- Round 1 rank: `39 / 117`
- Baseline submission status: prior-only tensor accepted for all 5 seeds
- Improved submission status: observation-based overwrite accepted for all 5 seeds
- Saved simulation artifacts: `48`
- Round 2 ID: `76909e29-f664-4b2f-b16b-61b7507277e9`
- Round 2 status: `active`
- Round 2 baseline submission status: prior-only tensor accepted for all 5 seeds
- Round 2 improved submission status: observation-based overwrite accepted for all 5 seeds
- Round 2 submissions: `5`
- Round 2 baseline submit timestamps (UTC): `2026-03-19T21:52:04.932488+00:00` to `2026-03-19T21:52:45.329343+00:00`
- Round 2 improved submit timestamps (UTC): `2026-03-19T22:06:06.082797+00:00` to `2026-03-19T22:06:20.111304+00:00`
- Round 2 extra repeat targets: `seed 1 @ (15,0,15,15)` and `seed 2 @ (0,15,15,15)`
- Round 2 query budget after final overwrite: `50 / 50` used
- Round 2 queries remaining: `0`
- Round 2 final score: `40.8117`
- Round 2 seed scores: `41.3371, 40.6250, 40.8440, 41.0013, 40.2510`
- Round 2 rank: `95 / 153`
- Round 2 analysis status: exported for all 5 seeds
- Round 2 analysis finding: model over-predicted settlements materially (`pred class 1 = 534` vs `truth class 1 = 155`)

## Working Rules

- Never submit any `0.0` probabilities
- Missing a seed means `0` for that seed
- Hidden parameters are shared across all 5 seeds
- Full-map tiling costs 9 queries per seed with `15x15` viewports
- Extra reveals are not directly penalized, but every `/simulate` call spends 1 of 50 total queries

## Artifact References

- Round artifact folder: `solutions/astar-island/artifacts/round_71451d74-be9f-471f-aacd-a41f3b68a9cd/`
- Coverage + repeat samples: `solutions/astar-island/artifacts/round_71451d74-be9f-471f-aacd-a41f3b68a9cd/simulate/`
- Cycle summary: `solutions/astar-island/artifacts/round_71451d74-be9f-471f-aacd-a41f3b68a9cd/observation_cycle_summary.json`
- Final improved tensors: `solutions/astar-island/artifacts/round_71451d74-be9f-471f-aacd-a41f3b68a9cd/improved_prediction_seed_*.json`
- Poller docs: `solutions/astar-island/POLLER.md`
- Poller state dir: `solutions/astar-island/artifacts/poller/`
- Round 1 exported analysis: `solutions/astar-island/artifacts/round_71451d74-be9f-471f-aacd-a41f3b68a9cd/analysis/`
- Round 2 baseline artifacts: `solutions/astar-island/artifacts/round_76909e29-f664-4b2f-b16b-61b7507277e9/`
- Round 2 coverage + repeat samples: `solutions/astar-island/artifacts/round_76909e29-f664-4b2f-b16b-61b7507277e9/simulate/`
- Round 2 cycle summary: `solutions/astar-island/artifacts/round_76909e29-f664-4b2f-b16b-61b7507277e9/observation_cycle_summary.json`
- Round 2 extra repeat summary: `solutions/astar-island/artifacts/round_76909e29-f664-4b2f-b16b-61b7507277e9/extra_repeat_summary.json`
- Round 2 improved tensors: `solutions/astar-island/artifacts/round_76909e29-f664-4b2f-b16b-61b7507277e9/improved_prediction_seed_*.json`
- Round 2 exported analysis: `solutions/astar-island/artifacts/round_76909e29-f664-4b2f-b16b-61b7507277e9/analysis/`

## Fresh Context Start Prompt

Use this at the start of a new context window:

```text
Read only these files first:
1. solutions/astar-island/next-steps.md
2. solutions/astar-island/TOKEN_WORKFLOW.md
3. solutions/astar-island/artifacts/round_71451d74-be9f-471f-aacd-a41f3b68a9cd/observation_cycle_summary.json
4. solutions/astar-island/POLLER.md
5. solutions/astar-island/artifacts/poller/latest_state.json (if it exists)
6. solutions/astar-island/submit_prior_baseline.py
7. solutions/astar-island/run_observation_cycle.py

Task: resume the Astar Island challenge from the current handoff state. Do not use the website UI. Use the local token workflow in solutions/astar-island/.token. First verify current round status, budget, my predictions, and whether /analysis is available. Then continue with the highest-priority unfinished item in solutions/astar-island/next-steps.md and update that file before stopping.
```

## Fresh Context End Prompt

Use this before ending a context window:

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

- Current objective: turn round-2 analysis into a safer round-3 starting policy before the next active round opens.
- Exact artifact reference: `solutions/astar-island/artifacts/round_76909e29-f664-4b2f-b16b-61b7507277e9/`
- What is proven: token workflow works; round 1 scored `42.623` with rank `39/117`; `/analysis` is available for all 5 round-1 and round-2 seeds; round 2 baseline, improved submission, and final overwrite were all accepted for all 5 seeds; round 2 query budget was fully used at `50 / 50`; repeat `/simulate` calls must send `viewport_x/viewport_y/viewport_w/viewport_h`, and the local workflow has been fixed accordingly; round 2 still underperformed round 1 (`40.8117` vs `42.623`) despite the cleaner execution.
- What is assumed: the next improvement should come from reducing settlement-heavy bias in priors and/or observation weighting rather than from further query-routing changes alone.
- Next highest-priority task: quantify a conservative prior update for plains and near-settlement cells before the next round, then re-check whether a new active round exists.
