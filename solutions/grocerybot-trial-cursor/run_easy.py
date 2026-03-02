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


load_dotenv()
raw = (os.getenv("GROCERY_BOT_TOKEN_EASY") or "").strip()
if not raw:
    raise SystemExit("Missing GROCERY_BOT_TOKEN_EASY in .env")

BASE_DIR = Path(__file__).resolve().parent
LOG_DIR = BASE_DIR / "logs"
RUN_HISTORY_CSV = LOG_DIR / "run_history.csv"
MEMORY_JSON = LOG_DIR / "memory.json"
MEMORY_MD = LOG_DIR / "TRIAL_MEMORY.md"


def resolve_connection(input_value: str) -> tuple[str, str]:
    # Accept either:
    # 1) raw JWT token
    # 2) full websocket URL containing ?token=...
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
            {
                "event": "game_state",
                "round": state.get("round"),
                "score": state.get("score"),
                "data": state,
            }
        )

    def log_actions(self, round_number: int, actions: list[dict]) -> None:
        for action in actions:
            self.action_counts[action.get("action", "unknown")] += 1
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
            "run_id",
            "started_utc",
            "duration_s",
            "difficulty",
            "map_id",
            "map_seed",
            "team_id",
            "score",
            "rounds_used",
            "items_delivered",
            "orders_completed",
            "replay_file",
            "action_counts_json",
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
            memory = {
                "targets": {"medium_score_to_beat": 19},
                "best_scores": {},
                "run_count": 0,
                "latest_run": {},
            }

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
                "\n".join(
                    [
                        "# Grocery Bot Trial Memory",
                        "",
                        "Target: Beat Medium score **19**",
                        "",
                        "## Run Log",
                        "",
                    ]
                )
                + "\n",
                encoding="utf-8",
            )

        medium_best = memory.get("best_scores", {}).get("medium", "n/a")
        line = (
            f"- {summary['run_id']} | diff={summary['difficulty'] or 'unknown'} "
            f"| score={summary['score']} | items={summary['items_delivered']} "
            f"| orders={summary['orders_completed']} | medium_best={medium_best} "
            f"| replay={summary['replay_file']}"
        )
        with MEMORY_MD.open("a", encoding="utf-8") as fp:
            fp.write(line + "\n")


WS_URL, TOKEN = resolve_connection(raw)
TOKEN_CLAIMS = decode_token_claims(TOKEN)
VALID_ACTIONS = {"move_up", "move_down", "move_left", "move_right", "pick_up", "drop_off", "wait"}


def token_is_expired(claims: dict) -> tuple[bool, Optional[datetime]]:
    exp = claims.get("exp")
    if not isinstance(exp, int):
        return False, None
    exp_dt = datetime.fromtimestamp(exp, tz=timezone.utc)
    return datetime.now(timezone.utc) >= exp_dt, exp_dt


