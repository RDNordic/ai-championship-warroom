# Grocery Bot

Bot for the [NM i AI 2026](https://dev.ainm.no) Grocery Bot pre-competition challenge. Controls agents via WebSocket to navigate a grocery store, pick up items from shelves, and deliver orders.

## Quick Start

```bash
# 1. Install (Python 3.11+)
pip install -e ".[dev]"

# 2. Get a token
#    Sign in at dev.ainm.no → Challenge page → pick a map → click Play → copy the WebSocket URL

# 3. Configure
cp .env.example .env
# Paste your JWT token into .env

# 4. Run
python scripts/run.py --strategy logger        # smoke-test: connects, waits every round, logs state
python scripts/run.py --strategy solo           # Easy: single-bot A* pathfinding
python scripts/run.py --strategy greedy         # Medium: multi-bot greedy assignment
python scripts/run.py --strategy coordinated    # Hard: reservation-table planning
python scripts/run.py --strategy expert         # Expert: throughput-optimized
```

## Token Safety

Tokens are short-lived JWTs. Store them in `.env` (git-ignored). **Never commit tokens.**

```bash
# Or pass directly:
GROCERY_BOT_TOKEN=eyJ... python scripts/run.py --strategy solo
```

## Smoke Test (Logger Mode)

```bash
python scripts/run.py --strategy logger
```

Connects to the game, sends `wait` for every bot every round, and saves the full game state stream to a `.jsonl` replay file. Use this to verify connectivity and inspect game state structure.

## Running Each Difficulty

The difficulty is encoded in your JWT token (determined by which map you clicked Play on). The strategy determines how your bots behave:

| Difficulty | Bots | Recommended Strategy |
|------------|------|---------------------|
| Easy       | 1    | `solo`              |
| Medium     | 3    | `greedy`            |
| Hard       | 5    | `coordinated`       |
| Expert     | 10   | `expert`            |

Any strategy works with any difficulty — but higher-level strategies are designed for more bots.

## Protocol Summary

The game server communicates over WebSocket (`wss://game-dev.ainm.no/ws?token=TOKEN`). Each round, the server sends a `game_state` JSON with the full grid, bot positions, shelf items, and orders. You respond within 2 seconds with an action per bot: `move_up/down/left/right`, `pick_up` (adjacent shelf item), `drop_off` (at the drop-off cell), or `wait`. Invalid actions silently become `wait`. Games last 300 rounds max / 120 seconds wall-clock. Scoring: +1 per delivered item, +5 per completed order.

Full spec: [spec/protocol.md](spec/protocol.md) | Schemas: [spec/schemas_global.json](spec/schemas_global.json)

## Development

```bash
ruff check src/ tests/              # lint
mypy src/                           # type check
pytest                              # run tests
python scripts/replay.py game.jsonl # replay a saved game
```

## Project Structure

```
src/grocerybot/
  models.py          Pydantic models (GameState, BotAction, etc.)
  client.py          WebSocket client loop with deadline enforcement
  grid.py            Passable grid, BFS, A*
  planner.py         Task assignment + collision resolution
  strategies/        Strategy implementations (logger, solo, greedy, coordinated, expert)
  util/              Timer, structured logging, replay
spec/                Protocol docs + JSON schemas + example messages
docs/                Architecture and roadmap
tests/               Unit + integration tests
scripts/             Entry points (run.py, replay.py)
```
