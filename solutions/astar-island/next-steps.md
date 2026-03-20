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
- [x] Round 3 active round confirmed
- [x] Round 3 team budget checked
- [x] Round 3 existing submissions checked before overwrite
- [x] Round 3 baseline submitted for seeds 0-4 using the updated conservative prior
- [x] Round 3 full 45-query coverage pass completed across all 5 seeds
- [x] Round 3 final 3 repeat queries used via the scripted workflow
- [x] Round 3 improved observation-based submission accepted for seeds 0-4
- [x] Round 3 completed and scored
- [x] Round 3 full analysis exported locally for all 5 seeds
- [x] Round 5 active round confirmed
- [x] Round 5 baseline submitted for seeds 0-4 using the updated conservative prior
- [x] Round 5 full 45-query coverage pass completed across all 5 seeds
- [x] Round 5 final 3 repeat queries used via the scripted workflow
- [x] Round 5 final 2 extra repeat queries spent on highest-value unrepeated hotspots
- [x] Round 5 final overwrite submitted after using the full `50 / 50` query budget
- [x] Round 5 analysis exported for all 5 seeds
- [x] Round 5 scored: mean `54.60` (best round so far)
- [x] Experimental Bayesian branch created and all modules implemented
- [x] Replay validation passed: 20/20 seeds improved across all 4 rounds
- [x] Round 6 submitted using experimental Bayesian pipeline (all 5 seeds accepted)

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
- [x] Convert round-1 findings into the next-round starting policy
- [x] Fix repeat-query payload handling so repeat `/simulate` calls target the intended viewport
- [x] Run the read-only poller through scoring / next-round transition
- [x] Convert round-2 analysis into concrete prior and observation-weight updates before the next active round
- [x] Wait for round-3 scoring and capture round results
- [x] Pull `/analysis/{round_id}/{seed_index}` for round 3 when available
- [x] Add a collapse detector so near-zero dynamic coverage forces a much safer prior/update regime
- [x] Run the round-5 full 45-query coverage pass across all 5 seeds
- [x] Use the remaining round-5 repeat queries after the first coverage pass
- [x] Submit the round-5 observation-based overwrite for seeds 0-4
- [x] Export round-5 `/analysis/{round_id}/{seed_index}` when available
- [x] Wait for round-5 scoring and capture round results

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
- Round 2 status: `completed`
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
- Round 2 offline replay finding: the old policy replays at `42.6351` / `40.8117` on rounds 1 / 2 after observations, while the updated conservative policy replays at `52.4455` / `52.9291`
- Round 3 ID: `f1dac9a9-5cf1-49a9-8f17-d6cb5d5ba5cb`
- Round 3 status: `completed`
- Round 3 round number: `3`
- Round 3 baseline submission status: accepted for seeds `0-4`
- Round 3 improved submission status: accepted for seeds `0-4`
- Round 3 improved submit timestamps (UTC): `2026-03-20T00:46:16.496832+00:00` to `2026-03-20T00:46:24.791168+00:00`
- Round 3 final score: `29.2383`
- Round 3 seed scores: `30.3371, 28.4992, 29.0390, 30.0836, 28.2327`
- Round 3 rank: `63 / 100`
- Round 3 final query usage: `48 / 50`
- Round 3 close time (UTC): `2026-03-20T02:53:20.948277+00:00`
- Round 3 analysis status: exported for all 5 seeds
- Round 3 repeat-target finding: the scripted dynamic-score heuristic returned `0` for all selected repeat targets, so the last `2` queries should only be spent if a better manual hotspot heuristic is defined
- Round 3 replay finding after the new collapse detector: the same saved observations would have scored about `77.10`, so the main miss was failing to detect a near-extinction round and globally crush dynamic mass
- Round 4 ID: `8e839974-b13b-407b-a5e7-fc749d877195`
- Round 4 status: `completed`
- Round 4 submissions: `0`
- Round 4 final score: `null` (missed round)
- Round 5 ID: `fd3c92ff-3178-4dc9-8d9b-acf389b3982b`
- Round 5 status: `completed`
- Round 5 round number: `5`
- Round 5 baseline submission status: accepted for seeds `0-4`
- Round 5 submissions: `5`
- Round 5 coverage dynamic rate: `0.13817` (`1399 / 10125` observed cells were class `1/2/3`)
- Round 5 collapse detector result: `false` (normal dynamic regime, so standard repeat logic was used)
- Round 5 improved submission status: accepted for seeds `0-4`
- Round 5 extra repeat targets: `seed 1 @ (15,0,15,15)` and `seed 2 @ (15,25,15,15)`
- Round 5 query budget now: `50 / 50` used
- Round 5 queries remaining: `0`
- Round 5 close time (UTC): `2026-03-20T08:48:10.400305+00:00`
- Round 5 final score: `54.5997`
- Round 5 seed scores: `53.1294, 51.0326, 55.1128, 56.498, 57.2255`
- Round 5 analysis status: exported for all 5 seeds
- Round 5 analysis finding: mild over-prediction of dynamic mass (pred ~420-435 vs truth ~378-414 argmax-dynamic cells); probability mass ~600 vs ~550 truth. Conservative prior is working — much closer than round 2's 534 vs 155 gap
- Round 5 exported analysis: `solutions/astar-island/artifacts/round_fd3c92ff-3178-4dc9-8d9b-acf389b3982b/analysis/`
- Round 6 ID: `ae78003a-4efe-425a-881a-d16a39bca0ad`
- Round 6 status: `active`
- Round 6 round number: `6`
- Round 6 approach: `experimental_bayesian`
- Round 6 regime posterior: `P(dynamic) = 1.0`
- Round 6 query budget: `50 / 50` used (5 sentinel + 40 coverage + 5 refinement)
- Round 6 submission status: accepted for seeds `0-4`
- Round 6 close time (UTC): `2026-03-20T11:53:16.644541+00:00`
- Round 6 artifacts: `solutions/astar-island/artifacts/round_ae78003a-4efe-425a-881a-d16a39bca0ad/`

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
- Round 3 baseline artifacts: `solutions/astar-island/artifacts/round_f1dac9a9-5cf1-49a9-8f17-d6cb5d5ba5cb/`
- Round 3 coverage + repeat samples: `solutions/astar-island/artifacts/round_f1dac9a9-5cf1-49a9-8f17-d6cb5d5ba5cb/simulate/`
- Round 3 cycle summary: `solutions/astar-island/artifacts/round_f1dac9a9-5cf1-49a9-8f17-d6cb5d5ba5cb/observation_cycle_summary.json`
- Round 3 improved tensors: `solutions/astar-island/artifacts/round_f1dac9a9-5cf1-49a9-8f17-d6cb5d5ba5cb/improved_prediction_seed_*.json`
- Round 3 exported analysis: `solutions/astar-island/artifacts/round_f1dac9a9-5cf1-49a9-8f17-d6cb5d5ba5cb/analysis/`
- Round 5 baseline artifacts: `solutions/astar-island/artifacts/round_fd3c92ff-3178-4dc9-8d9b-acf389b3982b/`
- Round 5 coverage + repeat samples: `solutions/astar-island/artifacts/round_fd3c92ff-3178-4dc9-8d9b-acf389b3982b/simulate/`
- Round 5 cycle summary: `solutions/astar-island/artifacts/round_fd3c92ff-3178-4dc9-8d9b-acf389b3982b/observation_cycle_summary.json`
- Round 5 extra repeat summary: `solutions/astar-island/artifacts/round_fd3c92ff-3178-4dc9-8d9b-acf389b3982b/extra_repeat_summary.json`
- Round 5 improved tensors: `solutions/astar-island/artifacts/round_fd3c92ff-3178-4dc9-8d9b-acf389b3982b/improved_prediction_seed_*.json`

