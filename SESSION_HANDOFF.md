# SESSION_HANDOFF.md

## Checkpoint

M2 (Solo Bot) implemented and live-tested (118 pts on Easy). Daily memory system built but optimized mode not yet improving over discovery mode.

## Latest Work

- Implemented grid.py: PassableGrid, BFS, A*, bfs_distance_map, adjacent_walkable, direction_for_move
- Implemented strategies/solo.py: single-bot A* with batch pickup
- Fixed critical bug: active order lookup by status=="active" (not active_order_index as array index)
- Fixed WS endpoint to wss://game.ainm.no/ws (official docs, not MCP server's game-dev URL)
- Saved official docs to spec/official-docs.md, added errata to spec/protocol.md
- Built daily_memory.py: DailySnapshot persistence keyed by date+level
- Built strategies/memory_solo.py: discovery/optimized auto-switching, nearest-neighbor routing, preview pre-pick
- Added on_game_over hook to Strategy ABC + client.py
- 92 tests pass, ruff clean, mypy clean

## Known Issues

- **memory_solo optimized mode scores identical to discovery mode (118)** — needs investigation:
  - Is the snapshot actually being saved/loaded? Check data/easy_YYYY-MM-DD.json exists
  - Is `_has_memory` True on 2nd run? Add logging to verify
  - Nearest-neighbor routing may not differ from reactive greedy when items restock and shelves are nearby
  - Real win: pre-knowing the full order sequence to optimize across orders
- active_order_index is a global counter, NOT an index into the orders array
- Orders are infinite (official docs confirm, not capped at total_orders)

## Next Steps

1. **Debug memory_solo optimized mode**: verify snapshot save/load, check _has_memory flag, compare decision paths
2. **Cross-order optimization**: pick items for order N+1 on return trip from delivering order N
3. **Consider M3 (Greedy Multi-Bot)**: grid.py + daily_memory ready; need planner.py

## Restart Prompt

```
Read CONTEXT.md and SESSION_HANDOFF.md. M2 done (118 pts Easy), daily memory built but optimized mode not improving score. Debug why memory_solo 2nd run scores same as 1st. Check: is snapshot saved? Is it loaded? Does _has_memory=True change behavior? The real optimization is cross-order pre-picking using the known order sequence.
```
