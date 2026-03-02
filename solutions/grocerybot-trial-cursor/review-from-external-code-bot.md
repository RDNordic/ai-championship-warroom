Good, I have a full picture of the code. Here's my analysis.

---

## Analysis and Top Improvements

### Decision priority chain in `_decide_one`

1. Drop-off if on cell with useful inventory (with duplicate-drop guard)
2. Evacuate drop-off cell if blocking others
3. End-game wait if round > 285 and no useful inventory
4. Stage near drop-off if full inventory of non-useful (preview) items
5. Continue filling preview inventory if partially loaded
6. Pick up adjacent needed item
7. Detour-pick if en route to drop-off with a free slot
8. Queue for drop-off (leader moves, others stage adjacent)
9. Fetch assigned target item
10. Stage toward aisle centre if nothing to do

---

### Improvement 1: End-game cutoff is too aggressive (high impact)

**Problem:** Round > 285 causes any bot without useful inventory to immediately wait. With a 300-round game, a bot could still complete a ~10-step round trip (pick up + deliver = ~14 rounds at minimum). The cutoff should be based on whether there is enough time left to reach the nearest needed item, pick it up, and reach drop-off — not a hardcoded 285.

**Old code (line 553):**
```python
        if round_number > 285 and not useful_inventory:
            self.bot_targets.pop(bot_id, None)
            return {"bot": bot_id, "action": "wait"}
```

**New code:**
```python
        # Dynamic end-game cutoff: only idle if there is no time to complete a useful trip.
        if not useful_inventory:
            rounds_left = state["max_rounds"] - round_number
            nearest_needed_dist = self._nearest_needed_item_dist(pos, state, needed)
            if nearest_needed_dist is None or rounds_left < nearest_needed_dist + self._manhattan(pos, drop_off) + 2:
                self.bot_targets.pop(bot_id, None)
                return {"bot": bot_id, "action": "wait"}
```

Add this helper to `TrialBot`:
```python
    def _nearest_needed_item_dist(
        self,
        pos: tuple[int, int],
        state: dict,
        needed: Counter,
    ) -> Optional[int]:
        best = None
        for item in state["items"]:
            if needed[item["type"]] <= 0:
                continue
            # +1 because bot needs to be adjacent, not on the shelf
            d = self._manhattan(pos, tuple(item["position"])) + 1
            if best is None or d < best:
                best = d
        return best
```

---

### Improvement 2: Drop-off congestion — only one bot queues adjacent, others keep fetching (high impact)

**Problem:** When multiple bots have useful inventory, the code sends almost all of them to stage near the drop-off cell. With 5-10 bots this creates a traffic jam: bots block each other's paths, BFS finds no route, and they all wait. Only the leader and one runner-up should stage near the drop-off; the rest should continue fetching if they have a free inventory slot or simply hold position in the aisle.

**Old code (lines 644–677):**
```python
            if bot_id in dropoff_queue_ids and bot_id != dropoff_queue_leader:
                staged = self._stage_near_dropoff(...)
                if staged is not None:
                    return staged
            if dropoff_queue_ids and bot_id not in dropoff_queue_ids:
                staged = self._stage_near_dropoff(...)
                if staged is not None:
                    return staged
```

**New code:**
```python
            if bot_id in dropoff_queue_ids and bot_id != dropoff_queue_leader:
                # Second in queue: stage adjacent so it can step in immediately.
                staged = self._stage_near_dropoff(
                    bot_id=bot_id,
                    pos=pos,
                    drop_off=drop_off,
                    state=state,
                    occupied_now=occupied_now,
                    reserved_next=reserved_next,
                )
                if staged is not None:
                    return staged
            # Bots outside the top-2 queue: do NOT clog the drop-off area.
            # They should keep fetching or hold in the aisle.
            if dropoff_queue_ids and bot_id not in dropoff_queue_ids:
                # Try a detour-pick first; if not possible, move toward drop-off directly
                # without trying to stage adjacent (avoids congestion).
                pass  # fall through to move_toward below
```

This alone removes the pile-up. The fall-through to `move_toward({drop_off})` still works, but bots behind in the queue are not fighting for the same two adjacent cells.

---

### Improvement 3: Greedy assignment uses Manhattan to shelf, not to the adjacent pickup cell (medium impact)

**Problem:** `_build_greedy_assignments` computes distance as `manhattan(bot_pos, item_pos)`. But items sit on shelves; bots must stand adjacent to pick up. On a grid where shelves are embedded in walls, the walkable neighbour can be several cells away from `item_pos`. This means a bot that appears "close" may actually be blocked by a wall and need a long detour. The fix is to penalise distance to the nearest walkable neighbour of the shelf rather than the shelf itself.

**Old code (line 477):**
```python
                dist = self._manhattan(tuple(bot["position"]), tuple(item["position"]))
```

