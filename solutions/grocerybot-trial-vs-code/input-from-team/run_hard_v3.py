
import asyncio
import base64
import json
import os
import random
import time
from collections import Counter, deque
from datetime import datetime, timezone
from typing import Optional
from urllib.parse import parse_qs, urlparse

from dotenv import load_dotenv
import websockets


load_dotenv()

RAW_TOKEN = (os.getenv("GROCERY_BOT_TOKEN_HARD") or "").strip()
if not RAW_TOKEN:
    raise SystemExit("Missing GROCERY_BOT_TOKEN_HARD in .env")


VALID_ACTIONS = {
    "move_up",
    "move_down",
    "move_left",
    "move_right",
    "pick_up",
    "drop_off",
    "wait",
}


def resolve_connection(input_value: str) -> tuple[str, str]:
    if input_value.startswith("ws://") or input_value.startswith("wss://"):
        parsed = urlparse(input_value)
        token = parse_qs(parsed.query).get("token", [""])[0].strip()
        if not token:
            raise SystemExit("WebSocket URL is missing ?token=...")
        return input_value, token

    if "token=" in input_value:
        token = input_value.split("token=", 1)[1].strip()
        return f"wss://game.ainm.no/ws?token={token}", token

    token = input_value
    return f"wss://game.ainm.no/ws?token={token}", token


def decode_token_claims(token: str) -> dict:
    parts = token.split(".")
    if len(parts) != 3:
        return {}
    payload = parts[1]
    padding = "=" * ((4 - len(payload) % 4) % 4)
    try:
        decoded = base64.urlsafe_b64decode(payload + padding).decode("utf-8")
        data = json.loads(decoded)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def token_is_expired(claims: dict) -> tuple[bool, Optional[datetime]]:
    exp = claims.get("exp")
    if not isinstance(exp, int):
        return False, None
    exp_dt = datetime.fromtimestamp(exp, tz=timezone.utc)
    return datetime.now(timezone.utc) >= exp_dt, exp_dt


def sanitize_actions(state: dict, actions: list[dict]) -> list[dict]:
    by_bot: dict[int, dict] = {}
    for action in actions:
        bot_id = action.get("bot")
        name = action.get("action")
        if not isinstance(bot_id, int) or name not in VALID_ACTIONS:
            continue
        if name == "pick_up":
            item_id = action.get("item_id")
            if isinstance(item_id, str) and item_id:
                by_bot[bot_id] = {"bot": bot_id, "action": "pick_up", "item_id": item_id}
            else:
                by_bot[bot_id] = {"bot": bot_id, "action": "wait"}
        else:
            by_bot[bot_id] = {"bot": bot_id, "action": name}

    safe = []
    for b in state.get("bots", []):
        bid = b["id"]
        safe.append(by_bot.get(bid, {"bot": bid, "action": "wait"}))
    return safe


