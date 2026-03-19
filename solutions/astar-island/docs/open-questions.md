# Astar Island — Open Questions, Ambiguities & Contradictions

---

## CRITICAL: Seed Count Contradiction

**The docs say 5 seeds in most places, but 15 in one place.**

Evidence for **5 seeds:**
- `overview.md`: "5 random seeds"
- `overview.md`: "50 queries total per round, shared across all 5 seeds"
- `endpoint.md` (rounds response): `"seeds_count": 5`
- `endpoint.md` (simulate request): `seed_index: int (0–4)` — implies max index is 4 = 5 seeds
- `endpoint.md` (submit request): `seed_index: int (0–4)`
- `quickstart.md`: `seeds = detail["seeds_count"]  # 5`
- `quickstart.md`: `for seed_idx in range(seeds):` — iterates over seeds_count

Evidence for **15 seeds:**
- `endpoint.md` (my-rounds response): `"seeds_submitted": 15`
- `endpoint.md` (submit section header): "You must submit all 15 seeds for a complete score."

**Assessment:** Almost certainly **5 seeds**. The "15" appears to be a documentation error — possibly a copy-paste from an earlier version where seeds_submitted tracked something else, or a typo (5 → 15). The `seed_index: int (0–4)` constraint is unambiguous. The submit section header saying "15 seeds" is likely stale text.

**Action:** Treat as 5 seeds. Verify against actual round data on first login: check `seeds_count` in `GET /rounds/{round_id}`.

---

## Multiple Rounds: How Many and When?

The docs describe a leaderboard weighted average across multiple rounds, and `round_weight` suggests later rounds may have higher weight. But:
- How many rounds will there be during the competition (March 19–22)?
- What triggers a new round? Is it admin-created on a schedule, or continuous?
- Can we query past completed rounds for post-round analysis (`/analysis`) to learn from?
- The `prediction_window_minutes: 165` (2h45m) example — is this always 165? Could rounds be shorter?

**Inferred:** Multiple rounds likely occur (daily? More frequent?). The hot streak score (last 3 rounds) suggests at least 3–5 rounds over the competition period. **Check `/rounds` immediately on login to see the round history and active round.**

---

## Query Budget: Per-Round or Per-Team-Per-Round?

The docs say "50 queries total per round, shared across all 5 seeds." It's unclear:
- Is this shared across the whole team, or per team member?
- `/budget` returns `queries_used` / `queries_max` — does submitting from one team member's JWT consume the shared team budget?

**Inferred:** Almost certainly a shared team budget (competition design norm), not per-member. But confirm by checking `/budget` as soon as the round is active.

---

## Viewport Width Minimum

The docs state `viewport_w: int (5–15)` and `viewport_h: int (5–15)`. The minimum is 5, not 1. Using a smaller viewport (e.g., 5×5) to zoom in on a specific cell cluster is valid but costs the same 1 query as a full 15×15. Prefer 15×15 always unless deliberately inspecting a small area.

---

## Does Resubmitting Overwrite for All Seeds or Just One?

"Resubmitting for the same seed overwrites your previous prediction. Only the last submission counts."

This is per-seed. Submitting seed 0 again does not affect seed 1–4. Confirmed by the `seed_index` field in the submit request. But: is there any rate limit or cooldown on resubmission? The docs do not mention one for `/submit` (unlike `/simulate` which has 5 req/sec).

**Inferred:** No cooldown on submit, but do not assume — test with the first submission.

---

## What Are the Hidden Parameters?

The mechanics docs describe many forces (expansion rate, aggression, winter severity, trade rate, etc.) but never enumerate or name the hidden parameters explicitly. We don't know:
- How many hidden parameters there are
- Their ranges
- Whether they're continuous or discrete

**Inferred from mechanics:** Key parameters likely include expansion aggressiveness, raiding aggressiveness, winter severity, trade willingness, coastal expansion rate. Must be inferred from observation patterns.

---

## Ground Truth Generation: How Many Simulations?

The scoring doc says ground truth is computed by running the simulation "hundreds of times." The exact number is not stated. This affects:
- How smooth/stable the ground truth distribution is
- Whether rare outcomes (1-in-1000 scenarios) appear in ground truth at all

**Implication:** If a scenario is truly rare (e.g. 0.1% chance), it may still appear in ground truth with a small positive probability. Your 0.01 floor covers this.

---

## Entropy Weighting: Log Base?

The scoring formula uses:
```
entropy(cell) = -Σ pᵢ × log(pᵢ)
KL(p || q) = Σ pᵢ × log(pᵢ / qᵢ)
```

The log base is not specified. Natural log (base e) is standard for information theory KL divergence and entropy. Assuming `np.log` (natural log) is correct. **This affects the scale of weighted_kl but not the ranking or relative comparison.**

---

## Score When Round Not Yet Scored

`/my-rounds` and `/my-predictions` return `null` for scores when not yet scored. The `/analysis` endpoint returns 400 until round is `scoring` or `completed`. During an active round, you cannot see your score until after the prediction window closes.

---

## Viewport Clamping Behaviour

"Viewport is clamped to map edges." If you request `viewport_x=30, viewport_w=15` on a 40-wide map, the actual viewport returned is `x=30, w=10` (clamped). The response `viewport` object reflects the actual clamped bounds. The `grid` returned will be the clamped size (e.g., 10 wide not 15).

**Implication:** When tiling, calculate tile positions carefully so you don't get smaller-than-expected grids at the right/bottom edges. Use `viewport_x=25` (not 30) for the last column tile to ensure you get the full 15-wide result: 25+15=40, exact fit.

---

## Initial Grid in my-rounds: First Seed Only

`my-rounds` response includes `initial_grid` described as "Initial terrain grid for the first seed." This is only seed 0's initial grid. To get all 5 seeds' initial grids, use `GET /rounds/{round_id}` which returns `initial_states` for all seeds.

---

## "Prediction Window" vs Round Close Time

The rounds object has both `closes_at` (ISO 8601 timestamp) and `prediction_window_minutes` (165). It's unclear whether `closes_at` is the same as "prediction window end" or if there's a separate observation-query window vs submission window. **Assume `closes_at` is the hard deadline for both queries and submissions.** Do not assume extra time.
