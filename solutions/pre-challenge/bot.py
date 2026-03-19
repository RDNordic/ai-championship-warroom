"""Main bot — wires together pathfinding, assignment, collision, and coordination modules.

Usage:
    from bot import GroceryBot, load_config
    config = load_config("expert")
    bot = GroceryBot(config)
    actions = bot.decide(game_state)
"""

from __future__ import annotations

import random
from collections import Counter
from pathlib import Path
from typing import Optional

import json

from core.types import Coord, Grid, action_from_step, manhattan, neighbors
from core.state_parser import (
    parse_grid,
    parse_bots,
    parse_items,
    parse_orders,
    required_minus_delivered,
    needed_counts_for_order,
    preview_needed_counts,
    occupied_positions,
)
from pathfinding.base import Pathfinder
from pathfinding.bfs import BFSPathfinder
from assignment.base import Assigner
from assignment.greedy import GreedyAssigner, RegretGreedyAssigner
from collision.reservation import ReservationResolver
from coordination.delivery import DeliveryCoordinator, delivery_count
from coordination.order_manager import OrderManager
from coordination.pick_cooldown import PickCooldownTracker


CONFIG_DIR = Path(__file__).parent / "config"


def load_config(difficulty: str = "expert") -> dict:
    """Load config by merging base.json with difficulty-specific json.

    The base config provides shared defaults (seed, BFS pathfinding, greedy
    assignment, etc.). The difficulty-specific file overrides only the keys
    it needs to change — e.g. expert.json switches assignment to
    'regret_greedy' and raises the stop_chasing_round to 290.

    Args:
        difficulty: One of 'easy', 'medium', 'hard', 'expert', 'nightmare'.

    Returns:
        Merged config dict ready to pass to GroceryBot().
    """
    base_path = CONFIG_DIR / "base.json"
    diff_path = CONFIG_DIR / f"{difficulty}.json"

    with open(base_path) as f:
        base = json.load(f)

    if diff_path.exists():
        with open(diff_path) as f:
            override = json.load(f)
        _deep_merge(base, override)

    return base


def _deep_merge(base: dict, override: dict) -> None:
    """Recursively merge override into base, mutating base in-place.

    Nested dicts are merged key-by-key. Scalar values and lists in
    override replace the corresponding value in base entirely.
    """
    for k, v in override.items():
        if k in base and isinstance(base[k], dict) and isinstance(v, dict):
            _deep_merge(base[k], v)
        else:
            base[k] = v


def _build_pathfinder(config: dict) -> Pathfinder:
    """Factory: instantiate the pathfinder specified in config.

    Currently supported: 'bfs'. Future: 'astar', 'whca'.
    """
    algo = config.get("pathfinding", {}).get("algorithm", "bfs")
    if algo == "bfs":
        return BFSPathfinder()
    raise ValueError(f"Unknown pathfinding algorithm: {algo}")


def _build_assigner(config: dict) -> Assigner:
    """Factory: instantiate the task assigner specified in config.

    Supported algorithms:
    - 'greedy': Sort all (distance, bot, item) candidates, claim greedily.
      Fast, used by Hard. Works well when BFS distances are accurate.
    - 'regret_greedy': Pick the bot with the highest "regret" (gap between
      its best and second-best option) first, so bots with fewer choices
      get priority. Used by Expert for better allocation quality.

    The delivery_penalty flag adds a distance surcharge for bots that are
    already carrying items to deliver, discouraging them from detouring
    far to pick more items.
    """
    ac = config.get("assignment", {})
    algo = ac.get("algorithm", "greedy")
    penalty = ac.get("delivery_penalty", True)
    if algo == "greedy":
        return GreedyAssigner(use_delivery_penalty=penalty)
    if algo == "regret_greedy":
        return RegretGreedyAssigner(use_delivery_penalty=penalty)
    raise ValueError(f"Unknown assignment algorithm: {algo}")