class HardModeBotV2:
    """
    Hard-mode bot with:
    - path-aware assignments (not just Manhattan to shelf centre)
    - stricter preview policy (prevents inventory clogging)
    - drop-off queue management
    - anti-stuck nudges / oscillation breaking
    - pick retry cooldowns for contested items
    """

    def __init__(self) -> None:
        self.rng = random.Random(1337)

        self.shelves: set[tuple[int, int]] = set()
        self.walls: set[tuple[int, int]] = set()
        self.grid_w = 0
        self.grid_h = 0
        self.static_ready = False

        self.neighbor_cache: dict[tuple[int, int], list[tuple[int, int]]] = {}
        self.walkable_cells: set[tuple[int, int]] = set()
        self.dropoff_dist_cache: dict[tuple[int, int], int] = {}
        self.dropoff_cache_for: Optional[tuple[int, int]] = None

        self.bot_targets: dict[int, str] = {}
        self.last_action: dict[int, str] = {}
        self.last_positions: dict[int, deque[tuple[int, int]]] = {}
        self.wait_streak: dict[int, int] = {}
        self.last_inventory_size: dict[int, int] = {}
        self.last_pick_item: dict[int, str] = {}

        self.pick_fail_streak: dict[str, int] = {}
        self.pick_block_until_round: dict[str, int] = {}

        self.round_seen = -1

    # ---------- Public API ----------

    def decide(self, state: dict) -> list[dict]:
        self.round_seen = int(state.get("round", -1))
        self._ensure_static_grid(state)
        drop_off = tuple(state["drop_off"])
        self._ensure_dropoff_dist(drop_off)

        bots = sorted(state["bots"], key=lambda b: b["id"])
        items = state["items"]
        items_by_id = {i["id"]: i for i in items}
        occupied_now = {tuple(b["position"]) for b in bots}

        self._update_pick_retry_state(bots, self.round_seen)
        self._update_stuck_state(bots)

        active_order = self._get_order_by_status(state, "active")
        preview_order = self._get_order_by_status(state, "preview")

        active_need_raw = self._required_minus_delivered(active_order)
        delivery_alloc, active_left_after_carried = self._allocate_delivery_slots(bots, active_need_raw)

        # Active collection demand = what's still missing after accounting for already carried useful items
        active_collect_need = Counter(active_left_after_carried)

        # Preview demand (raw), but we will only use it under strict gating
        preview_need_raw = self._required_minus_delivered(preview_order)

        # Precompute item metadata for scoring
        item_meta = self._build_item_meta(items, state)

        # Build active assignments for bots with capacity
        clear_dropoff_ids = self._dropoff_clearance_bots(bots, drop_off, delivery_alloc)
        active_assignments = self._assign_items_globally(
            bots=bots,
            state=state,
            items=items,
            item_meta=item_meta,
            needed=Counter(active_collect_need),
            delivery_alloc=delivery_alloc,
            clear_dropoff_ids=clear_dropoff_ids,
            drop_off=drop_off,
            preview_mode=False,
        )

        # Determine if active order is fully covered by carried + active assignments
        covered = Counter()
        for alloc in delivery_alloc.values():
            covered.update(alloc)
        for _, item_id in active_assignments.items():
            item = items_by_id.get(item_id)
            if item:
                covered[item["type"]] += 1
        active_fully_covered = all(covered[t] >= c for t, c in active_need_raw.items())

        # Stricter preview: only empty/slightly loaded surplus bots, early/mid game, active fully covered
        preview_assignments: dict[int, str] = {}
        if self._preview_allowed(state, active_fully_covered, preview_need_raw):
            surplus_bots = []
            for b in bots:
                bid = b["id"]
                inv = b["inventory"]
                useful = self._delivery_count(delivery_alloc.get(bid, Counter())) > 0
                if bid in clear_dropoff_ids:
                    continue
                if bid in active_assignments:
                    continue
                if useful:
                    continue
                # Hard-mode tweak: do not overfill preview. Prefer empty bots, allow 1-item preview carry.
                if len(inv) <= 1:
                    surplus_bots.append(b)

            preview_assignments = self._assign_items_globally(
                bots=surplus_bots,
                state=state,
                items=items,
                item_meta=item_meta,
                needed=Counter(preview_need_raw),
                delivery_alloc=delivery_alloc,
                clear_dropoff_ids=clear_dropoff_ids,
                drop_off=drop_off,
                preview_mode=True,
            )

        # Drop-off queue management
        dropoff_queue_ids = self._select_dropoff_queue_leader(bots, drop_off, delivery_alloc)
        dropoff_queue_leader = self._select_dropoff_queue_primary(dropoff_queue_ids, bots, drop_off)

        # Planning loop
        actions: list[dict] = []
        reserved_next: set[tuple[int, int]] = set()
        reserved_items: set[str] = set()

        # Mutable demand copies, decremented when we commit a pick / claim
        active_need_mut = Counter(active_collect_need)
        preview_need_mut = Counter(preview_need_raw)

        # Mark assigned items as reserved for others as each bot claims them
        for b in bots:
            bid = b["id"]
            action = self._decide_one(
                bot=b,
                state=state,
                drop_off=drop_off,
                occupied_now=occupied_now,
                reserved_next=reserved_next,
                reserved_items=reserved_items,
                items_by_id=items_by_id,
                item_meta=item_meta,
                active_need=active_need_mut,
                preview_need=preview_need_mut,
                delivery_alloc=delivery_alloc,
                clear_dropoff_ids=clear_dropoff_ids,
                active_assignment=active_assignments.get(bid),
                preview_assignment=preview_assignments.get(bid),
                dropoff_queue_ids=dropoff_queue_ids,
                dropoff_queue_leader=dropoff_queue_leader,
            )
            actions.append(action)

            self.last_action[bid] = action["action"]
            if action["action"] == "pick_up":
                item_id = action.get("item_id")
                if isinstance(item_id, str):
                    self.last_pick_item[bid] = item_id
            else:
                self.last_pick_item.pop(bid, None)

        return actions

    # ---------- Core planning ----------

    def _decide_one(
        self,
        bot: dict,
        state: dict,
        drop_off: tuple[int, int],
        occupied_now: set[tuple[int, int]],
        reserved_next: set[tuple[int, int]],
        reserved_items: set[str],
        items_by_id: dict[str, dict],
        item_meta: dict[str, dict],
        active_need: Counter,
        preview_need: Counter,
        delivery_alloc: dict[int, Counter],
        clear_dropoff_ids: set[int],
        active_assignment: Optional[str],
        preview_assignment: Optional[str],
        dropoff_queue_ids: set[int],
        dropoff_queue_leader: Optional[int],
    ) -> dict:
        bid = bot["id"]
        pos = tuple(bot["position"])
        inv = list(bot["inventory"])
        useful_delivery = delivery_alloc.get(bid, Counter())
        useful_count = self._delivery_count(useful_delivery)
        has_useful = useful_count > 0
        has_non_useful = bool(inv) and not has_useful

        # 1) Immediate drop
        if has_useful and pos == drop_off:
            self.bot_targets.pop(bid, None)
            return {"bot": bid, "action": "drop_off"}

        # 2) If standing on drop-off and not delivering, clear the lane
        if bid in clear_dropoff_ids:
            act = self._move_to_any(
                bid, pos, self._adjacent_walkable(drop_off, state, occupied_now, pos),
                state, occupied_now, reserved_next
            )
            if act is not None:
                return act

        # 3) Late-game discipline: stop speculative behaviour
        if self.round_seen >= 292 and not has_useful:
            # Only allow immediate adjacent active pickup, otherwise head to staging or wait
            pick = self._pick_if_adjacent(bot, state, active_need, reserved_items, preview_mode=False)
            if pick is not None:
                return pick
            act = self._stage_near_dropoff(bid, pos, drop_off, state, occupied_now, reserved_next)
            return act if act is not None else self._wait_or_nudge(bid, pos, state, occupied_now, reserved_next)

        # 4) Active adjacent pick always beats movement (even for bots with junk inventory if free slot available)
        pick_active = self._pick_if_adjacent(bot, state, active_need, reserved_items, preview_mode=False)
        if pick_active is not None:
            return pick_active

        # 5) If carrying useful items, move to drop-off with queue staging
        if has_useful:
            # Optional detour only if bot still has capacity and a strongly on-path active item is assigned
            if len(inv) < 3 and self.round_seen <= 255 and active_assignment:
                detour = self._delivery_detour_action(
                    bid, pos, state, active_need, drop_off, occupied_now, reserved_items,
                    reserved_next, items_by_id, item_meta, active_assignment
                )
                if detour is not None:
                    return detour

            # Non-leader deliverers stage adjacent to avoid pileups
            if bid in dropoff_queue_ids and bid != dropoff_queue_leader:
                act = self._stage_near_dropoff(bid, pos, drop_off, state, occupied_now, reserved_next)
                if act is not None:
                    return act
            elif dropoff_queue_ids and bid not in dropoff_queue_ids:
                # Other deliverers also stage, unless no good staging path exists
                if useful_count > 0:
                    act = self._stage_near_dropoff(bid, pos, drop_off, state, occupied_now, reserved_next)
                    if act is not None:
                        return act

            move = self._move_to_goal(
                bid, pos, {drop_off}, state, occupied_now, reserved_next,
                allow_occupied_goals=True, relax_if_blocked=True
            )
            return move

        # 6) Preview adjacent pick (only if currently assigned and capacity low enough)
        if preview_assignment and len(inv) <= 1:
            pick_preview = self._pick_if_adjacent(
                bot, state, preview_need, reserved_items, preview_mode=True, force_item_id=preview_assignment
            )
            if pick_preview is not None:
                return pick_preview

        # 7) If inventory is full but useless, stage near drop-off (don't clog shelves)
        if len(inv) >= 3 and not has_useful:
            act = self._stage_near_dropoff(bid, pos, drop_off, state, occupied_now, reserved_next)
            return act if act is not None else self._wait_or_nudge(bid, pos, state, occupied_now, reserved_next)

        # 8) Active target movement
        target_item = self._choose_target_for_bot(
            bot_id=bid,
            pos=pos,
            state=state,
            needed=active_need,
            reserved_items=reserved_items,
            items_by_id=items_by_id,
            item_meta=item_meta,
            preferred_item_id=active_assignment,
            preview_mode=False,
        )

        if target_item is not None:
            reserved_items.add(target_item["id"])
            t = target_item["type"]
            if active_need[t] > 0:
                active_need[t] -= 1

            goals = set(item_meta[target_item["id"]]["approach_cells"])
            act = self._move_to_goal(
                bid, pos, goals, state, occupied_now, reserved_next, allow_occupied_goals=False
            )
            return act if act is not None else self._wait_or_nudge(bid, pos, state, occupied_now, reserved_next)

        # 9) Preview target movement (conservative)
        if preview_assignment and len(inv) <= 1:
            target_item = self._choose_target_for_bot(
                bot_id=bid,
                pos=pos,
                state=state,
                needed=preview_need,
                reserved_items=reserved_items,
                items_by_id=items_by_id,
                item_meta=item_meta,
                preferred_item_id=preview_assignment,
                preview_mode=True,
            )
            if target_item is not None:
                reserved_items.add(target_item["id"])
                t = target_item["type"]
                if preview_need[t] > 0:
                    preview_need[t] -= 1
                goals = set(item_meta[target_item["id"]]["approach_cells"])
                act = self._move_to_goal(
                    bid, pos, goals, state, occupied_now, reserved_next, allow_occupied_goals=False
                )
                return act if act is not None else self._wait_or_nudge(bid, pos, state, occupied_now, reserved_next)

        # 10) Idle positioning
        act = self._stage_toward_central_walkway(bid, pos, state, occupied_now, reserved_next)
        return act if act is not None else self._wait_or_nudge(bid, pos, state, occupied_now, reserved_next)

    def _assign_items_globally(
        self,
        bots: list[dict],
        state: dict,
        items: list[dict],
        item_meta: dict[str, dict],
        needed: Counter,
        delivery_alloc: dict[int, Counter],
        clear_dropoff_ids: set[int],
        drop_off: tuple[int, int],
        preview_mode: bool,
    ) -> dict[int, str]:
        """
        Global greedy assignment using path-aware score:
        bot -> item with lowest estimated (to approach + to dropoff_weight + congestion penalties)
        """
        if not bots or sum(needed.values()) <= 0:
            return {}

        items_by_id = {i["id"]: i for i in items}
        assignments: dict[int, str] = {}

        # Keep lock types so a bot can keep chasing its previous target if still relevant
        lock_by_bot = {}
        for bid, iid in self.bot_targets.items():
            it = items_by_id.get(iid)
            if it:
                lock_by_bot[bid] = iid

        candidates: list[tuple[float, int, str]] = []
        for b in bots:
            bid = b["id"]
            pos = tuple(b["position"])
            inv_len = len(b["inventory"])
            if bid in clear_dropoff_ids:
                continue
            if inv_len >= 3:
                continue

            useful_delivery = self._delivery_count(delivery_alloc.get(bid, Counter())) > 0

            for item in items:
                iid = item["id"]
                itype = item["type"]
                if needed[itype] <= 0:
                    continue
                if self._item_pick_blocked(iid, self.round_seen):
                    continue
                meta = item_meta.get(iid)
                if not meta or not meta["approach_cells"]:
                    continue

                d_to_item = self._dist_to_any(pos, meta["approach_cells"])
                if d_to_item >= 10**8:
                    continue

                # Path-aware desirability: prefer items whose pickup position is still not too far from drop-off.
                d_item_to_drop = meta["best_approach_to_dropoff"]

                # Base score
                score = float(d_to_item)

                # Delivery bots should be biased to stay on path / not over-detour
                if useful_delivery:
                    score += 0.9 * d_item_to_drop + 3.0
                else:
                    score += 0.35 * d_item_to_drop

                # Preview picks are speculative, require stronger proximity
                if preview_mode:
                    score += 2.5
                    if inv_len > 0:
                        score += 2.0  # do not stack too much preview inventory

                # Strong bonus for maintaining same lock (reduces retarget thrash)
                if lock_by_bot.get(bid) == iid:
                    score -= 2.25

                # Penalise far detours late game
                if self.round_seen >= 250:
                    score += 0.06 * d_to_item * d_to_item

                # Tiny tie-breakers
                score += 0.001 * bid
                candidates.append((score, bid, iid))

        candidates.sort(key=lambda x: x[0])

        used_bots: set[int] = set()
        used_items: set[str] = set()
        needed_left = Counter(needed)
        for _, bid, iid in candidates:
            if bid in used_bots or iid in used_items:
                continue
            it = items_by_id.get(iid)
            if not it:
                continue
            if needed_left[it["type"]] <= 0:
                continue
            assignments[bid] = iid
            used_bots.add(bid)
            used_items.add(iid)
            needed_left[it["type"]] -= 1

        return assignments

    # ---------- Picking / targeting ----------

    def _choose_target_for_bot(
        self,
        bot_id: int,
        pos: tuple[int, int],
        state: dict,
        needed: Counter,
        reserved_items: set[str],
        items_by_id: dict[str, dict],
        item_meta: dict[str, dict],
        preferred_item_id: Optional[str],
        preview_mode: bool,
    ) -> Optional[dict]:
        # 1) Preferred assignment if still valid
        if preferred_item_id:
            it = items_by_id.get(preferred_item_id)
            if self._item_is_valid_target(it, needed, reserved_items):
                self.bot_targets[bot_id] = preferred_item_id
                return it

        # 2) Existing lock if valid
        locked_id = self.bot_targets.get(bot_id)
        if locked_id:
            it = items_by_id.get(locked_id)
            if self._item_is_valid_target(it, needed, reserved_items):
                return it
            self.bot_targets.pop(bot_id, None)

        # 3) Pick best remaining by path-aware score
        locked_by_others = {iid for obid, iid in self.bot_targets.items() if obid != bot_id}
        blocked_items = reserved_items | locked_by_others

        best_item = None
        best_score = 10**9
        for item in state["items"]:
            iid = item["id"]
            if iid in blocked_items:
                continue
            if self._item_pick_blocked(iid, self.round_seen):
                continue
            if needed[item["type"]] <= 0:
                continue
            meta = item_meta.get(iid)
            if not meta or not meta["approach_cells"]:
                continue
            d_to_item = self._dist_to_any(pos, meta["approach_cells"])
            if d_to_item >= 10**8:
                continue
            score = float(d_to_item) + (0.25 if preview_mode else 0.15) * meta["best_approach_to_dropoff"]
            if preview_mode:
                score += 2.0
            if score < best_score:
                best_score = score
                best_item = item

        if best_item is not None:
            self.bot_targets[bot_id] = best_item["id"]
        return best_item

    def _item_is_valid_target(self, item: Optional[dict], needed: Counter, reserved_items: set[str]) -> bool:
        if item is None:
            return False
        iid = item["id"]
        if iid in reserved_items:
            return False
        if self._item_pick_blocked(iid, self.round_seen):
            return False
        if needed[item["type"]] <= 0:
            return False
        return True

    def _pick_if_adjacent(
        self,
        bot: dict,
        state: dict,
        needed: Counter,
        reserved_items: set[str],
        preview_mode: bool,
        force_item_id: Optional[str] = None,
    ) -> Optional[dict]:
        if len(bot["inventory"]) >= 3:
            return None

        bid = bot["id"]
        pos = tuple(bot["position"])
        candidates: list[tuple[float, dict]] = []

        for item in state["items"]:
            iid = item["id"]
            if force_item_id is not None and iid != force_item_id:
                continue
            if iid in reserved_items:
                continue
            if self._item_pick_blocked(iid, self.round_seen):
                continue
            if needed[item["type"]] <= 0:
                continue
            if self._manhattan(pos, tuple(item["position"])) != 1:
                continue

            # Prioritise active over preview, and items closer to dropoff
            dd = self.dropoff_dist_cache.get(pos, 9999)
            score = float(dd)
            if preview_mode:
                score += 1.0
            candidates.append((score, item))

        if not candidates:
            return None

        candidates.sort(key=lambda t: (t[0], t[1]["id"]))
        chosen = candidates[0][1]
        reserved_items.add(chosen["id"])
        needed[chosen["type"]] -= 1
        self.bot_targets.pop(bid, None)
        return {"bot": bid, "action": "pick_up", "item_id": chosen["id"]}

    # ---------- Movement / pathfinding ----------

    def _move_to_goal(
        self,
        bot_id: int,
        start: tuple[int, int],
        goals: set[tuple[int, int]],
        state: dict,
        occupied_now: set[tuple[int, int]],
        reserved_next: set[tuple[int, int]],
        allow_occupied_goals: bool,
        relax_if_blocked: bool = False,
    ) -> Optional[dict]:
        if not goals:
            return None

        blocked = (occupied_now - {start}) | reserved_next
        if allow_occupied_goals:
            blocked = blocked - goals

        # Anti-oscillation: if bot is bouncing, temporarily avoid previous cell if possible
        blocked_extra = set()
        if self._is_oscillating(bot_id):
            hist = self.last_positions.get(bot_id)
            if hist and len(hist) >= 2:
                blocked_extra.add(hist[-2])
        blocked = blocked | blocked_extra

        step = self._bfs_first_step(start, goals, blocked)
        if step is None and relax_if_blocked:
            blocked2 = (occupied_now - {start}) - (goals if allow_occupied_goals else set())
            step = self._bfs_first_step(start, goals, blocked2)
        if step is None:
            return None

        reserved_next.add(step)
        return {"bot": bot_id, "action": self._action_from_step(start, step)}

    def _move_to_any(
        self,
        bot_id: int,
        start: tuple[int, int],
        goals: set[tuple[int, int]],
        state: dict,
        occupied_now: set[tuple[int, int]],
        reserved_next: set[tuple[int, int]],
    ) -> Optional[dict]:
        return self._move_to_goal(
            bot_id, start, goals, state, occupied_now, reserved_next,
            allow_occupied_goals=False, relax_if_blocked=False
        )

    def _stage_near_dropoff(
        self,
        bot_id: int,
        pos: tuple[int, int],
        drop_off: tuple[int, int],
        state: dict,
        occupied_now: set[tuple[int, int]],
        reserved_next: set[tuple[int, int]],
    ) -> Optional[dict]:
        goals = self._adjacent_walkable(drop_off, state, occupied_now, pos)
        if not goals:
            return None

        # Prefer adjacent staging cell with best onward route to drop-off (distance 1 by definition),
        # but avoid over-congesting same side via bot_id staggering.
        ordered_goals = sorted(goals, key=lambda g: ((g[0] + g[1] + bot_id) % 4, g[0], g[1]))
        return self._move_to_goal(
            bot_id, pos, set(ordered_goals), state, occupied_now, reserved_next,
            allow_occupied_goals=False, relax_if_blocked=False
        )

    def _stage_toward_central_walkway(
        self,
        bot_id: int,
        pos: tuple[int, int],
        state: dict,
        occupied_now: set[tuple[int, int]],
        reserved_next: set[tuple[int, int]],
    ) -> Optional[dict]:
        if not self.walkable_cells:
            return None
        # Heuristic staging: prefer walkable cells near geometric centre, but not too close to dropoff if crowded
        cx = self.grid_w / 2.0
        cy = self.grid_h / 2.0
        candidates = []
        blocked = (occupied_now - {pos}) | reserved_next
        for cell in self.walkable_cells:
            if cell == pos or cell in blocked:
                continue
            if self._manhattan(pos, cell) > 8:
                continue
            d_center = abs(cell[0] - cx) + abs(cell[1] - cy)
            d_drop = self.dropoff_dist_cache.get(cell, 9999)
            score = d_center + 0.15 * d_drop + (((cell[0] * 31 + cell[1] * 17 + bot_id) % 7) * 0.05)
            candidates.append((score, cell))
        if not candidates:
            return None
        candidates.sort(key=lambda t: t[0])
        top = {c for _, c in candidates[:6]}
        return self._move_to_goal(
            bot_id, pos, top, state, occupied_now, reserved_next,
            allow_occupied_goals=False, relax_if_blocked=False
        )

    def _delivery_detour_action(
        self,
        bot_id: int,
        pos: tuple[int, int],
        state: dict,
        needed: Counter,
        drop_off: tuple[int, int],
        occupied_now: set[tuple[int, int]],
        reserved_items: set[str],
        reserved_next: set[tuple[int, int]],
        items_by_id: dict[str, dict],
        item_meta: dict[str, dict],
        assigned_item_id: str,
    ) -> Optional[dict]:
        item = items_by_id.get(assigned_item_id)
        if item is None:
            return None
        iid = item["id"]
        if iid in reserved_items:
            return None
        if self._item_pick_blocked(iid, self.round_seen):
            return None
        if needed[item["type"]] <= 0:
            return None

        meta = item_meta.get(iid)
        if not meta or not meta["approach_cells"]:
            return None

        # Only detour if it is genuinely on/near the route
        d_direct = self.dropoff_dist_cache.get(pos, 10**8)
        d_to_item = self._dist_to_any(pos, meta["approach_cells"])
        d_item_to_drop = meta["best_approach_to_dropoff"]
        if d_to_item >= 10**8 or d_item_to_drop >= 10**8:
            return None
        if d_to_item > 6:
            return None
        if d_to_item + d_item_to_drop > d_direct + 4:
            return None

        if self._manhattan(pos, tuple(item["position"])) == 1:
            reserved_items.add(iid)
            needed[item["type"]] -= 1
            self.bot_targets.pop(bot_id, None)
            return {"bot": bot_id, "action": "pick_up", "item_id": iid}

        reserved_items.add(iid)
        needed[item["type"]] -= 1
        self.bot_targets[bot_id] = iid
        return self._move_to_goal(
            bot_id, pos, set(meta["approach_cells"]), state, occupied_now, reserved_next,
            allow_occupied_goals=False, relax_if_blocked=False
        )

    def _bfs_first_step(
        self,
        start: tuple[int, int],
        goals: set[tuple[int, int]],
        blocked: set[tuple[int, int]],
    ) -> Optional[tuple[int, int]]:
        if not goals or start in goals:
            return None

        q = deque([start])
        prev: dict[tuple[int, int], Optional[tuple[int, int]]] = {start: None}

        while q:
            cur = q.popleft()
            for nxt in self.neighbor_cache.get(cur, []):
                if nxt in prev or nxt in blocked:
                    continue
                prev[nxt] = cur
                if nxt in goals:
                    return self._unwind_first_step(start, nxt, prev)
                q.append(nxt)
        return None

    def _dist_to_any(self, start: tuple[int, int], goals: list[tuple[int, int]]) -> int:
        if not goals:
            return 10**8
        if start in goals:
            return 0

        goalset = set(goals)
        q = deque([start])
        dist = {start: 0}
        while q:
            cur = q.popleft()
            nd = dist[cur] + 1
            for nxt in self.neighbor_cache.get(cur, []):
                if nxt in dist:
                    continue
                dist[nxt] = nd
                if nxt in goalset:
                    return nd
                q.append(nxt)
        return 10**8

    @staticmethod
    def _unwind_first_step(
        start: tuple[int, int],
        goal: tuple[int, int],
        prev: dict[tuple[int, int], Optional[tuple[int, int]]],
    ) -> Optional[tuple[int, int]]:
        cur = goal
        parent = prev[cur]
        while parent is not None and parent != start:
            cur = parent
            parent = prev[cur]
        if parent is None:
            return None
        return cur

    # ---------- Grid / state helpers ----------

    def _ensure_static_grid(self, state: dict) -> None:
        if self.static_ready:
            return
        self.grid_w = int(state["grid"]["width"])
        self.grid_h = int(state["grid"]["height"])
        self.walls = {tuple(w) for w in state["grid"]["walls"]}
        self.shelves = {tuple(i["position"]) for i in state["items"]}

        self.walkable_cells.clear()
        self.neighbor_cache.clear()
        for x in range(self.grid_w):
            for y in range(self.grid_h):
                p = (x, y)
                if p in self.walls or p in self.shelves:
                    continue
                self.walkable_cells.add(p)

        for p in self.walkable_cells:
            ns = []
            for n in self._neighbors(p):
                if n in self.walkable_cells:
                    ns.append(n)
            self.neighbor_cache[p] = ns

        self.static_ready = True

    def _ensure_dropoff_dist(self, drop_off: tuple[int, int]) -> None:
        if self.dropoff_cache_for == drop_off:
            return
        self.dropoff_cache_for = drop_off
        self.dropoff_dist_cache = {}

        if drop_off not in self.walkable_cells:
            return

        q = deque([drop_off])
        self.dropoff_dist_cache[drop_off] = 0
        while q:
            cur = q.popleft()
            nd = self.dropoff_dist_cache[cur] + 1
            for nxt in self.neighbor_cache.get(cur, []):
                if nxt in self.dropoff_dist_cache:
                    continue
                self.dropoff_dist_cache[nxt] = nd
                q.append(nxt)

    def _build_item_meta(self, items: list[dict], state: dict) -> dict[str, dict]:
        meta: dict[str, dict] = {}
        for item in items:
            pos = tuple(item["position"])
            approaches = [
                p for p in self._neighbors(pos)
                if p in self.walkable_cells
            ]
            best_drop = min((self.dropoff_dist_cache.get(a, 10**8) for a in approaches), default=10**8)
            meta[item["id"]] = {
                "approach_cells": approaches,
                "best_approach_to_dropoff": best_drop,
            }
        return meta

    def _adjacent_walkable(
        self,
        shelf_pos: tuple[int, int],
        state: dict,
        occupied_now: set[tuple[int, int]],
        self_pos: tuple[int, int],
    ) -> set[tuple[int, int]]:
        blocked = occupied_now - {self_pos}
        goals = set()
        for p in self._neighbors(shelf_pos):
            if p in self.walkable_cells and p not in blocked:
                goals.add(p)
        return goals

    # ---------- Order / inventory helpers ----------

    def _get_order_by_status(self, state: dict, status: str) -> Optional[dict]:
        return next((o for o in state["orders"] if o.get("status") == status), None)

    def _required_minus_delivered(self, order: Optional[dict]) -> Counter:
        if order is None:
            return Counter()
        return Counter(order["items_required"]) - Counter(order["items_delivered"])

    @staticmethod
    def _delivery_count(alloc: Counter) -> int:
        return int(sum(alloc.values()))

    def _allocate_delivery_slots(
        self, bots: list[dict], remaining_needed: Counter
    ) -> tuple[dict[int, Counter], Counter]:
        left = Counter(remaining_needed)
        alloc: dict[int, Counter] = {}
        for b in bots:
            bid = b["id"]
            reserved = Counter()
            for t in b["inventory"]:
                if left[t] > 0:
                    reserved[t] += 1
                    left[t] -= 1
            alloc[bid] = reserved
        return alloc, left

    def _dropoff_clearance_bots(
        self, bots: list[dict], drop_off: tuple[int, int], delivery_alloc: dict[int, Counter]
    ) -> set[int]:
        waiting_deliveries = any(
            tuple(b["position"]) != drop_off and self._delivery_count(delivery_alloc.get(b["id"], Counter())) > 0
            for b in bots
        )
        if not waiting_deliveries:
            return set()
        return {
            b["id"]
            for b in bots
            if tuple(b["position"]) == drop_off and self._delivery_count(delivery_alloc.get(b["id"], Counter())) == 0
        }

    def _select_dropoff_queue_leader(
        self, bots: list[dict], drop_off: tuple[int, int], delivery_alloc: dict[int, Counter]
    ) -> set[int]:
        deliverers = [b for b in bots if self._delivery_count(delivery_alloc.get(b["id"], Counter())) > 0]
        if not deliverers:
            return set()
        ranked = sorted(
            deliverers,
            key=lambda b: (
                0 if tuple(b["position"]) == drop_off else 1,
                self._manhattan(tuple(b["position"]), drop_off),
                b["id"],
            ),
        )
        # Keep only 2 in active queue to reduce congestion
        return {b["id"] for b in ranked[:2]}

    def _select_dropoff_queue_primary(
        self, queue_ids: set[int], bots: list[dict], drop_off: tuple[int, int]
    ) -> Optional[int]:
        if not queue_ids:
            return None
        candidates = [b for b in bots if b["id"] in queue_ids]
        if not candidates:
            return None
        on_drop = [b for b in candidates if tuple(b["position"]) == drop_off]
        if on_drop:
            return min(b["id"] for b in on_drop)
        best = min(candidates, key=lambda b: (self._manhattan(tuple(b["position"]), drop_off), b["id"]))
        return best["id"]

    def _preview_allowed(self, state: dict, active_fully_covered: bool, preview_need_raw: Counter) -> bool:
        if not active_fully_covered:
            return False
        if sum(preview_need_raw.values()) <= 0:
            return False
        rnd = int(state.get("round", 0))
        # Hard-mode conservative preview window
        if rnd >= 270:
            return False
        return True

    # ---------- Stuck handling / retries ----------

    def _update_stuck_state(self, bots: list[dict]) -> None:
        active_ids = {b["id"] for b in bots}
        for b in bots:
            bid = b["id"]
            pos = tuple(b["position"])
            hist = self.last_positions.setdefault(bid, deque(maxlen=6))
            prev_pos = hist[-1] if hist else None
            hist.append(pos)

            prev_action = self.last_action.get(bid)
            if prev_action == "wait" and prev_pos == pos:
                self.wait_streak[bid] = self.wait_streak.get(bid, 0) + 1
            else:
                self.wait_streak[bid] = 0

        for d in (self.last_positions, self.wait_streak, self.last_action, self.last_inventory_size, self.last_pick_item):
            for k in list(d.keys()):
                if k not in active_ids:
                    d.pop(k, None)

    def _is_oscillating(self, bot_id: int) -> bool:
        hist = self.last_positions.get(bot_id)
        if not hist or len(hist) < 4:
            return False
        a, b, c, d = hist[-4], hist[-3], hist[-2], hist[-1]
        # A-B-A-B pattern
        return a == c and b == d and a != b

    def _wait_or_nudge(
        self,
        bot_id: int,
        pos: tuple[int, int],
        state: dict,
        occupied_now: set[tuple[int, int]],
        reserved_next: set[tuple[int, int]],
    ) -> dict:
        if self.wait_streak.get(bot_id, 0) >= 2 or self._is_oscillating(bot_id):
            nudge = self._random_nudge(bot_id, pos, occupied_now, reserved_next)
            if nudge is not None:
                return nudge
        return {"bot": bot_id, "action": "wait"}

    def _random_nudge(
        self,
        bot_id: int,
        pos: tuple[int, int],
        occupied_now: set[tuple[int, int]],
        reserved_next: set[tuple[int, int]],
    ) -> Optional[dict]:
        options = []
        blocked = (occupied_now - {pos}) | reserved_next
        for n in self.neighbor_cache.get(pos, []):
            if n in blocked:
                continue
            options.append(n)
        if not options:
            return None
        step = self.rng.choice(options)
        reserved_next.add(step)
        return {"bot": bot_id, "action": self._action_from_step(pos, step)}

    def _update_pick_retry_state(self, bots: list[dict], round_number: int) -> None:
        active_ids = {b["id"] for b in bots}
        for b in bots:
            bid = b["id"]
            prev_action = self.last_action.get(bid)
            prev_size = self.last_inventory_size.get(bid)
            cur_size = len(b["inventory"])

            if prev_action == "pick_up":
                attempted_item_id = self.last_pick_item.get(bid)
                if attempted_item_id and prev_size is not None:
                    if cur_size <= prev_size:
                        streak = self.pick_fail_streak.get(attempted_item_id, 0) + 1
                        self.pick_fail_streak[attempted_item_id] = streak
                        cooldown = min(16, 3 + 2 * (streak - 1))
                        until = round_number + cooldown
                        self.pick_block_until_round[attempted_item_id] = max(
                            self.pick_block_until_round.get(attempted_item_id, -1), until
                        )
                        # Drop locks to contested item
                        for obid, iid in list(self.bot_targets.items()):
                            if iid == attempted_item_id:
                                self.bot_targets.pop(obid, None)
                    else:
                        self.pick_fail_streak.pop(attempted_item_id, None)
                        self.pick_block_until_round.pop(attempted_item_id, None)

            self.last_inventory_size[bid] = cur_size

        for bid in list(self.last_inventory_size.keys()):
            if bid not in active_ids:
                self.last_inventory_size.pop(bid, None)
                self.last_pick_item.pop(bid, None)

        for iid, until in list(self.pick_block_until_round.items()):
            if until < round_number:
                self.pick_block_until_round.pop(iid, None)
                self.pick_fail_streak.pop(iid, None)

    def _item_pick_blocked(self, item_id: str, round_number: int) -> bool:
        until = self.pick_block_until_round.get(item_id)
        return until is not None and round_number <= until

    # ---------- Small utilities ----------

    @staticmethod
    def _neighbors(p: tuple[int, int]) -> list[tuple[int, int]]:
        x, y = p
        return [(x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)]

    @staticmethod
    def _manhattan(a: tuple[int, int], b: tuple[int, int]) -> int:
        return abs(a[0] - b[0]) + abs(a[1] - b[1])

    @staticmethod
    def _action_from_step(start: tuple[int, int], step: tuple[int, int]) -> str:
        sx, sy = start
        nx, ny = step
        if nx == sx + 1:
            return "move_right"
        if nx == sx - 1:
            return "move_left"
        if ny == sy + 1:
            return "move_down"
        if ny == sy - 1:
            return "move_up"
        return "wait"


