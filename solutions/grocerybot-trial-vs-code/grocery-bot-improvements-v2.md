# Grocery Bot Code Review: Top 5 Improvements (v2)

## Summary

The bot has solid architecture: BFS pathfinding, greedy assignment, delivery allocation, drop-off queueing, and preview pre-staging. The main weaknesses are (a) drop-off congestion at scale, (b) static end-game cutoff causing wasted rounds, (c) catastrophic deadlock scenarios, (d) suboptimal delivery allocation ignoring bot proximity, and (e) conservative preview duty gating.

Changes below are ordered for incremental application and testing. Each is self-contained.

---

## Improvement 1: Dynamic End-Game Cutoff

**Impact:** High. Fixes wasted rounds and reduces score variance.

**Problem:** The bot uses a hard cutoff at round 270. Bots with no useful inventory just wait for the last 30 rounds. But a bot 5 steps from an item and 8 steps from drop-off could finish a trip in 15 rounds. Conversely, on large Expert maps, round 270 may already be too late for a bot 25 steps away. There is also no "can I make it?" check for delivery trips.

**Find this block in `_decide_one` (the early-exit for idle bots near end of game):**

```python
        if round_number > 270 and not useful_inventory:
            self.bot_targets.pop(bot_id, None)
            return {"bot": bot_id, "action": "wait"}
```

**Replace with:**

```python
        # Dynamic end-game: don't start trips that can't finish
        if not useful_inventory:
            rounds_left = state.get("max_rounds", 300) - round_number
            nearest_dist = self._nearest_needed_item_dist(pos, state, needed, reserved_items)
            trip_cost = nearest_dist + self._manhattan(pos, drop_off) + 2 if nearest_dist < 10**9 else 10**9
            if rounds_left < trip_cost:
                self.bot_targets.pop(bot_id, None)
                return {"bot": bot_id, "action": "wait"}
```

**Add this helper method to the TrialBot class (place it near `_select_target_item`):**

```python
    def _nearest_needed_item_dist(
        self,
        pos: tuple[int, int],
        state: dict,
        needed: Counter,
        reserved_items: set[str],
    ) -> int:
        best = 10**9
        for item in state["items"]:
            if item["id"] in reserved_items:
                continue
            if needed[item["type"]] <= 0:
                continue
            dist = self._manhattan(pos, tuple(item["position"]))
            if dist < best:
                best = dist
        return best
```

**Expected impact:** Recovers 5-15 points on maps where bots idle needlessly in late rounds. Also prevents bots from starting hopeless trips.

---

## Improvement 2: Proximity-Aware Delivery Allocation

**Impact:** High. Main win on Hard/Expert.

**Problem:** `_allocate_delivery_slots` iterates bots by ID order, giving bot 0 priority regardless of position. On Expert with 10 bots, a far-away bot can claim delivery slots while the bot standing next to drop-off gets nothing and goes idle.

**Find the `_allocate_delivery_slots` method:**

```python
    def _allocate_delivery_slots(
        self, bots: list[dict], remaining_needed: Counter
    ) -> tuple[dict[int, Counter], Counter]:
        left = Counter(remaining_needed)
        alloc: dict[int, Counter] = {}
        for bot in bots:
            bot_id = bot["id"]
            reserved = Counter()
            for item_type in bot["inventory"]:
                if left[item_type] > 0:
                    reserved[item_type] += 1
                    left[item_type] -= 1
            alloc[bot_id] = reserved
        return alloc, left
```

**Replace with:**

```python
    def _allocate_delivery_slots(
        self, bots: list[dict], remaining_needed: Counter, drop_off: tuple[int, int] = None
    ) -> tuple[dict[int, Counter], Counter]:
        def priority(b: dict) -> tuple[int, int, int]:
            relevance = sum(1 for t in b["inventory"] if remaining_needed[t] > 0)
            dist = self._manhattan(tuple(b["position"]), drop_off) if drop_off else 0
            return (-relevance, dist, b["id"])

        left = Counter(remaining_needed)
        alloc: dict[int, Counter] = {}
        for bot in sorted(bots, key=priority):
            bot_id = bot["id"]
            reserved = Counter()
            for item_type in bot["inventory"]:
                if left[item_type] > 0:
                    reserved[item_type] += 1
                    left[item_type] -= 1
            alloc[bot_id] = reserved
        return alloc, left
```

