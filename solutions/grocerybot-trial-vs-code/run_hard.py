"""
Grocery Bot — Hard difficulty (NM i AI 2026)
Clean rewrite with key improvements over the original:
  1. random.seed(42) for deterministic runs
  2. BFS-distance replaces Manhattan in all assignment/targeting
  3. Walls cached once per grid (not rebuilt every BFS call)
  4. Priority-based bot processing: deliverers first, then pickers, then idle
  5. Pick retry/cooldown from original hard bot preserved
  6. Surplus preview assignment preserved
  7. Delivery pipeline and dropoff queue preserved

Requirements: pip install websockets python-dotenv
Usage: Set GROCERY_BOT_TOKEN_HARD in .env, then: python run_hard_v2.py
"""

import asyncio
import base64
import csv
import json
import os
import random
import time
from collections import Counter, deque
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional
from urllib.parse import parse_qs, urlparse

from dotenv import load_dotenv
import websockets

random.seed(42)

load_dotenv()
raw = (os.getenv("GROCERY_BOT_TOKEN_HARD") or "").strip()
if not raw:
    raise SystemExit("Missing GROCERY_BOT_TOKEN_HARD in .env")

BASE_DIR = Path(__file__).resolve().parent
LOG_DIR = BASE_DIR / "logs"
RUN_HISTORY_CSV = LOG_DIR / "run_history.csv"
MEMORY_JSON = LOG_DIR / "memory.json"
MEMORY_MD = LOG_DIR / "TRIAL_MEMORY.md"

# ---------------------------------------------------------------------------
# Connection helpers
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Run logger (unchanged from original — works well)
# ---------------------------------------------------------------------------

class RunLogger:
    def __init__(self, claims: dict) -> None:
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        self.claims = claims
        self.started_utc = datetime.now(timezone.utc)
        self.run_id = self.started_utc.strftime("%Y%m%d_%H%M%S")
        self.replay_file = LOG_DIR / f"game_{self.run_id}.jsonl"
        self._fp = self.replay_file.open("a", encoding="utf-8")
        self.start_monotonic = time.monotonic()
        self.action_counts: Counter = Counter()

    def log_state(self, state: dict) -> None:
        self._write_line(
            {"event": "game_state", "round": state.get("round"),
             "score": state.get("score"), "data": state}
        )

    def log_actions(self, round_number: int, actions: list[dict]) -> None:
        for a in actions:
            self.action_counts[a.get("action", "unknown")] += 1
        self._write_line({"event": "actions", "round": round_number, "actions": actions})

    def finish(self, game_over: dict) -> dict:
        self._write_line({"event": "game_over", "data": game_over})
        elapsed_s = round(time.monotonic() - self.start_monotonic, 3)
        summary = {
            "run_id": self.run_id,
            "started_utc": self.started_utc.isoformat(),
            "duration_s": elapsed_s,
            "difficulty": self.claims.get("difficulty", ""),
            "map_id": self.claims.get("map_id", ""),
            "map_seed": self.claims.get("map_seed", ""),
            "team_id": self.claims.get("team_id", ""),
            "score": int(game_over.get("score", 0)),
            "rounds_used": int(game_over.get("rounds_used", 0)),
            "items_delivered": int(game_over.get("items_delivered", 0)),
            "orders_completed": int(game_over.get("orders_completed", 0)),
            "replay_file": self.replay_file.name,
            "action_counts_json": json.dumps(dict(self.action_counts), sort_keys=True),
        }
        self._append_history_row(summary)
        memory = self._update_memory(summary)
        self._append_markdown_summary(summary, memory)
        self.close()
        return summary

    def close(self) -> None:
        if not self._fp.closed:
            self._fp.close()

    def _write_line(self, obj: dict) -> None:
        self._fp.write(json.dumps(obj, separators=(",", ":")) + "\n")
        self._fp.flush()

    def _append_history_row(self, summary: dict) -> None:
        header = [
            "run_id", "started_utc", "duration_s", "difficulty", "map_id",
            "map_seed", "team_id", "score", "rounds_used", "items_delivered",
            "orders_completed", "replay_file", "action_counts_json",
        ]
        write_header = not RUN_HISTORY_CSV.exists()
        with RUN_HISTORY_CSV.open("a", newline="", encoding="utf-8") as fp:
            writer = csv.DictWriter(fp, fieldnames=header)
            if write_header:
                writer.writeheader()
            writer.writerow(summary)

    def _update_memory(self, summary: dict) -> dict:
        if MEMORY_JSON.exists():
            with MEMORY_JSON.open("r", encoding="utf-8") as fp:
                memory = json.load(fp)
        else:
            memory = {"targets": {"hard_score_to_beat": 0}, "best_scores": {},
                      "run_count": 0, "latest_run": {}}
        difficulty = (summary.get("difficulty") or "").lower()
        score = int(summary.get("score", 0))
        best_scores = memory.setdefault("best_scores", {})
        current_best = int(best_scores.get(difficulty, 0)) if difficulty else 0
        if difficulty:
            best_scores[difficulty] = max(current_best, score)
        memory["run_count"] = int(memory.get("run_count", 0)) + 1
        memory["latest_run"] = summary
        with MEMORY_JSON.open("w", encoding="utf-8") as fp:
            json.dump(memory, fp, indent=2)
        return memory

    def _append_markdown_summary(self, summary: dict, memory: dict) -> None:
        if not MEMORY_MD.exists():
            MEMORY_MD.write_text(
                "# Grocery Bot Trial Memory\n\nTarget: Beat Hard best\n\n## Run Log\n\n",
                encoding="utf-8",
            )
        hard_best = memory.get("best_scores", {}).get("hard", "n/a")
        line = (
            f"- {summary['run_id']} | diff={summary['difficulty'] or 'unknown'} "
            f"| score={summary['score']} | items={summary['items_delivered']} "
            f"| orders={summary['orders_completed']} | hard_best={hard_best} "
            f"| replay={summary['replay_file']}"
        )
        with MEMORY_MD.open("a", encoding="utf-8") as fp:
            fp.write(line + "\n")


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

