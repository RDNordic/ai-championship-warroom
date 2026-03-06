Prompt 1: BFS Distance Matrix for Assignments (Hard + Expert)

CONTEXT: You are modifying a grocery bot for a multi-agent pickup-and-delivery game.
The bot file is a single self-contained Python file (run_hard.py or run_expert.py).
The bot currently uses Manhattan distance (_manhattan) to assign bots to items in
_build_greedy_assignments. This is wrong because Manhattan distance ignores walls
and aisle geometry — a bot assigned with Manhattan=5 might actually need BFS=12
steps due to walls.

TASK: Replace Manhattan distance with actual BFS shortest-path distance for item
assignment decisions. Do NOT change pathfinding for movement — only change how
assignments are scored in _build_greedy_assignments.

IMPLEMENTATION:
1. In __init__, add: self._bfs_cache: dict[tuple[int,int], dict[tuple[int,int], int]] = {}
2. Add a new method _bfs_distances(self, start, state) that runs a standard BFS
   from 'start' on the grid, returning a dict mapping every reachable (x,y) to its
   shortest distance. Cache results in self._bfs_cache keyed by start position.
   The grid is defined by state["grid"]["width"], state["grid"]["height"],
   state["grid"]["walls"] (list of [x,y] pairs). A cell is passable if it is
   within bounds, not a wall, and not a shelf (self.shelves). BUT: shelf cells
   ARE valid destinations (items live on shelves) — they are just not passable
   for transit. So BFS should not expand THROUGH shelf cells, but should record
   distance TO shelf cells if they are direct neighbors of a passable cell.
   
   Actually, simpler: bots move on walkable cells (not walls, not shelves). Items
   are ON shelf cells. Bots pick up items by standing ADJACENT to the shelf cell.
   So BFS should run on walkable cells only. When computing distance from bot to
   item, compute BFS distance from bot position to each walkable cell adjacent to
   the item's shelf position, and take the minimum.

3. In _build_greedy_assignments, replace:
     dist = self._manhattan(tuple(bot["position"]), tuple(item["position"]))
   with:
     dist = self._bfs_dist_to_item(tuple(bot["position"]), tuple(item["position"]), state)
   where _bfs_dist_to_item computes the min BFS distance from bot pos to any
   walkable neighbor of the item position. If unreachable, use 9999.

4. Precompute/cache BFS maps lazily — only compute a BFS from a position the
   first time it's needed. The grid doesn't change between rounds so caches are
   valid for the whole game.

CONSTRAINTS:
- Do NOT change _decide_one, _move_toward, or any pathfinding used for actual movement.
- Do NOT change the BFS/pathfinding used to generate move actions.
- Only change how assignment DISTANCES are computed in _build_greedy_assignments.
- Keep _manhattan for any other uses (drop-off distance comparisons, etc).
- The 2-second response deadline must be respected. BFS on a 22×14 or 28×18 grid
  is fast (<1ms per source), and caching means each source is computed at most once.

VALIDATION: Run the bot. Score should improve because assignments now reflect
actual travel cost. If score drops, revert — the change may need tuning on
which distance metric to use for the delivery-bot bias term.
Prompt 2: Spatial Partitioning for Expert (Expert only)

CONTEXT: You are modifying run_expert.py for a grocery bot game. Expert mode has
10 bots on a 28×18 grid with 5 aisles. The current bot treats all bots as a single
pool competing for all items globally. This causes massive cross-traffic — bots on
the left side get assigned items on the right side and vice versa, creating aisle
congestion and wasted movement.

Current score: 71. Benchmark: 219. The biggest Expert bottleneck is inter-bot
interference.

TASK: Add spatial zone assignment so bots primarily operate in their local area.

