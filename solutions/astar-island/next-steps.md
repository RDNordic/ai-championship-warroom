# Astar Island — Handoff

## Quick Start

```bash
# Check round status
cd "c:/Users/John Brown/ai-championship-warroom/solutions/astar-island"
python -c "import astar_api,json; rounds=astar_api.api_get('/rounds',auth=False); [print(f'R{r[\"round_number\"]}: {r[\"status\"]} w={r[\"round_weight\"]:.2f}') for r in sorted(rounds, key=lambda x:x['round_number'])[-5:]]"

# Run pipeline (when a round is active)
cd "c:/Users/John Brown/astar-bayesian-run" && python solutions/astar-island/run_bayesian.py

# Pull scores
cd "c:/Users/John Brown/ai-championship-warroom/solutions/astar-island"
python -c "import astar_api,json; [print(f'R{r[\"round_number\"]}: {r[\"round_score\"]} rank={r[\"rank\"]}/{r[\"total_teams\"]}') for r in astar_api.api_get('/my-rounds',auth=True) if r.get('round_score')]"

# Export ground truth after scoring
python export_round_analysis.py --round-id <uuid> --seeds 5
```

## State (2026-03-22 early morning)

- **Weighted avg: 68.0** (collapsed from 87 peak — three sub-70 rounds at the heaviest weights)
- **Deadline:** March 22, 15:00 CET (~13h remain)
- **R18 completed** (65.2, weight 2.41x — worst timing). Awaiting R19
- **Branch:** `experimental/bayesian-astar` in worktree `c:/Users/John Brown/astar-bayesian-run/`
- **Pipeline:** 3-phase Bayesian (5 sentinel → 40 coverage → 5 refinement = 50 queries), regime-adaptive
- **Decision: no code changes.** Pipeline scores 79-88 on favorable rounds. Bad rounds are hidden-param variance
- **Strategy: keep submitting.** Every high-weight round we score well on helps recovery

## Score History

| Rnd | Score | Wt | Regime | Note |
|-----|-------|----|--------|------|
| 1 | 42.6 | 1.05 | D | Hand-tuned priors (early pipeline) |
| 2 | 40.8 | 1.10 | D | Over-predicted settlements |
| 3 | 29.2 | 1.16 | C | Missed regime |
| 4 | MISS | 1.22 | ? | — |
| 5 | 54.6 | 1.28 | D | Collapse detector added |
| 6 | 73.6 | 1.34 | D | Bayesian pipeline debut |
| 7 | 42.7 | 1.41 | D | Regression — bucket bug |
| **8** | **88.1** | **1.48** | **C** | **Best ever — C fix** |
| **9** | **83.8** | **1.55** | **D** | **Best dynamic** |
| 10 | 70.2 | 1.63 | C | Peaked truth outlier |
| 11 | 74.6 | 1.71 | D | — |
| 12 | MISS | 1.80 | ? | PC sleep |
| **13** | **82.9** | **1.89** | **D** | Consistent |
| 14 | 66.6 | 1.98 | D | Extreme settlement expansion |
| **15** | **82.9** | **2.08** | **D** | Consistent |
| 16 | 69.1 | 2.18 | D | Under-predicted settlements |
| 17 | 79.1 | 2.29 | D | Decent but below mean |
| 18 | 65.2 | 2.41 | D | Worst seed ever (57.9). Settlement variance |

## The Problem

Three sub-70 rounds (R14, R16, R18) all landed at the heaviest weights (1.98, 2.18, 2.41). This is pure bad luck — the pipeline scores 79-88 on ~60% of dynamic rounds but the weighted scoring amplified the bad ones.

Settlement prediction is always the #1 KL source:
- Our 5 observation samples sometimes don't represent the Monte Carlo mean well
- This is a sample-size problem with a 50-query hard cap
- No code change fixes it without more queries

## Ground Truth Retrieval

```
GET /analysis/{round_id}/{seed_index}   (auth required)
```

Returns `{ground_truth, prediction, score, width, height, initial_grid}` — ground_truth is 40×40×6 tensor.

**All completed rounds (R1–R18) have ground truth exported** to `artifacts/round_{id}/analysis/`.

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

## Research Archive

Detailed analysis of regime detection, C tuning replay, scoring insights, and per-round facts: see [round-history.md](round-history.md).
