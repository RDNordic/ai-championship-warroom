# SESSION_HANDOFF.md

## Checkpoint

`optimized_medium_v4` is now working as intended: the plan prefix is replayed exactly, then control falls back to heuristics; latest live score is 91.

## Latest Work

- Added offline planner script:
  - `scripts/optimize_medium_v4.py`
  - Builds `data/medium_YYYY-MM-DD_plan_v4.json` with `actions` + per-round `checkpoints`.
- Planner now auto-merges known orders from `--current-run` replay into `data/medium_2026-03-02.json` before planning.
  - Snapshot grew from 7 known orders to 11 known orders.
- Added runtime strategy:
  - `src/grocerybot/strategies/optimized_medium_v4.py`
  - Replays plan by round with state validation, then falls back to `medium_v4`.
- Improved replay robustness:
  - checkpoint mismatch is advisory (not immediate global disable)
  - per-bot skip tolerance prevents single missed pick from killing plan
  - fallback only on sustained failure / plan end
- Registered strategy:
  - `src/grocerybot/strategies/__init__.py` includes `"optimized_medium_v4"`.
- Added tests:
  - `tests/test_optimized_medium_v4.py`
- Validation run:
  - `ruff` clean
  - `mypy` clean (with `PYTHONPATH=src`)
  - `pytest tests/test_optimized_medium_v4.py` passed

## Current Results

- Offline plan for first 9 known orders:
  - 251 rounds, score 81 at round 251.
- Live run:
  - `game_medium_20260302_214042.jsonl`
  - Final score 91, items 41, orders 10.
- Plan adherence check:
  - rounds 0-250 matched `plan_v4` exactly (100% round and per-bot action match).
  - rounds 251-299 are fallback phase.

## Known Issues

- Medium score still below best known benchmark (~104).
- Fallback phase (post-plan) is still mostly single-bot throughput.
- `medium_v3.py` has unrelated local modifications in working tree; not part of this checkpoint.

## Next Steps

1. Regenerate plan with `--max-orders 10` (or 11) from latest replay.
2. Run `optimized_medium_v4` and verify exact adherence for expanded plan horizon.
3. Optimize fallback window only (post-plan) for multi-bot contribution near drop-off.
4. Batch 3 runs and compare median score against current 91 baseline.

## Restart Prompt

```text
Read CONTEXT.md and SESSION_HANDOFF.md. Continue optimizing medium using optimized_medium_v4. Regenerate plan_v4 for max-orders 10 or 11 from latest replay, run a new game, verify exact plan adherence, then improve only the fallback phase (rounds after planned prefix) to increase final score beyond 91.
```
