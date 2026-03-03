# SESSION_HANDOFF.md

## Checkpoint

`optimized_medium_v5` is integrated, but latest run (`game_medium_20260303_012628.jsonl`) drifted from plan at round 49 and collapsed to fallback behavior (final score 28).

## Latest Work

- Added/updated medium plan replay stack:
  - `scripts/optimize_medium_v5.py`
  - `src/grocerybot/strategies/optimized_medium_v5.py`
  - registration in `src/grocerybot/strategies/__init__.py`
- Improved replay robustness in `optimized_medium_v4`:
  - checkpoint resync window (`back=5`, `forward=1`)
  - dynamic plan-round offset tracking
- Added test coverage:
  - `tests/test_optimized_medium_v4.py`
  - `tests/test_optimized_medium_v5.py`
- Verified latest replay vs plan:
  - replay matches plan through round 48 only
  - first divergence at round 49 (`bot1`: plan `drop_off`, replay `wait`)
- Root-cause identified:
  - v5 simulator allows move into occupied drop-off cell
  - server rule blocks move into occupied cell (treated as `wait`), causing immediate checkpoint mismatch.

## Known Issues

- `scripts/optimize_medium_v5.py` currently permits drop-off occupancy overlap during movement simulation (`nxt == drop_off` bypass), which is not server-accurate.
- Once checkpoints fail, replay strategy disables plan and falls back; this error-handling is coarse and can cause large throughput collapse.
- `tests/test_optimized_medium.py` could not be validated in this shell due temp-directory permission errors (environmental).

## Next Steps

1. Patch v5 simulator movement rules to block entering any occupied cell, including drop-off.
2. Regenerate `data/medium_2026-03-03_plan_v5.json` and re-run; verify first divergence is removed.
3. Tighten v5 runtime error-handling status:
   - keep current per-bot skip tolerance and checkpoint resync,
   - add explicit "transient mismatch" vs "hard divergence" counters,
   - only hard-disable plan after sustained mismatch window.
4. Add regression test for the round-49 occupied-dropoff scenario.

## Restart Prompt

```text
Read CONTEXT.md and SESSION_HANDOFF.md. Fix v5 desync by making optimize_medium_v5 occupancy rules server-accurate at drop-off, regenerate 2026-03-03 plan_v5, rerun medium, and confirm plan adherence beyond round 49. Then improve replay error-handling so transient mismatches do not immediately collapse to full fallback.
```