class TrialBot:
    def __init__(self) -> None:
        self.shelves: set[tuple[int, int]] = set()
        self.bot_targets: dict[int, str] = {}
        self.last_drop_round: dict[int, int] = {}
        self._staging_cache_key: Optional[tuple] = None
        self._staging_candidates: list[tuple[int, int]] = []
        self.wait_streak: dict[int, int] = {}
        self.last_observed_pos: dict[int, tuple[int, int]] = {}
        self.last_action: dict[int, str] = {}
        self.position_history: dict[int, deque[tuple[int, int]]] = {}
        self.lock_commit_until_round: dict[int, int] = {}
        self.last_inventory_count: dict[int, int] = {}
        self.last_pick_item: dict[int, str] = {}
        self.blocked_pick_item_until: dict[str, int] = {}
        self.successful_pick_count: dict[str, int] = {}
        self._distance_cache_key: Optional[tuple] = None
        self._distance_cache: dict[tuple[tuple[int, int], tuple[int, int]], int] = {}

    def decide(self, state: dict) -> list[dict]:
        for item in state["items"]:
            self.shelves.add(tuple(item["position"]))
        self._refresh_staging_candidates(state)

        bots = sorted(state["bots"], key=lambda b: b["id"])
        round_number = int(state.get("round", -1))
        self._update_pick_failure_state(bots, round_number)
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
        # For solo bot: allow preview pre-picking (original formula gives 0 for 1 bot)
        preview_duty_cap = max(1, min(max(0, len(bots) - 1), 3))

        # Pre-pick preview only when there is enough time left for a pickup+delivery loop.
        if sum(needed.values()) == 0:
            can_preview = any(
                self._can_start_pickup_delivery_trip(
                    pos=tuple(b["position"]),
                    state=state,
                    needed=preview_needed,
                    round_number=round_number,
                    safety_buffer=2,
                )
                for b in bots
            )
            if sum(preview_needed.values()) > 0 and can_preview:
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
        )
        actions: list[dict] = []

        for bot in bots:
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
            )
            actions.append(action)
            self.last_action[bot["id"]] = action["action"]
            if action["action"] == "pick_up" and isinstance(action.get("item_id"), str):
                self.last_pick_item[bot["id"]] = action["item_id"]
        return actions

    def _update_pick_failure_state(self, bots: list[dict], round_number: int) -> None:
        active_ids = {b["id"] for b in bots}
        for bot in bots:
            bot_id = bot["id"]
            inv_count = len(bot["inventory"])
            prev_count = self.last_inventory_count.get(bot_id)
            prev_action = self.last_action.get(bot_id)
            if prev_action == "pick_up" and prev_count is not None and inv_count <= prev_count:
                item_id = self.last_pick_item.get(bot_id)
                if item_id:
                    # Short temporary cooldown prevents immediate re-tries
                    # without permanently removing a valid shelf from consideration.
                    self.blocked_pick_item_until[item_id] = round_number + 3
                    if self.bot_targets.get(bot_id) == item_id:
                        self.bot_targets.pop(bot_id, None)
            elif prev_action == "pick_up" and prev_count is not None and inv_count > prev_count:
                item_id = self.last_pick_item.get(bot_id)
                if item_id:
                    self.successful_pick_count[item_id] = self.successful_pick_count.get(item_id, 0) + 1
            self.last_inventory_count[bot_id] = inv_count

        for bot_id in list(self.last_inventory_count.keys()):
            if bot_id not in active_ids:
                self.last_inventory_count.pop(bot_id, None)
                self.last_pick_item.pop(bot_id, None)

        for item_id, until_round in list(self.blocked_pick_item_until.items()):
            if round_number > until_round:
                self.blocked_pick_item_until.pop(item_id, None)

    def _rounds_left(self, state: dict, round_number: int) -> int:
        max_rounds = int(state.get("max_rounds", 300))
        return max(0, (max_rounds - 1) - round_number)

    def _min_pickup_delivery_trip_cost(
        self,
        pos: tuple[int, int],
        state: dict,
        needed: Counter,
        round_number: int,
        reserved_items: Optional[set[str]] = None,
    ) -> Optional[int]:
        if sum(needed.values()) <= 0:
            return 0

        self._refresh_distance_cache(state)
        drop_off = tuple(state["drop_off"])
        reserved = reserved_items or set()
        best_trip: Optional[int] = None

        for item in state["items"]:
            item_id = item["id"]
            if item_id in reserved:
                continue
            if self._item_pick_temporarily_blocked(item_id, round_number):
                continue
            if needed[item["type"]] <= 0:
                continue

            goals = self._walkable_adjacent_static(tuple(item["position"]), state)
            if not goals:
                continue
            to_item = self._distance_to_any_goal(pos, goals, state)
            if to_item is None:
                continue

            to_drop: Optional[int] = None
            for g in goals:
                d = self._distance_between_cells(g, drop_off, state)
                if d is None:
                    continue
                if to_drop is None or d < to_drop:
                    to_drop = d
            if to_drop is None:
                continue

            # move to pickup cell + pick + move to drop-off + drop
            trip_cost = to_item + 1 + to_drop + 1
            if best_trip is None or trip_cost < best_trip:
                best_trip = trip_cost

        return best_trip

    def _can_start_pickup_delivery_trip(
        self,
        pos: tuple[int, int],
        state: dict,
        needed: Counter,
        round_number: int,
        safety_buffer: int = 0,
        reserved_items: Optional[set[str]] = None,
    ) -> bool:
        trip_cost = self._min_pickup_delivery_trip_cost(
            pos=pos,
            state=state,
            needed=needed,
            round_number=round_number,
            reserved_items=reserved_items,
        )
        if trip_cost is None:
            return False
        return trip_cost + safety_buffer <= self._rounds_left(state, round_number)

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
            hist = self.position_history.setdefault(bot_id, deque(maxlen=12))
            hist.append(pos)

        for bot_id in list(self.wait_streak.keys()):
            if bot_id not in active_ids:
                self.wait_streak.pop(bot_id, None)
                self.last_observed_pos.pop(bot_id, None)
                self.last_action.pop(bot_id, None)
                self.position_history.pop(bot_id, None)
                self.lock_commit_until_round.pop(bot_id, None)
                self.last_pick_item.pop(bot_id, None)
                self.last_inventory_count.pop(bot_id, None)

    def _dropoff_clearance_bots(
        self, bots: list[dict], drop_off: tuple[int, int], delivery_alloc: dict[int, Counter]
    ) -> set[int]:
        waiting_deliveries = any(
            tuple(b["position"]) != drop_off
            and self._delivery_count(delivery_alloc.get(b["id"], Counter())) > 0
            for b in bots
        )
        if not waiting_deliveries:
            return set()
        return {
            b["id"]
            for b in bots
            if tuple(b["position"]) == drop_off
            and self._delivery_count(delivery_alloc.get(b["id"], Counter())) == 0
        }

    def _select_dropoff_queue_leader(
        self, bots: list[dict], drop_off: tuple[int, int], delivery_alloc: dict[int, Counter]
    ) -> set[int]:
        deliverers = [
            b
            for b in bots
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
        return {b["id"] for b in ranked[:2]}

    def _select_dropoff_queue_primary(
        self, queue_ids: set[int], bots: list[dict], drop_off: tuple[int, int]
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
            key=lambda b: (
                self._manhattan(tuple(b["position"]), drop_off),
                b["id"],
            ),
        )
        return leader["id"]

    def _get_order_by_status(self, state: dict, status: str) -> Optional[dict]:
        return next((o for o in state["orders"] if o.get("status") == status), None)

    def _preview_item_ids(self, items: list[dict], preview_needed: Counter) -> set[str]:
        ids: set[str] = set()
        if sum(preview_needed.values()) <= 0:
            return ids
        for item in items:
            if preview_needed[item["type"]] > 0:
                ids.add(item["id"])
        return ids

    def _current_preview_duty_bots(self, preview_item_ids: set[str], bots: list[dict]) -> set[int]:
        duty: set[int] = set()
        if not preview_item_ids:
            return duty
        bot_ids = {b["id"] for b in bots}
        for bot_id, target_item_id in self.bot_targets.items():
            if bot_id in bot_ids and target_item_id in preview_item_ids:
                duty.add(bot_id)
        return duty

    def _refresh_staging_candidates(self, state: dict) -> None:
        width = state["grid"]["width"]
        height = state["grid"]["height"]
        walls = {tuple(w) for w in state["grid"]["walls"]}
        key = (width, height, tuple(sorted(walls)), tuple(sorted(self.shelves)))
        if key == self._staging_cache_key:
            return

        self._staging_cache_key = key
        self._staging_candidates = []
        if not self.shelves:
            return

        cx = sum(p[0] for p in self.shelves) / len(self.shelves)
        cy = sum(p[1] for p in self.shelves) / len(self.shelves)
        candidates: list[tuple[float, tuple[int, int]]] = []
        for x in range(width):
            for y in range(height):
                cell = (x, y)
                if cell in walls or cell in self.shelves:
                    continue
                d = abs(cx - x) + abs(cy - y)
                candidates.append((d, cell))
        candidates.sort(key=lambda t: t[0])
        self._staging_candidates = [cell for _, cell in candidates]

    def _required_minus_delivered(self, order: Optional[dict]) -> Counter:
        if order is None:
            return Counter()
        return Counter(order["items_required"]) - Counter(order["items_delivered"])

    def _needed_counts_for_order(self, order: Optional[dict], bots: list[dict]) -> Counter:
        if order is None:
            return Counter()

        needed = self._required_minus_delivered(order)

        # Reserve already-carried items so empty bots don't over-chase.
        carried = Counter()
        for bot in bots:
            for item_type in bot["inventory"]:
                carried[item_type] += 1
        for item_type, count in carried.items():
            if needed[item_type] > 0:
                needed[item_type] = max(0, needed[item_type] - count)
        return needed

    def _build_greedy_assignments(
        self,
        bots: list[dict],
        items: list[dict],
        needed: Counter,
        clear_dropoff_ids: set[int],
        delivery_alloc: dict[int, Counter],
    ) -> dict[int, str]:
        assignments: dict[int, str] = {}
        needed_left = Counter(needed)

        # Count items locked by each bot so we only subtract OTHER bots' locks
        # when building candidates for a given bot.
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
            inv_len = len(bot["inventory"])
            if inv_len >= 3:
                continue
            # Compute per-bot needed_left: only subtract locks held by OTHER bots.
            bot_needed_left = Counter(needed_left)
            for other_bot_id, item_type in lock_type_by_bot.items():
                if other_bot_id == bot["id"]:
                    continue
                if bot_needed_left[item_type] > 0:
                    bot_needed_left[item_type] -= 1
            useful_delivery = self._delivery_count(delivery_alloc.get(bot["id"], Counter())) > 0
            for item in items:
                if bot_needed_left[item["type"]] <= 0:
                    continue
                dist = self._manhattan(tuple(bot["position"]), tuple(item["position"]))
                # Delivery bots with free slots may still batch-pick, but bias to nearby items.
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
    ) -> dict:
        bot_id = bot["id"]
        pos = tuple(bot["position"])
        inventory = bot["inventory"]
        useful_inventory = self._delivery_count(useful_delivery) > 0
        has_non_useful_inventory = bool(inventory) and not useful_inventory
        rounds_left = self._rounds_left(state, round_number)

        if useful_inventory and pos == drop_off:
            if self.last_drop_round.get(bot_id) == round_number - 1:
                return self._wait_or_nudge(
                    bot_id=bot_id,
                    pos=pos,
                    state=state,
                    occupied_now=occupied_now,
                    reserved_next=reserved_next,
                )
            self.bot_targets.pop(bot_id, None)
            self.lock_commit_until_round.pop(bot_id, None)
            self.last_drop_round[bot_id] = round_number
            return {"bot": bot_id, "action": "drop_off"}

        # If this bot is idling on drop-off while others need to deliver, clear the cell.
        if bot_id in clear_dropoff_ids:
            evac_goals = self._neighbors(drop_off)
            return self._move_toward(
                bot_id=bot_id,
                start=pos,
                goals=set(evac_goals),
                state=state,
                occupied_now=occupied_now,
                reserved_next=reserved_next,
                allow_occupied_goals=False,
            )

        if rounds_left <= 0 and not useful_inventory:
            self.bot_targets.pop(bot_id, None)
            self.lock_commit_until_round.pop(bot_id, None)
            return {"bot": bot_id, "action": "wait"}

        # End-game cutoff: do not start trips that cannot finish with a drop-off.
        if not useful_inventory and sum(needed.values()) > 0:
            if not self._can_start_pickup_delivery_trip(
                pos=pos,
                state=state,
                needed=needed,
                round_number=round_number,
                safety_buffer=0,
                reserved_items=reserved_items,
            ):
                self.bot_targets.pop(bot_id, None)
                self.lock_commit_until_round.pop(bot_id, None)
                # Pre-position toward likely next pickups instead of idling on drop-off.
                preposition_item = self._select_target_item(
                    bot_id=bot_id,
                    round_number=round_number,
                    pos=pos,
                    state=state,
                    needed=needed if sum(needed.values()) > 0 else preview_needed,
                    reserved_items=set(),
                )
                if preposition_item is not None:
                    goals = self._adjacent_walkable(
                        tuple(preposition_item["position"]),
                        state,
                        occupied_now,
                        pos,
                    )
                    if goals:
                        return self._move_toward(
                            bot_id=bot_id,
                            start=pos,
                            goals=goals,
                            state=state,
                            occupied_now=occupied_now,
                            reserved_next=reserved_next,
                            allow_occupied_goals=False,
                        )
                staging = self._stage_toward_aisle_center(
                    bot_id=bot_id,
                    pos=pos,
                    state=state,
                    occupied_now=occupied_now,
                    reserved_next=reserved_next,
                )
                if staging is not None:
                    return staging
                return self._wait_or_nudge(
                    bot_id=bot_id,
                    pos=pos,
                    state=state,
                    occupied_now=occupied_now,
                    reserved_next=reserved_next,
                )

        if has_non_useful_inventory and len(inventory) >= 3:
            # Carrying a full preview/non-useful bag: stage next to drop-off for fast flip.
            self.bot_targets.pop(bot_id, None)
            staging_goals = self._adjacent_walkable(drop_off, state, occupied_now, pos)
            if staging_goals:
                return self._move_toward(
                    bot_id=bot_id,
                    start=pos,
                    goals=staging_goals,
                    state=state,
                    occupied_now=occupied_now,
                    reserved_next=reserved_next,
                    allow_occupied_goals=False,
                )
            return self._wait_or_nudge(
                bot_id=bot_id,
                pos=pos,
                state=state,
                occupied_now=occupied_now,
                reserved_next=reserved_next,
            )

        if has_non_useful_inventory and len(inventory) < 3:
            # Continue building preview inventory instead of idling.
            preview_trip_possible = self._can_start_pickup_delivery_trip(
                pos=pos,
                state=state,
                needed=preview_needed,
                round_number=round_number,
                safety_buffer=2,
                reserved_items=reserved_items,
            )
            preview_duty_allowed = preview_trip_possible and (
                (bot_id in preview_duty_bots) or (len(preview_duty_bots) < preview_duty_cap)
            )
            if preview_duty_allowed and sum(preview_needed.values()) > 0:
                preview_pick = self._pick_if_adjacent(
                    bot,
                    state,
                    preview_needed,
                    reserved_items,
                    round_number,
                )
                if preview_pick is not None:
                    preview_duty_bots.add(bot_id)
                    return preview_pick

                preview_target = self._locked_or_best_item(
                    bot_id=bot_id,
                    round_number=round_number,
                    pos=pos,
                    state=state,
                    needed=preview_needed,
                    reserved_items=reserved_items,
                    items_by_id=items_by_id,
                    assigned_item_id=None,
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
                            bot_id=bot_id,
                            start=pos,
                            goals=goals,
                            state=state,
                            occupied_now=occupied_now,
                            reserved_next=reserved_next,
                            allow_occupied_goals=False,
                        )

        pick = self._pick_if_adjacent(bot, state, needed, reserved_items, round_number)
        if pick is not None:
            return pick

        if (
            not inventory
            and self._is_position_oscillation(bot_id, window=7)
            and self.bot_targets.get(bot_id) in items_by_id
        ):
            # Temporary commit prevents rapid target flipping in tight corridors.
            self.lock_commit_until_round[bot_id] = max(
                self.lock_commit_until_round.get(bot_id, -1),
                round_number + 10,
            )

        if useful_inventory:
            # Solo-bot optimization: keep collecting needed items before heading
            # to drop-off. Only go to drop-off when inventory is full (3) or
            # no more needed items exist, or very late in the game.
            still_needed = sum(needed.values())
            min_trip_cost = self._min_pickup_delivery_trip_cost(
                pos=pos,
                state=state,
                needed=needed,
                round_number=round_number,
                reserved_items=reserved_items,
            )
            useful_count = self._delivery_count(useful_delivery)
            # If time is short, cash in partial useful inventory now instead of
            # chasing a third item that may block another delivery cycle.
            if (
                useful_count > 0
                and min_trip_cost is not None
                and rounds_left < (2 * min_trip_cost)
            ):
                self.bot_targets.pop(bot_id, None)
                return self._move_toward(
                    bot_id=bot_id,
                    start=pos,
                    goals={drop_off},
                    state=state,
                    occupied_now=occupied_now,
                    reserved_next=reserved_next,
                    allow_occupied_goals=True,
                    relax_reservation_if_blocked=True,
                )
            can_collect_and_deliver = (
                len(inventory) < 3
                and still_needed > 0
                and self._can_start_pickup_delivery_trip(
                    pos=pos,
                    state=state,
                    needed=needed,
                    round_number=round_number,
                    safety_buffer=0,
                    reserved_items=reserved_items,
                )
            )
            if can_collect_and_deliver:
                # Target the next needed item directly (no detour distance limit)
                target_item = self._locked_or_best_item(
                    bot_id=bot_id,
                    round_number=round_number,
                    pos=pos,
                    state=state,
                    needed=needed,
                    reserved_items=reserved_items,
                    items_by_id=items_by_id,
                    assigned_item_id=assigned_item_id,
                )
                if target_item is not None:
                    self._refresh_distance_cache(state)
                    active_static_goals = self._walkable_adjacent_static(
                        tuple(target_item["position"]),
                        state,
                    )
                    dist_to_active = (
                        self._distance_to_any_goal(pos, active_static_goals, state)
                        if active_static_goals
                        else None
                    )

                    # Smart early delivery: if third useful item is too expensive,
                    # deliver two useful items now.
                    if len(inventory) == 2 and useful_count >= 2:
                        direct_drop_cost = self._distance_between_cells(pos, drop_off, state)
                        active_to_drop_cost: Optional[int] = None
                        for g in active_static_goals:
                            d = self._distance_between_cells(g, drop_off, state)
                            if d is None:
                                continue
                            if active_to_drop_cost is None or d < active_to_drop_cost:
                                active_to_drop_cost = d
                        if (
                            direct_drop_cost is not None
                            and dist_to_active is not None
                            and active_to_drop_cost is not None
                        ):
                            detour_cost = dist_to_active + active_to_drop_cost
                            if detour_cost > (1.5 * direct_drop_cost):
                                self.bot_targets.pop(bot_id, None)
                                return self._move_toward(
                                    bot_id=bot_id,
                                    start=pos,
                                    goals={drop_off},
                                    state=state,
                                    occupied_now=occupied_now,
                                    reserved_next=reserved_next,
                                    allow_occupied_goals=True,
                                    relax_reservation_if_blocked=True,
                                )

                    chosen_item = target_item

                    reserved_items.add(chosen_item["id"])
                    item_type = chosen_item["type"]
                    if chosen_item["id"] == target_item["id"]:
                        if needed[item_type] > 0:
                            needed[item_type] -= 1
                    else:
                        if preview_needed[item_type] > 0:
                            preview_needed[item_type] -= 1
                        elif needed[item_type] > 0:
                            needed[item_type] -= 1

                    item_pos = tuple(chosen_item["position"])
                    if self._manhattan(pos, item_pos) == 1:
                        self.bot_targets.pop(bot_id, None)
                        return {"bot": bot_id, "action": "pick_up", "item_id": chosen_item["id"]}
                    goals = self._adjacent_walkable(item_pos, state, occupied_now, pos)
                    if goals:
                        return self._move_toward(
                            bot_id=bot_id,
                            start=pos,
                            goals=goals,
                            state=state,
                            occupied_now=occupied_now,
                            reserved_next=reserved_next,
                            allow_occupied_goals=False,
                        )

            # Head to drop-off
            self.bot_targets.pop(bot_id, None)
            action = self._move_toward(
                bot_id=bot_id,
                start=pos,
                goals={drop_off},
                state=state,
                occupied_now=occupied_now,
                reserved_next=reserved_next,
                allow_occupied_goals=True,
                relax_reservation_if_blocked=True,
            )
            return action

        if len(inventory) >= 3:
            self.bot_targets.pop(bot_id, None)
            return self._wait_or_nudge(
                bot_id=bot_id,
                pos=pos,
                state=state,
                occupied_now=occupied_now,
                reserved_next=reserved_next,
            )

        target_item = self._locked_or_best_item(
            bot_id=bot_id,
            round_number=round_number,
            pos=pos,
            state=state,
            needed=needed,
            reserved_items=reserved_items,
            items_by_id=items_by_id,
            assigned_item_id=assigned_item_id,
        )
        if target_item is None:
            self.bot_targets.pop(bot_id, None)
            staging = self._stage_toward_aisle_center(
                bot_id=bot_id,
                pos=pos,
                state=state,
                occupied_now=occupied_now,
                reserved_next=reserved_next,
            )
            if staging is not None:
                return staging
            return self._wait_or_nudge(
                bot_id=bot_id,
                pos=pos,
                state=state,
                occupied_now=occupied_now,
                reserved_next=reserved_next,
            )

        reserved_items.add(target_item["id"])
        item_type = target_item["type"]
        if needed[item_type] > 0:
            needed[item_type] -= 1

        item_pos = tuple(target_item["position"])
        goals = self._adjacent_walkable(item_pos, state, occupied_now, pos)
        if not goals:
            return self._wait_or_nudge(
                bot_id=bot_id,
                pos=pos,
                state=state,
                occupied_now=occupied_now,
                reserved_next=reserved_next,
            )

        return self._move_toward(
            bot_id=bot_id,
            start=pos,
            goals=goals,
            state=state,
            occupied_now=occupied_now,
            reserved_next=reserved_next,
            allow_occupied_goals=False,
        )

    def _locked_or_best_item(
        self,
        bot_id: int,
        round_number: int,
        pos: tuple[int, int],
        state: dict,
        needed: Counter,
        reserved_items: set[str],
        items_by_id: dict[str, dict],
        assigned_item_id: Optional[str],
    ) -> Optional[dict]:
        # Lock-first policy for stability: an existing valid lock is never
        # replaced by round-by-round assignment churn.
        locked_item_id = self.bot_targets.get(bot_id)
        if locked_item_id:
            locked_item = items_by_id.get(locked_item_id)
            if (
                locked_item
                and locked_item_id not in reserved_items
                and not self._item_pick_temporarily_blocked(locked_item_id, round_number)
                and needed[locked_item["type"]] > 0
            ):
                return locked_item
            self.bot_targets.pop(bot_id, None)

        commit_until = self.lock_commit_until_round.get(bot_id, -1)
        if round_number > commit_until:
            self.lock_commit_until_round.pop(bot_id, None)

        # Only use assignment hint when no valid lock exists.
        if assigned_item_id:
            assigned = items_by_id.get(assigned_item_id)
            if (
                assigned
                and assigned_item_id not in reserved_items
                and not self._item_pick_temporarily_blocked(assigned_item_id, round_number)
                and needed[assigned["type"]] > 0
            ):
                self.bot_targets[bot_id] = assigned_item_id
                return assigned

        locked_by_others = {
            item_id
            for other_bot_id, item_id in self.bot_targets.items()
            if other_bot_id != bot_id
        }
        chosen = self._select_target_item(
            bot_id=bot_id,
            round_number=round_number,
            pos=pos,
            state=state,
            needed=needed,
            reserved_items=reserved_items | locked_by_others,
        )
        if chosen is not None:
            self.bot_targets[bot_id] = chosen["id"]
        return chosen

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
            if self._item_pick_temporarily_blocked(item["id"], round_number):
                continue
            if needed[item["type"]] <= 0:
                continue
            item_pos = tuple(item["position"])
            if self._manhattan(pos, item_pos) == 1:
                candidates.append(item)

        if not candidates:
            return None

        chosen = min(
            candidates,
            key=lambda item: (self.successful_pick_count.get(item["id"], 0), item["id"]),
        )
        self.bot_targets.pop(bot["id"], None)
        self.lock_commit_until_round.pop(bot["id"], None)
        reserved_items.add(chosen["id"])
        needed[chosen["type"]] -= 1
        return {"bot": bot["id"], "action": "pick_up", "item_id": chosen["id"]}

    def _is_position_oscillation(self, bot_id: int, window: int = 7) -> bool:
        hist = self.position_history.get(bot_id)
        if not hist or len(hist) < window:
            return False
        tail = list(hist)[-window:]
        unique = len(set(tail))
        if unique < 2 or unique > 3:
            return False
        return True

    def _item_pick_temporarily_blocked(self, item_id: str, round_number: int) -> bool:
        until_round = self.blocked_pick_item_until.get(item_id)
        if until_round is None:
            return False
        return round_number <= until_round

    def _select_target_item(
        self,
        bot_id: int,
        round_number: int,
        pos: tuple[int, int],
        state: dict,
        needed: Counter,
        reserved_items: set[str],
    ) -> Optional[dict]:
        if len(state.get("bots", [])) == 1:
            solo_bot = state["bots"][0]
            if solo_bot["id"] == bot_id:
                capacity_left = max(0, 3 - len(solo_bot.get("inventory", [])))
                if capacity_left > 0:
                    solo_choice = self._select_solo_item_with_lookahead(
                        round_number=round_number,
                        pos=pos,
                        state=state,
                        needed=needed,
                        reserved_items=reserved_items,
                        capacity_left=capacity_left,
                    )
                    if solo_choice is not None:
                        return solo_choice

        self._refresh_distance_cache(state)
        best_item = None
        best_dist = 10**9
        for item in state["items"]:
            if item["id"] in reserved_items:
                continue
            if self._item_pick_temporarily_blocked(item["id"], round_number):
                continue
            if needed[item["type"]] <= 0:
                continue
            item_pos = tuple(item["position"])
            goals = self._walkable_adjacent_static(item_pos, state)
            dist = self._distance_to_any_goal(pos, goals, state) if goals else None
            if dist is None:
                continue
            dist += self.successful_pick_count.get(item["id"], 0)
            if dist < best_dist:
                best_dist = dist
                best_item = item
        return best_item

    def _select_solo_item_with_lookahead(
        self,
        round_number: int,
        pos: tuple[int, int],
        state: dict,
        needed: Counter,
        reserved_items: set[str],
        capacity_left: int,
    ) -> Optional[dict]:
        if capacity_left <= 0 or sum(needed.values()) <= 0:
            return None

        self._refresh_distance_cache(state)
        drop_off = tuple(state["drop_off"])

        candidates: list[dict] = []
        for item in state["items"]:
            if item["id"] in reserved_items:
                continue
            if self._item_pick_temporarily_blocked(item["id"], round_number):
                continue
            if needed[item["type"]] <= 0:
                continue
            goals = self._walkable_adjacent_static(tuple(item["position"]), state)
            if not goals:
                continue
            dist_from_pos = self._distance_to_any_goal(pos, goals, state)
            if dist_from_pos is None:
                continue
            candidates.append(
                {
                    "id": item["id"],
                    "type": item["type"],
                    "item": item,
                    "goals": goals,
                    "start_dist": dist_from_pos + self.successful_pick_count.get(item["id"], 0),
                }
            )

        if not candidates:
            return None

        # Keep a compact set of nearby candidates per item type.
        per_type: dict[str, list[dict]] = {}
        for cand in candidates:
            per_type.setdefault(cand["type"], []).append(cand)
        shortlist: list[dict] = []
        for item_type, group in per_type.items():
            group.sort(key=lambda c: (c["start_dist"], c["id"]))
            needed_cap = max(1, needed[item_type])
            shortlist.extend(group[: min(len(group), needed_cap + 3)])

        if not shortlist:
            return None

        route_len = min(capacity_left, sum(needed.values()))
        if route_len <= 0:
            return None

        by_id = {cand["id"]: cand for cand in shortlist}
        ordered_ids = [cand["id"] for cand in sorted(shortlist, key=lambda c: (c["start_dist"], c["id"]))]
        best_sequence: Optional[list[str]] = None
        best_cost = 10**9

        def evaluate(seq_ids: list[str]) -> None:
            nonlocal best_sequence, best_cost
            cost = self._sequence_route_cost(
                start=pos,
                sequence_ids=seq_ids,
                candidates_by_id=by_id,
                drop_off=drop_off,
                state=state,
            )
            if cost is None:
                return
            if cost < best_cost:
                best_cost = cost
                best_sequence = list(seq_ids)
                return
            if cost == best_cost and best_sequence is not None:
                if tuple(seq_ids) < tuple(best_sequence):
                    best_sequence = list(seq_ids)

        def search(target_len: int, remaining: Counter, used_ids: set[str], seq_ids: list[str]) -> None:
            if len(seq_ids) == target_len:
                evaluate(seq_ids)
                return
            for item_id in ordered_ids:
                if item_id in used_ids:
                    continue
                cand = by_id[item_id]
                item_type = cand["type"]
                if remaining[item_type] <= 0:
                    continue
                used_ids.add(item_id)
                seq_ids.append(item_id)
                remaining[item_type] -= 1
                search(target_len, remaining, used_ids, seq_ids)
                remaining[item_type] += 1
                seq_ids.pop()
                used_ids.remove(item_id)

        # Prefer full bag routes first; fall back to shorter routes if needed.
        for target_len in range(route_len, 0, -1):
            best_sequence = None
            best_cost = 10**9
            search(target_len, Counter(needed), set(), [])
            if best_sequence:
                first_id = best_sequence[0]
                return by_id[first_id]["item"]

        return None

    def _sequence_route_cost(
        self,
        start: tuple[int, int],
        sequence_ids: list[str],
        candidates_by_id: dict[str, dict],
        drop_off: tuple[int, int],
        state: dict,
    ) -> Optional[int]:
        costs: dict[tuple[int, int], int] = {start: 0}
        for item_id in sequence_ids:
            goals = candidates_by_id[item_id]["goals"]
            next_costs: dict[tuple[int, int], int] = {}
            for goal in goals:
                best_goal_cost: Optional[int] = None
                for cell, cell_cost in costs.items():
                    dist = self._distance_between_cells(cell, goal, state)
                    if dist is None:
                        continue
                    total = cell_cost + dist
                    if best_goal_cost is None or total < best_goal_cost:
                        best_goal_cost = total
                if best_goal_cost is not None:
                    next_costs[goal] = best_goal_cost
            if not next_costs:
                return None
            costs = next_costs

        best_total: Optional[int] = None
        for cell, cell_cost in costs.items():
            dist_to_drop = self._distance_between_cells(cell, drop_off, state)
            if dist_to_drop is None:
                continue
            total = cell_cost + dist_to_drop
            if best_total is None or total < best_total:
                best_total = total
        if best_total is None:
            return None
        return best_total + self._aisle_span_penalty(sequence_ids, candidates_by_id)

    def _aisle_span_penalty(
        self,
        sequence_ids: list[str],
        candidates_by_id: dict[str, dict],
    ) -> int:
        sides: list[int] = []
        for item_id in sequence_ids:
            item = candidates_by_id[item_id]["item"]
            x = int(item["position"][0])
            if x <= 5:
                sides.append(-1)
            elif x >= 7:
                sides.append(1)

        if len(sides) <= 1:
            return 0

        unique_sides = set(sides)
        if len(unique_sides) <= 1:
            return 0

        switches = 0
        for i in range(1, len(sides)):
            if sides[i] != sides[i - 1]:
                switches += 1

        # Base cross-aisle penalty + extra penalty for each additional aisle switch.
        return 4 + (switches * 3)

    def _refresh_distance_cache(self, state: dict) -> None:
        grid = state["grid"]
        walls = tuple(sorted(tuple(w) for w in grid["walls"]))
        shelves = tuple(sorted(self.shelves))
        key = (grid["width"], grid["height"], walls, shelves)
        if key != self._distance_cache_key:
            self._distance_cache_key = key
            self._distance_cache = {}

    def _walkable_adjacent_static(
        self,
        shelf_pos: tuple[int, int],
        state: dict,
    ) -> tuple[tuple[int, int], ...]:
        width = state["grid"]["width"]
        height = state["grid"]["height"]
        walls = {tuple(w) for w in state["grid"]["walls"]}
        cells: list[tuple[int, int]] = []
        for p in self._neighbors(shelf_pos):
            x, y = p
            if not (0 <= x < width and 0 <= y < height):
                continue
            if p in walls or p in self.shelves:
                continue
            cells.append(p)
        return tuple(cells)

    def _distance_to_any_goal(
        self,
        start: tuple[int, int],
        goals: tuple[tuple[int, int], ...],
        state: dict,
    ) -> Optional[int]:
        best: Optional[int] = None
        for goal in goals:
            dist = self._distance_between_cells(start, goal, state)
            if dist is None:
                continue
            if best is None or dist < best:
                best = dist
        return best

    def _distance_between_cells(
        self,
        a: tuple[int, int],
        b: tuple[int, int],
        state: dict,
    ) -> Optional[int]:
        if a == b:
            return 0
        left, right = (a, b) if a <= b else (b, a)
        key = (left, right)
        if key in self._distance_cache:
            return self._distance_cache[key]

        dist = self._bfs_distance(a, {b}, state)
        if dist is None:
            return None
        self._distance_cache[key] = dist
        return dist

    def _bfs_distance(
        self,
        start: tuple[int, int],
        goals: set[tuple[int, int]],
        state: dict,
    ) -> Optional[int]:
        if start in goals:
            return 0
        if not goals:
            return None

        width = state["grid"]["width"]
        height = state["grid"]["height"]
        walls = {tuple(w) for w in state["grid"]["walls"]}

        def passable(p: tuple[int, int]) -> bool:
            x, y = p
            if not (0 <= x < width and 0 <= y < height):
                return False
            if p in walls or p in self.shelves:
                return False
            return True

        q: deque[tuple[tuple[int, int], int]] = deque([(start, 0)])
        seen: set[tuple[int, int]] = {start}
        while q:
            cur, dist = q.popleft()
            for nxt in self._neighbors(cur):
                if nxt in seen:
                    continue
                if not passable(nxt):
                    continue
                if nxt in goals:
                    return dist + 1
                seen.add(nxt)
                q.append((nxt, dist + 1))
        return None

    def _has_useful_inventory(self, inventory: list[str], remaining_needed: Counter) -> bool:
        if not inventory:
            return False
        inv_counts = Counter(inventory)
        for item_type, count in inv_counts.items():
            if remaining_needed[item_type] > 0 and count > 0:
                return True
        return False

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
    ) -> Optional[dict]:
        if not assigned_item_id:
            return None
        item = items_by_id.get(assigned_item_id)
        if item is None:
            return None
        if assigned_item_id in reserved_items:
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
            bot_id=bot_id,
            start=pos,
            goals=goals,
            state=state,
            occupied_now=occupied_now,
            reserved_next=reserved_next,
            allow_occupied_goals=False,
        )

    def _is_near_delivery_path(
        self, pos: tuple[int, int], drop_off: tuple[int, int], item_pos: tuple[int, int]
    ) -> bool:
        # "On the way" heuristic: allow small detours only.
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
            bot_id=bot_id,
            start=pos,
            goals=goals,
            state=state,
            occupied_now=occupied_now,
            reserved_next=reserved_next,
            allow_occupied_goals=False,
        )

    def _stage_toward_aisle_center(
        self,
        bot_id: int,
        pos: tuple[int, int],
        state: dict,
        occupied_now: set[tuple[int, int]],
        reserved_next: set[tuple[int, int]],
    ) -> Optional[dict]:
        if not self._staging_candidates:
            return None
        blocked = (occupied_now - {pos}) | reserved_next
        candidates = self._staging_candidates
        n = len(candidates)
        best_goal: Optional[tuple[int, int]] = None
        search_span = min(20, n)
        for i in range(search_span):
            idx = (bot_id + (i * 3)) % n
            cell = candidates[idx]
            if cell == pos:
                continue
            if cell in blocked:
                continue
            best_goal = cell
            break
        if best_goal is None:
            return None

        return self._move_toward(
            bot_id=bot_id,
            start=pos,
            goals={best_goal},
            state=state,
            occupied_now=occupied_now,
            reserved_next=reserved_next,
            allow_occupied_goals=False,
        )

    def _wait_or_nudge(
        self,
        bot_id: int,
        pos: tuple[int, int],
        state: dict,
        occupied_now: set[tuple[int, int]],
        reserved_next: set[tuple[int, int]],
    ) -> dict:
        if self.wait_streak.get(bot_id, 0) >= 3:
            nudge = self._random_nudge(bot_id, pos, state, occupied_now, reserved_next)
            if nudge is not None:
                return nudge
        return {"bot": bot_id, "action": "wait"}

    def _random_nudge(
        self,
        bot_id: int,
        pos: tuple[int, int],
        state: dict,
        occupied_now: set[tuple[int, int]],
        reserved_next: set[tuple[int, int]],
    ) -> Optional[dict]:
        width = state["grid"]["width"]
        height = state["grid"]["height"]
        walls = {tuple(w) for w in state["grid"]["walls"]}
        blocked = (occupied_now - {pos}) | reserved_next

        options: list[tuple[int, int]] = []
        for n in self._neighbors(pos):
            x, y = n
            if not (0 <= x < width and 0 <= y < height):
                continue
            if n in walls or n in self.shelves or n in blocked:
                continue
            options.append(n)
        if not options:
            return None

        step = random.choice(options)
        reserved_next.add(step)
        return {"bot": bot_id, "action": self._action_from_step(pos, step)}

    @staticmethod
    def _delivery_count(alloc: Counter) -> int:
        return int(sum(alloc.values()))

    def _allocate_delivery_slots(
        self, bots: list[dict], remaining_needed: Counter
    ) -> tuple[dict[int, Counter], Counter]:
        # Lower bot IDs claim delivery slots first to avoid over-committing
        # the same needed item type across multiple bots.
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
        step = self._bfs_first_step(
            start=start,
            goals=goals,
            state=state,
            blocked=blocked,
        )
        if step is None and relax_reservation_if_blocked:
            relaxed_blocked = occupied_now - {start}
            if allow_occupied_goals:
                relaxed_blocked = relaxed_blocked - goals
            step = self._bfs_first_step(
                start=start,
                goals=goals,
                state=state,
                blocked=relaxed_blocked,
            )
        if step is None:
            return {"bot": bot_id, "action": "wait"}
        action = self._action_from_step(start, step)
        reserved_next.add(step)
        return {"bot": bot_id, "action": action}

    def _bfs_first_step(
        self,
        start: tuple[int, int],
        goals: set[tuple[int, int]],
        state: dict,
        blocked: set[tuple[int, int]],
    ) -> Optional[tuple[int, int]]:
        if start in goals:
            return None
        if not goals:
            return None

        width = state["grid"]["width"]
        height = state["grid"]["height"]
        walls = {tuple(w) for w in state["grid"]["walls"]}

        def passable(p: tuple[int, int]) -> bool:
            x, y = p
            if not (0 <= x < width and 0 <= y < height):
                return False
            if p in walls:
                return False
            if p in self.shelves:
                return False
            if p in blocked:
                return False
            return True

        q: deque[tuple[int, int]] = deque([start])
        prev: dict[tuple[int, int], Optional[tuple[int, int]]] = {start: None}

        while q:
            cur = q.popleft()
            for nxt in self._neighbors(cur):
                if nxt in prev:
                    continue
                if not passable(nxt):
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
        width = state["grid"]["width"]
        height = state["grid"]["height"]
        walls = {tuple(w) for w in state["grid"]["walls"]}
        blocked = occupied_now - {self_pos}
        goals: set[tuple[int, int]] = set()
        for p in self._neighbors(shelf_pos):
            x, y = p
            if not (0 <= x < width and 0 <= y < height):
                continue
            if p in walls or p in self.shelves or p in blocked:
                continue
            goals.add(p)
        return goals

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
    bot = TrialBot()
    logger = RunLogger(TOKEN_CLAIMS)
    expired, exp_dt = token_is_expired(TOKEN_CLAIMS)
    if expired:
        raise SystemExit(
            f"Token expired at {exp_dt.isoformat()} UTC. Click Play to get a fresh token and update .env."
        )
    print("Connecting to Grocery Bot server...", flush=True)
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
                    print(f"Round {msg['round']} | score={msg.get('score', 0)}", flush=True)
                logger.log_state(msg)
                round_start = time.monotonic()
                try:
                    planned = bot.decide(msg)
                except Exception as exc:
                    print(f"Planner error on round {msg.get('round')}: {exc}. Falling back to wait.", flush=True)
                    planned = all_wait_actions(msg)

                if (time.monotonic() - round_start) > 1.8:
                    print(
                        f"Round {msg.get('round')} planning exceeded 1.8s. Falling back to wait.",
                        flush=True,
                    )
                    planned = all_wait_actions(msg)

                actions = sanitize_actions(msg, planned)
                logger.log_actions(int(msg.get("round", -1)), actions)
                await ws.send(json.dumps({"actions": actions}))
    finally:
        logger.close()


asyncio.run(main())
