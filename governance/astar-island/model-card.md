# Model Card — Astar Island: Viking World Prediction

Challenge: Astar Island
Owner: AD (Andrew/John)
Version: v1 (competition)
Date: 2026-03-19

---

## Model Overview

- **Name:** Astar Island Terrain Probability Predictor
- **Architecture:** Multi-phase statistical prediction pipeline (no neural network required at baseline). Phases: tiling observation → cross-seed parameter inference → proximity-weighted probability tensor construction.
- **Owner:** AD (Andrew/John)
- **Challenge:** NM i AI — Astar Island
- **Date:** 2026-03-22 (final submission)

---

## Intended Use

- **Primary use:** Given observations of a Norse civilisation simulation (post-50-year run), predict probability distributions over 6 terrain classes for every cell in a 40×40 grid. Submit a H×W×6 tensor where each cell sums to 1.0.
- **Users:** NM i AI automated scoring system (KL divergence against Monte Carlo ground truth). Operator: AD.
- **Environment:** Local Python (CPU-only). No hosted endpoint — pure computation.
- **Out of scope:** Not a simulator or generative model. Does not run the simulation. Does not make any real-world decisions.

---

## Data

- **Training sources:** No offline training. Model is built from:
  1. Initial grid state (year 0, freely available)
  2. Runtime observations from competition API (up to 50 queries)
  3. Terrain-based priors (hand-designed, derived from simulation mechanics)
- **Validation:** Cross-seed consistency checks (hidden params are same across 5 seeds — inconsistencies flag inference errors).
- **Data limitations:** 50 queries is the hard ceiling. Unobserved cells rely on proximity interpolation and inferred parameters, not direct evidence.

---

## Performance

- **Primary metric:** Competition score = `max(0, min(100, 100 × exp(-3 × weighted_KL)))` where weighted_KL weights cells by their entropy. Target: 60–80.
- **Secondary metrics:** Budget efficiency (queries used vs. map coverage); cross-seed parameter inference accuracy.
- **Known weak spots:**
  - Cells near settlement boundaries — highest entropy, hardest to predict, highest scoring weight.
  - Remote corners — low direct observation probability with 9-query tile budget.
  - Round 1 — no prior round data to calibrate parameter inference.

---

## Safety and Risk

- **Abuse / misuse considerations:** None. Read-only observation system with no real-world effects.
- **Failure modes:**
  1. **Zero probability in tensor** → KL divergence → ∞ for that cell → large score hit. Cardinal rule: always apply 0.01 floor before submission.
  2. **Missing seed submission** → score = 0 for that seed. Always submit all 5 seeds.
  3. **Budget overrun** → queries exhausted before all seeds observed → degrade to prior for unobserved seeds.
  4. **API auth failure** → token expired or invalid → zero observations possible.
- **Mitigations:** See R-006 through R-009 in risk register. 0.01 floor enforced in code. Budget plan committed before observation run.

---

## Operational Notes

- **Repro command:**
  ```bash
  python solutions/astar-island/run_observation_cycle.py
  python solutions/astar-island/model.py
  # Outputs submission tensor for all 5 seeds
  ```
- **Dependencies:** `numpy`, `requests` (pinned in requirements.txt). No GPU required.
- **Rollback / fallback:** If observation run fails mid-budget, submit baseline (terrain priors only) for remaining seeds — baseline scores 20–40 vs. 0 for missing.
- **Token setup:** Copy JWT from `app.ainm.no` browser session into `solutions/astar-island/.token`. Verify with `python solutions/astar-island/client.py`.
