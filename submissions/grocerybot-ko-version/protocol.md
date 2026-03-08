# Grocery Bot WebSocket Protocol

> Every rule is tagged **[GLOBAL]**, **[EASY]**, **[MEDIUM]**, **[HARD]**, or **[EXPERT]**.
> If the MCP server did not explicitly state something, it is marked **[UNKNOWN]**.

---

## GLOBAL

Everything in this section applies identically to all four difficulty levels.

### Connection Lifecycle [GLOBAL]

| Step | Detail |
|------|--------|
| Auth | JWT token passed as query parameter — no headers needed |
| Endpoint | `wss://game-dev.ainm.no/ws?token=<jwt_token>` |
| Token source | Click **Play** on a map at [dev.ainm.no/challenge](https://dev.ainm.no/challenge), or call the `request_game(map_id)` MCP tool |
| Level selection | The JWT token encodes the chosen map/difficulty. The WebSocket endpoint is the same for all levels. |
| Handshake | Standard WebSocket upgrade over TLS. No subprotocols or custom headers. |
| Game start | Immediate on connect — server sends `game_state` (round 0) with no client "ready" signal |
| Reconnect | **Not supported.** Disconnect = game over, score saved as-is. |
| Cooldown | 10 seconds between games per team |

### Message Envelope [GLOBAL]

All messages are single JSON objects over the WebSocket text frame. No framing, no batching, no binary.

```
Server → Client: {"type": "game_state", ...}   (each round)
Client → Server: {"actions": [...]}
...
Server → Client: {"type": "game_over", ...}     (once, final)
```

### Coordinate System [GLOBAL]

- Origin `(0, 0)` is the **top-left** corner
- X increases **rightward**, Y increases **downward**
- All positions are `[x, y]` integer arrays

```
(0,0) ───→ x
  │
  ↓
  y
```

### Cell Types [GLOBAL]

| Symbol | Meaning | Walkable |
|--------|---------|----------|
| `.`    | Floor   | Yes      |
| `#`    | Wall (borders + aisle structures) | No |
| Shelf  | Contains items | No — pick up by standing adjacent |
| `D`    | Drop-off zone | Yes |

### Store Layout [GLOBAL]

Stores have parallel vertical aisles (shelf–walkway–shelf, 3 cells wide), connected by horizontal corridors at top, bottom, and mid-height. All maps have border walls. Grid structure (walls, shelf positions) is fixed per map. Item placement and orders rotate daily at midnight UTC (seeded from `map_seed + day_of_competition`). Same day = deterministic game.

### Spawn [GLOBAL]

All bots start at the **bottom-right** corner (inside the border). The spawn tile is exempt from collision — bots can share it at game start.

### Timing [GLOBAL]

| Constraint | Value |
|------------|-------|
| Max rounds | 300 (rounds 0–299) |
| Per-round response deadline | 2 seconds |
| Wall-clock limit per game | 120 seconds |
| Timeout behavior | All bots `wait` that round — no penalty |

### Action Resolution Order [GLOBAL]

Actions resolve in **bot ID order** (ascending). Bot 0 moves first, then bot 1, etc. If bot 1 tries to move where bot 0 just arrived, bot 1 is blocked.

### Bot Inventory [GLOBAL]

- Capacity: **3 items** per bot
- Bots can pick up **any** item from any shelf, regardless of which order needs it

### Orders [GLOBAL]

- **Sequential**: only one active order at a time
- **Two visible**: `"active"` (deliverable) + `"preview"` (visible, not deliverable)
- **Infinite**: orders keep generating — rounds are the only limit
- On active order completion: preview → active, new preview appears, inventory auto-rechecked against new active order

### Inbound Message: `game_state` [GLOBAL]

Schema is identical across all levels. See `schemas_global.json` for the full JSON Schema.

| Field | Type | Description |
|-------|------|-------------|
| `type` | `string` | Always `"game_state"` |
| `round` | `int` | Current round (0-indexed) |
| `max_rounds` | `int` | Always `300` |
| `grid.width` | `int` | Grid width in cells |
| `grid.height` | `int` | Grid height in cells |
| `grid.walls` | `int[][]` | `[x, y]` wall positions |
| `bots` | `object[]` | All bots: `id`, `position [x,y]`, `inventory` |
| `items` | `object[]` | All shelf items: `id`, `type`, `position [x,y]` |
| `orders` | `object[]` | Active + preview (max 2): `id`, `items_required`, `items_delivered`, `complete`, `status` |
| `drop_off` | `int[]` | `[x, y]` of the drop-off zone |
| `score` | `int` | Current cumulative score |
| `active_order_index` | `int` | Index of the current active order |
| `total_orders` | `int` | Total orders in the game |

### Inbound Message: `game_over` [GLOBAL]

Sent once when the game ends. No response expected.

| Field | Type | Description |
|-------|------|-------------|
| `type` | `string` | Always `"game_over"` |
| `score` | `int` | Final score |
| `rounds_used` | `int` | Rounds played |
| `items_delivered` | `int` | Total items delivered |
| `orders_completed` | `int` | Total orders fully completed |

### Outbound Action Schema [GLOBAL]

The action envelope and all action types are identical across levels. Only the array length differs (matching bot count).

```json
{
  "actions": [
    {"bot": <id>, "action": "<action_type>", ...optional fields}
  ]
}
```

| Action | Extra Fields | Effect |
|--------|-------------|--------|
| `move_up` | — | y − 1 |
| `move_down` | — | y + 1 |
| `move_left` | — | x − 1 |
| `move_right` | — | x + 1 |
| `pick_up` | `item_id: string` | Pick up item from adjacent shelf |
| `drop_off` | — | Deliver matching inventory at drop-off cell |
| `wait` | — | Do nothing |

### Pickup Rules [GLOBAL]

- Bot must be **adjacent** (Manhattan distance 1) to the shelf containing the item
- Bot inventory must not be full (max 3)
- `item_id` must match an existing item on the map

### Dropoff Rules [GLOBAL]

- Bot must be standing **on** the drop-off cell
- Only items matching the **active order** are consumed
- Non-matching items **stay in inventory**
- Each delivered item: **+1 point**
- Completed order: **+5 bonus points**
- On completion, next order activates and remaining inventory is rechecked

### Scoring Formula [GLOBAL]

```
score = (items_delivered × 1) + (orders_completed × 5)
```

### Leaderboard [GLOBAL]

- Best score per map saved automatically
- Leaderboard score = sum of best scores across all 4 maps
- Deterministic within a day

### Termination Conditions [GLOBAL]

| Condition | Trigger |
|-----------|---------|
| Round limit | 300 rounds used |
| Wall-clock timeout | 120 seconds elapsed |
| Disconnect | Client WebSocket closes |

### Error Handling [GLOBAL]

**There are no error messages.** The server never sends error payloads.

| Scenario | Result |
|----------|--------|
| Move into wall / shelf / out-of-bounds | Treated as `wait` |
| Move into occupied cell | Treated as `wait` (blocked) |
| `pick_up` invalid/non-adjacent/full inventory | Treated as `wait` |
| `drop_off` not on drop-off cell | Treated as `wait` |
| `drop_off` empty inventory | Treated as `wait` |
| `drop_off` no matching items | Non-matching items stay in inventory |
| Malformed JSON | All bots `wait` |
| Response timeout (>2s) | All bots `wait` |
| Missing bot in actions array | That bot `wait`s |

---

## EASY

### Level Parameters [EASY]

| Parameter | Value |
|-----------|-------|
| Grid size | 12 × 10 |
| Bot count | 1 |
| Aisles | 2 |
| Item types | 4 |
| Items per order | 3–4 |
| Description | Solo pathfinding |

### Session Selection [EASY]

Select the **Easy** map on [dev.ainm.no/challenge](https://dev.ainm.no/challenge) and click Play. The returned JWT token encodes this difficulty. WebSocket endpoint is the same as GLOBAL.

### Mechanics Notes [EASY]

- Single bot — no collision concerns, no coordination needed
- Smallest grid, fewest item types — pathfinding is the primary challenge
- Action array always has exactly 1 element

### Inbound Messages [EASY]

Schema: identical to **GLOBAL**. `bots` array always has 1 element.

### Outbound Example [EASY]

See `examples/easy/` — action array always contains exactly 1 action.

### Scoring / Termination / Timeouts [EASY]

Identical to **GLOBAL**. No level-specific overrides.

### Level-Specific Rules Beyond GLOBAL [EASY]

**[UNKNOWN]** — the MCP server does not document any Easy-specific rules beyond the parameters above.

---

## MEDIUM

### Level Parameters [MEDIUM]

| Parameter | Value |
|-----------|-------|
| Grid size | 16 × 12 |
| Bot count | 3 |
| Aisles | 3 |
| Item types | 8 |
| Items per order | 3–5 |
| Description | Team coordination |

### Session Selection [MEDIUM]

Select the **Medium** map on [dev.ainm.no/challenge](https://dev.ainm.no/challenge) and click Play. The returned JWT token encodes this difficulty. WebSocket endpoint is the same as GLOBAL.

### Mechanics Notes [MEDIUM]

- 3 bots — collision avoidance and task assignment become relevant
- Larger item variety — more items on shelves, more routing decisions
- Action array always has exactly 3 elements

### Inbound Messages [MEDIUM]

Schema: identical to **GLOBAL**. `bots` array always has 3 elements.

### Outbound Example [MEDIUM]

See `examples/medium/` — action array always contains exactly 3 actions.

### Scoring / Termination / Timeouts [MEDIUM]

Identical to **GLOBAL**. No level-specific overrides.

### Level-Specific Rules Beyond GLOBAL [MEDIUM]

**[UNKNOWN]** — the MCP server does not document any Medium-specific rules beyond the parameters above.

---

## HARD

### Level Parameters [HARD]

| Parameter | Value |
|-----------|-------|
| Grid size | 22 × 14 |
| Bot count | 5 |
| Aisles | 4 |
| Item types | 12 |
| Items per order | 3–5 |
| Description | Multi-agent planning |

### Session Selection [HARD]

Select the **Hard** map on [dev.ainm.no/challenge](https://dev.ainm.no/challenge) and click Play. The returned JWT token encodes this difficulty. WebSocket endpoint is the same as GLOBAL.

### Mechanics Notes [HARD]

- 5 bots — significant collision risk in narrow aisles
- 12 item types across 4 aisles — route optimization matters
- Action array always has exactly 5 elements

### Inbound Messages [HARD]

Schema: identical to **GLOBAL**. `bots` array always has 5 elements.

### Outbound Example [HARD]

See `examples/hard/` — action array always contains exactly 5 actions.

### Scoring / Termination / Timeouts [HARD]

Identical to **GLOBAL**. No level-specific overrides.

### Level-Specific Rules Beyond GLOBAL [HARD]

**[UNKNOWN]** — the MCP server does not document any Hard-specific rules beyond the parameters above.

---

## EXPERT

### Level Parameters [EXPERT]

| Parameter | Value |
|-----------|-------|
| Grid size | 28 × 18 |
| Bot count | 10 |
| Aisles | 5 |
| Item types | 16 |
| Items per order | 4–6 |
| Description | Massive coordination |

### Session Selection [EXPERT]

Select the **Expert** map on [dev.ainm.no/challenge](https://dev.ainm.no/challenge) and click Play. The returned JWT token encodes this difficulty. WebSocket endpoint is the same as GLOBAL.

### Mechanics Notes [EXPERT]

- 10 bots — highest collision density, most complex coordination
- Largest grid, most item types, largest orders
- Action array always has exactly 10 elements
- Only level with 4–6 items per order (others are 3–4 or 3–5)

### Inbound Messages [EXPERT]

Schema: identical to **GLOBAL**. `bots` array always has 10 elements.

### Outbound Example [EXPERT]

See `examples/expert/` — action array always contains exactly 10 actions.

### Scoring / Termination / Timeouts [EXPERT]

Identical to **GLOBAL**. No level-specific overrides.

### Level-Specific Rules Beyond GLOBAL [EXPERT]

**[UNKNOWN]** — the MCP server does not document any Expert-specific rules beyond the parameters above.