WS_URL, TOKEN = resolve_connection(raw)
TOKEN_CLAIMS = decode_token_claims(TOKEN)
VALID_ACTIONS = {"move_up", "move_down", "move_left", "move_right", "pick_up", "drop_off", "wait"}

# ---------------------------------------------------------------------------
# Bot
# ---------------------------------------------------------------------------

class HardBot:
    """
    Improvements over original hard bot:
    - _bfs_distance(): real walkable distance for assignment, replacing Manhattan
    - _walls cached once (not rebuilt per BFS call)
    - Bots processed in priority order: deliverers -> pickers -> idle
    - All original features preserved: pick retry, surplus preview, delivery pipeline
    """

    def __init__(self) -> None:
        self.shelves: set[tuple[int, int]] = set()
        self._walls: set[tuple[int, int]] = set()
        self._grid_width: int = 0
        self._grid_height: int = 0
        self._grid_inited: bool = False

        # Bot state tracking
        self.bot_targets: dict[int, str] = {}
        self.last_drop_round: dict[int, int] = {}
        self.wait_streak: dict[int, int] = {}
        self.last_observed_pos: dict[int, tuple[int, int]] = {}
        self.last_action: dict[int, str] = {}

        # Pick retry / cooldown (from original hard)
        self.last_inventory_size: dict[int, int] = {}
        self.last_pick_item: dict[int, str] = {}
        self.pick_fail_streak: dict[str, int] = {}
        self.pick_block_until_round: dict[str, int] = {}

        # Staging cache
        self._staging_cache_key: Optional[tuple] = None
        self._staging_candidates: list[tuple[int, int]] = []

        # BFS distance cache: cleared each round
        self._bfs_dist_cache: dict[tuple[tuple[int,int], tuple[int,int]], int] = {}

    # -------------------------------------------------------------------
    # Grid setup (once)
    # -------------------------------------------------------------------

    def _init_grid(self, state: dict) -> None:
        if self._grid_inited:
            return
        self._grid_width = state["grid"]["width"]
        self._grid_height = state["grid"]["height"]
        self._walls = {tuple(w) for w in state["grid"]["walls"]}
        self._grid_inited = True

    # -------------------------------------------------------------------
    # BFS distance (NEW — replaces Manhattan for assignment)
    # -------------------------------------------------------------------

    def _bfs_distance(
        self,
        start: tuple[int, int],
        goal_pos: tuple[int, int],
        state: dict,
    ) -> int:
        """
        Real walkable distance from start to any cell adjacent to goal_pos
        (since goal_pos is typically a shelf and not walkable).
        Returns 9999 if unreachable.
        """
        cache_key = (start, goal_pos)
        if cache_key in self._bfs_dist_cache:
            return self._bfs_dist_cache[cache_key]

        # Goals are walkable cells adjacent to the shelf/item position
        goals: set[tuple[int, int]] = set()
        for nx, ny in self._neighbors(goal_pos):
            if not (0 <= nx < self._grid_width and 0 <= ny < self._grid_height):
                continue
            if (nx, ny) not in self._walls and (nx, ny) not in self.shelves:
                goals.add((nx, ny))

        if not goals:
            self._bfs_dist_cache[cache_key] = 9999
            return 9999

        if start in goals:
            self._bfs_dist_cache[cache_key] = 0
            return 0

        # BFS
        q: deque[tuple[tuple[int, int], int]] = deque([(start, 0)])
        visited: set[tuple[int, int]] = {start}

        while q:
            pos, dist = q.popleft()
            for nxt in self._neighbors(pos):
                if nxt in visited:
                    continue
                nx, ny = nxt
                if not (0 <= nx < self._grid_width and 0 <= ny < self._grid_height):
                    continue
                if nxt in self._walls or nxt in self.shelves:
                    continue
                new_dist = dist + 1
                if nxt in goals:
                    self._bfs_dist_cache[cache_key] = new_dist
                    return new_dist
                visited.add(nxt)
                q.append((nxt, new_dist))

        self._bfs_dist_cache[cache_key] = 9999
        return 9999

    # -------------------------------------------------------------------
    # Main decision loop
    # -------------------------------------------------------------------

    def decide(self, state: dict) -> list[dict]:
        self._init_grid(state)
        self._bfs_dist_cache.clear()  # Fresh cache each round

        for item in state["items"]:
            self.shelves.add(tuple(item["position"]))
        self._refresh_staging_candidates(state)

        round_number = int(state.get("round", -1))
        bots = sorted(state["bots"], key=lambda b: b["id"])
        self._update_pick_retry_state(bots, round_number)
        self._update_wait_state(bots)
        items_by_id = {item["id"]: item for item in state["items"]}
        occupied_now = {tuple(b["position"]) for b in bots}
        reserved_next: set[tuple[int, int]] = set()
        reserved_items: set[str] = set()

        active_order = self._get_order_by_status(state, "active")
        active_needed_raw = self._required_minus_delivered(active_order)
        delivery_alloc, _ = self._allocate_delivery_slots(bots, active_needed_raw)
        needed = self._needed_counts_for_order(active_order, bots)
        preview_order = self._get_order_by_status(state, "preview")
        preview_needed = self._needed_counts_for_order(preview_order, bots)
        preview_item_ids = self._preview_item_ids(state["items"], preview_needed)
        preview_duty_bots = self._current_preview_duty_bots(preview_item_ids, bots)
        preview_duty_cap = min(max(0, len(bots) - 1), 3)

        # Pre-pick preview items once active needs are fully covered by inventory
        if sum(needed.values()) == 0 and sum(preview_needed.values()) > 0:
            needed = preview_needed

        drop_off = tuple(state["drop_off"])
        dropoff_queue_ids = self._select_dropoff_queue_leader(bots, drop_off, delivery_alloc)
        dropoff_queue_leader = self._select_dropoff_queue_primary(
            dropoff_queue_ids, bots, drop_off
        )
        clear_dropoff_ids = self._dropoff_clearance_bots(bots, drop_off, delivery_alloc)
        assignments = self._build_greedy_assignments(
            bots=bots,
            items=state["items"],
            needed=needed,
            clear_dropoff_ids=clear_dropoff_ids,
            delivery_alloc=delivery_alloc,
            round_number=round_number,
            state=state,
        )

        # Surplus bot preview assignment (from original hard)
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
                coverage[item_type] >= count
                for item_type, count in active_needed_raw.items()
            )
            if active_fully_covered:
                surplus_bots = [
                    b for b in bots
                    if b["id"] not in assignments
                    and b["id"] not in clear_dropoff_ids
                    and self._delivery_count(delivery_alloc.get(b["id"], Counter())) == 0
                    and len(b["inventory"]) < 3
                ]
                preview_assignments = self._build_greedy_assignments(
                    bots=surplus_bots,
                    items=state["items"],
                    needed=preview_needed,
                    clear_dropoff_ids=clear_dropoff_ids,
                    delivery_alloc=delivery_alloc,
                    round_number=round_number,
                    state=state,
                )
                assignments.update(preview_assignments)
                preview_priority_bots = set(preview_assignments.keys())
                preview_duty_bots.update(preview_priority_bots)

        # IMPROVEMENT: Process bots in priority order
        # Deliverers first (closest to drop_off), then assigned pickers, then idle.
        # This ensures delivery bots get first pick of paths via reserved_next.
        def bot_priority(b: dict) -> tuple[int, int, int]:
            bid = b["id"]
            has_delivery = self._delivery_count(delivery_alloc.get(bid, Counter())) > 0
            has_assignment = bid in assignments
            if has_delivery:
                return (0, self._manhattan(tuple(b["position"]), drop_off), bid)
            if has_assignment:
                return (1, 0, bid)
            return (2, 0, bid)

        ordered_bots = sorted(bots, key=bot_priority)
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
                clear_dropoff_ids=clear_dropoff_ids,
                items_by_id=items_by_id,
                assigned_item_id=assignments.get(bot["id"]),
                useful_delivery=delivery_alloc.get(bot["id"], Counter()),
                preview_needed=preview_needed,
                preview_item_ids=preview_item_ids,
                preview_duty_bots=preview_duty_bots,
                preview_duty_cap=preview_duty_cap,
                dropoff_queue_ids=dropoff_queue_ids,
                dropoff_queue_leader=dropoff_queue_leader,
                preview_priority=bot["id"] in preview_priority_bots,
            )
            action_map[bot["id"]] = action
            self.last_action[bot["id"]] = action["action"]
            if action["action"] == "pick_up":
                item_id = action.get("item_id")
                if isinstance(item_id, str) and item_id:
                    self.last_pick_item[bot["id"]] = item_id
                else:
                    self.last_pick_item.pop(bot["id"], None)
            else:
                self.last_pick_item.pop(bot["id"], None)

        # Return actions in original bot ID order (server expects this)
        return [action_map[b["id"]] for b in bots]

    # -------------------------------------------------------------------
    # Pick retry / cooldown (from original hard — preserved exactly)
    # -------------------------------------------------------------------

    def _update_pick_retry_state(self, bots: list[dict], round_number: int) -> None:
        active_ids = {b["id"] for b in bots}
        for bot in bots:
            bot_id = bot["id"]
            prev_action = self.last_action.get(bot_id)
            prev_size = self.last_inventory_size.get(bot_id)
            current_size = len(bot["inventory"])
            if prev_action == "pick_up":
                attempted_item_id = self.last_pick_item.get(bot_id)
                if attempted_item_id and prev_size is not None:
                    if current_size <= prev_size:
                        streak = self.pick_fail_streak.get(attempted_item_id, 0) + 1
                        self.pick_fail_streak[attempted_item_id] = streak
                        cooldown_rounds = min(18, 4 + ((streak - 1) * 2))
                        until_round = round_number + cooldown_rounds
                        self.pick_block_until_round[attempted_item_id] = max(
                            self.pick_block_until_round.get(attempted_item_id, -1),
                            until_round,
                        )
                        for target_bot_id, target_item_id in list(self.bot_targets.items()):
                            if target_item_id == attempted_item_id:
                                self.bot_targets.pop(target_bot_id, None)
                    else:
                        self.pick_fail_streak.pop(attempted_item_id, None)
                        self.pick_block_until_round.pop(attempted_item_id, None)
            self.last_inventory_size[bot_id] = current_size

        for bot_id in list(self.last_inventory_size.keys()):
            if bot_id not in active_ids:
                self.last_inventory_size.pop(bot_id, None)
                self.last_pick_item.pop(bot_id, None)

        for item_id, until_round in list(self.pick_block_until_round.items()):
            if until_round < round_number:
                self.pick_block_until_round.pop(item_id, None)
                self.pick_fail_streak.pop(item_id, None)

    def _item_pick_blocked(self, item_id: str, round_number: int) -> bool:
        until_round = self.pick_block_until_round.get(item_id)
        return until_round is not None and round_number <= until_round

    # -------------------------------------------------------------------
    # Wait state tracking
    # -------------------------------------------------------------------

    def _update_wait_state(self, bots: list[dict]) -> None:
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

    # -------------------------------------------------------------------
    # Dropoff management
    # -------------------------------------------------------------------

    def _dropoff_clearance_bots(
        self, bots: list[dict], drop_off: tuple[int, int],
        delivery_alloc: dict[int, Counter],
    ) -> set[int]:
        waiting_deliveries = any(
            tuple(b["position"]) != drop_off
            and self._delivery_count(delivery_alloc.get(b["id"], Counter())) > 0
            for b in bots
        )
        if not waiting_deliveries:
            return set()
        return {
            b["id"] for b in bots
            if tuple(b["position"]) == drop_off
            and self._delivery_count(delivery_alloc.get(b["id"], Counter())) == 0
        }

    def _select_dropoff_queue_leader(
        self, bots: list[dict], drop_off: tuple[int, int],
        delivery_alloc: dict[int, Counter],
    ) -> set[int]:
        deliverers = [
            b for b in bots
            if self._delivery_count(delivery_alloc.get(b["id"], Counter())) > 0
        ]
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
        return {b["id"] for b in ranked[:1]}

    def _select_dropoff_queue_primary(
        self, queue_ids: set[int], bots: list[dict], drop_off: tuple[int, int],
    ) -> Optional[int]:
        if not queue_ids:
            return None
        candidates = [b for b in bots if b["id"] in queue_ids]
        if not candidates:
            return None
        on_dropoff = [b for b in candidates if tuple(b["position"]) == drop_off]
        if on_dropoff:
            return min(b["id"] for b in on_dropoff)
        leader = min(
            candidates,
            key=lambda b: (self._manhattan(tuple(b["position"]), drop_off), b["id"]),
        )
        return leader["id"]

    # -------------------------------------------------------------------
    # Order helpers
    # -------------------------------------------------------------------

    def _get_order_by_status(self, state: dict, status: str) -> Optional[dict]:
        return next((o for o in state["orders"] if o.get("status") == status), None)

    def _required_minus_delivered(self, order: Optional[dict]) -> Counter:
        if order is None:
            return Counter()
        return Counter(order["items_required"]) - Counter(order["items_delivered"])

    def _needed_counts_for_order(self, order: Optional[dict], bots: list[dict]) -> Counter:
        if order is None:
            return Counter()
        needed = self._required_minus_delivered(order)
        carried = Counter()
        for bot in bots:
            for item_type in bot["inventory"]:
                carried[item_type] += 1
        for item_type, count in carried.items():
            if needed[item_type] > 0:
                needed[item_type] = max(0, needed[item_type] - count)
        return needed

    def _preview_item_ids(self, items: list[dict], preview_needed: Counter) -> set[str]:
        if sum(preview_needed.values()) <= 0:
            return set()
        return {item["id"] for item in items if preview_needed[item["type"]] > 0}

    def _current_preview_duty_bots(self, preview_item_ids: set[str], bots: list[dict]) -> set[int]:
        if not preview_item_ids:
            return set()
        bot_ids = {b["id"] for b in bots}
        return {
            bot_id for bot_id, target_item_id in self.bot_targets.items()
            if bot_id in bot_ids and target_item_id in preview_item_ids
        }

    # -------------------------------------------------------------------
    # Assignment (IMPROVED: uses BFS distance)
    # -------------------------------------------------------------------

    def _build_greedy_assignments(
        self,
        bots: list[dict],
        items: list[dict],
        needed: Counter,
        clear_dropoff_ids: set[int],
        delivery_alloc: dict[int, Counter],
        round_number: int,
        state: dict,
    ) -> dict[int, str]:
        assignments: dict[int, str] = {}
        needed_left = Counter(needed)

        lock_type_by_bot: dict[int, str] = {}
        for lock_bot_id, item_id in self.bot_targets.items():
            for item in items:
                if item["id"] == item_id:
                    lock_type_by_bot[lock_bot_id] = item["type"]
                    break

        candidates: list[tuple[int, int, str]] = []
        for bot in bots:
            if bot["id"] in clear_dropoff_ids:
                continue
            if len(bot["inventory"]) >= 3:
                continue
            bot_needed_left = Counter(needed_left)
            for other_bot_id, item_type in lock_type_by_bot.items():
                if other_bot_id == bot["id"]:
                    continue
                if bot_needed_left[item_type] > 0:
                    bot_needed_left[item_type] -= 1
            useful_delivery = self._delivery_count(delivery_alloc.get(bot["id"], Counter())) > 0
            bot_pos = tuple(bot["position"])
            for item in items:
                if bot_needed_left[item["type"]] <= 0:
                    continue
                if self._item_pick_blocked(item["id"], round_number):
                    continue
                # KEY CHANGE: BFS distance instead of Manhattan
                dist = self._bfs_distance(bot_pos, tuple(item["position"]), state)
                if useful_delivery:
                    dist += max(3, dist // 3)
                candidates.append((dist, bot["id"], item["id"]))

        candidates.sort(key=lambda x: x[0])
        used_bots: set[int] = set()
        used_items: set[str] = set()
        for _, bot_id, item_id in candidates:
            if bot_id in used_bots or item_id in used_items:
                continue
            item = next((it for it in items if it["id"] == item_id), None)
            if item is None:
                continue
            if needed_left[item["type"]] <= 0:
                continue
            assignments[bot_id] = item_id
            used_bots.add(bot_id)
            used_items.add(item_id)
            needed_left[item["type"]] -= 1
        return assignments

    # -------------------------------------------------------------------
    # Per-bot decision
    # -------------------------------------------------------------------

    def _decide_one(
        self,
        bot: dict,
        round_number: int,
        state: dict,
        needed: Counter,
        drop_off: tuple[int, int],
        occupied_now: set[tuple[int, int]],
        reserved_items: set[str],
        reserved_next: set[tuple[int, int]],
        clear_dropoff_ids: set[int],
        items_by_id: dict[str, dict],
        assigned_item_id: Optional[str],
        useful_delivery: Counter,
        preview_needed: Counter,
        preview_item_ids: set[str],
        preview_duty_bots: set[int],
        preview_duty_cap: int,
        dropoff_queue_ids: set[int],
        dropoff_queue_leader: Optional[int],
        preview_priority: bool,
    ) -> dict:
        bot_id = bot["id"]
        pos = tuple(bot["position"])
        inventory = bot["inventory"]
        useful_inventory = self._delivery_count(useful_delivery) > 0
        has_non_useful_inventory = bool(inventory) and not useful_inventory

        # --- Drop off if at delivery point with useful items ---
        if useful_inventory and pos == drop_off:
            if self.last_drop_round.get(bot_id) == round_number - 1:
                return self._wait_or_nudge(bot_id, pos, state, occupied_now, reserved_next)
            self.bot_targets.pop(bot_id, None)
            self.last_drop_round[bot_id] = round_number
            return {"bot": bot_id, "action": "drop_off"}

        # --- Clear dropoff for others ---
        if bot_id in clear_dropoff_ids:
            evac_goals = self._neighbors(drop_off)
            return self._move_toward(
                bot_id, pos, set(evac_goals), state,
                occupied_now, reserved_next, allow_occupied_goals=False,
            )

        # --- Late game: stop chasing if no useful inventory ---
        if round_number > 280 and not useful_inventory:
            self.bot_targets.pop(bot_id, None)
            return {"bot": bot_id, "action": "wait"}

        # --- Full preview bag: stage near dropoff ---
        if has_non_useful_inventory and len(inventory) >= 3:
            self.bot_targets.pop(bot_id, None)
            staging_goals = self._adjacent_walkable(drop_off, state, occupied_now, pos)
            if staging_goals:
                return self._move_toward(
                    bot_id, pos, staging_goals, state,
                    occupied_now, reserved_next, allow_occupied_goals=False,
                )
            return self._wait_or_nudge(bot_id, pos, state, occupied_now, reserved_next)

        # --- Non-useful inventory, room to pick more preview items ---
        if has_non_useful_inventory and len(inventory) < 3:
            preview_duty_allowed = (
                bot_id in preview_duty_bots
                or len(preview_duty_bots) < preview_duty_cap
            )
            if preview_duty_allowed:
                preview_pick = self._pick_if_adjacent(bot, state, preview_needed, reserved_items, round_number)
                if preview_pick is not None:
                    preview_duty_bots.add(bot_id)
                    return preview_pick
                preview_target = self._locked_or_best_item(
                    bot_id, pos, state, preview_needed, reserved_items,
                    items_by_id, None, round_number,
                )
                if preview_target is not None:
                    reserved_items.add(preview_target["id"])
                    item_type = preview_target["type"]
                    if preview_needed[item_type] > 0:
                        preview_needed[item_type] -= 1
                    if preview_target["id"] in preview_item_ids:
                        preview_duty_bots.add(bot_id)
                    item_pos = tuple(preview_target["position"])
                    goals = self._adjacent_walkable(item_pos, state, occupied_now, pos)
                    if goals:
                        return self._move_toward(
                            bot_id, pos, goals, state,
                            occupied_now, reserved_next, allow_occupied_goals=False,
                        )

        # --- Preview priority bots (surplus assignment) ---
        if preview_priority and not useful_inventory:
            preview_pick = self._pick_if_adjacent(bot, state, preview_needed, reserved_items, round_number)
            if preview_pick is not None:
                preview_duty_bots.add(bot_id)
                return preview_pick
            preview_target = self._locked_or_best_item(
                bot_id, pos, state, preview_needed, reserved_items,
                items_by_id, assigned_item_id, round_number,
            )
            if preview_target is not None:
                reserved_items.add(preview_target["id"])
                item_type = preview_target["type"]
                if preview_needed[item_type] > 0:
                    preview_needed[item_type] -= 1
                if preview_target["id"] in preview_item_ids:
                    preview_duty_bots.add(bot_id)
                item_pos = tuple(preview_target["position"])
                goals = self._adjacent_walkable(item_pos, state, occupied_now, pos)
                if goals:
                    return self._move_toward(
                        bot_id, pos, goals, state,
                        occupied_now, reserved_next, allow_occupied_goals=False,
                    )

        # --- Pick adjacent needed item ---
        pick = self._pick_if_adjacent(bot, state, needed, reserved_items, round_number)
        if pick is not None:
            return pick

        # --- Deliver (with optional detour batching) ---
        if useful_inventory:
            if round_number <= 250 and len(inventory) < 3:
                detour = self._delivery_detour_action(
                    bot_id, pos, state, needed, drop_off,
                    occupied_now, reserved_items, reserved_next,
                    items_by_id, assigned_item_id, round_number,
                )
                if detour is not None:
                    return detour

            # Delivery pipeline: leader goes to dropoff, others stage nearby
            if bot_id in dropoff_queue_ids and bot_id != dropoff_queue_leader:
                staged = self._stage_near_dropoff(
                    bot_id, pos, drop_off, state, occupied_now, reserved_next,
                )
                if staged is not None:
                    return staged
            if dropoff_queue_ids and bot_id not in dropoff_queue_ids:
                staged = self._stage_near_dropoff(
                    bot_id, pos, drop_off, state, occupied_now, reserved_next,
                )
                if staged is not None:
                    return staged
            self.bot_targets.pop(bot_id, None)
            return self._move_toward(
                bot_id, pos, {drop_off}, state,
                occupied_now, reserved_next,
                allow_occupied_goals=True, relax_reservation_if_blocked=True,
            )

        # --- Full inventory, nothing useful: wait ---
        if len(inventory) >= 3:
            self.bot_targets.pop(bot_id, None)
            return self._wait_or_nudge(bot_id, pos, state, occupied_now, reserved_next)

        # --- Go pick an item ---
        target_item = self._locked_or_best_item(
            bot_id, pos, state, needed, reserved_items,
            items_by_id, assigned_item_id, round_number,
        )
        if target_item is None:
            self.bot_targets.pop(bot_id, None)
            staging = self._stage_toward_aisle_center(
                bot_id, pos, state, occupied_now, reserved_next,
            )
            if staging is not None:
                return staging
            return self._wait_or_nudge(bot_id, pos, state, occupied_now, reserved_next)

        reserved_items.add(target_item["id"])
        item_type = target_item["type"]
        if needed[item_type] > 0:
            needed[item_type] -= 1

        item_pos = tuple(target_item["position"])
        goals = self._adjacent_walkable(item_pos, state, occupied_now, pos)
        if not goals:
            return self._wait_or_nudge(bot_id, pos, state, occupied_now, reserved_next)

        return self._move_toward(
            bot_id, pos, goals, state,
            occupied_now, reserved_next, allow_occupied_goals=False,
        )

    # -------------------------------------------------------------------
    # Item targeting (IMPROVED: uses BFS distance)
    # -------------------------------------------------------------------

    def _locked_or_best_item(
        self,
        bot_id: int,
        pos: tuple[int, int],
        state: dict,
        needed: Counter,
        reserved_items: set[str],
        items_by_id: dict[str, dict],
        assigned_item_id: Optional[str],
        round_number: int,
    ) -> Optional[dict]:
        if assigned_item_id:
            assigned = items_by_id.get(assigned_item_id)
            if (
                assigned
                and assigned_item_id not in reserved_items
                and not self._item_pick_blocked(assigned_item_id, round_number)
                and needed[assigned["type"]] > 0
            ):
                self.bot_targets[bot_id] = assigned_item_id
                return assigned

        locked_item_id = self.bot_targets.get(bot_id)
        if locked_item_id:
            locked_item = items_by_id.get(locked_item_id)
            if (
                locked_item
                and locked_item_id not in reserved_items
                and not self._item_pick_blocked(locked_item_id, round_number)
                and needed[locked_item["type"]] > 0
            ):
                return locked_item
            self.bot_targets.pop(bot_id, None)

        locked_by_others = {
            item_id for other_bot_id, item_id in self.bot_targets.items()
            if other_bot_id != bot_id
        }
        chosen = self._select_target_item(
            pos, state, needed, reserved_items | locked_by_others, round_number,
        )
        if chosen is not None:
            self.bot_targets[bot_id] = chosen["id"]
        return chosen

    def _select_target_item(
        self,
        pos: tuple[int, int],
        state: dict,
        needed: Counter,
        reserved_items: set[str],
        round_number: int,
    ) -> Optional[dict]:
        best_item = None
        best_dist = 9999
        for item in state["items"]:
            if item["id"] in reserved_items:
                continue
            if self._item_pick_blocked(item["id"], round_number):
                continue
            if needed[item["type"]] <= 0:
                continue
            # KEY CHANGE: BFS distance instead of Manhattan
            dist = self._bfs_distance(pos, tuple(item["position"]), state)
            if dist < best_dist:
                best_dist = dist
                best_item = item
        return best_item

    def _pick_if_adjacent(
        self,
        bot: dict,
        state: dict,
        needed: Counter,
        reserved_items: set[str],
        round_number: int,
    ) -> Optional[dict]:
        pos = tuple(bot["position"])
        if len(bot["inventory"]) >= 3:
            return None
        candidates: list[dict] = []
        for item in state["items"]:
            if item["id"] in reserved_items:
                continue
            if self._item_pick_blocked(item["id"], round_number):
                continue
            if needed[item["type"]] <= 0:
                continue
            if self._manhattan(pos, tuple(item["position"])) == 1:
                candidates.append(item)
        if not candidates:
            return None
        chosen = candidates[0]
        self.bot_targets.pop(bot["id"], None)
        reserved_items.add(chosen["id"])
        needed[chosen["type"]] -= 1
        return {"bot": bot["id"], "action": "pick_up", "item_id": chosen["id"]}

    # -------------------------------------------------------------------
    # Delivery helpers
    # -------------------------------------------------------------------

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
        assigned_item_id: Optional[str],
        round_number: int,
    ) -> Optional[dict]:
        if not assigned_item_id:
            return None
        item = items_by_id.get(assigned_item_id)
        if item is None:
            return None
        if assigned_item_id in reserved_items:
            return None
        if self._item_pick_blocked(assigned_item_id, round_number):
            return None
        item_type = item["type"]
        if needed[item_type] <= 0:
            return None
        item_pos = tuple(item["position"])
        if not self._is_near_delivery_path(pos, drop_off, item_pos):
            return None
        if self._manhattan(pos, item_pos) == 1:
            reserved_items.add(assigned_item_id)
            needed[item_type] -= 1
            self.bot_targets.pop(bot_id, None)
            return {"bot": bot_id, "action": "pick_up", "item_id": assigned_item_id}
        goals = self._adjacent_walkable(item_pos, state, occupied_now, pos)
        if not goals:
            return None
        reserved_items.add(assigned_item_id)
        needed[item_type] -= 1
        self.bot_targets[bot_id] = assigned_item_id
        return self._move_toward(
            bot_id, pos, goals, state,
            occupied_now, reserved_next, allow_occupied_goals=False,
        )

    def _is_near_delivery_path(
        self, pos: tuple[int, int], drop_off: tuple[int, int],
        item_pos: tuple[int, int],
    ) -> bool:
        direct = self._manhattan(pos, drop_off)
        via_item = self._manhattan(pos, item_pos) + self._manhattan(item_pos, drop_off)
        return via_item <= direct + 5 and self._manhattan(pos, item_pos) <= 8

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
        return self._move_toward(
            bot_id, pos, goals, state,
            occupied_now, reserved_next, allow_occupied_goals=False,
        )

    def _allocate_delivery_slots(
        self, bots: list[dict], remaining_needed: Counter,
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

    # -------------------------------------------------------------------
    # Staging / idle movement
    # -------------------------------------------------------------------

    def _refresh_staging_candidates(self, state: dict) -> None:
        key = (self._grid_width, self._grid_height,
               tuple(sorted(self._walls)), tuple(sorted(self.shelves)))
        if key == self._staging_cache_key:
            return
        self._staging_cache_key = key
        self._staging_candidates = []
        if not self.shelves:
            return
        cx = sum(p[0] for p in self.shelves) / len(self.shelves)
        cy = sum(p[1] for p in self.shelves) / len(self.shelves)
        candidates: list[tuple[float, tuple[int, int]]] = []
        for x in range(self._grid_width):
            for y in range(self._grid_height):
                cell = (x, y)
                if cell in self._walls or cell in self.shelves:
                    continue
                d = abs(cx - x) + abs(cy - y)
                candidates.append((d, cell))
        candidates.sort(key=lambda t: t[0])
        self._staging_candidates = [cell for _, cell in candidates]

    def _stage_toward_aisle_center(
        self, bot_id: int, pos: tuple[int, int], state: dict,
        occupied_now: set[tuple[int, int]], reserved_next: set[tuple[int, int]],
    ) -> Optional[dict]:
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
            return self._move_toward(
                bot_id, pos, {cell}, state,
                occupied_now, reserved_next, allow_occupied_goals=False,
            )
        return None

    # -------------------------------------------------------------------
    # Movement
    # -------------------------------------------------------------------

    def _move_toward(
        self,
        bot_id: int,
        start: tuple[int, int],
        goals: set[tuple[int, int]],
        state: dict,
        occupied_now: set[tuple[int, int]],
        reserved_next: set[tuple[int, int]],
        allow_occupied_goals: bool,
        relax_reservation_if_blocked: bool = False,
    ) -> dict:
        blocked = (occupied_now - {start}) | reserved_next
        if allow_occupied_goals:
            blocked = blocked - goals
        step = self._bfs_first_step(start, goals, blocked)
        if step is None and relax_reservation_if_blocked:
            relaxed_blocked = occupied_now - {start}
            if allow_occupied_goals:
                relaxed_blocked = relaxed_blocked - goals
            step = self._bfs_first_step(start, goals, relaxed_blocked)
        if step is None:
            return {"bot": bot_id, "action": "wait"}
        action = self._action_from_step(start, step)
        reserved_next.add(step)
        return {"bot": bot_id, "action": action}

    def _bfs_first_step(
        self,
        start: tuple[int, int],
        goals: set[tuple[int, int]],
        blocked: set[tuple[int, int]],
    ) -> Optional[tuple[int, int]]:
        if start in goals:
            return None
        if not goals:
            return None
        q: deque[tuple[int, int]] = deque([start])
        prev: dict[tuple[int, int], Optional[tuple[int, int]]] = {start: None}
        while q:
            cur = q.popleft()
            for nxt in self._neighbors(cur):
                if nxt in prev:
                    continue
                nx, ny = nxt
                if not (0 <= nx < self._grid_width and 0 <= ny < self._grid_height):
                    continue
                if nxt in self._walls or nxt in self.shelves or nxt in blocked:
                    continue
                prev[nxt] = cur
                if nxt in goals:
                    return self._unwind_first_step(start, nxt, prev)
                q.append(nxt)
        return None

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

    def _adjacent_walkable(
        self,
        shelf_pos: tuple[int, int],
        state: dict,
        occupied_now: set[tuple[int, int]],
        self_pos: tuple[int, int],
    ) -> set[tuple[int, int]]:
        blocked = occupied_now - {self_pos}
        goals: set[tuple[int, int]] = set()
        for p in self._neighbors(shelf_pos):
            x, y = p
            if not (0 <= x < self._grid_width and 0 <= y < self._grid_height):
                continue
            if p in self._walls or p in self.shelves or p in blocked:
                continue
            goals.add(p)
        return goals

    # -------------------------------------------------------------------
    # Wait / nudge
    # -------------------------------------------------------------------

    def _wait_or_nudge(
        self, bot_id: int, pos: tuple[int, int], state: dict,
        occupied_now: set[tuple[int, int]], reserved_next: set[tuple[int, int]],
    ) -> dict:
        if self.wait_streak.get(bot_id, 0) >= 3:
            nudge = self._random_nudge(bot_id, pos, state, occupied_now, reserved_next)
            if nudge is not None:
                return nudge
        return {"bot": bot_id, "action": "wait"}

    def _random_nudge(
        self, bot_id: int, pos: tuple[int, int], state: dict,
        occupied_now: set[tuple[int, int]], reserved_next: set[tuple[int, int]],
    ) -> Optional[dict]:
        blocked = (occupied_now - {pos}) | reserved_next
        options: list[tuple[int, int]] = []
        for n in self._neighbors(pos):
            x, y = n
            if not (0 <= x < self._grid_width and 0 <= y < self._grid_height):
                continue
            if n in self._walls or n in self.shelves or n in blocked:
                continue
            options.append(n)
        if not options:
            return None
        step = random.choice(options)
        reserved_next.add(step)
        return {"bot": bot_id, "action": self._action_from_step(pos, step)}

    # -------------------------------------------------------------------
    # Utilities
    # -------------------------------------------------------------------

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

    @staticmethod
    def _neighbors(p: tuple[int, int]) -> list[tuple[int, int]]:
        x, y = p
        return [(x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)]

    @staticmethod
    def _manhattan(a: tuple[int, int], b: tuple[int, int]) -> int:
        return abs(a[0] - b[0]) + abs(a[1] - b[1])

    @staticmethod
    def _delivery_count(alloc: Counter) -> int:
        return int(sum(alloc.values()))


# ---------------------------------------------------------------------------
# Sanitisation / game loop
# ---------------------------------------------------------------------------

def all_wait_actions(state: dict) -> list[dict]:
    return [{"bot": b["id"], "action": "wait"} for b in state.get("bots", [])]


def sanitize_actions(state: dict, actions: list[dict]) -> list[dict]:
    by_bot: dict[int, dict] = {}
    for action in actions:
        bot_id = action.get("bot")
        name = action.get("action")
        if not isinstance(bot_id, int):
            continue
        if name not in VALID_ACTIONS:
            by_bot[bot_id] = {"bot": bot_id, "action": "wait"}
            continue
        if name == "pick_up":
            item_id = action.get("item_id")
            if isinstance(item_id, str) and item_id:
                by_bot[bot_id] = {"bot": bot_id, "action": "pick_up", "item_id": item_id}
            else:
                by_bot[bot_id] = {"bot": bot_id, "action": "wait"}
            continue
        by_bot[bot_id] = {"bot": bot_id, "action": name}

    safe: list[dict] = []
    for bot in state.get("bots", []):
        bot_id = bot["id"]
        safe.append(by_bot.get(bot_id, {"bot": bot_id, "action": "wait"}))
    return safe


async def main():
    bot = HardBot()
    logger = RunLogger(TOKEN_CLAIMS)
    expired, exp_dt = token_is_expired(TOKEN_CLAIMS)
    if expired:
        raise SystemExit(
            f"Token expired at {exp_dt.isoformat()} UTC. "
            "Click Play to get a fresh token and update .env."
        )
    print("Connecting to Grocery Bot server (Hard v2)...", flush=True)
    try:
        async with websockets.connect(WS_URL) as ws:
            print("Connected. Running game loop...", flush=True)
            while True:
                msg = json.loads(await ws.recv())
                if msg.get("type") == "game_over":
                    summary = logger.finish(msg)
                    print("Game over:", msg)
                    print(
                        "Run logged:",
                        {
                            "history": str(RUN_HISTORY_CSV),
                            "memory": str(MEMORY_JSON),
                            "notes": str(MEMORY_MD),
                            "replay": str(LOG_DIR / summary["replay_file"]),
                        },
                    )
                    return
                if "round" in msg and msg["round"] % 25 == 0:
                    print(
                        f"Round {msg['round']} | score={msg.get('score', 0)}",
                        flush=True,
                    )
                logger.log_state(msg)
                round_start = time.monotonic()
                try:
                    planned = bot.decide(msg)
                except Exception as exc:
                    print(
                        f"Planner error on round {msg.get('round')}: {exc}. "
                        "Falling back to wait.",
                        flush=True,
                    )
                    planned = all_wait_actions(msg)

                if (time.monotonic() - round_start) > 1.8:
                    print(
                        f"Round {msg.get('round')} planning exceeded 1.8s. "
                        "Falling back to wait.",
                        flush=True,
                    )
                    planned = all_wait_actions(msg)

                actions = sanitize_actions(msg, planned)
                logger.log_actions(int(msg.get("round", -1)), actions)
                await ws.send(json.dumps({"actions": actions}))
    finally:
        logger.close()


asyncio.run(main())
