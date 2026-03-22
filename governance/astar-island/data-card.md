# Data Card — Astar Island: Viking World Prediction

Challenge: Astar Island
Owner: AD (Andrew/John)
Date: 2026-03-22 (final submission)

---

## Dataset Overview

- **Name:** Astar Island Simulation Observations
- **Version:** Competition round (March 2026)
- **Source:** NM i AI Astar Island API — `api.ainm.no/astar-island`
- **License / usage basis:** NM i AI competition rules. All data is competition-issued synthetic simulation output. No external data rights required.
- **Owner:** Competition infrastructure (read/query by our team within budget)

---

## Composition

- **Map:** 40×40 grid per seed. 6 terrain classes: Empty/Ocean/Plains (0), Settlement (1), Port (2), Ruin (3), Forest (4), Mountain (5).
- **Seeds per round:** 5 — same hidden parameters, different stochastic runs.
- **Queries per round:** 50 total across all seeds. Max viewport: 15×15 cells per query.
- **Observable data per query:** Grid values in viewport + settlement stats (population, food, wealth, defense, has_port, alive, owner_id) for settlements visible in viewport.
- **Initial state:** Full 40×40 grid at year 0 available without spending queries (via `/rounds/{round_id}`).
- **Missingness:** Cells outside observed viewports are unobserved for that seed. With 9 queries/seed, full map coverage is achievable but leaves ~1 query/seed for targeted re-observation.

---

## Collection and Processing

- **Collection method:** Active querying via POST `/simulate`. Each query costs 1 from the shared 50-query budget. Observations collected during the ~2h45min prediction window per round.
- **Preprocessing steps:**
  1. Tile the full 40×40 map (9 queries × ceil(40/15)² viewports per seed)
  2. Merge viewport responses into per-seed observation tensors
  3. Extract settlement stats to infer hidden parameters (expansion rate, aggression, winter severity)
  4. Apply terrain priors to unobserved cells
  5. Cross-seed parameter sharing — same hidden params across all 5 seeds
- **Filtering:** None — all observations used.

---

## Quality and Bias Notes

- **Known quality issues:** Observations are a single stochastic sample of a probabilistic simulation. High-variance cells (settlements, ports, ruins) observed only once carry high uncertainty.
- **Bias risks:** Tiling strategy biases repeated observation toward early-visited cells if budget allows re-queries. Settlement-rich regions get better probability estimates than remote plains.
- **Mitigation:** Use remaining queries (after tiling) on highest-density settlement zones. Cross-seed aggregation reduces per-seed stochastic noise.

---

## Security and Privacy

- **Sensitive fields present:** JWT access_token (authentication credential). Stored in `solutions/astar-island/.token` — gitignored. Never logged. No personal data in simulation output.
- **Protection controls:** `.token` excluded from version control via `.gitignore`. Token is competition-issued, scoped to our team account.
- **Retention policy:** Token valid through competition end (March 22, 2026). Rotate or revoke post-competition. Observation data (grid tensors) can be retained for post-competition analysis — no PII involved.
