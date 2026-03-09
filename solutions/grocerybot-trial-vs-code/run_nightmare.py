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
raw = (os.getenv("GROCERY_BOT_TOKEN_NIGHTMARE") or "").strip()
if not raw:
    raise SystemExit("Missing GROCERY_BOT_TOKEN_NIGHTMARE in .env")

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
NIGHTMARE_EXPECTED_WIDTH = 30
NIGHTMARE_EXPECTED_HEIGHT = 18
NIGHTMARE_EXPECTED_ROUNDS = 500
NIGHTMARE_EXPECTED_BOTS = 20
NIGHTMARE_ACTIVE_BOT_LIMIT = 7
NIGHTMARE_EXPECTED_DROP_ZONES = 3


def nightmare_shape_summary(state: dict) -> dict[str, int]:
    grid = state.get("grid") or {}
    width = int(grid.get("width", -1))
    height = int(grid.get("height", -1))
    max_rounds = int(state.get("max_rounds", -1))
    bots = len(state.get("bots") or [])
    drop_off_zones = state.get("drop_off_zones")
    if isinstance(drop_off_zones, list):
        drop_zone_count = len(drop_off_zones)
    elif state.get("drop_off") is not None:
        drop_zone_count = 1
    else:
        drop_zone_count = 0

    return {
        "width": width,
        "height": height,
        "max_rounds": max_rounds,
        "bots": bots,
        "drop_zones": drop_zone_count,
    }