async def main() -> None:
    ws_url, token = resolve_connection(RAW_TOKEN)
    claims = decode_token_claims(token)
    expired, exp_dt = token_is_expired(claims)
    if expired:
        raise SystemExit(
            f"Token expired at {exp_dt.isoformat()} UTC. Click Play to get a fresh token and update .env."
        )

    bot = HardModeBotV2()
    print("Connecting to Grocery Bot server...", flush=True)

    async with websockets.connect(ws_url) as ws:
        print("Connected. Running hard-mode bot v2...", flush=True)
        while True:
            msg = json.loads(await ws.recv())

            if msg.get("type") == "game_over":
                print("Game over:", msg, flush=True)
                return

            if "round" in msg and int(msg["round"]) % 25 == 0:
                print(
                    f"Round {msg['round']} | score={msg.get('score', 0)} | "
                    f"items={msg.get('items_delivered', '?')} | orders={msg.get('orders_completed', '?')}",
                    flush=True,
                )

            round_start = time.monotonic()
            try:
                planned = bot.decide(msg)
            except Exception as exc:
                print(f"Planner error on round {msg.get('round')}: {exc}", flush=True)
                planned = [{"bot": b["id"], "action": "wait"} for b in msg.get("bots", [])]

            if (time.monotonic() - round_start) > 1.8:
                print(f"Round {msg.get('round')} planning > 1.8s. Fallback to wait.", flush=True)
                planned = [{"bot": b["id"], "action": "wait"} for b in msg.get("bots", [])]

            actions = sanitize_actions(msg, planned)
            await ws.send(json.dumps({"actions": actions}))


if __name__ == "__main__":
    asyncio.run(main())
