# CLAUDE.md — AI Assistant Working Agreement

## Repo Structure

```
src/grocerybot/         Production code (package)
  models.py             Pydantic v2 models — GameState, BotAction, BotResponse, etc.
  client.py             Async WebSocket client loop with 1.8s deadline enforcement
  grid.py               PassableGrid, BFS, A*, distance maps
  planner.py            TaskAssigner, CollisionResolver, OrderTracker
  strategies/           Strategy implementations — one file per strategy
    base.py             Strategy ABC (on_game_start, decide)
    logger.py           Milestone 1: always wait + log
    solo.py             Milestone 2: single-bot A*
    greedy.py           Milestone 3: multi-bot greedy assignment
    coordinated.py      Milestone 4: reservation-table planning
    expert.py           Milestone 5: throughput-optimized
  util/                 Timer, structured logging, replay writer
scripts/                Entry points (run.py, replay.py)
spec/                   Protocol source of truth — DO NOT EDIT
tests/                  pytest tests
docs/                   Architecture + roadmap
```

## Protocol Source of Truth

- `spec/protocol.md` — full rules (connection, actions, scoring, timing, errors)
- `spec/schemas_global.json` — JSON Schema for all message types
- `spec/schemas_{easy,medium,hard,expert}.json` — per-level constraints
- `spec/examples/` — reference JSON payloads

If protocol.md and code disagree, **protocol.md wins**. Fix the code.

## Coding Conventions

- Python 3.11+, type hints everywhere
- Pydantic v2 for all protocol models — use `model_validate` for parsing
- `ruff check` must pass (line-length 100, rules: E/F/W/I/UP)
- `mypy --strict` must pass
- `pytest` must pass
- Async code uses `asyncio` + `websockets` library
- Coordinates are always `tuple[int, int]` internally (converted from `[x, y]` JSON lists)

## How to Add a New Strategy

1. Create `src/grocerybot/strategies/my_strategy.py`
2. Subclass `Strategy` from `strategies/base.py`
3. Implement `on_game_start(state)` and `decide(state) -> list[BotAction]`
4. Register in `strategies/__init__.py` name map
5. Run: `python scripts/run.py --strategy my_strategy`
6. Add tests in `tests/test_my_strategy.py`

## How to Run Tests

```bash
pytest                    # all tests
pytest tests/test_models.py  # just model parsing tests
pytest -x                 # stop on first failure
```

## Critical Rules (From Protocol)

- 2-second response deadline per round — client.py enforces 1.8s hard cutoff
- Actions resolve in bot ID order (0 first) — collision avoidance must simulate this
- Invalid actions silently become `wait` — never crash, never send bad JSON
- Inventory max 3 items per bot
- Only active order accepts deliveries; non-matching items stay in inventory
- Disconnect = game over, no reconnect

## Token Safety

- Tokens go in `.env` (git-ignored) or env var `GROCERY_BOT_TOKEN`
- NEVER commit tokens, NEVER hardcode tokens in source files
- `.env` is in `.gitignore` — verify before every commit

## Module Size

Soft limit: 300 lines per file. Split if approaching.

## Session Workflow

This project follows the global session discipline from `~/.claude/CLAUDE.md`:

- **Start**: Read CLAUDE.md → CONTEXT.md → SESSION_HANDOFF.md → do the next step
- **During**: One focused task per session. Stop cleanly at ~80-90% context.
- **End**: Archive SESSION_HANDOFF.md → `handoff_archive/SESSION_HANDOFF_{YYYY-MM-DD-HHmm}.md`, write a new one (<80 lines), commit both.

Key files:
- `CONTEXT.md` — project structure, non-negotiables, module map
- `SESSION_HANDOFF.md` — current checkpoint + exact next step
- `handoff_archive/` — timestamped previous handoffs
