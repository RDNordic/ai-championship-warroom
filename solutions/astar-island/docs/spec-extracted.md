# Astar Island — Operational Spec (Extracted)

Machine-readable reference for building competition code. No prose. Exact values preserved.

---

## Authentication

- **Login URL:** `https://app.ainm.no` (Google sign-in)
- **Token location after login:** Cookie `access_token` (JWT)
- **Method 1:** Cookie header: `Cookie: access_token=<JWT>`
- **Method 2:** Bearer header: `Authorization: Bearer <JWT>`
- Both methods use the same JWT token value.
- All "Team" endpoints require auth. "Public" endpoints do not.

---

## Base URL

```
https://api.ainm.no/astar-island
```

---

## Endpoints

### GET /astar-island/rounds
- **Auth:** Public
- **Returns:** Array of round objects

Round object fields:

| Field | Type | Notes |
|-------|------|-------|
| `id` | string (UUID) | Use as `round_id` in all other calls |
| `round_number` | int | |
| `event_date` | string (YYYY-MM-DD) | |
| `status` | string | `pending` / `active` / `scoring` / `completed` |
| `map_width` | int | Default 40 |
| `map_height` | int | Default 40 |
| `prediction_window_minutes` | int | Typical: 165 (2h45m) |
| `started_at` | string (ISO 8601) | |
| `closes_at` | string (ISO 8601) | Submission deadline |
| `round_weight` | int | Used in leaderboard weighted average |
| `created_at` | string (ISO 8601) | |

Round statuses:
- `pending` — round created, not started. No queries or submissions.
- `active` — queries and submissions open.
- `scoring` — submissions closed, scoring running.
- `completed` — scores finalised.

---

### GET /astar-island/rounds/{round_id}
- **Auth:** Public
- **Returns:** Round detail + initial states for ALL seeds

Additional fields vs rounds list:

| Field | Type | Notes |
|-------|------|-------|
| `seeds_count` | int | Number of seeds (typically 5) |
| `initial_states` | array | One entry per seed |

`initial_states[i]` fields:

| Field | Type | Notes |
|-------|------|-------|
| `grid` | int[][] | height × width array of terrain codes |
| `settlements` | array | Initial settlements visible in this seed |

`settlements[j]` fields (initial state — limited):

| Field | Type | Notes |
|-------|------|-------|
| `x` | int | Column index |
| `y` | int | Row index |
| `has_port` | bool | |
| `alive` | bool | |

**Note:** Internal stats (population, food, wealth, defense) NOT exposed in initial states. Only visible via `/simulate` response.

---

### GET /astar-island/budget
- **Auth:** Team
- **Returns:** Budget for active round

| Field | Type | Notes |
|-------|------|-------|
| `round_id` | string (UUID) | |
| `queries_used` | int | |
| `queries_max` | int | Default 50 |
| `active` | bool | |

---

### POST /astar-island/simulate
- **Auth:** Team
- **Cost:** 1 query per call
- **Budget:** 50 queries per round, shared across all seeds
- **Rate limit:** max 5 requests/sec

#### Request body

| Field | Type | Constraints |
|-------|------|-------------|
| `round_id` | string | UUID of active round |
| `seed_index` | int | 0–4 |
| `viewport_x` | int | ≥ 0, default 0 |
| `viewport_y` | int | ≥ 0, default 0 |
| `viewport_w` | int | 5–15, default 15 |
| `viewport_h` | int | 5–15, default 15 |

Viewport is clamped to map edges. Actual bounds returned in response.

#### Response body

| Field | Type | Notes |
|-------|------|-------|
| `grid` | int[][] | viewport_h × viewport_w terrain codes (final state after 50 years) |
| `settlements` | array | Settlements within viewport only |
| `viewport` | object | `{x, y, w, h}` — actual (clamped) bounds |
| `width` | int | Full map width |
| `height` | int | Full map height |
| `queries_used` | int | Running total after this call |
| `queries_max` | int | 50 |

`settlements[j]` fields (full stats, unlike initial state):