**New code:**
```python
                shelf_pos = tuple(item["position"])
                # Estimate distance to nearest accessible face of the shelf.
                bot_pos_local = tuple(bot["position"])
                adj_cells = [
                    n for n in self._neighbors(shelf_pos)
                    if n not in self._walls and n not in self.shelves
                ]
                if adj_cells:
                    dist = min(self._manhattan(bot_pos_local, adj) for adj in adj_cells)
                else:
                    dist = self._manhattan(bot_pos_local, shelf_pos) + 99  # inaccessible
```

---

### Improvement 4: Catastrophic failure prevention — stale `bot_targets` lock (medium-high impact, explains the 2-3 outliers)

**Problem:** `bot_targets` persists across rounds. If an item is picked up by another bot or disappears (delivered), the locking bot's target becomes stale. `_locked_or_best_item` does clear a stale lock when `items_by_id.get(locked_item_id)` returns `None` — but only if `needed[locked_item["type"]] > 0`. If the item type is no longer needed (e.g. another bot delivered it), the lock is **also** cleared. However, the bot then calls `_select_target_item`, which searches against `reserved_items | locked_by_others`. If many bots hold stale locks on vanished items (those item IDs remain in `bot_targets` for other bots), they pollute `locked_by_others` and can block a valid item from being selected by any bot. The fix is to prune stale targets at the start of `decide`.

Add at the top of `decide`, after building `items_by_id`:

**Old code (line 234):**
```python
        items_by_id = {item["id"]: item for item in state["items"]}
```

**New code:**
```python
        items_by_id = {item["id"]: item for item in state["items"]}
        # Prune stale bot_targets where the item no longer exists on the floor.
        for stale_bot_id in [bid for bid, iid in self.bot_targets.items() if iid not in items_by_id]:
            self.bot_targets.pop(stale_bot_id, None)
```

---

### Improvement 5: Preview staging should only trigger when the active order is nearly complete (medium impact)

**Problem:** The preview pre-staging logic activates whenever `sum(needed.values()) == 0` (line 250), meaning all active items are either delivered or being carried. But the check at line 579 (`has_non_useful_inventory and len(inventory) < 3`) also allows bots already carrying a mix of active + preview items to chase preview targets before delivering. This can cause bots to wander away from the drop-off when they should be delivering.

The preview duty cap (`preview_duty_cap = min(max(0, len(bots) - 1), 3)`) is already conservative, but the condition for entering preview duty when a bot has non-useful inventory should require that the active order will complete on its own (i.e. enough active items are already in transit/inventory).

**Old code (line 579):**
```python
        if has_non_useful_inventory and len(inventory) < 3:
            # Continue building preview inventory instead of idling.
            preview_duty_allowed = (bot_id in preview_duty_bots) or (
                len(preview_duty_bots) < preview_duty_cap
            )
```

**New code:**
```python
        if has_non_useful_inventory and len(inventory) < 3:
            # Only chase preview items if the active order can complete without this bot.
            active_in_transit = sum(delivery_alloc.get(b["id"], Counter()).values()
                                    for b in state["bots"])
            active_still_needed_raw = sum(self._required_minus_delivered(
                self._get_order_by_status(state, "active")
            ).values())
            active_order_covered = active_in_transit >= active_still_needed_raw
            preview_duty_allowed = active_order_covered and (
                (bot_id in preview_duty_bots) or (len(preview_duty_bots) < preview_duty_cap)
            )
```

Pass `state` into `_decide_one` (it already is) and `delivery_alloc` (already available as `useful_delivery` in context — but you need the full dict). Since `delivery_alloc` is not currently passed, the cleanest way is to compute the sum differently:

```python
            # Sum of useful deliveries already committed across all bots
            active_in_transit = sum(
                self._delivery_count(delivery_alloc.get(b["id"], Counter()))
                for b in state["bots"]
            )
```

This requires passing `delivery_alloc` into `_decide_one`. Add it as a parameter:

**In `_decide_one` signature** (line 500), add:
```python
        delivery_alloc: dict[int, Counter],
```

**In the `decide` loop** (line 270), add to the call:
```python
                delivery_alloc=delivery_alloc,
```

---

### Summary by expected impact

| # | Improvement | Addresses |
|---|---|---|
| 1 | Dynamic end-game cutoff | Easy variance, ~3-8 extra deliveries per run |
| 4 | Prune stale `bot_targets` | Catastrophic 2-3 score outliers on Hard/Expert |
| 2 | Limit drop-off staging to top-2 bots | Hard/Expert congestion bottleneck |
| 3 | Distance to shelf face, not centre | Assignment accuracy, Medium+ |
| 5 | Gate preview duty on active order coverage | Prevents premature preview defection |

Apply in the order listed — 4 is a one-liner with no risk, 1 and 2 are independent and safe, 3 is a local change to one method, 5 adds one parameter to `_decide_one`.