class GroceryBot:
    """
    Modular grocery bot. Delegates to:
    - pathfinder: distance computation and step planning
    - assigner: bot-to-item task allocation
    - collision: movement resolution with reservation
    - delivery: dropoff queue and slot management
    - order_mgr: order tracking and preview prefetching
    - cooldown: pick-fail cooldown tracking
    """

    def __init__(self, config: dict) -> None:
        """Initialize the bot with a config dict (from load_config).

        Instantiates all sub-modules (pathfinder, assigner, collision
        resolver, delivery coordinator, order manager, pick cooldown
        tracker) based on the algorithm choices in the config.

        Also initializes persistent cross-round state:
        - bot_targets: dict[bot_id -> item_id] — which item each bot is
          currently "locked on to" (persists across rounds until the bot
          picks it up, the item becomes blocked, or a better target appears).
        - last_drop_round: tracks when each bot last dropped off, to prevent
          issuing drop_off two rounds in a row (server ignores the second).
        - wait_streak: counts consecutive rounds a bot hasn't moved, used
          to trigger random nudges that break deadlocks.
        - _staging_candidates: cached list of walkable cells sorted by
          distance to the shelf centroid, used to park idle bots near aisles.
        """
        self.config = config
        random.seed(config.get("seed", 42))

        self.pathfinder = _build_pathfinder(config)
        self.assigner = _build_assigner(config)

        cc = config.get("collision", {})
        self.collision = ReservationResolver(
            wait_streak_nudge_threshold=cc.get("wait_streak_nudge_threshold", 3),
        )

        coord_cfg = config.get("coordination", {})
        self.delivery = DeliveryCoordinator(
            max_queue_leaders=coord_cfg.get("delivery_queue_leaders", 2),
        )
        self.order_mgr = OrderManager(
            preview_duty_cap_offset=coord_cfg.get("preview_duty_cap_offset", 1),
        )
        pc = coord_cfg.get("pick_cooldown", {})
        self.cooldown = PickCooldownTracker(
            max_cooldown=pc.get("max_cooldown", 18),
            base_cooldown=pc.get("base_cooldown", 4),
            step=pc.get("step", 2),
        )

        late = config.get("late_game", {})
        self._stop_chasing_round = late.get("stop_chasing_round", 280)
        self._detour_cutoff_round = late.get("detour_cutoff_round", 250)

        # Persistent state
        self._grid: Optional[Grid] = None
        self.bot_targets: dict[int, str] = {}
        self.last_drop_round: dict[int, int] = {}
        self.wait_streak: dict[int, int] = {}
        self.last_observed_pos: dict[int, tuple[int, int]] = {}
        self.last_action: dict[int, str] = {}

        # Staging cache
        self._staging_cache_key: Optional[tuple] = None
        self._staging_candidates: list[Coord] = []

    def decide(self, state: dict) -> list[dict]:
        """Main entry point — called once per round by the game runner.

        Orchestrates the full decision pipeline:

        1. PARSE: Convert raw game_state JSON into typed structures (grid,
           bots, items, orders). The grid is cached after round 0 since
           walls never change; only shelves are updated each round.

        2. UPDATE TRACKERS: Refresh pick-fail cooldowns (detect if last
           round's pick_up actually succeeded by comparing inventory sizes),
           update wait streaks, and rebuild staging candidates if needed.

        3. ANALYZE ORDERS: Determine what items are still needed for the
           active order (after subtracting delivered + carried items).
           Compute delivery slot allocations (which bot's inventory matches
           which needed items). If the active order is fully covered by
           inventory, switch to pre-picking preview order items.

        4. DROPOFF MANAGEMENT: Select queue leaders (closest deliverers),
           identify bots idling on the dropoff cell that should move aside.

        5. TASK ASSIGNMENT: Run the configured assigner (greedy or
           regret_greedy) to map bots to items. Bots clearing the dropoff
           or with full inventory are excluded. Items in pick-fail cooldown
           are excluded. Delivery bots get a distance penalty to discourage
           long detours.

        6. SURPLUS PREVIEW: If the active order is fully covered (all needed
           items are either carried or assigned), assign leftover bots to
           pick preview order items. This eliminates idle time between orders.

        7. PER-BOT DECISIONS: Process bots in priority order (deliverers
           first, then pickers, then idle). Each bot's chosen next cell is
           reserved so subsequent bots route around it. See _decide_one().

        Args:
            state: Raw game_state dict from the WebSocket server.

        Returns:
            List of action dicts, one per bot, in bot ID order.
            Example: [{"bot": 0, "action": "move_right"}, ...]
        """
        # Parse state
        self._grid = parse_grid(state, self._grid)
        grid = self._grid
        self.pathfinder.clear_cache()

        round_number = int(state.get("round", -1))
        bots = parse_bots(state)
        items_by_id = parse_items(state)
        active_order, preview_order = parse_orders(state)
        drop_off: Coord = tuple(state["drop_off"])
        occupied_now = occupied_positions(bots)
        reserved_next: set[Coord] = set()
        reserved_items: set[str] = set()

        # Update trackers
        self.cooldown.update(bots, round_number, self.bot_targets)
        self._update_wait_state(bots)
        self._refresh_staging_candidates(grid)

        # Order analysis
        active_needed_raw = required_minus_delivered(active_order)
        delivery_alloc, _ = self.delivery.allocate_delivery_slots(bots, active_needed_raw)
        needed = needed_counts_for_order(active_order, bots)
        preview_needed = preview_needed_counts(preview_order, active_order, bots)
        preview_ids = self.order_mgr.preview_item_ids(state["items"], preview_needed)
        preview_duty_bots = self.order_mgr.current_preview_duty_bots(
            preview_ids, bots, self.bot_targets
        )
        preview_duty_cap = self.order_mgr.preview_duty_cap(len(bots))

        # Pre-pick preview items when active is fully covered
        if sum(needed.values()) == 0 and sum(preview_needed.values()) > 0:
            needed = preview_needed

        # Dropoff management
        queue_ids = self.delivery.select_queue_leaders(bots, drop_off, delivery_alloc)
        queue_primary = self.delivery.select_queue_primary(queue_ids, bots, drop_off)
        clear_ids = self.delivery.dropoff_clearance_bots(bots, drop_off, delivery_alloc)

        # Task assignment
        parked_bots = {6, 7, 8, 9}
        excluded_bots = clear_ids | parked_bots
        blocked_items = {
            iid for iid in items_by_id
            if self.cooldown.is_blocked(iid, round_number)
        }

        # Distance function for assignment — round-trip: bot→item + item→dropoff
        def dist_fn(a: Coord, b: Coord) -> int:
            return self.pathfinder.distance(grid, a, b) + self.pathfinder.distance(grid, b, drop_off)
        delivering_bots = {
            b["id"] for b in bots
            if delivery_count(delivery_alloc.get(b["id"], Counter())) > 0
        }
        assignments = self.assigner.assign(
            bots=bots,
            items=state["items"],
            needed=needed,
            distance_fn=dist_fn,
            excluded_bots=excluded_bots,
            excluded_items=blocked_items,
            delivery_bots=delivering_bots,
            bot_locks=dict(self.bot_targets),
        )

        # Surplus preview assignment
        preview_priority_bots: set[int] = set()
        if sum(preview_needed.values()) > 0:
            coverage = Counter()
            for alloc in delivery_alloc.values():
                coverage.update(alloc)
            for item_id in assignments.values():
                item = items_by_id.get(item_id)
                if item is not None:
                    coverage[item["type"]] += 1
            active_fully_covered = all(
                coverage[t] >= c for t, c in active_needed_raw.items()
            )
            if active_fully_covered:
                surplus_bots = [
                    b for b in bots
                    if b["id"] not in assignments
                    and b["id"] not in clear_ids
                    and delivery_count(delivery_alloc.get(b["id"], Counter())) == 0
                    and len(b["inventory"]) < 3
                ]
                preview_assignments = self.assigner.assign(
                    bots=surplus_bots,
                    items=state["items"],
                    needed=preview_needed,
                    distance_fn=dist_fn,
                    excluded_bots=excluded_bots,
                    excluded_items=blocked_items,
                    delivery_bots=frozenset(),
                    bot_locks=dict(self.bot_targets),
                )
                assignments.update(preview_assignments)
                preview_priority_bots = set(preview_assignments.keys())
                preview_duty_bots.update(preview_priority_bots)

        # Process delivery bots first so they claim path cells via reserved_next,
        # then non-delivery bots route around them.
        delivery_bots_list = [b for b in bots if delivery_count(delivery_alloc.get(b["id"], Counter())) > 0]
        non_delivery_bots_list = [b for b in bots if delivery_count(delivery_alloc.get(b["id"], Counter())) == 0]
        ordered_bots = delivery_bots_list + non_delivery_bots_list
        action_map: dict[int, dict] = {}

        for bot in ordered_bots:
            action = self._decide_one(
                bot=bot,
                round_number=round_number,
                state=state,
                needed=needed,
                drop_off=drop_off,
                occupied_now=occupied_now,
                reserved_items=reserved_items,
                reserved_next=reserved_next,
                clear_ids=clear_ids,
                items_by_id=items_by_id,
                assigned_item_id=assignments.get(bot["id"]),
                useful_delivery=delivery_alloc.get(bot["id"], Counter()),
                preview_needed=preview_needed,
                preview_ids=preview_ids,
                preview_duty_bots=preview_duty_bots,
                preview_duty_cap=preview_duty_cap,
                queue_ids=queue_ids,
                queue_primary=queue_primary,
                preview_priority=bot["id"] in preview_priority_bots,
            )
            action_map[bot["id"]] = action
            self.last_action[bot["id"]] = action["action"]
            self.cooldown.record_action(bot["id"], action)

        return [action_map[b["id"]] for b in bots]

    def _decide_one(
        self,
        bot: dict,
        round_number: int,
        state: dict,
        needed: Counter,
        drop_off: Coord,
        occupied_now: set[Coord],
        reserved_items: set[str],
        reserved_next: set[Coord],
        clear_ids: set[int],
        items_by_id: dict[str, dict],
        assigned_item_id: Optional[str],
        useful_delivery: Counter,
        preview_needed: Counter,
        preview_ids: set[str],
        preview_duty_bots: set[int],
        preview_duty_cap: int,
        queue_ids: set[int],
        queue_primary: Optional[int],
        preview_priority: bool,
    ) -> dict:
        """Decide one action for a single bot. Called in priority order.

        The decision follows a strict priority cascade — the FIRST matching
        condition wins. This ordering is critical for correct behavior:

        1. DROP OFF: If the bot is on the dropoff cell and carries items that
           match the active order, issue 'drop_off'. (Skip if it dropped off
           last round to avoid a no-op double-drop.)

        2. CLEAR DROPOFF: If this bot is idling on the dropoff cell while
           other bots need to deliver, move to a neighboring cell.

        3. LATE GAME STOP: After round ~280-290 (configurable), bots without
           useful inventory stop chasing items — no time to complete a
           pick-deliver cycle before round 300.

        4. FULL PREVIEW BAG: Bot has 3 items but none match the active order
           (they're preview items). Move to a holding position 3-6 cells from
           dropoff to stay nearby without blocking the dropoff cell.

        5. PARTIAL PREVIEW: Bot carries some preview items and has room for
           more. If allowed by preview_duty_cap, pick adjacent preview items
           or move toward the nearest preview target.

        6. SURPLUS PREVIEW PICKER: This bot was assigned to preview duty
           by the surplus assignment step. Pick or move toward preview items.

        7. PICK ADJACENT: If any needed item (active order) is Manhattan
           distance 1 away, pick it up immediately. Never walk past a
           needed item.

        8. DELIVER: Bot carries items matching the active order.
           a. If early enough and inventory not full, check if a needed item
              is "on the way" to dropoff (small detour) and batch-pick it.
           b. If this bot is a queue runner-up, stage adjacent to dropoff.
           c. If this bot is outside the queue, hold in a nearby position.
           d. Otherwise, head straight to the dropoff cell.

        9. FULL INVENTORY, NOTHING USEFUL: Bot has 3 items, none match the
           active order, and it's not eligible for preview work. Wait/nudge.

        10. GO PICK: Default — find the best item target (prefer the
            assigned item from the assigner, then the locked target from
            last round, then the nearest unreserved needed item) and move
            toward it. If no target exists, stage toward the aisle center.

        Args:
            bot: Bot dict with 'id', 'position', 'inventory'.
            round_number: Current game round (0-indexed).
            state: Full game state (for item list access).
            needed: Counter of item types still needed (mutated as items are reserved).
            drop_off: (x, y) of the dropoff cell.
            occupied_now: Set of cells occupied by any bot this round.
            reserved_items: Set of item IDs already claimed by higher-priority bots.
            reserved_next: Set of cells reserved by higher-priority bots' next moves.
            clear_ids: Bot IDs that should evacuate the dropoff cell.
            items_by_id: Item dict indexed by item ID.
            assigned_item_id: Item ID assigned to this bot by the assigner (or None).
            useful_delivery: Counter of item types this bot carries that match active order.
            preview_needed: Counter of item types needed for preview order.
            preview_ids: Item IDs on the map matching preview needs.
            preview_duty_bots: Bot IDs currently committed to preview work.
            preview_duty_cap: Max bots allowed on preview duty.
            queue_ids: Bot IDs in the dropoff queue.
            queue_primary: The single bot ID that should head to dropoff first.
            preview_priority: Whether this bot was assigned surplus preview work.

        Returns:
            Action dict, e.g. {"bot": 0, "action": "move_right"}.
        """
        grid = self._grid
        bot_id = bot["id"]
        pos: Coord = tuple(bot["position"])
        inventory = bot["inventory"]
        useful_inv = delivery_count(useful_delivery) > 0
        has_non_useful_inv = bool(inventory) and not useful_inv

        # --- Parked bots: stay out of the way ---
        if bot_id in {6, 7, 8, 9}:
            return {"bot": bot_id, "action": "wait"}

        # --- Drop off at delivery point ---
        if useful_inv and pos == drop_off:
            if self.last_drop_round.get(bot_id) == round_number - 1:
                return self.collision.wait_or_nudge(
                    bot_id, pos, grid, occupied_now, reserved_next,
                    self.wait_streak.get(bot_id, 0),
                )
            self.bot_targets.pop(bot_id, None)
            self.last_drop_round[bot_id] = round_number
            return {"bot": bot_id, "action": "drop_off"}

        # --- Clear dropoff for deliverers ---
        if bot_id in clear_ids:
            evac_goals = set(neighbors(drop_off))
            return self.collision.move_toward(
                bot_id, pos, evac_goals, grid, self.pathfinder,
                occupied_now, reserved_next, allow_occupied_goals=False,
            )

        # --- Late game: stop chasing ---
        if round_number > self._stop_chasing_round and not useful_inv:
            self.bot_targets.pop(bot_id, None)
            return {"bot": bot_id, "action": "wait"}

        # --- Full preview bag: stage near dropoff ---
        if has_non_useful_inv and len(inventory) >= 3:
            self.bot_targets.pop(bot_id, None)
            staging = self._staging_action(bot_id, pos, drop_off, grid, occupied_now, reserved_next)
            if staging is not None:
                return staging
            return self.collision.wait_or_nudge(
                bot_id, pos, grid, occupied_now, reserved_next,
                self.wait_streak.get(bot_id, 0),
            )

        # --- Non-useful inventory, pick more preview ---
        if has_non_useful_inv and len(inventory) < 3:
            preview_duty_allowed = (
                bot_id in preview_duty_bots
                or len(preview_duty_bots) < preview_duty_cap
            )
            if preview_duty_allowed:
                pick = self.order_mgr.pick_if_adjacent(
                    bot, state["items"], preview_needed, reserved_items,
                    round_number, self.cooldown.is_blocked,
                )
                if pick is not None:
                    self.bot_targets.pop(bot_id, None)
                    preview_duty_bots.add(bot_id)
                    return pick
                target = self._locked_or_best_item(
                    bot_id, pos, state, preview_needed, reserved_items,
                    items_by_id, None, round_number,
                )
                if target is not None:
                    reserved_items.add(target["id"])
                    if preview_needed[target["type"]] > 0:
                        preview_needed[target["type"]] -= 1
                    if target["id"] in preview_ids:
                        preview_duty_bots.add(bot_id)
                    goals = grid.adjacent_walkable(
                        tuple(target["position"]),
                        blocked=(occupied_now - {pos}),
                    )
                    if goals:
                        return self.collision.move_toward(
                            bot_id, pos, goals, grid, self.pathfinder,
                            occupied_now, reserved_next,
                        )

        # --- Preview priority bots ---
        if preview_priority and not useful_inv:
            pick = self.order_mgr.pick_if_adjacent(
                bot, state["items"], preview_needed, reserved_items,
                round_number, self.cooldown.is_blocked,
            )
            if pick is not None:
                self.bot_targets.pop(bot_id, None)
                preview_duty_bots.add(bot_id)
                return pick
            target = self._locked_or_best_item(
                bot_id, pos, state, preview_needed, reserved_items,
                items_by_id, assigned_item_id, round_number,
            )
            if target is not None:
                reserved_items.add(target["id"])
                if preview_needed[target["type"]] > 0:
                    preview_needed[target["type"]] -= 1
                if target["id"] in preview_ids:
                    preview_duty_bots.add(bot_id)
                goals = grid.adjacent_walkable(
                    tuple(target["position"]),
                    blocked=(occupied_now - {pos}),
                )
                if goals:
                    return self.collision.move_toward(
                        bot_id, pos, goals, grid, self.pathfinder,
                        occupied_now, reserved_next,
                    )

        # --- Pick adjacent needed item ---
        pick = self.order_mgr.pick_if_adjacent(
            bot, state["items"], needed, reserved_items,
            round_number, self.cooldown.is_blocked,
        )
        if pick is not None:
            self.bot_targets.pop(bot_id, None)
            return pick

        # --- Deliver ---
        if useful_inv:
            # Detour to batch-pick on the way
            if round_number <= self._detour_cutoff_round and len(inventory) < 3:
                detour = self._delivery_detour(
                    bot_id, pos, state, needed, drop_off,
                    occupied_now, reserved_items, reserved_next,
                    items_by_id, assigned_item_id, round_number,
                )
                if detour is not None:
                    return detour

            # Queue pipeline
            if bot_id in queue_ids and bot_id != queue_primary:
                # If close, stage adjacent to dropoff for instant step-in
                # If far, head straight to dropoff (primary will be done by arrival)
                if manhattan(pos, drop_off) <= 5:
                    staged = self._stage_near_dropoff(
                        bot_id, pos, drop_off, grid, occupied_now, reserved_next,
                    )
                    if staged is not None:
                        return staged
                # Fall through to "Head to dropoff" below
            elif queue_ids and bot_id not in queue_ids:
                if manhattan(pos, drop_off) <= 5:
                    staged = self._staging_action(
                        bot_id, pos, drop_off, grid, occupied_now, reserved_next,
                    )
                    if staged is not None:
                        return staged
                    return self.collision.wait_or_nudge(
                        bot_id, pos, grid, occupied_now, reserved_next,
                        self.wait_streak.get(bot_id, 0),
                    )
                # Fall through to "Head to dropoff" below

            # Head to dropoff
            self.bot_targets.pop(bot_id, None)
            return self.collision.move_toward(
                bot_id, pos, {drop_off}, grid, self.pathfinder,
                occupied_now, reserved_next,
                allow_occupied_goals=True,
                relax_reservation_if_blocked=True,
            )

        # --- Full inventory, nothing useful ---
        if len(inventory) >= 3:
            self.bot_targets.pop(bot_id, None)
            return self.collision.wait_or_nudge(
                bot_id, pos, grid, occupied_now, reserved_next,
                self.wait_streak.get(bot_id, 0),
            )

        # --- Go pick an item ---
        target = self._locked_or_best_item(
            bot_id, pos, state, needed, reserved_items,
            items_by_id, assigned_item_id, round_number,
        )
        if target is None:
            self.bot_targets.pop(bot_id, None)
            staging = self._stage_toward_center(
                bot_id, pos, grid, occupied_now, reserved_next,
            )
            if staging is not None:
                return staging
            return self.collision.wait_or_nudge(
                bot_id, pos, grid, occupied_now, reserved_next,
                self.wait_streak.get(bot_id, 0),
            )

        reserved_items.add(target["id"])
        if needed[target["type"]] > 0:
            needed[target["type"]] -= 1

        goals = grid.adjacent_walkable(
            tuple(target["position"]),
            blocked=(occupied_now - {pos}),
        )
        if not goals:
            return self.collision.wait_or_nudge(
                bot_id, pos, grid, occupied_now, reserved_next,
                self.wait_streak.get(bot_id, 0),
            )

        return self.collision.move_toward(
            bot_id, pos, goals, grid, self.pathfinder,
            occupied_now, reserved_next,
        )

    # --- Item targeting (reused from existing codebase) ---

    def _locked_or_best_item(
        self,
        bot_id: int,
        pos: Coord,
        state: dict,
        needed: Counter,
        reserved_items: set[str],
        items_by_id: dict[str, dict],
        assigned_item_id: Optional[str],
        round_number: int,
    ) -> Optional[dict]:
        """Resolve which item this bot should target, using a 3-tier fallback.

        Priority order:
        1. The item assigned by the assigner this round (assigned_item_id).
           This is the "globally optimal" choice from the assignment algorithm.
        2. The item this bot was locked on to from a previous round
           (self.bot_targets[bot_id]). Preserving locks avoids flip-flopping
           where a bot changes target every round and never reaches any item.
        3. Fresh search: find the nearest unreserved, unblocked, needed item
           that no other bot is locked on to.

        Each tier validates that the item still exists, isn't reserved by
        another bot this round, isn't in pick-fail cooldown, and is still
        needed by the order.

        Returns the item dict if found, or None if no valid target exists.
        Side effect: updates self.bot_targets[bot_id] to the chosen item.
        """
        # Prefer assigned item
        if assigned_item_id:
            assigned = items_by_id.get(assigned_item_id)
            if (
                assigned
                and assigned_item_id not in reserved_items
                and not self.cooldown.is_blocked(assigned_item_id, round_number)
                and needed[assigned["type"]] > 0
            ):
                self.bot_targets[bot_id] = assigned_item_id
                return assigned

        # Prefer locked target
        locked_id = self.bot_targets.get(bot_id)
        if locked_id:
            locked = items_by_id.get(locked_id)
            if (
                locked
                and locked_id not in reserved_items
                and not self.cooldown.is_blocked(locked_id, round_number)
                and needed[locked["type"]] > 0
            ):
                return locked
            self.bot_targets.pop(bot_id, None)

        # Find new target
        locked_by_others = {
            iid for other_id, iid in self.bot_targets.items()
            if other_id != bot_id
        }

        def dist_fn(a, b):
            return self.pathfinder.distance(self._grid, a, b)

        chosen = self.order_mgr.select_target_item(
            pos, state["items"], needed,
            reserved_items | locked_by_others,
            dist_fn, round_number, self.cooldown.is_blocked,
        )
        if chosen is not None:
            self.bot_targets[bot_id] = chosen["id"]
        return chosen

    # --- Delivery detour ---

    def _delivery_detour(
        self,
        bot_id: int,
        pos: Coord,
        state: dict,
        needed: Counter,
        drop_off: Coord,
        occupied_now: set[Coord],
        reserved_items: set[str],
        reserved_next: set[Coord],
        items_by_id: dict[str, dict],
        assigned_item_id: Optional[str],
        round_number: int,
    ) -> Optional[dict]:
        """Attempt to batch-pick an item while en route to dropoff.

        When a bot is heading to deliver but still has inventory space,
        check if its assigned item is "on the way" (small detour from the
        direct path to dropoff). If so, pick it up to batch more items
        per delivery trip.

        The detour is allowed only if:
        - The bot has an assigned item that is still needed and not blocked.
        - The item is within 5 extra steps of the direct path to dropoff.
        - The item is at most 8 cells away (Manhattan).
        - The round is early enough (before detour_cutoff_round).

        Returns an action dict if a detour is taken, or None to continue
        the normal delivery path.
        """
        if not assigned_item_id:
            return None
        item = items_by_id.get(assigned_item_id)
        if item is None or assigned_item_id in reserved_items:
            return None
        if self.cooldown.is_blocked(assigned_item_id, round_number):
            return None
        if needed[item["type"]] <= 0:
            return None

        item_pos = tuple(item["position"])
        if not self.delivery.is_near_delivery_path(pos, drop_off, item_pos):
            return None

        if manhattan(pos, item_pos) == 1:
            reserved_items.add(assigned_item_id)
            needed[item["type"]] -= 1
            self.bot_targets.pop(bot_id, None)
            return {"bot": bot_id, "action": "pick_up", "item_id": assigned_item_id}

        goals = self._grid.adjacent_walkable(item_pos, blocked=(occupied_now - {pos}))
        if not goals:
            return None

        reserved_items.add(assigned_item_id)
        needed[item["type"]] -= 1
        self.bot_targets[bot_id] = assigned_item_id
        return self.collision.move_toward(
            bot_id, pos, goals, self._grid, self.pathfinder,
            occupied_now, reserved_next,
        )

    # --- Staging helpers ---

    def _stage_near_dropoff(
        self,
        bot_id: int,
        pos: Coord,
        drop_off: Coord,
        grid: Grid,
        occupied_now: set[Coord],
        reserved_next: set[Coord],
    ) -> Optional[dict]:
        """Move to a cell directly adjacent to the dropoff cell.

        Used by delivery queue runner-ups: they stage one cell away from
        dropoff so they can step in immediately once the primary deliverer
        finishes and moves out.

        Returns None if all adjacent cells are blocked.
        """
        goals = grid.adjacent_walkable(drop_off, blocked=(occupied_now - {pos}))
        if not goals:
            return None
        return self.collision.move_toward(
            bot_id, pos, goals, grid, self.pathfinder,
            occupied_now, reserved_next,
        )

    def _staging_action(
        self,
        bot_id: int,
        pos: Coord,
        drop_off: Coord,
        grid: Grid,
        occupied_now: set[Coord],
        reserved_next: set[Coord],
    ) -> Optional[dict]:
        """Move to a holding position 3-6 Manhattan cells from dropoff.

        Used by bots that are waiting for their turn in the delivery queue,
        or by bots carrying a full bag of preview items. The 3-6 range keeps
        them close enough to reach dropoff quickly but far enough to not
        block active delivery traffic.

        Candidates are scored by (distance_to_dropoff, distance_from_bot,
        hash_tiebreak) to spread bots across different holding positions.
        """
        blocked = (occupied_now - {pos}) | reserved_next
        candidates: list[tuple[tuple[int, int, int], Coord]] = []
        for x in range(grid.width):
            for y in range(grid.height):
                cell = (x, y)
                if cell == pos or not grid.walkable(cell) or cell in blocked:
                    continue
                dist_to_drop = manhattan(cell, drop_off)
                if not (3 <= dist_to_drop <= 6):
                    continue
                score = (
                    dist_to_drop,
                    manhattan(pos, cell),
                    (x * 31 + y * 17 + bot_id) % 7,
                )
                candidates.append((score, cell))

        if not candidates:
            return None
        candidates.sort(key=lambda t: t[0])
        return self.collision.move_toward(
            bot_id, pos, {candidates[0][1]}, grid, self.pathfinder,
            occupied_now, reserved_next,
        )

    def _stage_toward_center(
        self,
        bot_id: int,
        pos: Coord,
        grid: Grid,
        occupied_now: set[Coord],
        reserved_next: set[Coord],
    ) -> Optional[dict]:
        """Move an idle bot toward the center of the shelf area.

        When a bot has no item target (all needed items are claimed by
        other bots), it moves toward the centroid of all shelves. This
        keeps idle bots positioned centrally so they can quickly reach
        items when the next order activates.

        Each bot picks a different candidate cell based on its bot_id to
        avoid all idle bots converging on the same spot.
        """
        if not self._staging_candidates:
            return None
        blocked = (occupied_now - {pos}) | reserved_next
        n = len(self._staging_candidates)
        search_span = min(20, n)
        for i in range(search_span):
            idx = (bot_id + (i * 3)) % n
            cell = self._staging_candidates[idx]
            if cell == pos or cell in blocked:
                continue
            return self.collision.move_toward(
                bot_id, pos, {cell}, grid, self.pathfinder,
                occupied_now, reserved_next,
            )
        return None

    def _refresh_staging_candidates(self, grid: Grid) -> None:
        """Rebuild the sorted list of staging candidates if the grid changed.

        Staging candidates are all walkable cells, sorted by Manhattan
        distance to the centroid of all shelf positions. This list is
        cached and only rebuilt when walls or shelves change (which in
        practice means it's built once at round 0 and never again, since
        the grid structure is static).
        """
        key = (grid.width, grid.height,
               tuple(sorted(grid.walls)), tuple(sorted(grid.shelves)))
        if key == self._staging_cache_key:
            return
        self._staging_cache_key = key
        self._staging_candidates = []
        if not grid.shelves:
            return
        cx = sum(p[0] for p in grid.shelves) / len(grid.shelves)
        cy = sum(p[1] for p in grid.shelves) / len(grid.shelves)
        candidates: list[tuple[float, Coord]] = []
        for x in range(grid.width):
            for y in range(grid.height):
                cell = (x, y)
                if not grid.walkable(cell):
                    continue
                d = abs(cx - x) + abs(cy - y)
                candidates.append((d, cell))
        candidates.sort(key=lambda t: t[0])
        self._staging_candidates = [cell for _, cell in candidates]

    def _update_wait_state(self, bots: list[dict]) -> None:
        """Track consecutive rounds each bot has stayed in the same position.

        Used by the collision resolver's wait_or_nudge: if a bot has been
        stuck for N rounds (configurable via wait_streak_nudge_threshold),
        it makes a random valid move to break potential deadlocks where
        two bots are mutually blocking each other.
        """
        active_ids = {b["id"] for b in bots}
        for bot in bots:
            bot_id = bot["id"]
            pos = tuple(bot["position"])
            prev_pos = self.last_observed_pos.get(bot_id)
            prev_action = self.last_action.get(bot_id)
            if prev_action == "wait" and prev_pos == pos:
                self.wait_streak[bot_id] = self.wait_streak.get(bot_id, 0) + 1
            else:
                self.wait_streak[bot_id] = 0
            self.last_observed_pos[bot_id] = pos
        for bot_id in list(self.wait_streak.keys()):
            if bot_id not in active_ids:
                self.wait_streak.pop(bot_id, None)
                self.last_observed_pos.pop(bot_id, None)
                self.last_action.pop(bot_id, None)