| Field | Type | Notes |
|-------|------|-------|
| `x` | int | |
| `y` | int | |
| `population` | float | |
| `food` | float | |
| `wealth` | float | |
| `defense` | float | |
| `has_port` | bool | |
| `alive` | bool | |
| `owner_id` | int | Faction allegiance |

Each simulate call uses a **different random sim_seed** — stochastic outcomes vary per call even for same `seed_index` and viewport.

#### Error codes

| HTTP | Meaning |
|------|---------|
| 400 | Round not active, or invalid `seed_index` |
| 403 | Not on a team |
| 404 | Round not found |
| 429 | Budget exhausted (50/50) OR rate limit exceeded (>5 req/sec) |

---

### POST /astar-island/submit
- **Auth:** Team
- **Behaviour:** Resubmitting for same seed **overwrites** previous prediction. Only last submission counts.

#### Request body

| Field | Type | Constraints |
|-------|------|-------------|
| `round_id` | string | UUID of active round |
| `seed_index` | int | 0–4 |
| `prediction` | float[][][] | H×W×6 tensor |

#### Prediction tensor format

- Shape: `[H][W][6]` — i.e., `prediction[y][x][class_index]`
- H = map height (e.g. 40)
- W = map width (e.g. 40)
- Inner dimension: exactly 6 floats, one per terrain class
- Each cell: all 6 values must sum to **1.0 ± 0.01**
- All values must be **non-negative**
- **Never use 0.0** — if ground truth pᵢ > 0 and your qᵢ = 0, KL divergence = infinity for that cell

#### Class indices

| Index | Class | Notes |
|-------|-------|-------|
| 0 | Empty | Covers Ocean (10), Plains (11), Empty (0) |
| 1 | Settlement | |
| 2 | Port | |
| 3 | Ruin | |
| 4 | Forest | |
| 5 | Mountain | |

#### Validation errors (exact messages)

| Message | Cause |
|---------|-------|
| `Expected H rows, got N` | Wrong number of rows |
| `Row Y: expected W cols, got N` | Wrong number of columns |
| `Cell (Y,X): expected 6 probs, got N` | Wrong inner dimension |
| `Cell (Y,X): probs sum to S, expected 1.0` | Sum not 1.0 ± 0.01 |
| `Cell (Y,X): negative probability` | Negative value |

#### Response

```json
{"status": "accepted", "round_id": "uuid", "seed_index": 3}
```

---

### GET /astar-island/my-rounds
- **Auth:** Team

Key fields beyond the rounds list:

| Field | Type | Notes |
|-------|------|-------|
| `round_score` | float \| null | Average across seeds; null if unscored |
| `seed_scores` | float[] \| null | Per-seed scores |
| `seeds_submitted` | int | How many seeds have a submitted prediction |
| `rank` | int \| null | Team rank for this round |
| `total_teams` | int \| null | Teams scored |
| `queries_used` | int | |
| `initial_grid` | int[][] | Initial terrain for **first seed only** |

---

### GET /astar-island/my-predictions/{round_id}
- **Auth:** Team
- **Returns:** Array of submitted predictions with derived fields

| Field | Type | Notes |
|-------|------|-------|
| `seed_index` | int | |
| `argmax_grid` | int[][] | H×W — argmax of probability vector per cell |
| `confidence_grid` | float[][] | H×W — max probability per cell, 3 decimal places |
| `score` | float \| null | null if not yet scored |
| `submitted_at` | string \| null | ISO 8601 |

---

### GET /astar-island/analysis/{round_id}/{seed_index}
- **Auth:** Team
- **Available:** Only when round status is `scoring` or `completed`
- **Returns:** Your prediction vs ground truth for one seed

| Field | Type | Notes |
|-------|------|-------|
| `prediction` | float[][][] | H×W×6 — your submitted tensor |
| `ground_truth` | float[][][] | H×W×6 — computed from Monte Carlo simulations |
| `score` | float \| null | |
| `width` | int | |
| `height` | int | |
| `initial_grid` | int[][] \| null | |

