# Architecture

## Overview

```
┌─────────────────────────────────────────────────────────┐
│  scripts/run.py                                         │
│  (entry point: parse args, load token, pick strategy)   │
└──────────────────────┬──────────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────────┐
│  client.py — WebSocket Client Loop                      │
│                                                         │
│  connect(token) → loop:                                 │
│    recv game_state → parse → timer.start()              │
│    strategy.decide(state) → actions                     │
│    timer.check(1.8s) → fallback to all-wait if over     │
│    send actions → log to replay .jsonl                  │
│    recv game_over → break                               │
└──────┬──────────────────┬───────────────────────────────┘
       │                  │
       ▼                  ▼
┌──────────────┐   ┌──────────────────────────────────────┐
│  models.py   │   │  Strategy (base.py ABC)              │
│  (pydantic)  │   │                                      │
│              │   │  on_game_start(state) → setup grid   │
│  GameState   │   │  decide(state) → list[BotAction]     │
│  GameOver    │   │                                      │
│  BotAction   │   │  Implementations:                    │
│  BotResponse │   │    logger.py   → always wait         │
│  Bot, Item   │   │    solo.py     → single-bot A*       │
│  Order, Grid │   │    greedy.py   → multi-bot greedy    │
│  Position    │   │    coordinated → reservation table   │
└──────────────┘   │    expert.py   → throughput-max      │
                   └──────┬───────────────────────────────┘
                          │ uses
                          ▼
         ┌────────────────────────────────────┐
         │  grid.py         │  planner.py     │
         │                  │                 │
         │  PassableGrid    │  TaskAssigner   │
         │  bfs()           │  CollisionRes.  │
         │  astar()         │  OrderTracker   │
         │  distance_map()  │                 │
         └────────────────────────────────────┘
```

## Components

### models.py — Protocol Models

Pydantic v2 models mapped 1:1 from `spec/schemas_global.json`.

```
Position = tuple[int, int]   # validated from [x, y] JSON lists

GameState:
  type: Literal["game_state"]
  round: int
  max_rounds: int = 300
  grid: Grid                 # width, height, walls: list[Position]
  bots: list[Bot]            # id, position, inventory: list[str]
  items: list[Item]          # id, type, position (shelf cell)
  orders: list[Order]        # id, items_required, items_delivered, complete, status
  drop_off: Position
  score: int
  active_order_index: int
  total_orders: int

GameOver:
  type: Literal["game_over"]
  score, rounds_used, items_delivered, orders_completed: int

BotAction = MoveAction | PickUpAction | DropOffAction | WaitAction
  - discriminated on "action" field
  - PickUpAction has extra "item_id: str"

BotResponse:
  actions: list[BotAction]
```

Key design decisions:
- `Position` is a `tuple[int, int]` internally for hashability (dict keys, sets). Pydantic validator converts `[x, y]` lists on parse.
- Models use `model_validate(json_data)` — no manual dict wrangling.
- `BotResponse.model_dump()` produces the exact JSON the server expects.

### client.py — WebSocket Client Loop

```python
async def play(token: str, strategy: Strategy) -> GameOver:
    url = f"wss://game-dev.ainm.no/ws?token={token}"
    async with websockets.connect(url) as ws:
        replay = ReplayWriter(...)
        while True:
            raw = await ws.recv()
            msg = json.loads(raw)

            if msg["type"] == "game_over":
                result = GameOver.model_validate(msg)
                replay.write(msg)
                return result

            state = GameState.model_validate(msg)
            replay.write(msg)

            if state.round == 0:
                strategy.on_game_start(state)

            with TimeBudget(limit=1.8) as timer:
                actions = strategy.decide(state)

            if timer.exceeded:
                actions = [WaitAction(bot=b.id) for b in state.bots]

            response = BotResponse(actions=actions)
            await ws.send(response.model_dump_json())
            replay.write(response.model_dump())
```

Guarantees:
- Never sends after 2s (1.8s cutoff + serialization overhead < 200ms)
- Never sends malformed JSON (pydantic serialization)
- Always includes an action for every bot (strategy contract + fallback)
- Logs every round to .jsonl for replay/debugging

### grid.py — Spatial Data Structures

**PassableGrid** — built once from round-0 GameState:

```
passable: list[list[bool]]    # passable[x][y], True = floor/drop-off
walls: set[Position]          # O(1) lookup
shelves: set[Position]        # all item positions from round 0 (permanently blocked)
drop_off: Position
width: int
height: int
```

**Why snapshot shelves from round 0?**
Items disappear from `state.items` when picked up, but the shelf cell remains physically there — it's never walkable. By capturing all item positions on round 0, we have the permanent shelf layout even after items are collected.

**BFS** — `bfs(start, goal, grid) -> list[Position]`:
- Standard queue-based BFS on 4-connected grid
- Returns path from start to goal (inclusive), or empty list if unreachable

**A*** — `astar(start, goal, grid, blocked: set[Position] = {}) -> list[Position]`:
- Manhattan heuristic (admissible)
- `blocked` parameter: additional cells to avoid (used for multi-agent reservation)
- `heapq` with `(f_score, counter, position)` for stable priority