## Experimental: Bayesian Branch (PARALLEL PROTOTYPE)

This is a separate experimental effort on branch `experimental/bayesian-astar`.
The current baseline code on `main` is preserved and remains the fallback.
The formulation is in `solutions/astar-island/astar_island_bayesian_formulation.md`.

### Score History (baseline approach)

| Round | Score | Rank | Notes |
|-------|-------|------|-------|
| 1 | 42.62 | 39/117 | First run, hand-tuned priors |
| 2 | 40.81 | 95/153 | Over-predicted dynamic mass badly (534 vs 155) |
| 3 | 29.24 | 63/100 | Collapse round — missed regime, replay showed 77.10 possible |
| 4 | null | — | Missed round entirely |
| 5 | 54.60 | TBD | Conservative prior + collapse detector. Best score so far |

### Key problems the Bayesian approach addresses

1. **No cross-seed pooling** — baseline treats each seed independently, wastes shared signal
2. **Post-hoc regime detection** — collapse detected after all 45 queries, not after 5 sentinel queries
3. **Ad-hoc observation updates** — not proper Dirichlet-multinomial conjugate updates
4. **Fixed query strategy** — always tiles 9x5=45 then repeats 3-5, never adapts to regime
5. **No entropy weighting** — submits naive posterior mean, not entropy-weighted optimal

