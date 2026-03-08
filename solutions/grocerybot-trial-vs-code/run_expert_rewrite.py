import asyncio
import base64
import csv
import heapq
import json
import os
import random
import time
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from itertools import combinations, permutations
from pathlib import Path
from typing import Optional
from urllib.parse import parse_qs, urlparse

from dotenv import load_dotenv
import websockets

random.seed(42)

load_dotenv()
raw = (os.getenv("GROCERY_BOT_TOKEN_EXPERT") or "").strip()
if not raw:
    raise SystemExit("Missing GROCERY_BOT_TOKEN_EXPERT in .env")

BASE_DIR = Path(__file__).resolve().parent
LOG_DIR = BASE_DIR / "logs"
RUN_HISTORY_CSV = LOG_DIR / "run_history.csv"
MEMORY_JSON = LOG_DIR / "memory.json"
MEMORY_MD = LOG_DIR / "TRIAL_MEMORY.md"


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


@dataclass(frozen=True)
class BundleCandidate:
    bundle_types: tuple[str, ...]
    source_ids: tuple[str, ...]
    goal_cells: tuple[tuple[int, int], ...]
    travel_cost: int
    drop_eta: int
    preferred_zone: int


class TrialBot:
    def __init__(self) -> None:
        self.initialized = False
        self.width = 0
        self.height = 0
        self.walls: set[tuple[int, int]] = set()
        self.walkable: set[tuple[int, int]] = set()
        self.neighbors: dict[tuple[int, int], list[tuple[int, int]]] = {}
        self.shelves: set[tuple[int, int]] = set()
        self.drop_off: tuple[int, int] = (0, 0)
        self.spawn: tuple[int, int] = (0, 0)
        self.items_by_id: dict[str, dict] = {}
        self.items_by_type: dict[str, list[dict]] = defaultdict(list)
        self.pick_goals: dict[str, tuple[tuple[int, int], ...]] = {}
        self.item_zone: dict[str, int] = {}
        self.zone_centers: list[int] = []
        self.zone_stage_cells: dict[int, tuple[int, int]] = {}
        self.parking_cells: list[tuple[int, int]] = []
        self.holding_cells: list[tuple[int, int]] = []
        self.queue_cells: list[tuple[int, int]] = []
        self.dist_cache: dict[tuple[tuple[int, int], tuple[int, int]], int] = {}
        self.wait_streak: dict[int, int] = {}
        self.last_positions: dict[int, tuple[int, int]] = {}
        self.last_actions: dict[int, str] = {}
        self.last_pick_item: dict[int, str] = {}
        self.last_inventory_size: dict[int, int] = {}
        self.pick_fail_streak: dict[tuple[int, str], int] = {}
        self.pick_block_until_round: dict[tuple[int, str], int] = {}

    def decide(self, state: dict) -> list[dict]:
        if not self.initialized:
            self._setup_map(state)
        self._update_wait_state(state["bots"])
        self._update_pick_retry_state(state["bots"], int(state.get("round", -1)))

        round_number = int(state.get("round", -1))
        bots = sorted(state["bots"], key=lambda b: b["id"])
        occupied_now = {tuple(b["position"]) for b in bots}
        reserved_next: set[tuple[int, int]] = set()

        active_order = self._get_order_by_status(state, "active")
        preview_order = self._get_order_by_status(state, "preview")
        active_remaining = self._remaining_counter(active_order)
        preview_remaining = self._remaining_counter(preview_order)

        delivery_alloc, fetch_remaining = self._allocate_delivery_slots(bots, active_remaining)
        active_missing_total = sum(fetch_remaining.values())

        collector_limit = self._collector_limit(round_number)
        deliver_now_ids: set[int] = set()
        worker_candidates: list[dict] = []

        for bot in bots:
            bot_id = bot["id"]
            inv = list(bot["inventory"])
            useful_active = self._delivery_count(delivery_alloc.get(bot_id, Counter()))
            polluted = len(inv) > useful_active

            should_deliver = useful_active > 0 and (
                len(inv) >= 3
                or useful_active >= 2
                or active_missing_total == 0
                or round_number >= 230
            )
            if should_deliver:
                deliver_now_ids.add(bot_id)
                continue

            if len(inv) < 3 and not polluted:
                worker_candidates.append(bot)
                continue

            if useful_active > 0:
                deliver_now_ids.add(bot_id)

        worker_candidates.sort(
            key=lambda b: (
                -self._delivery_count(delivery_alloc.get(b["id"], Counter())),
                -self._manhattan(tuple(b["position"]), self.spawn),
                -tuple(b["position"])[0],
                b["id"],
            )
        )
        selected_workers = worker_candidates[:collector_limit]

        active_assignments = self._assign_active_bundles(
            selected_workers=selected_workers,
            fetch_remaining=fetch_remaining,
        )
        preview_assignments = self._assign_preview_bundles(
            bots=bots,
            active_remaining=fetch_remaining,
            preview_remaining=preview_remaining,
            active_assignments=active_assignments,
            deliver_now_ids=deliver_now_ids,
            round_number=round_number,
        )

        for bot_id, candidate in active_assignments.items():
            if candidate is None:
                continue
            if len(candidate.bundle_types) == 0 and self._delivery_count(delivery_alloc.get(bot_id, Counter())) > 0:
                deliver_now_ids.add(bot_id)

        deliverers = [b for b in bots if b["id"] in deliver_now_ids]
        delivery_order = self._rank_deliverers(deliverers, delivery_alloc)

        actions_by_id: dict[int, dict] = {}
        ordered_ids: list[int] = []
        ordered_ids.extend([b["id"] for b in delivery_order])
        ordered_ids.extend([b["id"] for b in bots if b["id"] in active_assignments and b["id"] not in ordered_ids])
        ordered_ids.extend([b["id"] for b in bots if b["id"] in preview_assignments and b["id"] not in ordered_ids])
        ordered_ids.extend([b["id"] for b in bots if b["id"] not in ordered_ids])
        bots_by_id = {b["id"]: b for b in bots}

        for bot_id in ordered_ids:
            bot = bots_by_id[bot_id]
            inv = list(bot["inventory"])
            useful_active = delivery_alloc.get(bot_id, Counter())

            if bot_id in deliver_now_ids:
                action = self._decide_delivery(
                    bot=bot,
                    delivery_order=delivery_order,
                    delivery_alloc=delivery_alloc,
                    occupied_now=occupied_now,
                    reserved_next=reserved_next,
                )
            elif bot_id in active_assignments and active_assignments[bot_id] is not None:
                action = self._decide_bundle_pick(
                    bot=bot,
                    candidate=active_assignments[bot_id],
                    occupied_now=occupied_now,
                    reserved_next=reserved_next,
                    mode="collect",
                    round_number=round_number,
                )
            elif bot_id in preview_assignments and preview_assignments[bot_id] is not None:
                action = self._decide_bundle_pick(
                    bot=bot,
                    candidate=preview_assignments[bot_id],
                    occupied_now=occupied_now,
                    reserved_next=reserved_next,
                    mode="preview",
                    round_number=round_number,
                )
            elif inv and self._delivery_count(useful_active) > 0:
                action = self._decide_delivery(
                    bot=bot,
                    delivery_order=delivery_order,
                    delivery_alloc=delivery_alloc,
                    occupied_now=occupied_now,
                    reserved_next=reserved_next,
                )
            elif inv:
                action = self._stage_preview_carrier(
                    bot=bot,
                    occupied_now=occupied_now,
                    reserved_next=reserved_next,
                )
            elif round_number < 20:
                action = {"bot": bot_id, "action": "wait"}
            else:
                action = self._decide_parking(
                    bot=bot,
                    occupied_now=occupied_now,
                    reserved_next=reserved_next,
                )

            actions_by_id[bot_id] = action
            self.last_actions[bot_id] = action["action"]
            if action["action"] == "pick_up":
                item_id = action.get("item_id")
                if isinstance(item_id, str) and item_id:
                    self.last_pick_item[bot_id] = item_id
                else:
                    self.last_pick_item.pop(bot_id, None)
            else:
                self.last_pick_item.pop(bot_id, None)

        return [actions_by_id[b["id"]] for b in bots]

    def _setup_map(self, state: dict) -> None:
        self.width = int(state["grid"]["width"])
        self.height = int(state["grid"]["height"])
        self.walls = {tuple(w) for w in state["grid"]["walls"]}
        self.drop_off = tuple(state["drop_off"])
        self.spawn = tuple(state["bots"][0]["position"])
        self.shelves = {tuple(item["position"]) for item in state["items"]}
        self.walkable = {
            (x, y)
            for x in range(self.width)
            for y in range(self.height)
            if (x, y) not in self.walls and (x, y) not in self.shelves
        }
        self.neighbors = {}
        for cell in self.walkable:
            x, y = cell
            next_cells = []
            for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                nxt = (x + dx, y + dy)
                if nxt in self.walkable:
                    next_cells.append(nxt)
            self.neighbors[cell] = next_cells

        self.items_by_id = {}
        self.items_by_type = defaultdict(list)
        unique_item_xs = sorted({int(item["position"][0]) for item in state["items"]})
        self.zone_centers = [
            (unique_item_xs[i] + unique_item_xs[i + 1]) // 2
            for i in range(0, len(unique_item_xs), 2)
        ]
        for item in state["items"]:
            item_copy = {
                "id": item["id"],
                "type": item["type"],
                "position": tuple(item["position"]),
            }
            self.items_by_id[item["id"]] = item_copy
            self.items_by_type[item["type"]].append(item_copy)
            goals = tuple(
                sorted(
                    p
                    for p in self.neighbors_of(item_copy["position"])
                    if p in self.walkable
                )
            )
            self.pick_goals[item_copy["id"]] = goals
            self.item_zone[item_copy["id"]] = self._zone_for_x(item_copy["position"][0])

        self.queue_cells = sorted(
            [cell for cell in self.neighbors_of(self.drop_off) if cell in self.walkable],
            key=lambda c: (self._manhattan(c, self.drop_off), self._manhattan(c, self.spawn)),
        )
        self.holding_cells = sorted(
            [
                cell
                for cell in self.walkable
                if 2 <= self._manhattan(cell, self.drop_off) <= 5
                and cell not in self.queue_cells
                and cell[0] <= 6
            ],
            key=lambda c: (self._manhattan(c, self.drop_off), c[1], c[0]),
        )
        self.parking_cells = sorted(
            [
                cell
                for cell in self.walkable
                if cell[0] >= self.width - 5 and cell[1] >= self.height - 4
            ],
            key=lambda c: (self._manhattan(c, self.spawn), -c[0], -c[1]),
        )
        for zone in range(len(self.zone_centers)):
            center = self.zone_centers[zone]
            candidates = [
                cell
                for cell in self.walkable
                if cell[1] in {self.height - 3, self.height - 2}
            ]
            best = min(
                candidates,
                key=lambda c: (abs(c[0] - center), self._manhattan(c, self.spawn)),
            )
            self.zone_stage_cells[zone] = best
        self.initialized = True

    def _collector_limit(self, round_number: int) -> int:
        if round_number < 20:
            return 2
        if round_number < 80:
            return 3
        if round_number < 180:
            return 4
        return 5

    def _assign_active_bundles(
        self,
        selected_workers: list[dict],
        fetch_remaining: Counter,
    ) -> dict[int, Optional[BundleCandidate]]:
        if not selected_workers or sum(fetch_remaining.values()) <= 0:
            return {}

        ranked_workers = sorted(
            selected_workers,
            key=lambda b: (-tuple(b["position"])[0], b["id"]),
        )
        zone_order = list(range(len(self.zone_centers) - 1, -1, -1))
        zone_by_bot: dict[int, int] = {}
        for idx, bot in enumerate(ranked_workers):
            zone_by_bot[bot["id"]] = zone_order[idx % len(zone_order)]

        total_missing = int(sum(fetch_remaining.values()))
        max_bundle_size = 2 if total_missing <= 4 else 3
        candidate_lists: list[tuple[int, list[BundleCandidate]]] = []
        for bot in ranked_workers:
            bot_id = bot["id"]
            zone = zone_by_bot[bot_id]
            candidates = self._build_bundle_candidates(
                pos=tuple(bot["position"]),
                free_slots=max(0, 3 - len(bot["inventory"])),
                needed=fetch_remaining,
                preferred_zone=zone,
                include_empty=True,
                max_bundle_size=max_bundle_size,
            )
            candidate_lists.append((bot_id, candidates))
        best_score = -10**9
        best_assignment: dict[int, Optional[BundleCandidate]] = {bot_id: None for bot_id, _ in candidate_lists}

        def search(index: int, used: Counter, chosen: dict[int, Optional[BundleCandidate]]) -> None:
            nonlocal best_score, best_assignment
            if index >= len(candidate_lists):
                covered = int(sum(used.values()))
                if covered <= 0:
                    score = -500
                else:
                    distinct_zones = len(
                        {
                            cand.preferred_zone
                            for cand in chosen.values()
                            if cand is not None and len(cand.bundle_types) > 0
                        }
                    )
                    travel = sum(
                        cand.travel_cost
                        for cand in chosen.values()
                        if cand is not None and len(cand.bundle_types) > 0
                    )
                    makespan = max(
                        [cand.drop_eta for cand in chosen.values() if cand is not None and len(cand.bundle_types) > 0]
                        or [0]
                    )
                    nonempty = sum(
                        1 for cand in chosen.values() if cand is not None and len(cand.bundle_types) > 0
                    )
                    completion_bonus = 450 if covered >= total_missing and total_missing > 0 else 0
                    score = completion_bonus + (45 * covered) + (10 * distinct_zones) - (2 * makespan) - travel - (3 * nonempty)
                if score > best_score:
                    best_score = score
                    best_assignment = dict(chosen)
                return

            bot_id, candidates = candidate_lists[index]
            for cand in candidates:
                feasible = True
                for item_type, count in Counter(cand.bundle_types).items():
                    if used[item_type] + count > fetch_remaining[item_type]:
                        feasible = False
                        break
                if not feasible:
                    continue
                next_used = Counter(used)
                next_used.update(cand.bundle_types)
                chosen[bot_id] = cand if len(cand.bundle_types) > 0 else None
                search(index + 1, next_used, chosen)
                chosen.pop(bot_id, None)

        search(0, Counter(), {})
        return best_assignment

    def _assign_preview_bundles(
        self,
        bots: list[dict],
        active_remaining: Counter,
        preview_remaining: Counter,
        active_assignments: dict[int, Optional[BundleCandidate]],
        deliver_now_ids: set[int],
        round_number: int,
    ) -> dict[int, Optional[BundleCandidate]]:
        if sum(active_remaining.values()) > 0 or sum(preview_remaining.values()) <= 0:
            return {}
        if round_number >= 220:
            return {}

        assignments: dict[int, Optional[BundleCandidate]] = {}
        idle = [
            b
            for b in bots
            if b["id"] not in deliver_now_ids
            and b["id"] not in active_assignments
            and len(b["inventory"]) == 0
        ]
        idle.sort(key=lambda b: (-tuple(b["position"])[0], b["id"]))
        for bot in idle[:1]:
            zone = self._zone_for_x(tuple(bot["position"])[0])
            candidates = self._build_bundle_candidates(
                pos=tuple(bot["position"]),
                free_slots=1,
                needed=preview_remaining,
                preferred_zone=zone,
                include_empty=False,
            )
            if candidates:
                assignments[bot["id"]] = candidates[0]
        return assignments

    def _build_bundle_candidates(
        self,
        pos: tuple[int, int],
        free_slots: int,
        needed: Counter,
        preferred_zone: int,
        include_empty: bool,
        max_bundle_size: int = 3,
    ) -> list[BundleCandidate]:
        candidates: list[BundleCandidate] = []
        if include_empty:
            candidates.append(BundleCandidate((), (), (), 0, 0, preferred_zone))
        if free_slots <= 0 or sum(needed.values()) <= 0:
            return candidates

        token_types: list[str] = []
        for item_type, count in needed.items():
            token_types.extend([item_type] * count)
        unique_types = sorted(
            set(token_types),
            key=lambda item_type: self._best_type_distance(pos, item_type, preferred_zone),
        )
        candidate_type_pool = unique_types[:6]
        multiset_options: set[tuple[str, ...]] = set()
        for size in range(1, min(free_slots, max_bundle_size) + 1):
            indexed = []
            for item_type in candidate_type_pool:
                indexed.extend([item_type] * min(needed[item_type], size))
            for combo in combinations(range(len(indexed)), size):
                bundle = tuple(sorted(indexed[i] for i in combo))
                if Counter(bundle) <= needed:
                    multiset_options.add(bundle)

        scored: list[tuple[float, BundleCandidate]] = []
        for bundle in multiset_options:
            planned = self._plan_bundle_route(pos, bundle, preferred_zone)
            if planned is None:
                continue
            local_score = (16 * len(bundle)) - planned.travel_cost - (0.5 * planned.drop_eta)
            scored.append((local_score, planned))
        by_size: dict[int, list[tuple[float, BundleCandidate]]] = defaultdict(list)
        for score, candidate in scored:
            by_size[len(candidate.bundle_types)].append((score, candidate))
        for size in sorted(by_size):
            by_size[size].sort(key=lambda t: t[0], reverse=True)
            take = 3 if size == 1 else 2
            candidates.extend(candidate for _, candidate in by_size[size][:take])
        return candidates

    def _plan_bundle_route(
        self,
        start: tuple[int, int],
        bundle: tuple[str, ...],
        preferred_zone: int,
    ) -> Optional[BundleCandidate]:
        best: Optional[BundleCandidate] = None
        best_cost = 10**9
        seen_orders = set(permutations(bundle))
        for ordered_types in seen_orders:
            current = start
            travel = 0
            sources: list[str] = []
            goals: list[tuple[int, int]] = []
            feasible = True
            for item_type in ordered_types:
                choice = self._best_source_for_type(current, item_type, preferred_zone)
                if choice is None:
                    feasible = False
                    break
                source_id, goal_cell, dist = choice
                travel += dist + 1
                sources.append(source_id)
                goals.append(goal_cell)
                current = goal_cell
            if not feasible:
                continue
            drop_dist = self._static_distance(current, self.drop_off)
            total_cost = travel + drop_dist + 1
            if total_cost < best_cost:
                best_cost = total_cost
                best = BundleCandidate(
                    bundle_types=tuple(ordered_types),
                    source_ids=tuple(sources),
                    goal_cells=tuple(goals),
                    travel_cost=travel,
                    drop_eta=total_cost,
                    preferred_zone=preferred_zone,
                )
        return best

    def _best_type_distance(self, pos: tuple[int, int], item_type: str, preferred_zone: int) -> int:
        choice = self._best_source_for_type(pos, item_type, preferred_zone)
        if choice is None:
            return 10**6
        return choice[2]

    def _best_source_for_type(
        self,
        start: tuple[int, int],
        item_type: str,
        preferred_zone: int,
    ) -> Optional[tuple[str, tuple[int, int], int]]:
        best: Optional[tuple[str, tuple[int, int], int]] = None
        best_score = 10**9
        for item in self.items_by_type.get(item_type, []):
            item_id = item["id"]
            best_goal = None
            best_dist = 10**9
            for goal_cell in self.pick_goals[item_id]:
                dist = self._static_distance(start, goal_cell)
                if dist < best_dist:
                    best_dist = dist
                    best_goal = goal_cell
            if best_goal is None:
                continue
            zone_penalty = 2 * abs(self.item_zone[item_id] - preferred_zone)
            score = best_dist + zone_penalty
            if score < best_score:
                best_score = score
                best = (item_id, best_goal, best_dist)
        return best

    def _decide_delivery(
        self,
        bot: dict,
        delivery_order: list[dict],
        delivery_alloc: dict[int, Counter],
        occupied_now: set[tuple[int, int]],
        reserved_next: set[tuple[int, int]],
    ) -> dict:
        bot_id = bot["id"]
        pos = tuple(bot["position"])
        if pos == self.drop_off:
            return {"bot": bot_id, "action": "drop_off"}

        leader_id = delivery_order[0]["id"] if delivery_order else None
        second_id = delivery_order[1]["id"] if len(delivery_order) > 1 else None
        if bot_id == leader_id:
            return self._move_toward(
                bot_id=bot_id,
                start=pos,
                goals={self.drop_off},
                occupied_now=occupied_now,
                reserved_next=reserved_next,
                mode="delivery",
                allow_goal_occupied=True,
            )
        if bot_id == second_id and self.queue_cells:
            return self._move_toward(
                bot_id=bot_id,
                start=pos,
                goals=set(self.queue_cells),
                occupied_now=occupied_now,
                reserved_next=reserved_next,
                mode="delivery",
                allow_goal_occupied=False,
            )
        if self.holding_cells:
            return self._move_toward(
                bot_id=bot_id,
                start=pos,
                goals=set(self.holding_cells[:6]),
                occupied_now=occupied_now,
                reserved_next=reserved_next,
                mode="holding",
                allow_goal_occupied=False,
            )
        return self._wait_or_nudge(bot_id, pos, occupied_now, reserved_next)

    def _decide_bundle_pick(
        self,
        bot: dict,
        candidate: BundleCandidate,
        occupied_now: set[tuple[int, int]],
        reserved_next: set[tuple[int, int]],
        mode: str,
        round_number: int,
    ) -> dict:
        bot_id = bot["id"]
        pos = tuple(bot["position"])
        if len(candidate.bundle_types) == 0:
            if mode == "preview":
                return self._stage_preview_carrier(bot, occupied_now, reserved_next)
            return self._decide_parking(bot, occupied_now, reserved_next)

        target_item_id = candidate.source_ids[0]
        if self._item_pick_blocked(bot_id, target_item_id, round_number):
            return self._wait_or_nudge(bot_id, pos, occupied_now, reserved_next)

        target_goal = candidate.goal_cells[0]
        if self._manhattan(pos, self.items_by_id[target_item_id]["position"]) == 1:
            return {"bot": bot_id, "action": "pick_up", "item_id": target_item_id}
        return self._move_toward(
            bot_id=bot_id,
            start=pos,
            goals={target_goal},
            occupied_now=occupied_now,
            reserved_next=reserved_next,
            mode=mode,
            allow_goal_occupied=False,
        )

    def _stage_preview_carrier(
        self,
        bot: dict,
        occupied_now: set[tuple[int, int]],
        reserved_next: set[tuple[int, int]],
    ) -> dict:
        bot_id = bot["id"]
        pos = tuple(bot["position"])
        if self.holding_cells:
            return self._move_toward(
                bot_id=bot_id,
                start=pos,
                goals=set(self.holding_cells[:4]),
                occupied_now=occupied_now,
                reserved_next=reserved_next,
                mode="preview",
                allow_goal_occupied=False,
            )
        return self._decide_parking(bot, occupied_now, reserved_next)

    def _decide_parking(
        self,
        bot: dict,
        occupied_now: set[tuple[int, int]],
        reserved_next: set[tuple[int, int]],
    ) -> dict:
        bot_id = bot["id"]
        pos = tuple(bot["position"])
        if self.parking_cells:
            goals = set(self.parking_cells[: min(8, len(self.parking_cells))])
            return self._move_toward(
                bot_id=bot_id,
                start=pos,
                goals=goals,
                occupied_now=occupied_now,
                reserved_next=reserved_next,
                mode="park",
                allow_goal_occupied=False,
            )
        return self._wait_or_nudge(bot_id, pos, occupied_now, reserved_next)

    def _rank_deliverers(self, deliverers: list[dict], delivery_alloc: dict[int, Counter]) -> list[dict]:
        return sorted(
            deliverers,
            key=lambda b: (
                0 if tuple(b["position"]) == self.drop_off else 1,
                self._manhattan(tuple(b["position"]), self.drop_off),
                -self._delivery_count(delivery_alloc.get(b["id"], Counter())),
                b["id"],
            ),
        )

    def _remaining_counter(self, order: Optional[dict]) -> Counter:
        if order is None:
            return Counter()
        return Counter(order["items_required"]) - Counter(order["items_delivered"])

    def _allocate_delivery_slots(
        self,
        bots: list[dict],
        remaining_needed: Counter,
    ) -> tuple[dict[int, Counter], Counter]:
        left = Counter(remaining_needed)
        alloc: dict[int, Counter] = {}
        for bot in bots:
            reserved = Counter()
            for item_type in bot["inventory"]:
                if left[item_type] > 0:
                    reserved[item_type] += 1
                    left[item_type] -= 1
            alloc[bot["id"]] = reserved
        return alloc, left

    def _update_wait_state(self, bots: list[dict]) -> None:
        active_ids = {b["id"] for b in bots}
        for bot in bots:
            bot_id = bot["id"]
            pos = tuple(bot["position"])
            prev_pos = self.last_positions.get(bot_id)
            prev_action = self.last_actions.get(bot_id)
            if prev_action == "wait" and prev_pos == pos:
                self.wait_streak[bot_id] = self.wait_streak.get(bot_id, 0) + 1
            else:
                self.wait_streak[bot_id] = 0
            self.last_positions[bot_id] = pos
            self.last_inventory_size[bot_id] = len(bot["inventory"])

        for bot_id in list(self.wait_streak.keys()):
            if bot_id not in active_ids:
                self.wait_streak.pop(bot_id, None)
                self.last_positions.pop(bot_id, None)
                self.last_actions.pop(bot_id, None)
                self.last_inventory_size.pop(bot_id, None)
                self.last_pick_item.pop(bot_id, None)

    def _update_pick_retry_state(self, bots: list[dict], round_number: int) -> None:
        active_ids = {b["id"] for b in bots}
        for bot in bots:
            bot_id = bot["id"]
            prev_action = self.last_actions.get(bot_id)
            prev_size = self.last_inventory_size.get(bot_id)
            current_size = len(bot["inventory"])
            if prev_action == "pick_up":
                attempted_item_id = self.last_pick_item.get(bot_id)
                if attempted_item_id and prev_size is not None and current_size <= prev_size:
                    key = (bot_id, attempted_item_id)
                    streak = self.pick_fail_streak.get(key, 0) + 1
                    self.pick_fail_streak[key] = streak
                    self.pick_block_until_round[key] = round_number + min(10, 2 + streak)
            self.last_inventory_size[bot_id] = current_size

        for key, until_round in list(self.pick_block_until_round.items()):
            if key[0] not in active_ids or until_round < round_number:
                self.pick_block_until_round.pop(key, None)
                self.pick_fail_streak.pop(key, None)

    def _item_pick_blocked(self, bot_id: int, item_id: str, round_number: int) -> bool:
        until_round = self.pick_block_until_round.get((bot_id, item_id))
        return until_round is not None and round_number <= until_round

    def _move_toward(
        self,
        bot_id: int,
        start: tuple[int, int],
        goals: set[tuple[int, int]],
        occupied_now: set[tuple[int, int]],
        reserved_next: set[tuple[int, int]],
        mode: str,
        allow_goal_occupied: bool,
    ) -> dict:
        blocked = (occupied_now - {start}) | reserved_next
        if allow_goal_occupied:
            blocked = blocked - goals
        step = self._astar_first_step(start, goals, blocked, mode)
        if step is None:
            return self._wait_or_nudge(bot_id, start, occupied_now, reserved_next)
        reserved_next.add(step)
        return {"bot": bot_id, "action": self._action_from_step(start, step)}

    def _astar_first_step(
        self,
        start: tuple[int, int],
        goals: set[tuple[int, int]],
        blocked: set[tuple[int, int]],
        mode: str,
    ) -> Optional[tuple[int, int]]:
        if not goals or start in goals:
            return None

        goal_list = list(goals)

        def heuristic(cell: tuple[int, int]) -> int:
            return min(self._manhattan(cell, goal) for goal in goal_list)

        frontier: list[tuple[float, int, tuple[int, int]]] = []
        counter = 0
        heapq.heappush(frontier, (heuristic(start), counter, start))
        prev: dict[tuple[int, int], Optional[tuple[int, int]]] = {start: None}
        best_cost: dict[tuple[int, int], float] = {start: 0.0}

        while frontier:
            _, _, current = heapq.heappop(frontier)
            if current in goals:
                return self._unwind_first_step(start, current, prev)

            for nxt in self.neighbors.get(current, []):
                if nxt in blocked:
                    continue
                move_cost = best_cost[current] + 1 + self._cell_penalty(nxt, mode)
                if move_cost >= best_cost.get(nxt, 10**9):
                    continue
                best_cost[nxt] = move_cost
                prev[nxt] = current
                counter += 1
                heapq.heappush(frontier, (move_cost + heuristic(nxt), counter, nxt))
        return None

    def _cell_penalty(self, cell: tuple[int, int], mode: str) -> float:
        x, y = cell
        penalty = 0.0
        if mode not in {"delivery", "holding"} and cell in self.queue_cells:
            penalty += 4.0
        if mode == "park":
            penalty += 0.0 if cell in self.parking_cells[:8] else 0.6
        elif mode == "delivery":
            penalty -= 0.15 if y in {self.height - 2, self.height - 3} else 0.0
        elif mode in {"collect", "preview"}:
            if y in {1, 9, self.height - 3, self.height - 2}:
                penalty -= 0.1
        if x >= self.width - 2 and mode not in {"park"}:
            penalty += 0.2
        return penalty

    def _wait_or_nudge(
        self,
        bot_id: int,
        pos: tuple[int, int],
        occupied_now: set[tuple[int, int]],
        reserved_next: set[tuple[int, int]],
    ) -> dict:
        if self.wait_streak.get(bot_id, 0) >= 1:
            for nxt in self.neighbors.get(pos, []):
                if nxt in occupied_now or nxt in reserved_next:
                    continue
                if nxt in self.queue_cells:
                    continue
                reserved_next.add(nxt)
                return {"bot": bot_id, "action": self._action_from_step(pos, nxt)}
        return {"bot": bot_id, "action": "wait"}

    def _static_distance(self, start: tuple[int, int], goal: tuple[int, int]) -> int:
        if start == goal:
            return 0
        key = (start, goal)
        if key in self.dist_cache:
            return self.dist_cache[key]
        q = [start]
        dist = {start: 0}
        idx = 0
        while idx < len(q):
            current = q[idx]
            idx += 1
            for nxt in self.neighbors.get(current, []):
                if nxt in dist:
                    continue
                dist[nxt] = dist[current] + 1
                if nxt == goal:
                    self.dist_cache[key] = dist[nxt]
                    self.dist_cache[(goal, start)] = dist[nxt]
                    return dist[nxt]
                q.append(nxt)
        return 10**6

    def _zone_for_x(self, x: int) -> int:
        return min(range(len(self.zone_centers)), key=lambda i: abs(x - self.zone_centers[i]))

    def _get_order_by_status(self, state: dict, status: str) -> Optional[dict]:
        return next((o for o in state["orders"] if o.get("status") == status), None)

    def neighbors_of(self, pos: tuple[int, int]) -> list[tuple[int, int]]:
        x, y = pos
        return [(x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)]

    @staticmethod
    def _delivery_count(alloc: Counter) -> int:
        return int(sum(alloc.values()))

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
            print("Connected. Running rewrite game loop...", flush=True)
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
