# CONTEXT.md — Grocery Bot Project

## What This Is

Bot for the NM i AI 2026 Grocery Bot WebSocket challenge. Controls agents on a grid-based grocery store to pick up items and deliver orders. Four difficulty levels (Easy/Medium/Hard/Expert) with 1/3/5/10 bots.

## Non-Negotiables

- **Protocol truth lives in `spec/`** — spec/protocol.md and spec/schemas_global.json are authoritative. If code disagrees, fix the code.
- **2-second response deadline** — client.py enforces 1.8s hard cutoff. Strategies must respect this.
- **Never commit tokens** — .env is git-ignored. Tokens go in env vars only.
- **Pydantic v2 for all protocol models** — no manual dict wrangling.
- **Actions resolve in bot ID order** — collision avoidance must simulate this.
- **Invalid actions silently become wait** — never crash, never send bad JSON.

## Module Map

```
src/grocerybot/
  models.py             Protocol models (GameState, BotAction, etc.)
  client.py             WebSocket loop + deadline enforcement
  grid.py               PassableGrid, BFS, A*, distance maps
  planner.py            Task assignment + collision resolution
  strategies/
    base.py             Strategy ABC (on_game_start, decide)
    logger.py           M1: always wait + log
    solo.py             M2: single-bot A* (Easy)
    greedy.py           M3: multi-bot greedy (Medium)
    coordinated.py      M4: reservation-table (Hard)
    expert.py           M5: throughput-optimized (Expert)
  util/
    timer.py            TimeBudget context manager
    logger.py           ReplayWriter + rich console output
scripts/
  run.py                CLI entry: --strategy <name>, token from .env
  replay.py             Replay saved .jsonl games
spec/                   Protocol docs + schemas + examples (DO NOT EDIT)
docs/
  ARCHITECTURE.md       Component design + data flow
  ROADMAP.md            Milestones + acceptance criteria
tests/
  conftest.py           Fixtures loading spec/examples/
  test_models.py        Model parsing tests
  test_grid.py          Grid + pathfinding tests (M2)
  test_planner.py       Assignment + collision tests (M3)
```

## Key Dependencies

- `websockets` — async WebSocket client
- `pydantic` v2 — model validation
- `python-dotenv` — token from .env
- `rich` — console output
- Dev: `ruff`, `mypy`, `pytest`, `pytest-asyncio`

## Build Milestones (see docs/ROADMAP.md)

M1 Logger → M2 Solo → M3 Greedy → M4 Coordinated → M5 Expert → M6 Polish

## Running

```bash
pip install -e ".[dev]"        # install
pytest                          # test
python scripts/run.py --strategy logger   # run
```
