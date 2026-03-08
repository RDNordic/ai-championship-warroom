# CLAUDE.md — Pre-Challenge Modular Bot

Inherits from the root `CLAUDE.md`. Additional rules below.

## Architecture
- Each module has a single responsibility with clear input/output contract.
- Technique selection is config-driven (`config/*.json`).
- Abstract base classes define interfaces; concrete implementations are swappable.

## Module Contracts
| Module | Input | Output |
|--------|-------|--------|
| Pathfinder | grid, start, goals, blocked | distance (int) or next_step (Coord) |
| Assigner | bots, items, needed, distance_fn | dict[bot_id -> item_id] |
| CollisionResolver | bot_id, start, goals, grid, pathfinder, occupied, reserved | action dict |
| DeliveryCoordinator | bots, drop_off, delivery_alloc | queue leadership, slot allocation |
| OrderManager | items, needed, bot_targets | preview IDs, duty bots, item targeting |
| PickCooldownTracker | bots, round, bot_targets | is_blocked(item_id, round) |

## Rules
- New algorithms go in their own file under the relevant module directory.
- New algorithms must implement the module's abstract base class.
- Config changes go in `config/` JSON files.
- Always run `python -c "from bot import GroceryBot, load_config; ..."` to verify imports after changes.
- Track progress in `PROGRESS.md`.