IMPLEMENTATION:
1. At game start (first call to decide), divide the grid into vertical zones
   based on the X-axis. With 5 aisles on a 28-wide grid, create 3 zones:
   - Zone 0: x in [0, 9]
   - Zone 1: x in [10, 18]  
   - Zone 2: x in [19, 27]
   Assign bots to zones based on their starting positions: sort bots by x-position,
   assign roughly 3-4 bots per zone. Store zone assignments in self.bot_zones: dict[int, int].
   Zone assignments are PERSISTENT — don't reassign every round.

2. In _build_greedy_assignments, add a zone preference bias: if a bot and item are
   in different zones, add a penalty to the distance score. Use penalty = 8 (roughly
   the cost of crossing a zone). This doesn't PREVENT cross-zone assignment — it just
   makes bots prefer local items.

3. The drop-off point is shared by all zones. Do NOT apply zone penalties to
   drop-off routing — that stays global.

4. When active order items are all in one zone and other zones' bots are idle,
   allow cross-zone assignment without penalty (the penalty only applies when
   there are local items available).

CONSTRAINTS:
- Zone boundaries should be computed once and cached.
- Do NOT change drop-off queuing, delivery allocation, or movement logic.
- The zone penalty is a BIAS, not a hard constraint. If no local items exist,
  bots should still pick up distant items.
- Keep the change minimal — only modify _build_greedy_assignments and add
  zone tracking state.

VALIDATION: Run the bot. Score should improve due to reduced cross-traffic.
If score drops, try adjusting penalty from 8 to 5 or 12 before reverting.
Prompt 3: Expert Drop-Off Queue Depth (Expert only)

CONTEXT: You are modifying run_expert.py. The bot has 10 bots but the drop-off
queue logic only allows 1 bot to approach the drop-off at a time (ranked[:1] in
_select_dropoff_queue_leader). This creates a massive bottleneck — with 10 bots,
several may have items ready to deliver but only 1 is allowed to approach while
the rest wait or wander.

TASK: Increase drop-off queue depth and implement staggered approach.

IMPLEMENTATION:
1. In _select_dropoff_queue_leader, change ranked[:1] to ranked[:3]. This allows
   3 bots to be in the "delivery approach" state simultaneously.

2. Add drop-off staging: the queue leader (rank 0) goes directly to drop_off.
   Rank 1 targets a walkable cell adjacent to drop_off. Rank 2 targets a cell
   2 steps away from drop_off. This prevents all 3 from trying to occupy the
   same cell.

3. In _decide_one, when a bot is in dropoff_queue_ids but is NOT the
   dropoff_queue_leader: instead of routing directly to drop_off, route to
   a staging position near drop_off. When the leader finishes dropping off
   and leaves, the next bot advances.

4. Implement this by adding a method _dropoff_staging_goal(self, bot_id, rank,
   drop_off, state, occupied_now) that returns the appropriate target position
   based on the bot's rank in the queue.

CONSTRAINTS:
- Do NOT change how delivery_alloc or useful_delivery is computed.
- The drop_off action itself still only happens when pos == drop_off.
- Keep the existing clear_dropoff_ids logic for bots that have nothing to deliver.
- Test with queue depth 3 first. If it causes gridlock near drop-off, reduce to 2.

VALIDATION: Run the bot. Score should improve from better delivery throughput.
If score drops due to drop-off congestion, reduce queue depth to 2 and retry.
Prompt 4: Scarcity-Weighted Item Assignment (Hard + Expert)

CONTEXT: You are modifying run_hard.py or run_expert.py. The current
_build_greedy_assignments sorts candidates purely by distance. This means common
items (many shelf positions, e.g. "milk" appears 6 times) get assigned before
rare items (e.g. "saffron" appears once). If a bot grabs a common item and blocks
the only bot near the rare item, the rare item takes many extra rounds to collect.

TASK: Add scarcity weighting so rare items get assigned first.

IMPLEMENTATION:
1. Before building the candidates list in _build_greedy_assignments, compute
   item_type_count: Counter that counts how many shelf positions exist per item
   type (from state["items"]).

