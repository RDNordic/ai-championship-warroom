# Challenge 2 — Astar Island: Viking World Prediction

**Sponsor:** Astar
**Status:** In progress
**Owner:** AD (Andrew/John)

---

## What We're Doing

Predict **probability distributions** of terrain types after 50 years of Norse civilisation simulation. Not a single outcome — a probability per class per cell across the entire 40×40 map.

We never run the simulation ourselves. We observe partial glimpses of it via a viewport API, then submit a W×H×6 probability tensor for each of 5 seeds.

---

## The World

### Terrain → Prediction Class Mapping

| Class Index | Terrain | Dynamic? |
|---|---|---|
| 0 | Empty / Ocean / Plains | Mostly static |
| 1 | Settlement | **Highly dynamic** |
| 2 | Port | **Highly dynamic** |
| 3 | Ruin | **Highly dynamic** |
| 4 | Forest | Mostly static (can reclaim ruins) |
| 5 | Mountain | **Completely static — never changes** |

### Grid Cell Codes (from API)

| Value | Terrain |
|---|---|
| 0 | Empty |
| 1 | Settlement |
| 2 | Port |
| 3 | Ruin |
| 4 | Forest |
| 5 | Mountain |
| 10 | Ocean |
| 11 | Plains |

---

## Round Structure

- **Map seed:** Determines initial terrain layout — **visible to us**. Same map, different seeds.
- **Sim seed:** Different random seed per simulation run — changes each query.
- **Hidden parameters:** Control world behaviour (expansion rate, aggression, winter severity). **Same across all 5 seeds in a round.** This is the key exploit.
- **50 queries total per round**, shared across all 5 seeds
- **Viewport:** Max 15×15 cells per query
- **Prediction window:** ~2h45min per round
- **Seeds per round:** 5 — must submit all 5 or missing seeds score 0

---

## Query Budget Maths

| | Value |
|---|---|
| Total queries | 50 |
| Seeds | 5 |
| Queries/seed (even split) | ~10 |
| Max viewport | 15×15 = 225 cells |
| Full map | 40×40 = 1,600 cells |
| Queries to tile full map | ceil(40/15)² = **9 queries** |

You can cover the entire map once per seed in 9 queries, with ~1 leftover per seed. Efficiency matters — every wasted query hurts.

---

## Simulation Lifecycle (50 years)

Each year cycles through these phases:

1. **Growth** — settlements produce food, expand, found new settlements, build ports and longships
2. **Conflict** — settlements raid each other; longships extend range; desperate settlements raid more
3. **Trade** — ports within range trade if not at war; technology diffuses
4. **Winter** — all settlements lose food; starvation/raids can collapse settlements into Ruins
5. **Environment** — ruins reclaimed by nearby settlements or overtaken by forest

---

## API Reference

**Base URL:** `https://api.ainm.no/astar-island`
**Auth:** JWT Bearer token or `access_token` cookie (from `app.ainm.no` login)

### Key Endpoints

| Method | Path | Description |
|---|---|---|
| `GET` | `/rounds` | List all rounds (public) |
| `GET` | `/rounds/{round_id}` | Round details + initial states for all seeds |
| `GET` | `/budget` | Remaining query budget |
| `POST` | `/simulate` | Observe one simulation through viewport (costs 1 query) |
| `POST` | `/submit` | Submit prediction tensor for one seed |
| `GET` | `/my-rounds` | Your scores, rank, budget per round |
| `GET` | `/leaderboard` | Public leaderboard |

### Simulate Request

```json
{
  "round_id": "uuid-of-active-round",
  "seed_index": 0,
  "viewport_x": 10,
  "viewport_y": 5,
  "viewport_w": 15,
  "viewport_h": 15
}
```

### Simulate Response

```json
{
  "grid": [[4, 11, 1, ...], ...],
  "settlements": [
    {
      "x": 12, "y": 7,
      "population": 2.8,
      "food": 0.4,
      "wealth": 0.7,
      "defense": 0.6,
      "has_port": true,
      "alive": true,
      "owner_id": 3
    }
  ],
  "viewport": {"x": 10, "y": 5, "w": 15, "h": 15},
  "queries_used": 24,
  "queries_max": 50
}
```

Settlement stats (population, food, wealth, defense) **are only visible through simulation queries** — not from the initial state. These indirectly reveal hidden parameters.

### Submit Request

```json
{
  "round_id": "uuid-of-active-round",
  "seed_index": 0,
  "prediction": [
    [[0.85, 0.05, 0.02, 0.03, 0.03, 0.02], ...],
    ...
  ]
}
```

Prediction format: `prediction[y][x][class]` — H×W×6 tensor. Each cell's 6 values must sum to 1.0 (±0.01 tolerance). Resubmitting overwrites. Only last submission counts.

---

## Scoring Formula

```
ground truth = Monte Carlo average over hundreds of simulation runs

KL(p || q) = Σ pᵢ × log(pᵢ / qᵢ)    (p = ground truth, q = our prediction)

entropy(cell) = -Σ pᵢ × log(pᵢ)

weighted_kl = Σ entropy(cell) × KL(ground_truth, prediction) / Σ entropy(cell)

score = max(0, min(100, 100 × exp(-3 × weighted_kl)))
```

- **100** = perfect match
- **0** = catastrophic KL divergence
- Static cells (Mountain, Ocean) have near-zero entropy — excluded from scoring
- High-entropy cells (uncertain outcomes) count **more**
- Exponential decay: diminishing returns past ~70

**Overall leaderboard:** Weighted average across all rounds. Later rounds may have higher weight.