**Also update the call site in `decide` where `_allocate_delivery_slots` is called:**

```python
# Old:
delivery_alloc, _ = self._allocate_delivery_slots(bots, active_needed_raw)
# New:
delivery_alloc, _ = self._allocate_delivery_slots(bots, active_needed_raw, tuple(state["drop_off"]))
```

**Expected impact:** Ensures closest bots with the most useful cargo get delivery priority. Should reduce wasted movement by 10-20% on multi-bot difficulties.

---

## Improvement 3: Scale Drop-Off Queue Depth

**Impact:** Medium-high. Targeted at Expert congestion.

This is a single, isolated change. The wider staging radius (discussed in v1) is deliberately separated out; apply it later if this alone does not resolve congestion.

**Problem:** `_select_dropoff_queue_leader` only allows 2 bots into the delivery pipeline regardless of bot count. With 10 bots on Expert, this bottleneck stalls throughput.

**Find this line at the end of `_select_dropoff_queue_leader` (the `ranked[:2]` slice):**

```python
        return {b["id"] for b in ranked[:2]}
```

**Replace with:**

```python
        # Scale queue depth: 2 for 1-3 bots, 3 for 4-6, 4 for 7+
        queue_depth = 2 if len(bots) <= 3 else (3 if len(bots) <= 6 else 4)
        return {b["id"] for b in ranked[:queue_depth]}
```

**Expected impact:** Lets more bots deliver concurrently on Hard/Expert. Easy/Medium behaviour unchanged (queue depth stays at 2).

---

## Improvement 4: Reduce Deadlock and Catastrophic Failures

**Impact:** Medium. Targets the 2-3 score outlier runs.

Two changes, both small and safe.

### 4a. Lower the wait-streak threshold

A bot must wait 3 consecutive rounds before nudging. In a 300-round game, losing 3 rounds per deadlock episode accumulates quickly.

**Find this line in `_wait_or_nudge`:**

```python
        if self.wait_streak.get(bot_id, 0) >= 3:
```

**Replace with:**

```python
        if self.wait_streak.get(bot_id, 0) >= 2:
```

### 4b. Add a random-nudge fallback when BFS fails

When `_bfs_first_step` returns None and the bot has no path, it currently just waits. In congested maps this can persist for many rounds.

**Find this block in `_move_toward` (the `step is None` fallback after relaxation):**

```python
        if step is None:
            return {"bot": bot_id, "action": "wait"}
```

**Replace with:**

```python
        if step is None:
            # Last-resort: try any unblocked neighbour to break gridlock
            nudge = self._random_nudge(bot_id, start, state, occupied_now, reserved_next)
            if nudge is not None:
                return nudge
            return {"bot": bot_id, "action": "wait"}
```

### 4c. Remove fixed random seed (optional, apply after stability improves)

`random.seed(42)` at module level means `_random_nudge` always picks the same direction. If that direction is blocked by map geometry, the bot deadlocks permanently. Removing the seed fixes this but makes runs non-deterministic.

**Recommendation:** Keep the seed for now while testing improvements 1-4b. Remove it once you have a stable baseline and want to reduce outlier variance. When you do remove it, consider logging a per-run seed for reproducibility:

```python
# Replace: random.seed(42)
# With:
import time as _time
_run_seed = int(_time.time() * 1000) % (2**32)
random.seed(_run_seed)
print(f"Random seed: {_run_seed}", flush=True)
```

---

## Improvement 5: Earlier Preview Duty for Surplus Bots

**Impact:** Medium. Increases throughput on multi-bot difficulties.

**Problem:** The current logic only switches to preview items when `sum(needed.values()) == 0`, meaning all active-order items must already be carried or delivered. On Expert with 10 bots and a 4-item order, 6+ bots sit idle while 4 handle the active order.