2. Modify the candidate scoring. Currently: candidates.append((dist, bot_id, item_id)).
   Change to: candidates.append((dist + scarcity_bonus, bot_id, item_id)) where
   scarcity_bonus = max(0, item_type_count[item["type"]] - 2) * 2.
   
   This means: items with only 1-2 shelf positions get no penalty. Items with
   3+ positions get a distance penalty of (count - 2) * 2, making bots prefer
   rarer items when distances are similar.

3. Only count shelf positions for items that are actually needed (in needed_left).
   Don't count shelves for item types not in the current order.

CONSTRAINTS:
- Do NOT change the structure of _build_greedy_assignments beyond the scoring.
- Do NOT change how needed/needed_left is computed.
- The scarcity bonus is additive to distance, not multiplicative.
- Keep it simple — this is a tiebreaker, not a complete rewrite of assignment logic.

VALIDATION: Run the bot. Improvement should show as fewer rounds where a needed
rare item goes unpicked while bots chase common items. If score drops, reduce
the multiplier from 2 to 1, or remove the bonus entirely and revert.
Prompt 5: Pick-Fail Cooldown for Expert (Expert only)

CONTEXT: You are modifying run_expert.py. The hard bot (run_hard.py) has a
pick_fail_streak / pick_block_until_round mechanism that tracks when a pick_up
action fails (inventory size didn't increase) and temporarily blocks that item
from being targeted. The expert bot does NOT have this — when a pick fails
(e.g. another bot is blocking the shelf), the expert bot will retry the same
item indefinitely, wasting rounds.

TASK: Port the pick-fail tracking from run_hard.py to run_expert.py.

IMPLEMENTATION:
Copy these from run_hard.py into run_expert.py's TrialBot class:
1. In __init__, add:
   self.last_inventory_size: dict[int, int] = {}
   self.last_pick_item: dict[int, str] = {}
   self.pick_fail_streak: dict[str, int] = {}
   self.pick_block_until_round: dict[str, int] = {}

2. Copy the _update_pick_retry_state method exactly from run_hard.py.
3. Copy the _item_pick_blocked method exactly from run_hard.py.

4. In decide(), add round_number tracking (already exists in hard):
   round_number = int(state.get("round", -1))
   Call self._update_pick_retry_state(bots, round_number) after _update_wait_state.

5. In _build_greedy_assignments, add round_number as a parameter and add the check:
   if self._item_pick_blocked(item["id"], round_number): continue
   (This already exists in run_hard.py's version.)

6. In decide(), update last_action tracking to also track last_pick_item:
   After setting self.last_action[bot["id"]] = action["action"], add:
   if action["action"] == "pick_up":
       item_id = action.get("item_id")
       if isinstance(item_id, str) and item_id:
           self.last_pick_item[bot["id"]] = item_id
       else:
           self.last_pick_item.pop(bot["id"], None)
   else:
       self.last_pick_item.pop(bot["id"], None)

CONSTRAINTS:
- Copy the logic exactly from run_hard.py — it's already tested and working.
- Do NOT modify the cooldown timing parameters (they're tuned).
- Do NOT change any other expert bot logic.

VALIDATION: Run the bot. Score should improve from fewer wasted rounds on
blocked picks. This is very low-risk since it's a proven mechanism from hard.
Execution Order
I'd recommend running them in this order for maximum ROI:

Prompt 5 (pick-fail cooldown for Expert) — Lowest risk, copy-paste from working code
Prompt 1 (BFS distances) — Biggest single improvement for both Hard and Expert
Prompt 4 (scarcity weighting) — Small surgical change, easy to validate
Prompt 3 (drop-off queue depth for Expert) — Medium complexity
Prompt 2 (spatial partitioning for Expert) — Highest potential but most complex
Each prompt is designed to be one commit, one run, one decision (keep or revert) — matching your protocol.