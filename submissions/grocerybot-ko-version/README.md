# Grocery Bot

Bot for the [NM i AI 2026](https://dev.ainm.no) Grocery Bot challenge.

This repository solves a real-time multi-agent planning problem:
- parse full game state from WebSocket each round,
- produce one valid action per bot within 2 seconds,
- maximize delivered items and completed orders over 300 rounds.

## Project Status (as of 2026-03-08)

### What Has Been Solved

- Protocol-safe client loop with strict timing budget (`1.8s` internal cutoff).
- Typed protocol/model layer (`pydantic` models for game messages and actions).
- Replay tooling (`.jsonl`) and analysis scripts for debugging and optimization loops.
- Easy-mode strategy stack:
  - `memory_solo`: strong heuristic baseline with per-day snapshot memory.
  - `optimized_easy`: offline plan replay with runtime validation and fallback to `memory_solo`.
- Medium-mode strategy stack:
  - evolved from `greedy` -> `medium_v2/v3/v4` -> `optimized_medium_v4/v5`.
  - offline planning (`scripts/optimize_medium_v4.py`, `scripts/optimize_medium_v5.py`) plus replay-time checkpoint validation.
  - latest fixes include drop-off occupancy handling, order-boundary carryover handling, and transient-vs-hard mismatch handling.

### What Is Still Not Done

- Re-validate `optimized_medium_v5` on fresh live runs after the latest occupancy/carryover fixes (current handoff marks this as pending).
- Improve medium consistency, not only peak score (reduce run-to-run variance and fallback collapses).
- Hard/Expert strategy track is not currently the focus in this branch (current active optimization work is Easy/Medium).

## Best Strategies So Far (Easy + Medium)

| Difficulty | Best Current Choice | Best Observed Replay | Notes |
|---|---|---|---|
| Easy | `optimized_easy` | `142` in `game_easy_20260304_212146.jsonl` | Replay matched `data/easy_2026-03-04_plan.json` 300/300 rounds in local analysis. |
| Medium (peak) | `optimized_medium_v5` | `106` in `game_medium_20260303_065132.jsonl` | Highest observed ceiling; replay includes `OptimizedMediumV5Strategy` diagnostics. |
| Medium (most validated checkpoint) | `optimized_medium_v4` | `91` in `game_medium_20260302_214042.jsonl` | Explicitly validated in handoff with exact planned-prefix adherence before fallback. |

Practical recommendation today:
- Easy: run `optimized_easy`.
- Medium: run `optimized_medium_v5` for ceiling, keep `optimized_medium_v4` as stable fallback while v5 post-fix validation is ongoing.

## Quick Start

```bash
# 1) Install (Python 3.11+)
pip install -e ".[dev]"

# 2) Configure token(s)
# .env is git-ignored. Never commit tokens.
# You can set either:
#   GROCERY_BOT_TOKEN=<jwt>
# or per-level:
#   GROCERY_BOT_TOKEN_EASY=<jwt>
#   GROCERY_BOT_TOKEN_MEDIUM=<jwt>

# 3) Smoke test
python scripts/run.py --strategy logger

# 4) Run recommended strategies
python scripts/run.py --level easy --strategy optimized_easy
python scripts/run.py --level medium --strategy optimized_medium_v5
```

## Optimization Workflow

```bash
# Capture/refresh daily snapshot from replay
python scripts/optimize.py --level easy --date 2026-03-08 --current-run game_easy_YYYYMMDD_HHMMSS.jsonl

# Build easy plan
python scripts/optimize.py --level easy --date 2026-03-08

# Build medium v5 plan
python scripts/optimize_medium_v5.py --level medium --date 2026-03-08 --max-orders 12
```

Generated plans are written under `data/` (git-ignored), then consumed by `optimized_easy` / `optimized_medium_v5`.

## Available Strategy Names

Current registry (`src/grocerybot/strategies/__init__.py`):
- `logger`
- `solo`
- `greedy`
- `memory_solo`
- `optimized_easy`
- `medium_v2`
- `medium_v3`
- `medium_v4`
- `optimized_medium`
- `optimized_medium_v4`
- `optimized_medium_v5`

## Protocol Summary

Server endpoint format:
- `wss://game-dev.ainm.no/ws?token=TOKEN`

Round contract:
- receive `game_state`,
- respond with one action per bot (`move_*`, `pick_up`, `drop_off`, `wait`) within 2 seconds.

Scoring:
- `+1` per delivered item,
- `+5` per completed order.

References:
- [spec/protocol.md](spec/protocol.md)
- [spec/schemas_global.json](spec/schemas_global.json)

## Development

```bash
ruff check src/ tests/
mypy src/
pytest
python scripts/replay.py game.jsonl
python scripts/analyze_replay.py game.jsonl
```

## Project Structure

```
src/grocerybot/
  models.py          Protocol models
  client.py          WebSocket loop + deadline handling
  grid.py            Grid/pathfinding helpers
  planner.py         Assignment and coordination utilities
  strategies/        Bot strategy implementations
  util/              Timer and logging utilities
scripts/             Runners, optimizers, replay analysis
docs/                Architecture and roadmap notes
spec/                Protocol docs + schemas (authoritative)
tests/               Unit and strategy tests
```