---

## Cardinal Rule: Never Use 0.0 Probability

If ground truth has `p > 0` for a class but your prediction has `q = 0`, KL divergence → **infinity**. Your entire score for that cell is destroyed. One zero in the wrong place can tank the whole submission.

```python
import numpy as np

# Always apply before submitting
prediction = np.maximum(prediction, 0.01)
prediction = prediction / prediction.sum(axis=-1, keepdims=True)
```

This must run on every cell, every submission, no exceptions.

---

## Baseline Strategy (Score ~20–40, zero queries used)

Use the initial grid alone. Static cells are known. Apply terrain-based priors:

| Initial Terrain | Recommended Prior |
|---|---|
| Mountain | `[0.02, 0.02, 0.02, 0.02, 0.02, 0.92]` |
| Ocean | `[0.92, 0.02, 0.02, 0.02, 0.02, 0.02]` |
| Plains (remote) | `[0.80, 0.05, 0.03, 0.05, 0.05, 0.02]` |
| Plains (near settlement) | `[0.50, 0.25, 0.10, 0.10, 0.03, 0.02]` |
| Forest | `[0.05, 0.05, 0.02, 0.05, 0.80, 0.03]` |
| Initial Settlement | `[0.05, 0.60, 0.15, 0.15, 0.03, 0.02]` |

Then apply the 0.01 floor + renormalise. This alone beats uniform (1–5 score) by 15–35 points.

---

## Competitive Strategy (Score ~60–80)

### Phase 1: Tile the map (45 queries)
- 9 queries per seed × 5 seeds = 45 queries
- Use max 15×15 viewport to cover entire 40×40 map for each seed
- Record final terrain state for every cell across 5 different stochastic runs
- Direct probability evidence from observations

### Phase 2: Targeted repeat observations (5 queries)
- Focus remaining 5 queries on highest-density settlement regions
- Multiple observations of same area → direct frequency estimation

### Phase 3: Cross-seed parameter inference
- Hidden params are **same for all 5 seeds**
- Compare observed settlement counts across seeds → infer expansion rate
- Compare ruin counts → infer aggression/winter severity
- Apply inferred world model to cells not directly observed

### Phase 4: Build probability tensor
1. Start with terrain prior (initial grid)
2. Override cells with direct observations where we have them
3. Interpolate unobserved cells using proximity model + inferred params
4. Apply 0.01 floor + renormalise
5. Submit all 5 seeds

---

## Settlement Stats as Parameter Signals

Observation responses include settlement stats that reveal hidden parameters:

| High value | Suggests |
|---|---|
| `population` | High food / low aggression (stable growth) |
| `food` low + many ruins | Harsh winter severity or high aggression |
| `wealth` | Successful trade (trade_rate param high) |
| Many ports observed | High coastal expansion |
| Many ruins observed | High aggression or winter severity |

---

## Authentication Setup

```python
import requests

BASE = "https://api.ainm.no"
session = requests.Session()
session.headers["Authorization"] = "Bearer YOUR_JWT_TOKEN"

# Get JWT: log in at app.ainm.no, inspect browser cookies for access_token
```

## Local Token Workflow

- Paste the full `access_token` JWT into `solutions/astar-island/.token`
- The template file is `solutions/astar-island/.token.example`
- Quick auth + round check:

```powershell
python solutions/astar-island/client.py
```

This fetches:
- public `GET /astar-island/rounds`
- public `GET /astar-island/rounds/{round_id}` for the active round
- authenticated `GET /astar-island/budget`

It does **not** consume query budget.

---

## Quickstart Code

```python
import numpy as np

# 1. Get active round
rounds = session.get(f"{BASE}/astar-island/rounds").json()
active = next(r for r in rounds if r["status"] == "active")
round_id = active["id"]

# 2. Get initial states
detail = session.get(f"{BASE}/astar-island/rounds/{round_id}").json()
width, height = detail["map_width"], detail["map_height"]  # 40x40

# 3. Query (10 per seed, tile the map)
result = session.post(f"{BASE}/astar-island/simulate", json={
    "round_id": round_id,
    "seed_index": 0,
    "viewport_x": 0, "viewport_y": 0,
    "viewport_w": 15, "viewport_h": 15,
}).json()

# 4. Build and submit prediction
prediction = np.full((height, width, 6), 1/6)  # replace with model
prediction = np.maximum(prediction, 0.01)
prediction /= prediction.sum(axis=-1, keepdims=True)

session.post(f"{BASE}/astar-island/submit", json={
    "round_id": round_id,
    "seed_index": 0,
    "prediction": prediction.tolist(),
})
```

---

## Strategy Notes

1. **No endpoint to host** — pure analysis/ML. No infrastructure burden.
2. **The initial grid alone is worth 20–40 points** — implement baseline before spending a single query.
3. **Always submit all 5 seeds** — missing a seed = 0 for that seed. Even a prior beats 0.
4. **Cross-seed parameter sharing is the main lever** — same hidden params across all 5 seeds.
5. **Settlement proximity matters most** — plains adjacent to initial settlements are the most uncertain cells and carry the highest entropy weight.
6. **Multiple rounds** — score is weighted average across rounds. Improving between rounds compounds.

---

## Open Questions

- [ ] Who owns this challenge? (Patrick / Chris — no hosting required, CPU-only)
- [ ] Get JWT token from `app.ainm.no` now — needed to check if a round is already active
- [ ] Is a round currently active? Check `/rounds` immediately.
- [ ] Can we approximate the simulator locally to calibrate the hidden parameter inference model?
