# Astar Island — Handoff

## Quick Start

```bash
cd "c:/Users/John Brown/astar-bayesian-run/solutions/astar-island"
python -c "import astar_api, json; rounds=astar_api.api_get('/rounds',auth=False); print(json.dumps([{k:r.get(k) for k in ['round_number','status','round_weight']} for r in rounds[:3]], indent=2))"
```

If a round is active, run the pipeline:
```bash
cd "c:/Users/John Brown/astar-bayesian-run" && python solutions/astar-island/run_bayesian.py
```

After scoring, pull scores:
```bash
cd "c:/Users/John Brown/astar-bayesian-run/solutions/astar-island"
python -c "import astar_api,json; [print(f'R{r[\"round_number\"]}: {r[\"round_score\"]} rank={r[\"rank\"]}/{r[\"total_teams\"]}') for r in astar_api.api_get('/my-rounds',auth=True) if r.get('round_score')]"
```

## State

- **Rank 8** (174.65 weighted), gap to #1 is 2.5 points — very tight top 15
- **Deadline:** March 22, 15:00 CET
- **R15 submitted** (weight 2.08x, dynamic regime) — awaiting score. ~8 rounds remain after R15
- **Branch:** `experimental/bayesian-astar` in worktree `c:/Users/John Brown/astar-bayesian-run/`
- **Pipeline:** 3-phase Bayesian (5 sentinel → 40 coverage → 5 refinement = 50 queries), regime-adaptive C
- **Regime detection:** 1 query, >99% confidence. Dynamic → C=15/floor=0.01. Collapse → C=30/floor=0.005
- **Auto-watcher:** unreliable (laptop sleep kills it). Prefer manual runs
- **No code changes planned.** Pipeline is stable — variance is in the sim, not our model

## Score History

| Rnd | Score | Wt | Regime | Note |
|-----|-------|----|--------|------|
| 1 | 42.6 | 1.05 | D | Hand-tuned priors |
| 2 | 40.8 | 1.10 | D | Over-predicted settlements |
| 3 | 29.2 | 1.16 | C | Missed regime |
| 4 | MISS | 1.22 | ? | — |
| 5 | 54.6 | 1.28 | D | Collapse detector added |
| 6 | 73.6 | 1.34 | D | Bayesian pipeline debut |
| 7 | 42.7 | 1.41 | D | Regression — bucket bug |
| **8** | **88.1** | **1.48** | **C** | **Best — C fix** |
| **9** | **83.8** | **1.55** | **D** | **Best dynamic** |
| 10 | 70.2 | 1.63 | C | Peaked truth outlier |
| 11 | 74.6 | 1.71 | D | — |
| 12 | MISS | 1.80 | ? | PC sleep |
| **13** | **82.9** | **1.89** | **D** | Seeds: 84.6, 82.1, 81.8, 82.8, 83.0 |
| **14** | **66.6** | **1.98** | **D** | Drop — settlement underestimation (see below) |
| 15 | *pending* | 2.08 | D | Submitted, awaiting score |

## R14 Post-Mortem (66.6 avg, seeds: 67.7, 68.4, 68.4, 65.6, 62.7)

Pipeline used C=15 (same as all prior dynamic rounds — the new dynamic-C code made no difference). Settlement layer was the failure: predicted sparse settlements, ground truth showed aggressive expansion. Cause is round variance in hidden sim parameters, not a code regression. **No revert needed.**

## Key Rules

- Never submit `0.0` probabilities — instant KL explosion
- Hidden params shared across all 5 seeds — cross-seed pooling is the main lever
- Score formula: `100 × exp(-3 × entropy_weighted_KL)` — high-entropy cells dominate
- `GET` endpoints are free; only `/simulate` costs queries (50/round)
- Always run from the worktree, not main repo

## If Worktree Missing

```bash
cd "c:/Users/John Brown/ai-championship-warroom"
git worktree add ../astar-bayesian-run experimental/bayesian-astar
cp solutions/astar-island/.token ../astar-bayesian-run/solutions/astar-island/.token
```

## Ground Truth Retrieval

**RESOLVED.** The endpoint was already in the codebase:

```
GET /analysis/{round_id}/{seed_index}   (auth required)
```

Returns: `{ground_truth, prediction, score, width, height, initial_grid}` — ground_truth is a 40×40×6 probability tensor.

Export all seeds for a completed round:
```bash
cd "c:/Users/John Brown/ai-championship-warroom/solutions/astar-island"
python export_round_analysis.py --round-id <uuid> --seeds 5
```

**All 14 completed rounds (R1–R14) now have ground truth exported** to `artifacts/round_{id}/analysis/`. The replay system (`replay_bayesian.py`) can validate against any of them, not just R10.

## Known Gaps

- *(Ground truth gap resolved — see above)*

## Research Archive

Detailed analysis of regime detection, C tuning replay, scoring insights, and per-round facts: see [round-history.md](round-history.md).
