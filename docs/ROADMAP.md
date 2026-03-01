# Roadmap

## Milestone 1 — Logger Bot

**Goal:** Validate connectivity, model parsing, replay logging, timing.

### Tasks
1. Implement `models.py` — all pydantic models from schemas_global.json
2. Implement `util/timer.py` — TimeBudget context manager
3. Implement `util/logger.py` — ReplayWriter (.jsonl) + rich console output
4. Implement `client.py` — async WebSocket loop with 1.8s deadline
5. Implement `strategies/base.py` — Strategy ABC
6. Implement `strategies/logger.py` — always-wait strategy
7. Implement `scripts/run.py` — CLI entry point (--strategy, token from .env)
8. Write `tests/test_models.py` — parse all examples/*.json fixtures
9. Write `tests/conftest.py` — fixtures for loading example JSON files

### Acceptance Criteria
- [ ] `pytest tests/test_models.py` passes — all example JSONs parse correctly
- [ ] `python scripts/run.py --strategy logger` connects, runs 300 rounds, exits cleanly
- [ ] Replay .jsonl file is produced with 300 game_state entries + 1 game_over
- [ ] Console shows round number, score, and per-round elapsed time
- [ ] Final score = 0 (all waits)
- [ ] No crashes, no timeouts, no malformed JSON sent

### Estimated Effort
~200 lines of production code + ~100 lines of tests.

---

## Milestone 2 — Easy Baseline (Solo Bot)

**Goal:** Single-bot pathfinding that completes orders on Easy maps.

### Tasks
1. Implement `grid.py` — PassableGrid, BFS, A*, distance maps, adjacent_walkable
2. Implement `strategies/solo.py`:
   - Round 0: build grid, cache drop-off distance map
   - Each round: determine needed items → find nearest → A* → move/pick_up/drop_off
3. Write `tests/test_grid.py`:
   - Build grid from easy example → verify passable/impassable
   - A* from spawn to drop-off → valid path
   - A* to item-adjacent cell → doesn't include shelf cell
   - Distance map correctness
4. Manual testing on Easy map via dev.ainm.no

### Acceptance Criteria
- [ ] `pytest tests/test_grid.py` passes
- [ ] On Easy: bot navigates to items, picks them up, delivers to drop-off
- [ ] On Easy: at least 1 order completed (score >= 8: 3 items + 1 order bonus)
- [ ] Bot never walks into walls (verify from replay)
- [ ] Bot never attempts pick_up from non-adjacent position
- [ ] Response time consistently < 100ms per round

---

## Milestone 3 — Medium Baseline (Greedy Multi-Bot)

**Goal:** 3-bot coordination with greedy task assignment on Medium maps.

### Tasks
1. Implement `planner.py` — OrderTracker, TaskAssigner, CollisionResolver
2. Implement `strategies/greedy.py`:
   - OrderTracker computes remaining needs
   - TaskAssigner assigns each bot to item or drop-off (greedy by distance)
   - Each bot A*s independently
   - CollisionResolver deconflicts (bot-ID order)
3. Write `tests/test_planner.py`:
   - OrderTracker: correct remaining count with partial deliveries + inventory
   - TaskAssigner: 2 items, 3 bots → 2 assigned to items, 1 to drop-off or wait
   - CollisionResolver: two bots same target → lower ID keeps, higher waits
4. Manual testing on Medium map

### Acceptance Criteria
- [ ] `pytest tests/test_planner.py` passes
- [ ] On Medium: all 3 bots contribute (no bot permanently idle)
- [ ] On Medium: score > Easy best score (more bots = more throughput)
- [ ] No two bots collide (from replay: no round where 2+ bots share a non-spawn cell)
- [ ] Response time < 200ms per round

---

## Milestone 4 — Hard (Coordinated Planning)

**Goal:** 5-bot coordination with reservation tables on Hard maps.

### Tasks
1. Extend `grid.py`:
   - A* accepts `blocked: set[Position]` parameter
   - Reservation table: `dict[Position, int]` (cell → claiming bot ID)
2. Implement `strategies/coordinated.py`:
   - Plan bots in ID order; each bot's A* avoids cells reserved by lower-ID bots
   - Yield behavior in 1-wide aisles
   - Preview-order pre-picking when active order fully assigned
3. Test reservation table logic:
   - Bot 0 reserves path; bot 1 routes around
   - Aisle bottleneck: bots yield correctly
4. Manual testing on Hard map, compare score to greedy strategy on Hard

### Acceptance Criteria
- [ ] On Hard: score > greedy strategy on same map
- [ ] No deadlocks (bots never permanently stuck)
- [ ] Preview-order pre-picking occurs (verify from replay: bot picks item not in active order)
- [ ] Response time < 500ms per round

---

## Milestone 5 — Expert (Throughput Optimization)

**Goal:** Maximum throughput with 10 bots on 28x18 grid.

### Tasks
1. Implement `strategies/expert.py`:
   - Batch pickups: route through up to 3 items per trip
   - Zone assignment: divide 5 aisles among 10 bots (2 per zone)
   - Pipeline: stagger pickup/delivery phases
   - Congestion control: if >2 bots near drop-off, defer others
2. Implement batch routing: given bot + list of up to 3 item positions, find short route visiting all (nearest-neighbor heuristic, not full TSP)
3. Test zone assignment logic
4. Manual testing + score comparison on Expert map

### Acceptance Criteria
- [ ] On Expert: score > coordinated strategy on same map
- [ ] Bots are distributed across aisles (no aisle has >3 bots simultaneously)
- [ ] Drop-off throughput: no more than 2 bots waiting at drop-off at any time
- [ ] Response time < 1000ms per round (10 bots, larger grid)

---

## Milestone 6 — Polish & Leaderboard

**Goal:** Maximize leaderboard score (sum of best across all 4 maps).

### Tasks
1. Run each strategy on its target difficulty, record best scores
2. Profile and optimize bottlenecks if any round exceeds 500ms
3. Tune parameters:
   - Assignment weights (distance vs. inventory fullness)
   - Congestion thresholds
   - Pre-pick aggressiveness
4. Add `scripts/replay.py` — visual replay of saved .jsonl files
5. Clean up, final lint/type-check pass

### Acceptance Criteria
- [ ] All 4 maps played, best scores recorded
- [ ] `ruff check` clean
- [ ] `mypy --strict` clean
- [ ] All tests pass
- [ ] No token in any committed file

---

## Milestone Dependency Graph

```
M1 Logger ──→ M2 Solo ──→ M3 Greedy ──→ M4 Coordinated ──→ M5 Expert ──→ M6 Polish
   │              │            │
   └─ models      └─ grid      └─ planner
      client         astar        assignment
      timer                       collision
      replay
```

Each milestone is independently testable and produces a working bot at that level.