**Constraint:** The `assignments` dict is computed after this block in the current flow, so we cannot reference it here. Instead, count bots that already have useful deliveries allocated (which IS available at this point).

**Find this block in `decide` (the preview fallback logic):**

```python
        # Pre-pick preview items once active needs are already in-flight/carried.
        if sum(needed.values()) == 0:
            if sum(preview_needed.values()) > 0:
                needed = preview_needed
```

**Replace with:**

```python
        # Let surplus bots pursue preview items even while active order is in progress.
        # delivery_alloc is already computed above, so we can count active-duty bots safely.
        active_delivery_bots = sum(
            1 for b in bots
            if self._delivery_count(delivery_alloc.get(b["id"], Counter())) > 0
        )
        active_needs_zero = sum(needed.values()) == 0
        has_preview_work = sum(preview_needed.values()) > 0
        surplus_available = active_delivery_bots > 0 and active_delivery_bots < len(bots) // 2

        if has_preview_work and (active_needs_zero or surplus_available):
            # Merge: keep remaining active needs, overlay preview needs
            merged = Counter(needed)
            for item_type, count in preview_needed.items():
                merged[item_type] = max(merged[item_type], count)
            needed = merged
```

**Why this works:** `delivery_alloc` is computed on the line immediately above this block, so all referenced variables exist. The `len(bots) // 2` threshold means preview work only kicks in when fewer than half the bots are busy with deliveries, avoiding interference with the active order.

**Tuning note:** The `len(bots) // 2` threshold is conservative. On Expert (10 bots), it activates when 4 or fewer bots have delivery cargo. You may want to test `len(bots) // 3` for more aggressive preview collection.

**Expected impact:** On Expert, puts 4-6 extra bots to work per order cycle. Should improve throughput by 10-20%.

---

## Application Order and Testing

Apply and test each change individually in this order:

1. **Improvement 1** (dynamic cutoff) -- safest, no interaction with other changes
2. **Improvement 2** (delivery allocation) -- independent, test on Hard/Expert
3. **Improvement 4a+4b** (deadlock fixes) -- low risk, check outlier scores improve
4. **Improvement 3** (queue depth) -- test on Expert specifically
5. **Improvement 5** (preview duty) -- test on Expert, tune threshold if needed
6. **Improvement 4c** (remove seed) -- apply last, once baseline is stable

Run at least 5 iterations per difficulty after each change to separate signal from map variance.

---

## Implementation Prompt

Paste this into your coding tool after attaching `run_expert.py`:

```
You are editing run_expert.py for the Grocery Bot challenge.
Apply the following changes precisely. Do not restructure, rename, or
reorganise anything beyond what is specified.

CHANGE 1 -- Dynamic end-game cutoff
Find the block in _decide_one that checks `round_number > 270`.
Replace it with a trip-cost estimate using rounds_left and a new
helper method _nearest_needed_item_dist. [See Improvement 1 above.]

CHANGE 2 -- Proximity-aware delivery allocation
Replace _allocate_delivery_slots with a version that sorts bots by
(-relevance, distance_to_dropoff, bot_id). Add a drop_off parameter
and update the call site in decide(). [See Improvement 2 above.]

CHANGE 3 -- Scale drop-off queue depth
In _select_dropoff_queue_leader, replace the hardcoded [:2] slice
with a bot-count-scaled queue_depth. [See Improvement 3 above.]

CHANGE 4 -- Deadlock fixes
(a) In _wait_or_nudge, change the threshold from >= 3 to >= 2.
(b) In _move_toward, add a _random_nudge fallback when step is None.

CHANGE 5 -- Earlier preview duty
Replace the preview fallback block in decide() with logic that counts
active_delivery_bots from delivery_alloc and merges preview_needed
into needed when surplus bots are available. [See Improvement 5 above.]

After all changes, verify:
- python -c "import ast; ast.parse(open('run_expert.py').read())"
- All method signatures match their call sites
- No duplicate method names
```