**Distance map** — `bfs_distance_map(goal, grid) -> dict[Position, int]`:
- BFS from goal outward, recording distance to every reachable cell
- Cached by goal position (grid never changes within a game)
- Used as perfect heuristic for A* and for nearest-item selection

**Adjacency helper** — `adjacent_walkable(shelf_pos, grid) -> list[Position]`:
- Returns walkable cells at Manhattan distance 1 from a shelf
- Used to find where a bot must stand to pick up an item

### planner.py — Task Assignment & Coordination

**OrderTracker**:
- Input: `state.orders` (active + preview), all bot inventories
- Output: `needed: dict[str, int]` — item types still needed for active order (accounting for items in transit in bot inventories)

**TaskAssigner**:
- Input: `needed` items, `state.items` (shelf items), `state.bots`, distance maps
- Logic:
  1. Bots with useful inventory → assign to drop-off
  2. Bots with full inventory (no useful items) → assign to drop-off (deliver what matches, useless items stay)
  3. Remaining bots → assign to nearest needed item (greedy by distance)
  4. Deduplication: if two bots target the same item, closer bot wins
- Output: `dict[int, Task]` — bot_id → task (GoToItem, GoToDropoff, Wait)

**CollisionResolver**:
- Input: planned next-position for each bot (from pathfinding)
- Process in bot-ID order:
  1. Bot 0: mark its destination as occupied
  2. Bot 1: if destination occupied, change to wait; else mark occupied
  3. Continue for all bots
- Output: final `list[BotAction]` with collisions resolved
- This mirrors the server's sequential resolution exactly

### strategies/ — Strategy Implementations

All strategies subclass `Strategy(ABC)`:

```python
class Strategy(ABC):
    @abstractmethod
    def on_game_start(self, state: GameState) -> None:
        """Called once on round 0. Build grid, caches."""

    @abstractmethod
    def decide(self, state: GameState) -> list[BotAction]:
        """Called each round. Must return one action per bot."""
```

**logger.py** (M1): `decide` returns `[WaitAction(bot=b.id) for b in state.bots]`

**solo.py** (M2): Single-bot logic:
1. Need items? → A* to nearest needed item's adjacent cell → move or pick_up
2. Have useful items? → A* to drop-off → move or drop_off
3. Else → wait

**greedy.py** (M3): Multi-bot extension:
1. OrderTracker → needed items
2. TaskAssigner → assign bots to items/drop-off
3. Each bot: A* to assigned target, take first step
4. CollisionResolver → resolve conflicts

**coordinated.py** (M4): Reservation-table planning:
1. Same as greedy, but A* uses `blocked` set from reservation table
2. Bots planned in ID order; each bot's path reserves cells for higher-ID bots to avoid
3. Preview-order pre-picking when active order items are fully assigned

**expert.py** (M5): Throughput optimization:
1. Batch pickups: route through up to 3 items before returning to drop-off
2. Zone assignment: divide aisles among bots (2 per aisle at 10 bots / 5 aisles)
3. Pipeline: deliver/pick in parallel across bot groups
4. Congestion control: stagger drop-off visits

### util/ — Support Utilities

**timer.py** — `TimeBudget`:
- Context manager wrapping `time.monotonic()`
- `remaining() -> float` — seconds left
- `exceeded: bool` — set if limit hit
- Used by client (1.8s hard limit) and strategies (bail early if tight)

**logger.py** — `ReplayWriter`:
- Appends JSON objects to a `.jsonl` file (one per line)
- Each line: `{"round": N, "type": "game_state"|"response"|"game_over", "data": {...}}`
- Rich console output: round, score, elapsed, bot positions

## Data Flow Per Round

```
1. ws.recv() → raw JSON string
2. json.loads() → dict
3. GameState.model_validate() → typed GameState object
4. strategy.on_game_start() [round 0 only] → builds PassableGrid, caches
5. strategy.decide(state):
   a. OrderTracker.needed() → what items the active order still needs
   b. TaskAssigner.assign() → bot → task mapping
   c. For each bot: A*/pathfind to target → planned next position
   d. CollisionResolver.resolve() → final safe actions
6. TimeBudget check → if over 1.8s, replace with all-wait
7. BotResponse(actions=...).model_dump_json() → JSON string
8. ws.send() → server
9. ReplayWriter.write() → .jsonl file
```

## Performance Considerations

- Grid + shelves computed once (round 0). Never recomputed.
- BFS distance maps cached per goal. ~200 maps max (expert). Each ~500 cells. Total <1MB.
- A* with cached BFS distance as heuristic → optimal path found immediately (no backtracking).
- Assignment is O(bots * items) ≈ O(60) for expert. Sub-millisecond.
- Total per-round budget: ~1-5ms for easy, ~10-50ms for expert. Well within 1.8s.
- JSON parse + pydantic validation: ~1ms for expert-sized state.
- Bottleneck for expert: collision resolution with 10 bots in narrow aisles. Reservation table is O(bots * path_length) ≈ O(10 * 30) = O(300). Trivial.