### Implementation plan

All new code lives in `solutions/astar-island/experimental/`. Imports from existing `astar_api.py` and reuses utilities.

- [x] Step 0: Create branch `experimental/bayesian-astar` and directory structure
- [x] Step 1: Feature buckets + Dirichlet priors (`features.py`, `dirichlet.py`, `config.py`)
- [x] Step 2: Cross-seed pooling (`pooling.py`)
- [x] Step 3: Regime detection (`regime.py`)
- [x] Step 4: Adaptive query planner (`query_planner.py`)
- [x] Step 5: Predictor + submission pipeline (`predictor.py`, `submission.py`, `runner.py`)
- [x] Step 6: Offline validation — replay rounds 1, 2, 3, 5: **20/20 seeds improved, 4/4 rounds BETTER**
- [x] Step 7: Live deployment — round 6 submitted using Bayesian pipeline, all seeds accepted

### Validation gate

The experimental branch must score higher on offline replay for at least 3 of 4 completed rounds (1, 2, 3, 5) before being used for live submission. Otherwise fall back to baseline.

### Files (experimental branch only)

```
solutions/astar-island/experimental/
├── __init__.py
├── config.py          # All hyperparameters
├── features.py        # Cell feature extraction
├── dirichlet.py       # Dirichlet-multinomial model
├── pooling.py         # Cross-seed evidence aggregation
├── regime.py          # Bayesian regime detection
├── query_planner.py   # 3-phase adaptive query strategy
├── predictor.py       # Full prediction pipeline
├── submission.py      # Entropy-weighted posterior mean
├── runner.py          # Drop-in replacement for run_observation_cycle.py
└── replay.py          # Offline replay validation against saved artifacts
```

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

- Current objective: monitor round 6 scoring (Bayesian submission), export analysis, and continue using the Bayesian pipeline for round 7+.
- Current branch: `experimental/bayesian-astar`
- Exact artifact reference: `solutions/astar-island/artifacts/round_ae78003a-4efe-425a-881a-d16a39bca0ad/`
- What is proven: the experimental Bayesian pipeline dominates the baseline on all 4 replayed rounds (20/20 seeds improved); round 6 submitted using the Bayesian pipeline with all 5 seeds accepted; regime detection correctly identified dynamic (rounds 1,2,5,6) and collapse (round 3); cross-seed pooling and proper Dirichlet updates provide large KL improvements.
- What is assumed: the Dirichlet prior hyperparameters in `config.py` are reasonable defaults but not yet calibrated from analysis data; the live round 6 score will confirm whether replay gains translate to API score improvements.
- Next highest-priority task: wait for round 6 scoring, export `/analysis`, compare API score against round 5 baseline (54.60), then use the Bayesian pipeline for round 7. If round 6 scores worse than round 5, investigate and recalibrate priors before round 8.
- Fallback: baseline code on `main` branch remains intact. Switch back with `git checkout main` and use `run_observation_cycle.py`.
- Live deployment command: `python solutions/astar-island/run_bayesian.py`
- Replay validation command: `python solutions/astar-island/replay_bayesian.py`
