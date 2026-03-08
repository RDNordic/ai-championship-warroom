# Pre-Challenge Modular Codebase — Progress

## Phase 1: Scaffolding — DONE
Created modular directory structure with clear separation of concerns.

```
solutions/pre-challenge/
├── config/
│   ├── base.json              # Shared defaults
│   ├── expert.json            # Expert overrides (regret_greedy, 2 queue leaders)
│   └── hard.json              # Hard overrides (greedy, 1 queue leader)
├── core/
│   ├── __init__.py
│   ├── types.py               # Coord, Grid, neighbors, manhattan, action_from_step
│   └── state_parser.py        # parse_grid/bots/items/orders, needed_counts, occupied_positions
├── pathfinding/
│   ├── __init__.py
│   ├── base.py                # Abstract Pathfinder interface
│   └── bfs.py                 # BFS pathfinder with per-round cache
├── assignment/
│   ├── __init__.py
│   ├── base.py                # Abstract Assigner interface
│   └── greedy.py              # GreedyAssigner + RegretGreedyAssigner
├── collision/
│   ├── __init__.py
│   ├── base.py                # Abstract CollisionResolver interface
│   └── reservation.py         # ReservationResolver with progressive relaxation
├── coordination/
│   ├── __init__.py
│   ├── delivery.py            # DeliveryCoordinator (queue, slots, clearance, staging)
│   ├── order_manager.py       # OrderManager (preview duty, item targeting, pick_if_adjacent)
│   └── pick_cooldown.py       # PickCooldownTracker (failed pick detection + blocking)
├── bot.py                     # GroceryBot — wires modules via config
├── runner.py                  # WebSocket client + RunLogger + CLI
├── CLAUDE.md                  # Challenge-specific rules
└── PROGRESS.md                # This file
```

### What was extracted from existing code
- **BFS pathfinder**: from `run_hard.py` `_bfs_distance` + `_bfs_first_step` (with wall/shelf caching)
- **Greedy assignment**: from `run_hard.py` `_build_greedy_assignments` (distance-sorted candidates)
- **Regret-greedy assignment**: from `run_expert.py` `_build_greedy_assignments` (regret-based priority)
- **Reservation collision**: from both files `_move_toward` (with 3-level relaxation from expert)
- **Delivery coordination**: from both files (slot allocation, queue leadership, clearance, staging)
- **Order management**: from both files (preview duty, item targeting, pick_if_adjacent)
- **Pick cooldown**: from both files `_update_pick_retry_state` (streak tracking + blocking)
- **Runner**: from both files (WebSocket loop, RunLogger, sanitize_actions)

### Config-driven technique selection
- `config/base.json`: shared defaults
- `config/expert.json`: overrides for Expert (regret_greedy assignment, 2 preview cap offset)
- `config/hard.json`: overrides for Hard (greedy assignment, 1 queue leader)
- Config merging: difficulty JSON deep-merges over base JSON

### Verified
- All modules import correctly
- Config loading and merging works
- Grid, BFS, assignment, collision modules pass basic smoke tests
- GroceryBot instantiates with correct module wiring

## Phase 2: BFS Pathfinding Extraction — DONE
Extracted into `pathfinding/bfs.py` with:
- `distance(grid, start, goal_pos, blocked)` → int (9999 if unreachable)
- `first_step(grid, start, goals, blocked)` → Coord | None
- Per-round cache via `clear_cache()`
- Abstract `Pathfinder` base class for future A* / WHCA* implementations

## Phase 3: Integration Test — DONE
Ran modular bot live against Expert server. Initial run scored 2 (vs monolith 40).
Diagnosed and fixed 3 extraction bugs, final score **59** (6 orders, 29 items delivered).

### Bugs found and fixed

1. **Wait streak condition** (`bot.py` `_update_wait_state`):
   Modular incremented wait_streak whenever the bot didn't move (position unchanged).
   Monolith only increments when `prev_action == "wait" AND prev_pos == pos`.
   **Impact**: Collision failures (bot tried to move but couldn't) were counted as waits,
   triggering random nudges that caused oscillation and 54% collision rate.

2. **Nudge threshold** (`config/base.json`, `config/expert.json`):
   Modular used threshold 3, monolith uses `>= 1`.
   **Impact**: Deadlock-breaking nudges were delayed, compounding with bug #1.

3. **Bot processing order** (`bot.py` `decide`):
   Modular sorted delivery bots by dropoff distance, then assigned pickers, then idle.
   Monolith simply processes delivery bots first, then non-delivery bots (no sub-sorting).
   **Impact**: Sub-sorting changed reservation order, causing interference between bots.

### Additional fix: `last_action` tracking
Added `self.last_action: dict[int, str]` to `GroceryBot.__init__` and recording after
each bot decision, matching the monolith's pattern. Used by wait streak and pick cooldown.

### Results
| Run | Score | Items | Orders | Collision Rate |
|-----|-------|-------|--------|----------------|
| Modular (before fix) | 2 | 2 | 0 | 54% |
| Monolith baseline | 40 | — | 4 | 38% |
| Modular (after fix) | 59 | 29 | 6 | TBD |

### Replay logs
- `logs/game_20260308_153717.jsonl` — pre-fix run (score 2)
- `logs/game_20260308_181452.jsonl` — post-fix run (score 59)
- `logs/run_history.csv` — run history

## Phases Remaining

### Phase 4: New Algorithm Stubs
- `pathfinding/astar.py` — A* with Manhattan heuristic
- `assignment/hungarian.py` — Hungarian algorithm for optimal assignment
- `collision/cbs.py` — Conflict-Based Search

### Phase 5: Expert-Specific Tuning
- Endgame policy improvements (wait clusters in rounds 271-299)
- Congestion/deadlock handling
- Spatial partitioning for 10-bot traffic
