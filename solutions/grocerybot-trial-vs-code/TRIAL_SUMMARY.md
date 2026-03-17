# Grocery Bot — Pre-Competition Trial Summary

**Period:** March 1–13, 2026
**Final rank:** ~70th out of 317 teams
**Status:** CLOSED — pre-competition warmup complete

---

## Final Scores

| Difficulty | Best Score | Status |
|-----------|-----------|--------|
| Easy | 137 | Inactive |
| Medium | 118 | Frozen |
| Hard | 99 | Volatile |
| Expert | 93 | Volatile |
| Nightmare | 193 | Stable |
| **Total** | **640** | |

---

## Key Learnings for Competition

- WebSocket platform mechanics are now understood (2s timeout, action_status, round field)
- Bot collision: swaps blocked 97.4% of time; don't design around swaps
- Grid structure deterministic; item types rotate daily at midnight UTC
- Commit-before-run / revert-on-regression protocol proven effective
- 3-run clean-median gate is the right evaluation discipline
- random.seed(42) essential for reproducible A/B testing
- Simple heuristics (greedy assignment, BFS) beat over-engineered approaches

---

## Active Artifacts

- Expert bot: `run_expert.py`
- Expert baseline (score 93): `run_expert_baseline_93_20260309.py`
- Nightmare baseline (score 193): `run_nightmare_baseline_193.py`
- Replay analyzer: `analyze_expert_replay.py`
- Run history: `logs/run_history.csv`
- Full trial log: `logs/TRIAL_MEMORY.md`

---

## Expert Trial History (March 9)

**Clean baseline:** 70 median on seed 7004

| Trial | Result | Keep/Revert |
|-------|--------|------------|
| Remove random nudge fallback | Clean runs 21, 30 | Reverted |
| Force non-useful bots to yield near drop-off | Clean runs 20, 42 | Reverted |
| Tighten preview activation | Clean runs 82, 70, 3; median 70 | **Kept** |
| Allow preview buildup when active remaining ≤ 1 | First clean run 4 | Reverted immediately |
| Remove delivery detours for useful carriers | First clean run 2 | Reverted immediately |
| Clear non-useful carriers toward perimeter (rounds 35-140) | Clean 60, 4; median 32 | Reverted |

**Replay-derived thresholds:**
- Healthy by round 100: ≥ 2 orders, score ≥ 20
- Strong by round 100: 3 orders, score ≥ 28
- Danger: no active-order progress for ≥ 90 rounds after first stall
- Collapse: 0 orders by round 100 OR starvation ≥ 200 rounds
- Earliest divergence window: rounds 35–60

**Strong runs analyzed:**
- `20260309_162144` score 84: round 100 → score 22, orders 2, starvation 30
- `20260309_205554` score 82: round 100 → score 28, orders 3, starvation 30
- `20260309_205750` score 70: round 100 → score 28, orders 3, starvation 45

**Collapse runs analyzed:**
- `20260309_205004` score 42: round 100 → score 21, orders 2, starvation 97
- `20260309_205937` score 3: round 100 → score 2, orders 0, starvation 255
- `20260309_210722` score 4: round 100 → score 4, orders 0, starvation 210
- `20260309_211809` score 2: round 100 → score 2, orders 0, starvation 264

---

## Nightmare History (March 8)

Breakthrough: 7-worker config achieved score 193, replicated 6+ times.
Stale pivot threshold: reduced from 20 to 12 rounds.
Do not retry: NUM_WORKERS=3 with preview disabled → score=1 (massive regression).
