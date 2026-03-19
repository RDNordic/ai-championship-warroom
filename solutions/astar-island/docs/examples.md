# Astar Island — Exact Examples from Docs

All examples are verbatim from the MCP documentation unless noted.

---

## Authentication

```python
import requests

BASE = "https://api.ainm.no"

# Option 1: Cookie-based auth
session = requests.Session()
session.cookies.set("access_token", "YOUR_JWT_TOKEN")

# Option 2: Bearer token auth
session = requests.Session()
session.headers["Authorization"] = "Bearer YOUR_JWT_TOKEN"
```

How to get token: log in at `https://app.ainm.no`, inspect browser cookies for `access_token`.

---

## Step 1: Get Active Round

```python
rounds = session.get(f"{BASE}/astar-island/rounds").json()
active = next((r for r in rounds if r["status"] == "active"), None)

if active:
    round_id = active["id"]
    print(f"Active round: {active['round_number']}")
```

### Example rounds response

```json
[
  {
    "id": "uuid",
    "round_number": 1,
    "event_date": "2026-03-19",
    "status": "active",
    "map_width": 40,
    "map_height": 40,
    "prediction_window_minutes": 165,
    "started_at": "2026-03-19T10:00:00Z",
    "closes_at": "2026-03-19T10:45:00Z",
    "round_weight": 1,
    "created_at": "2026-03-19T09:00:00Z"
  }
]
```

---

## Step 2: Get Round Details + Initial States

```python
detail = session.get(f"{BASE}/astar-island/rounds/{round_id}").json()

width = detail["map_width"]      # 40
height = detail["map_height"]    # 40
seeds = detail["seeds_count"]    # 5

for i, state in enumerate(detail["initial_states"]):
    grid = state["grid"]                    # height x width terrain codes
    settlements = state["settlements"]      # [{x, y, has_port, alive}, ...]
    print(f"Seed {i}: {len(settlements)} settlements")
```

### Example rounds/{round_id} response

```json
{
  "id": "uuid",
  "round_number": 1,
  "status": "active",
  "map_width": 40,
  "map_height": 40,
  "seeds_count": 5,
  "initial_states": [
    {
      "grid": [[10, 10, 10], [10, 11, 1], [10, 4, 5]],
      "settlements": [
        {
          "x": 5, "y": 12,
          "has_port": true,
          "alive": true
        }
      ]
    }
  ]
}
```

---

## Step 3: Query the Simulator

```python
result = session.post(f"{BASE}/astar-island/simulate", json={
    "round_id": round_id,
    "seed_index": 0,
    "viewport_x": 10,
    "viewport_y": 5,
    "viewport_w": 15,
    "viewport_h": 15,
}).json()

grid = result["grid"]                # 15x15 terrain after 50-year simulation
settlements = result["settlements"]  # settlements in viewport with full stats
viewport = result["viewport"]        # {x, y, w, h}
```

### Example simulate response

```json
{
  "grid": [[4, 11, 1], [11, 1, 2], [4, 3, 4]],
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
  "width": 40,
  "height": 40,
  "queries_used": 24,
  "queries_max": 50
}
```

---

## Step 4: Build and Submit Predictions

### Uniform baseline (scores ~1–5)

```python
import numpy as np

for seed_idx in range(seeds):
    prediction = np.full((height, width, 6), 1/6)  # uniform baseline

    resp = session.post(f"{BASE}/astar-island/submit", json={
        "round_id": round_id,
        "seed_index": seed_idx,
        "prediction": prediction.tolist(),
    })
    print(f"Seed {seed_idx}: {resp.status_code}")
```

### Submit response (success)

```json
{
  "status": "accepted",
  "round_id": "uuid",
  "seed_index": 3
}
```

---

## 0.01 Floor + Renormalise (always apply before submitting)

```python
prediction = np.maximum(prediction, 0.01)
prediction = prediction / prediction.sum(axis=-1, keepdims=True)
```

---

## Example cell prediction vector

```
[0.85, 0.05, 0.02, 0.03, 0.03, 0.02]
 ^      ^     ^     ^     ^     ^
 Empty  Sett  Port  Ruin  Forest Mountain
```

Sum = 1.0 ✓

---

## Example ground truth cell (from scoring docs)

```
[0.0, 0.60, 0.25, 0.15, 0.0, 0.0]
```

Meaning: 60% Settlement, 25% Port, 15% Ruin after 50 years.
Note the 0.0 values — these are in the *ground truth*. Your *prediction* must never have 0.0 for any class, or KL = ∞ for that cell.

---

## my-rounds response example

```json
[
  {
    "id": "uuid",
    "round_number": 1,
    "status": "completed",
    "map_width": 40,
    "map_height": 40,
    "seeds_count": 5,
    "round_weight": 1,
    "prediction_window_minutes": 165,
    "round_score": 72.5,
    "seed_scores": [80.1, 65.3, 71.9],
    "seeds_submitted": 15,
    "rank": 3,
    "total_teams": 12,
    "queries_used": 48,
    "queries_max": 50,
    "initial_grid": [[10, 10, 10]]
  }
]
```

---

## my-predictions/{round_id} response example

```json
[
  {
    "seed_index": 0,
    "argmax_grid": [[0, 4, 5], [0, 1, 2]],
    "confidence_grid": [[0.85, 0.72, 0.93], [0.80, 0.60, 0.71]],
    "score": 78.2,
    "submitted_at": "2026-03-19T10:30:00+00:00"
  }
]
```

---

## analysis/{round_id}/{seed_index} response example

```json
{
  "prediction": [[[0.85, 0.05, 0.02, 0.03, 0.03, 0.02]]],
  "ground_truth": [[[0.90, 0.03, 0.01, 0.02, 0.02, 0.02]]],
  "score": 78.2,
  "width": 40,
  "height": 40,
  "initial_grid": [[10, 10, 10]]
}
```

---

## Leaderboard response example

```json
[
  {
    "team_id": "uuid",
    "team_name": "Vikings ML",
    "team_slug": "vikings-ml",
    "weighted_score": 72.5,
    "rounds_participated": 3,
    "hot_streak_score": 78.1,
    "rank": 1
  }
]
```

---

## budget response example

```json
{
  "round_id": "uuid",
  "queries_used": 23,
  "queries_max": 50,
  "active": true
}
```

---

## Scoring formula worked example

```python
import numpy as np

# Ground truth for one cell
p = np.array([0.0, 0.60, 0.25, 0.15, 0.0, 0.0])

# Your prediction (with 0.01 floor applied)
q = np.array([0.01, 0.58, 0.24, 0.14, 0.02, 0.01])
q /= q.sum()  # renormalise

# KL divergence for this cell (only where p > 0)
mask = p > 0
kl = np.sum(p[mask] * np.log(p[mask] / q[mask]))

# Entropy of this cell
entropy = -np.sum(p[mask] * np.log(p[mask]))

# Final score
weighted_kl_total = ...  # sum over all cells
score = max(0, min(100, 100 * np.exp(-3 * weighted_kl_total)))
```