Error 400 if round not yet completed/scoring.

---

### GET /astar-island/leaderboard
- **Auth:** Public

| Field | Type |
|-------|------|
| `team_id` | string |
| `team_name` | string |
| `team_slug` | string |
| `weighted_score` | float |
| `rounds_participated` | int |
| `hot_streak_score` | float |
| `rank` | int |

---

## Grid Terrain Codes

| Code | Terrain | Prediction class |
|------|---------|-----------------|
| 0 | Empty | 0 |
| 1 | Settlement | 1 |
| 2 | Port | 2 |
| 3 | Ruin | 3 |
| 4 | Forest | 4 |
| 5 | Mountain | 5 |
| 10 | Ocean | 0 |
| 11 | Plains | 0 |

---

## Simulation Mechanics Summary

### Phases (each of 50 years, in order)
1. **Growth** — food production → population growth → ports → longships → new settlements
2. **Conflict** — raiding (longships extend range) → looting → damage → allegiance change
3. **Trade** — ports trade if not at war → wealth/food gain → tech diffusion
4. **Winter** — food loss → collapse if starved/raided → Ruin → population disperses
5. **Environment** — ruins reclaimed by nearby settlements or overtaken by forest/plains

### Static terrain
- Mountain (5): **never changes**
- Ocean (10): **never changes**

### Mostly static
- Forest (4): stable, but can reclaim ruins if no settlement does

### Dynamic terrain (subject to prediction uncertainty)
- Settlement (1), Port (2), Ruin (3), Plains (11) near settlements

### Hidden parameters
- Same across all 5 seeds in a round
- Control: expansion rate, aggression, winter severity, trade rate, etc.
- Not exposed — must be inferred from observations

### Initial state visibility
- Settlement **position** and **has_port**: visible in `initial_states`
- Settlement **population, food, wealth, defense**: NOT visible — only via `/simulate`

---

## Scoring Formula

```
# Ground truth: Monte Carlo average over hundreds of simulation runs
# p = ground truth distribution per cell
# q = your prediction per cell

KL(p || q) = Σ pᵢ × log(pᵢ / qᵢ)        # per cell

entropy(cell) = -Σ pᵢ × log(pᵢ)           # per cell

weighted_kl = Σ [entropy(cell) × KL(p, q)] / Σ entropy(cell)

score = max(0, min(100, 100 × exp(-3 × weighted_kl)))
```

Score range: 0–100. Higher is better.

### Per-round score
```
round_score = mean(score_seed_0 ... score_seed_N)
```
Missing seed = 0. Always submit for every seed.

### Leaderboard score
```
leaderboard_score = Σ (round_score × round_weight) / Σ round_weight
```

Hot streak score = average of last 3 rounds.

### Critical constraint
- If `qᵢ = 0.0` and ground truth `pᵢ > 0`: `log(pᵢ / 0)` = **infinity** → cell score = infinity → penalised catastrophically
- **Always apply floor:** `prediction = np.maximum(prediction, 0.01); prediction /= prediction.sum(axis=-1, keepdims=True)`

---

## Round Timing

- Prediction window: typically **165 minutes (2h45m)** per round
- After window closes: status → `scoring` → `completed`
- Multiple rounds may occur during competition (leaderboard = weighted average)
- Round weights: typically 1; later rounds may be higher

---

## Map Geometry

- Default map: **40×40**
- Max viewport: **15×15**
- Tiles needed to cover full 40×40 map: ceil(40/15) × ceil(40/15) = **3×3 = 9 queries**
- Viewport positions for full coverage (0-indexed, clamped at edges):
  - x: 0, 15, 25 (or 28 — adjust so last tile catches right edge)
  - y: 0, 15, 25

---

## Rate Limits

| Limit | Value |
|-------|-------|
| Query budget per round | 50 total, shared across all seeds |
| Simulate rate limit | max 5 requests/sec |
| Seeds per round | 5 (seed_index 0–4) |