def print_nightmare_shape_check(state: dict) -> None:
    observed = nightmare_shape_summary(state)
    print(f"Nightmare map check: {observed}", flush=True)
    expected = {
        "width": NIGHTMARE_EXPECTED_WIDTH,
        "height": NIGHTMARE_EXPECTED_HEIGHT,
        "max_rounds": NIGHTMARE_EXPECTED_ROUNDS,
        "bots": NIGHTMARE_EXPECTED_BOTS,
        "drop_zones": NIGHTMARE_EXPECTED_DROP_ZONES,
    }
    mismatches = [
        f"{key}={observed[key]} (expected {expected[key]})"
        for key in expected
        if observed[key] != expected[key]
    ]
    if mismatches:
        print(
            "WARNING: received map does not match documented nightmare shape: "
            + ", ".join(mismatches),
            flush=True,
        )


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
        self.last_inventory_size: dict[int, int] = {}
        self.last_pick_item: dict[int, str] = {}
        self.pick_fail_streak: dict[str, int] = {}
        self.pick_block_until_round: dict[str, int] = {}
        self._last_score: int = 0
        self._last_score_round: int = 0
        self._parking_spots: list[tuple[int, int]] = []
        self._parking_assignments: dict[int, tuple[int, int]] = {}
        self._parking_cache_key: Optional[tuple] = None

    def decide(self, state: dict) -> list[dict]:
        for item in state["items"]:
            self.shelves.add(tuple(item["position"]))
        self._refresh_staging_candidates(state)
        self._refresh_parking_spots(state)

        round_number = int(state.get("round", -1))
        bots = sorted(state["bots"], key=lambda b: b["id"])
        controlled_bots = bots[: min(NIGHTMARE_ACTIVE_BOT_LIMIT, len(bots))]
        controlled_bot_ids = {bot["id"] for bot in controlled_bots}
        self._update_pick_retry_state(bots, round_number)
        self._update_wait_state(bots)
        items_by_id = {item["id"]: item for item in state["items"]}
        occupied_now = {tuple(b["position"]) for b in bots}
        reserved_next: set[tuple[int, int]] = set()
        reserved_items: set[str] = set()

        active_order = self._get_order_by_status(state, "active")
        active_needed_raw = self._required_minus_delivered(active_order)
        delivery_alloc, _ = self._allocate_delivery_slots(controlled_bots, active_needed_raw)
        needed = self._needed_counts_for_order(active_order, controlled_bots)
        preview_order = self._get_order_by_status(state, "preview")
        preview_needed = self._needed_counts_for_order(preview_order, controlled_bots)
        preview_item_ids = self._preview_item_ids(state["items"], preview_needed)
        preview_duty_bots = self._current_preview_duty_bots(preview_item_ids, controlled_bots)
        preview_duty_cap = min(max(0, len(controlled_bots) - 1), 6)
        current_score = int(state.get("score", 0))
        if current_score > self._last_score:
            self._last_score = current_score
            self._last_score_round = round_number
        score_stale_rounds = round_number - self._last_score_round

        # Pre-pick preview items once active needs are already in-flight/carried.
        active_remaining_needed = sum(needed.values())
        preview_remaining = sum(preview_needed.values())
        stale_pivot = (
            round_number >= 100
            and round_number < 425
            and score_stale_rounds >= 12
            and preview_remaining > 0
            and active_remaining_needed > 0
        )
        if active_remaining_needed == 0:
            if sum(preview_needed.values()) > 0:
                needed = preview_needed
        elif stale_pivot:
            needed = needed + preview_needed

        drop_off = tuple(state["drop_off"])
        drop_zones = self._drop_zones(state)
        delivery_zone_by_bot = self._assign_delivery_zones(
            bots=controlled_bots,
            delivery_alloc=delivery_alloc,
            drop_zones=drop_zones,
        )
        clear_dropoff_ids = self._dropoff_clearance_bots_multi(
            bots=controlled_bots,
            drop_zones=drop_zones,
            delivery_alloc=delivery_alloc,
            delivery_zone_by_bot=delivery_zone_by_bot,
        )
        zone_primary_by_zone = self._select_dropoff_zone_primaries(
            bots=controlled_bots,
            drop_zones=drop_zones,
            delivery_alloc=delivery_alloc,
            delivery_zone_by_bot=delivery_zone_by_bot,
        )
        assignments = self._build_greedy_assignments(
            bots=controlled_bots,
            items=state["items"],
            needed=needed,
            clear_dropoff_ids=clear_dropoff_ids,
            delivery_alloc=delivery_alloc,
            round_number=round_number,
        )
        # Idle bots just wait — keeping them stacked is better than scattering
        actions_by_id: dict[int, dict] = {
            b["id"]: {"bot": b["id"], "action": "wait"}
            for b in bots
            if b["id"] not in controlled_bot_ids
        }
        for bot_id in actions_by_id:
            self.last_action[bot_id] = "wait"
            self.last_pick_item.pop(bot_id, None)

        # Process delivery bots first so they claim path cells via reserved_next,
        # then idle bots route around them.
        delivery_bots = [
            b for b in controlled_bots if sum(delivery_alloc.get(b["id"], Counter()).values()) > 0
        ]
        non_delivery_bots = [
            b for b in controlled_bots if sum(delivery_alloc.get(b["id"], Counter()).values()) == 0
        ]

        # --- Phase 1: Process delivery bots first ---
        for bot in delivery_bots:
            action = self._decide_one(
                bot=bot,
                round_number=round_number,
                state=state,
                needed=needed,
                target_drop_off=delivery_zone_by_bot.get(bot["id"], drop_off),
                drop_zones=drop_zones,
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
                zone_primary_by_zone=zone_primary_by_zone,
            )
            actions_by_id[bot["id"]] = action
            self.last_action[bot["id"]] = action["action"]
            if action["action"] == "pick_up":
                item_id = action.get("item_id")
                if isinstance(item_id, str) and item_id:
                    self.last_pick_item[bot["id"]] = item_id
                else:
                    self.last_pick_item.pop(bot["id"], None)
            else:
                self.last_pick_item.pop(bot["id"], None)

        # --- Phase 2: Identify stuck delivery bots ---
        stuck_delivery_info: dict[int, dict] = {}
        for bot in delivery_bots:
            bot_id = bot["id"]
            if (
                actions_by_id[bot_id]["action"] == "wait"
                and self.wait_streak.get(bot_id, 0) >= 1
                and self._delivery_count(delivery_alloc.get(bot_id, Counter())) > 0
            ):
                stuck_delivery_info[bot_id] = {
                    "pos": tuple(bot["position"]),
                    "target": delivery_zone_by_bot.get(bot_id, drop_off),
                }

        # --- Phase 3: Process non-delivery bots with yield awareness ---
        yielded_from: set[tuple[int, int]] = set()
        for bot in non_delivery_bots:
            bot_id = bot["id"]
            pos = tuple(bot["position"])
            yield_action = self._yield_for_delivery(
                bot_id=bot_id,
                pos=pos,
                stuck_delivery_info=stuck_delivery_info,
                state=state,
                occupied_now=occupied_now,
                reserved_next=reserved_next,
            )
            if yield_action is not None:
                yielded_from.add(pos)
                action = yield_action
            else:
                action = self._decide_one(
                    bot=bot,
                    round_number=round_number,
                    state=state,
                    needed=needed,
                    target_drop_off=delivery_zone_by_bot.get(bot["id"], drop_off),
                    drop_zones=drop_zones,
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
                    zone_primary_by_zone=zone_primary_by_zone,
                )
            actions_by_id[bot["id"]] = action
            self.last_action[bot["id"]] = action["action"]
            if action["action"] == "pick_up":
                item_id = action.get("item_id")
                if isinstance(item_id, str) and item_id:
                    self.last_pick_item[bot["id"]] = item_id
                else:
                    self.last_pick_item.pop(bot["id"], None)
            else:
                self.last_pick_item.pop(bot["id"], None)

        # --- Phase 4: Re-plan stuck delivery bots that now have cleared paths ---
        if yielded_from:
            replan_occupied = occupied_now - yielded_from
            for bot in delivery_bots:
                bot_id = bot["id"]
                if bot_id not in stuck_delivery_info:
                    continue
                pos = tuple(bot["position"])
                if not any(self._manhattan(pos, yc) <= 1 for yc in yielded_from):
                    continue
                action = self._move_toward(
                    bot_id=bot_id,
                    start=pos,
                    goals={stuck_delivery_info[bot_id]["target"]},
                    state=state,
                    occupied_now=replan_occupied,
                    reserved_next=reserved_next,
                    allow_occupied_goals=True,
                    relax_reservation_if_blocked=True,
                )
                if action["action"] != "wait":
                    actions_by_id[bot_id] = action
                    self.last_action[bot_id] = action["action"]
                    self.last_pick_item.pop(bot_id, None)

        return [actions_by_id[b["id"]] for b in bots]

    def _refresh_parking_spots(self, state: dict) -> None:
        width = state["grid"]["width"]
        height = state["grid"]["height"]
        walls = {tuple(w) for w in state["grid"]["walls"]}
        key = (width, height, tuple(sorted(walls)), tuple(sorted(self.shelves)))
        if key == self._parking_cache_key:
            return
        self._parking_cache_key = key

        drop_zones = set()
        for z in state.get("drop_off_zones", []):
            drop_zones.add((int(z[0]), int(z[1])))
        if state.get("drop_off"):
            drop_zones.add((int(state["drop_off"][0]), int(state["drop_off"][1])))

        # Score cells: prefer dead-ends (1 neighbor) and corners, far from drop zones
        scored: list[tuple[float, tuple[int, int]]] = []
        for x in range(width):
            for y in range(height):
                cell = (x, y)
                if cell in walls or cell in self.shelves or cell in drop_zones:
                    continue
                walkable_neighbors = 0
                for nx, ny in [(x+1,y),(x-1,y),(x,y+1),(x,y-1)]:
                    if 0 <= nx < width and 0 <= ny < height:
                        if (nx, ny) not in walls and (nx, ny) not in self.shelves:
                            walkable_neighbors += 1
                # Dead-ends (1 neighbor) are best, then 2-neighbor corridors
                # Add distance from nearest drop zone as tiebreaker (farther = better)
                min_drop_dist = min(
                    (abs(x - dz[0]) + abs(y - dz[1]) for dz in drop_zones), default=0
                )
                # Lower score = better parking spot
                score = walkable_neighbors * 100 - min_drop_dist
                scored.append((score, cell))
        scored.sort(key=lambda t: (t[0], t[1][0], t[1][1]))
        self._parking_spots = [cell for _, cell in scored]

    def _assign_parking(
        self, idle_bots: list[dict], occupied_now: set[tuple[int, int]]
    ) -> None:
        # Only reassign if we haven't assigned yet or a bot reached its spot
        if self._parking_assignments and all(
            tuple(b["position"]) == self._parking_assignments.get(b["id"], tuple(b["position"]))
            for b in idle_bots
        ):
            return
        used: set[tuple[int, int]] = set(self._parking_assignments.values())
        for bot in idle_bots:
            bot_id = bot["id"]
            pos = tuple(bot["position"])
            # Keep existing assignment if bot hasn't reached it yet
            if bot_id in self._parking_assignments:
                target = self._parking_assignments[bot_id]
                if pos != target:
                    used.add(target)
                    continue
            # Assign nearest available parking spot
            for spot in self._parking_spots:
                if spot in used and spot != pos:
                    continue
                self._parking_assignments[bot_id] = spot
                used.add(spot)
                break

    def _park_idle_bot(
        self,
        bot: dict,
        state: dict,
        occupied_now: set[tuple[int, int]],
        reserved_next: set[tuple[int, int]],
    ) -> dict:
        bot_id = bot["id"]
        pos = tuple(bot["position"])
        target = self._parking_assignments.get(bot_id)
        if target is None or pos == target:
            return {"bot": bot_id, "action": "wait"}
        return self._move_toward(
            bot_id=bot_id,
            start=pos,
            goals={target},
            state=state,
            occupied_now=occupied_now,
            reserved_next=reserved_next,
            allow_occupied_goals=False,
            relax_reservation_if_blocked=True,
        )

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

    def _drop_zones(self, state: dict) -> list[tuple[int, int]]:
        zones: list[tuple[int, int]] = []
        raw_zones = state.get("drop_off_zones")
        if isinstance(raw_zones, list):
            for zone in raw_zones:
                if isinstance(zone, (list, tuple)) and len(zone) == 2:
                    zones.append((int(zone[0]), int(zone[1])))
        if not zones and state.get("drop_off") is not None:
            drop_off = state["drop_off"]
            if isinstance(drop_off, (list, tuple)) and len(drop_off) == 2:
                zones.append((int(drop_off[0]), int(drop_off[1])))

        seen: set[tuple[int, int]] = set()
        unique: list[tuple[int, int]] = []
        for zone in zones:
            if zone in seen:
                continue
            seen.add(zone)
            unique.append(zone)
        return unique

    def _nearest_drop_zone(
        self,
        pos: tuple[int, int],
        drop_zones: list[tuple[int, int]],
        fallback: tuple[int, int],
    ) -> tuple[int, int]:
        if not drop_zones:
            return fallback
        return min(
            drop_zones,
            key=lambda zone: (
                self._manhattan(pos, zone),
                zone[0],
                zone[1],
            ),
        )

    def _assign_delivery_zones(
        self,
        bots: list[dict],
        delivery_alloc: dict[int, Counter],
        drop_zones: list[tuple[int, int]],
    ) -> dict[int, tuple[int, int]]:
        if not drop_zones:
            return {}

        deliverers = [
            b
            for b in bots
            if self._delivery_count(delivery_alloc.get(b["id"], Counter())) > 0
        ]
        if not deliverers:
            return {}

        assignments: dict[int, tuple[int, int]] = {}
        zone_load: Counter = Counter()

        ranked_deliverers = sorted(
            deliverers,
            key=lambda b: (
                min(self._manhattan(tuple(b["position"]), zone) for zone in drop_zones),
                -self._delivery_count(delivery_alloc.get(b["id"], Counter())),
                b["id"],
            ),
        )

        for bot in ranked_deliverers:
            bot_id = bot["id"]
            pos = tuple(bot["position"])
            if pos in drop_zones:
                chosen_zone = pos
            else:
                chosen_zone = min(
                    drop_zones,
                    key=lambda zone: (
                        self._manhattan(pos, zone) + (zone_load[zone] * 4),
                        zone_load[zone],
                        zone[0],
                        zone[1],
                    ),
                )
            assignments[bot_id] = chosen_zone
            zone_load[chosen_zone] += 1
        return assignments

    def _dropoff_clearance_bots_multi(
        self,
        bots: list[dict],
        drop_zones: list[tuple[int, int]],
        delivery_alloc: dict[int, Counter],
        delivery_zone_by_bot: dict[int, tuple[int, int]],
    ) -> set[int]:
        if not drop_zones:
            return set()

        zone_waiting: Counter = Counter()
        for bot in bots:
            bot_id = bot["id"]
            if self._delivery_count(delivery_alloc.get(bot_id, Counter())) <= 0:
                continue
            target_zone = delivery_zone_by_bot.get(bot_id)
            if target_zone is None:
                continue
            if tuple(bot["position"]) != target_zone:
                zone_waiting[target_zone] += 1

        if not zone_waiting:
            return set()

        zone_set = set(drop_zones)
        clear_ids: set[int] = set()
        for bot in bots:
            bot_id = bot["id"]
            pos = tuple(bot["position"])
            if pos not in zone_set:
                continue
            if zone_waiting.get(pos, 0) <= 0:
                continue
            if self._delivery_count(delivery_alloc.get(bot_id, Counter())) == 0:
                clear_ids.add(bot_id)
        return clear_ids

    def _select_dropoff_zone_primaries(
        self,
        bots: list[dict],
        drop_zones: list[tuple[int, int]],
        delivery_alloc: dict[int, Counter],
        delivery_zone_by_bot: dict[int, tuple[int, int]],
    ) -> dict[tuple[int, int], int]:
        primaries: dict[tuple[int, int], int] = {}
        if not drop_zones:
            return primaries

        for zone in drop_zones:
            candidates = [
                b
                for b in bots
                if self._delivery_count(delivery_alloc.get(b["id"], Counter())) > 0
                and delivery_zone_by_bot.get(b["id"]) == zone
            ]
            if not candidates:
                continue

            on_zone = [b for b in candidates if tuple(b["position"]) == zone]
            if on_zone:
                primaries[zone] = min(b["id"] for b in on_zone)
                continue

            leader = min(
                candidates,
                key=lambda b: (
                    self._manhattan(tuple(b["position"]), zone),
                    b["id"],
                ),
            )
            primaries[zone] = leader["id"]
        return primaries

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
        round_number: int,
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

        available_bots: dict[int, dict] = {}
        for bot in bots:
            if bot["id"] in clear_dropoff_ids:
                continue
            inv_len = len(bot["inventory"])
            if inv_len >= 3:
                continue
            available_bots[bot["id"]] = bot

        used_items: set[str] = set()
        while available_bots:
            chosen: Optional[tuple[int, int, str, str]] = None
            chosen_regret = -1
            chosen_best_dist = 9999

            for bot_id, bot in available_bots.items():
                # Compute per-bot needed_left: only subtract locks held by OTHER bots.
                bot_needed_left = Counter(needed_left)
                for other_bot_id, item_type in lock_type_by_bot.items():
                    if other_bot_id == bot_id:
                        continue
                    if bot_needed_left[item_type] > 0:
                        bot_needed_left[item_type] -= 1

                useful_delivery = self._delivery_count(delivery_alloc.get(bot_id, Counter())) > 0
                options: list[tuple[int, str, str]] = []
                for item in items:
                    item_id = item["id"]
                    if item_id in used_items:
                        continue
                    item_type = item["type"]
                    if bot_needed_left[item_type] <= 0:
                        continue
                    if self._item_pick_blocked(item_id, round_number):
                        continue
                    dist = self._manhattan(tuple(bot["position"]), tuple(item["position"]))
                    # Delivery bots with free slots may still batch-pick, but bias to nearby items.
                    if useful_delivery:
                        dist += max(3, dist // 3)
                    options.append((dist, item_id, item_type))

                if not options:
                    continue

                options.sort(key=lambda t: (t[0], t[1]))
                best_dist, best_item_id, best_item_type = options[0]
                second_dist = options[1][0] if len(options) > 1 else (best_dist + 8)
                regret = second_dist - best_dist

                if regret > chosen_regret or (regret == chosen_regret and best_dist < chosen_best_dist):
                    chosen_regret = regret
                    chosen_best_dist = best_dist
                    chosen = (bot_id, best_dist, best_item_id, best_item_type)

            if chosen is None:
                break

            bot_id, _, item_id, item_type = chosen
            if needed_left[item_type] <= 0:
                available_bots.pop(bot_id, None)
                continue

            assignments[bot_id] = item_id
            available_bots.pop(bot_id, None)
            used_items.add(item_id)
            needed_left[item_type] -= 1

        return assignments

    def _yield_for_delivery(
        self,
        bot_id: int,
        pos: tuple[int, int],
        stuck_delivery_info: dict[int, dict],
        state: dict,
        occupied_now: set[tuple[int, int]],
        reserved_next: set[tuple[int, int]],
    ) -> Optional[dict]:
        """Move out of the way if blocking a stuck delivery bot."""
        if not stuck_delivery_info:
            return None
        width = state["grid"]["width"]
        height = state["grid"]["height"]
        walls = {tuple(w) for w in state["grid"]["walls"]}
        blocked = (occupied_now - {pos}) | reserved_next

        for del_id, info in stuck_delivery_info.items():
            del_pos = info["pos"]
            del_target = info["target"]
            if self._manhattan(pos, del_pos) != 1:
                continue

            # Only yield if this bot is roughly between delivery bot and its target
            direct_dist = self._manhattan(del_pos, del_target)
            via_me = self._manhattan(del_pos, pos) + self._manhattan(pos, del_target)
            if via_me > direct_dist + 1:
                continue

            # Direction from delivery bot to this bot
            dx = pos[0] - del_pos[0]
            dy = pos[1] - del_pos[1]
            # Try perpendicular moves first, then continue-away
            if dx != 0:
                candidates = [
                    (pos[0], pos[1] + 1),
                    (pos[0], pos[1] - 1),
                    (pos[0] + dx, pos[1]),
                ]
            else:
                candidates = [
                    (pos[0] + 1, pos[1]),
                    (pos[0] - 1, pos[1]),
                    (pos[0], pos[1] + dy),
                ]

            for cell in candidates:
                cx, cy = cell
                if not (0 <= cx < width and 0 <= cy < height):
                    continue
                if cell in walls or cell in self.shelves or cell in blocked:
                    continue
                reserved_next.add(cell)
                return {"bot": bot_id, "action": self._action_from_step(pos, cell)}

        return None

    def _decide_one(
        self,
        bot: dict,
        round_number: int,
        state: dict,
        needed: Counter,
        target_drop_off: tuple[int, int],
        drop_zones: list[tuple[int, int]],
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
        zone_primary_by_zone: dict[tuple[int, int], int],
    ) -> dict:
        bot_id = bot["id"]
        pos = tuple(bot["position"])
        inventory = bot["inventory"]
        useful_inventory = self._delivery_count(useful_delivery) > 0
        has_non_useful_inventory = bool(inventory) and not useful_inventory
        drop_zone_set = set(drop_zones)
        nearest_drop_off = self._nearest_drop_zone(pos, drop_zones, target_drop_off)
        max_rounds = int(state.get("max_rounds", 300))
        late_unstick_round = max(0, max_rounds - 60)
        hard_wait_round = max(0, max_rounds - 15)

        if useful_inventory and (pos == target_drop_off or pos in drop_zone_set):
            if self.last_drop_round.get(bot_id) == round_number - 1:
                return self._wait_or_nudge(
                    bot_id=bot_id,
                    pos=pos,
                    state=state,
                    occupied_now=occupied_now,
                    reserved_next=reserved_next,
                )
            self.bot_targets.pop(bot_id, None)
            self.last_drop_round[bot_id] = round_number
            return {"bot": bot_id, "action": "drop_off"}

        # If this bot is idling on drop-off while others need to deliver, clear the cell.
        if bot_id in clear_dropoff_ids:
            evac_origin = pos if pos in drop_zone_set else target_drop_off
            evac_goals = self._neighbors(evac_origin)
            return self._move_toward(
                bot_id=bot_id,
                start=pos,
                goals=set(evac_goals),
                state=state,
                occupied_now=occupied_now,
                reserved_next=reserved_next,
                allow_occupied_goals=False,
            )

        if round_number >= hard_wait_round and not useful_inventory:
            self.bot_targets.pop(bot_id, None)
            return self._wait_or_nudge(
                bot_id=bot_id,
                pos=pos,
                state=state,
                occupied_now=occupied_now,
                reserved_next=reserved_next,
            )

        if round_number >= late_unstick_round and not useful_inventory and self.wait_streak.get(bot_id, 0) >= 2:
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

        if has_non_useful_inventory and len(inventory) >= 3:
            # Carrying a full preview/non-useful bag: stage next to drop-off for fast flip.
            self.bot_targets.pop(bot_id, None)
            staging_goals = self._adjacent_walkable(nearest_drop_off, state, occupied_now, pos)
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
            preview_duty_allowed = (bot_id in preview_duty_bots) or (
                len(preview_duty_bots) < preview_duty_cap
            )
            if preview_duty_allowed:
                preview_pick = self._pick_if_adjacent(bot, state, preview_needed, reserved_items, round_number)
                if preview_pick is not None:
                    preview_duty_bots.add(bot_id)
                    return preview_pick

                preview_target = self._locked_or_best_item(
                    bot_id=bot_id,
                    pos=pos,
                    state=state,
                    needed=preview_needed,
                    reserved_items=reserved_items,
                    items_by_id=items_by_id,
                    assigned_item_id=None,
                    round_number=round_number,
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

        if useful_inventory:
            if round_number <= 250 and len(inventory) < 3:
                detour = self._delivery_detour_action(
                    bot_id=bot_id,
                    pos=pos,
                    state=state,
                    needed=needed,
                    drop_off=target_drop_off,
                    occupied_now=occupied_now,
                    reserved_items=reserved_items,
                    reserved_next=reserved_next,
                    items_by_id=items_by_id,
                    assigned_item_id=assigned_item_id,
                )
                if detour is not None:
                    return detour

            zone_primary = zone_primary_by_zone.get(target_drop_off)
            if zone_primary is not None and zone_primary != bot_id and self._manhattan(pos, target_drop_off) <= 2:
                staged = self._stage_near_dropoff(
                    bot_id=bot_id,
                    pos=pos,
                    drop_off=target_drop_off,
                    state=state,
                    occupied_now=occupied_now,
                    reserved_next=reserved_next,
                )
                if staged is not None:
                    return staged
            self.bot_targets.pop(bot_id, None)
            action = self._move_toward(
                bot_id=bot_id,
                start=pos,
                goals={target_drop_off},
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
            pos=pos,
            state=state,
            needed=needed,
            reserved_items=reserved_items,
            items_by_id=items_by_id,
            assigned_item_id=assigned_item_id,
            round_number=round_number,
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
        pos: tuple[int, int],
        state: dict,
        needed: Counter,
        reserved_items: set[str],
        items_by_id: dict[str, dict],
        assigned_item_id: Optional[str],
        round_number: int = -1,
    ) -> Optional[dict]:
        if assigned_item_id:
            assigned = items_by_id.get(assigned_item_id)
            if (
                assigned
                and assigned_item_id not in reserved_items
                and needed[assigned["type"]] > 0
                and not self._item_pick_blocked(assigned_item_id, round_number)
            ):
                self.bot_targets[bot_id] = assigned_item_id
                return assigned

        locked_item_id = self.bot_targets.get(bot_id)
        if locked_item_id:
            locked_item = items_by_id.get(locked_item_id)
            if (
                locked_item
                and locked_item_id not in reserved_items
                and needed[locked_item["type"]] > 0
                and not self._item_pick_blocked(locked_item_id, round_number)
            ):
                return locked_item
            self.bot_targets.pop(bot_id, None)

        locked_by_others = {
            item_id
            for other_bot_id, item_id in self.bot_targets.items()
            if other_bot_id != bot_id
        }
        chosen = self._select_target_item(
            pos=pos,
            state=state,
            needed=needed,
            reserved_items=reserved_items | locked_by_others,
            round_number=round_number,
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
        round_number: int = -1,
    ) -> Optional[dict]:
        pos = tuple(bot["position"])
        if len(bot["inventory"]) >= 3:
            return None

        candidates: list[dict] = []
        for item in state["items"]:
            if item["id"] in reserved_items:
                continue
            if needed[item["type"]] <= 0:
                continue
            if self._item_pick_blocked(item["id"], round_number):
                continue
            item_pos = tuple(item["position"])
            if self._manhattan(pos, item_pos) == 1:
                candidates.append(item)

        if not candidates:
            return None

        chosen = candidates[0]
        self.bot_targets.pop(bot["id"], None)
        reserved_items.add(chosen["id"])
        needed[chosen["type"]] -= 1
        return {"bot": bot["id"], "action": "pick_up", "item_id": chosen["id"]}

    def _select_target_item(
        self,
        pos: tuple[int, int],
        state: dict,
        needed: Counter,
        reserved_items: set[str],
        round_number: int = -1,
    ) -> Optional[dict]:
        best_item = None
        best_dist = 10**9
        for item in state["items"]:
            if item["id"] in reserved_items:
                continue
            if needed[item["type"]] <= 0:
                continue
            if self._item_pick_blocked(item["id"], round_number):
                continue
            dist = self._manhattan(pos, tuple(item["position"]))
            if dist < best_dist:
                best_dist = dist
                best_item = item
        return best_item

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
        if self.wait_streak.get(bot_id, 0) >= 1:
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
        if step is None and relax_reservation_if_blocked:
            # Final fallback: only block immediately adjacent bots so BFS
            # can find longer detours around nearby blockers.
            adjacent = {(start[0]+dx, start[1]+dy)
                        for dx, dy in [(0,1),(0,-1),(1,0),(-1,0)]}
            near_blocked = (occupied_now - {start}) & adjacent
            step = self._bfs_first_step(
                start=start,
                goals=goals,
                state=state,
                blocked=near_blocked,
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
    shape_checked = False
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
                if not shape_checked and msg.get("type") == "game_state":
                    print_nightmare_shape_check(msg)
                    shape_checked = True
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
