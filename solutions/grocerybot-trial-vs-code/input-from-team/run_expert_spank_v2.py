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
raw = (os.getenv("GROCERY_BOT_TOKEN_EXPERT") or "").strip()
if not raw:
    raise SystemExit("Missing GROCERY_BOT_TOKEN_EXPERT in .env")

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
    """
    Expert bot rebuilt around:
    - real path distances (BFS) for assignment
    - explicit active vs preview task assignment
    - drop-off ring traffic control
    - edge-swap prevention
    - stuck detection / de-jam nudges
    """
    def __init__(self) -> None:
        # Static map caches
        self.shelves: set[tuple[int, int]] = set()
        self._grid_cache_key: Optional[tuple] = None
        self._walkable_cells: set[tuple[int, int]] = set()
        self._neighbors_cache: dict[tuple[int, int], list[tuple[int, int]]] = {}
        self._all_pairs_dropoff_cache: dict[tuple[int, int], dict[tuple[int, int], int]] = {}

        # Bot memory
        self.bot_targets: dict[int, str] = {}
        self.bot_target_kind: dict[int, str] = {}  # "active" / "preview"
        self.last_action: dict[int, str] = {}
        self.last_observed_pos: dict[int, tuple[int, int]] = {}
        self.wait_streak: dict[int, int] = {}
        self.stuck_streak: dict[int, int] = {}
        self.last_inventory_size: dict[int, int] = {}
        self.last_pick_item: dict[int, str] = {}
        self.last_drop_round: dict[int, int] = {}

        # Failed-pick cooldown
        self.pick_fail_streak: dict[str, int] = {}
        self.pick_block_until_round: dict[str, int] = {}

    def decide(self, state: dict) -> list[dict]:
        self._update_static_map(state)

        round_number = int(state.get("round", -1))
        bots = sorted(state.get("bots", []), key=lambda b: b["id"])
        if not bots:
            return []

        self._update_pick_retry_state(bots, round_number)
        self._update_motion_state(bots)

        drop_off = tuple(state["drop_off"])
        items = state.get("items", [])
        items_by_id = {it["id"]: it for it in items}
        occupied_now = {tuple(b["position"]) for b in bots}

        active_order = self._get_order_by_status(state, "active")
        preview_order = self._get_order_by_status(state, "preview")
        active_missing = self._required_minus_delivered(active_order)
        preview_missing = self._required_minus_delivered(preview_order)

        # What is already carried counts towards both "don't over-pick active" and preview prefetch.
        carried_counts = Counter()
        for b in bots:
            carried_counts.update(b.get("inventory", []))

        active_pick_need = Counter(active_missing)
        for t, c in carried_counts.items():
            if active_pick_need[t] > 0:
                active_pick_need[t] = max(0, active_pick_need[t] - c)

        preview_pick_need = Counter(preview_missing)
        for t, c in carried_counts.items():
            if preview_pick_need[t] > 0:
                preview_pick_need[t] = max(0, preview_pick_need[t] - c)

        # Delivery usefulness allocation (which bots currently carry active-useful items)
        useful_delivery_alloc, _ = self._allocate_delivery_slots(bots, active_missing)

        # Distance maps (static geometry only)
        drop_dists = self._dist_from(drop_off)
        bot_dists: dict[int, dict[tuple[int, int], int]] = {
            b["id"]: self._dist_from(tuple(b["position"])) for b in bots
        }

        # Build item metadata once
        item_meta: dict[str, dict] = {}
        for it in items:
            pos = tuple(it["position"])
            approaches = [p for p in self._neighbors_static(pos) if p in self._walkable_cells]
            if not approaches:
                continue
            # Static distance from item approach to dropoff (for batching / endgame)
            d_to_drop = min(drop_dists.get(a, 10**9) for a in approaches)
            item_meta[it["id"]] = {
                "id": it["id"],
                "type": it["type"],
                "position": pos,
                "approaches": approaches,
                "dist_item_to_drop": d_to_drop,
            }

        # Traffic regions near dropoff
        ring1 = {p for p in self._neighbors_static(drop_off) if p in self._walkable_cells}
        ring2 = {
            p
            for p in self._walkable_cells
            if p != drop_off and p not in ring1 and self._manhattan(p, drop_off) <= 3
        }

        # Identify delivery queue and blockers
        delivery_bots = []
        for b in bots:
            bid = b["id"]
            useful_count = self._delivery_count(useful_delivery_alloc.get(bid, Counter()))
            if useful_count > 0:
                delivery_bots.append((b, useful_count))
        delivery_ranked = sorted(
            [b for b, _ in delivery_bots],
            key=lambda b: (
                0 if tuple(b["position"]) == drop_off else 1,
                drop_dists.get(tuple(b["position"]), 10**9),
                b["id"],
            ),
        )
        queue_to_dropoff = {b["id"] for b in delivery_ranked[:2]}
        stage_near_dropoff = {b["id"] for b in delivery_ranked[2:5]}

        clear_blockers: set[int] = set()
        if delivery_ranked:
            for b in bots:
                bid = b["id"]
                pos = tuple(b["position"])
                useful_count = self._delivery_count(useful_delivery_alloc.get(bid, Counter()))
                if useful_count == 0 and (pos == drop_off or pos in ring1):
                    clear_blockers.add(bid)

        # Build active and preview pick assignments using actual path costs.
        # We assign specific item IDs, not just types.
        target_locks_by_other: set[str] = {
            item_id for item_id in self.bot_targets.values() if item_id in items_by_id
        }
        assignments: dict[int, tuple[str, str]] = {}  # bot_id -> (kind, item_id)
        reserved_items_for_assignment: set[str] = set()

        # Eligibility and budgets
        bots_by_id = {b["id"]: b for b in bots}
        rounds_left = max(0, 300 - max(0, round_number))
        active_need_total = int(sum(active_pick_need.values()))

        # Phase 1: assign ACTIVE items
        active_items_remaining = Counter(active_pick_need)
        for _ in range(len(bots) * 2):
            best = None  # (score, cost, bot_id, item_id)
            for b in bots:
                bid = b["id"]
                if bid in assignments:
                    continue
                if bid in clear_blockers:
                    continue
                if len(b["inventory"]) >= 3:
                    continue
                if bid in stage_near_dropoff and self._delivery_count(useful_delivery_alloc.get(bid, Counter())) > 0:
                    # keep some deliverers flowing instead of detouring far
                    continue

                # If bot already carries useful items, only take a batching detour when cheap.
                carrying_useful = self._delivery_count(useful_delivery_alloc.get(bid, Counter())) > 0
                pos = tuple(b["position"])
                dmap = bot_dists[bid]
                to_drop = drop_dists.get(pos, 10**9)

                # Prefer existing lock if still valid
                lock_id = self.bot_targets.get(bid)
                lock_kind = self.bot_target_kind.get(bid, "active")
                candidate_ids = []
                if (
                    lock_id
                    and lock_kind == "active"
                    and lock_id in item_meta
                    and active_items_remaining[item_meta[lock_id]["type"]] > 0
                    and lock_id not in reserved_items_for_assignment
                    and not self._item_pick_blocked(lock_id, round_number)
                ):
                    candidate_ids.append(lock_id)

                for iid, meta in item_meta.items():
                    if iid == lock_id:
                        continue
                    if iid in reserved_items_for_assignment:
                        continue
                    if iid in target_locks_by_other and self.bot_targets.get(bid) != iid:
                        continue
                    if active_items_remaining[meta["type"]] <= 0:
                        continue
                    if self._item_pick_blocked(iid, round_number):
                        continue
                    candidate_ids.append(iid)

                # Trim search for speed by rough geometric closeness
                # (bot_dists lookup already cheap, but this avoids huge loops when item count is large)
                # We sort only a short shortlist.
                scored_local = []
                for iid in candidate_ids:
                    meta = item_meta[iid]
                    d_to_item = self._best_approach_dist(dmap, meta["approaches"])
                    if d_to_item >= 10**8:
                        continue
                    # Endgame pruning for far tasks
                    est_total = d_to_item + 1 + meta["dist_item_to_drop"] + 1
                    if rounds_left < est_total + 2:
                        continue
                    penalty = 0
                    if carrying_useful:
                        # Prefer delivering if detour is not clearly worth it
                        if d_to_item + meta["dist_item_to_drop"] > to_drop + 6:
                            penalty += 25
                        else:
                            penalty += 6
                    # discourage bots sitting on/near dropoff from going too far if queue exists
                    if bid in queue_to_dropoff and carrying_useful:
                        penalty += 12
                    # slight preference for keeping progressing bots on same target
                    if self.bot_targets.get(bid) == iid:
                        penalty -= 4
                    scored_local.append((d_to_item + penalty, iid))
                if not scored_local:
                    continue
                scored_local.sort(key=lambda t: (t[0], t[1]))
                cost, iid = scored_local[0]

                # Score favours short distance and bots with empty inventory.
                inv_penalty = len(b["inventory"]) * 2
                score = 1000 - (cost * 10) - inv_penalty
                if best is None or score > best[0] or (score == best[0] and cost < best[1]):
                    best = (score, cost, bid, iid)

            if best is None:
                break
            _, _, bid, iid = best
            t = item_meta[iid]["type"]
            if active_items_remaining[t] <= 0:
                continue
            assignments[bid] = ("active", iid)
            reserved_items_for_assignment.add(iid)
            active_items_remaining[t] -= 1

        # Phase 2: assign PREVIEW items to remaining idle capacity (aggressive but bounded)
        preview_enabled = round_number < 265
        if preview_enabled and sum(preview_pick_need.values()) > 0:
            preview_items_remaining = Counter(preview_pick_need)

            # Dynamic cap: keep enough bots for active and delivery, use the rest for preview.
            active_and_delivery_pressure = active_need_total + len(delivery_ranked)
            preview_bot_cap = max(1, min(len(bots) - 1, len(bots) - min(len(bots), active_and_delivery_pressure)))
            assigned_preview_count = 0

            for _ in range(len(bots) * 2):
                if assigned_preview_count >= preview_bot_cap and active_need_total > 0:
                    break
                best = None  # (score, cost, bot_id, item_id)
                for b in bots:
                    bid = b["id"]
                    if bid in assignments:
                        continue
                    if bid in clear_blockers:
                        continue
                    if len(b["inventory"]) >= 3:
                        continue
                    if self._delivery_count(useful_delivery_alloc.get(bid, Counter())) > 0:
                        continue

                    # If carrying non-useful preview already, prioritise continuing that role.
                    dmap = bot_dists[bid]
                    carries_previewish = any(preview_missing.get(it, 0) > 0 for it in b["inventory"])
                    lock_id = self.bot_targets.get(bid)
                    lock_kind = self.bot_target_kind.get(bid, "preview")

                    candidate_ids = []
                    if (
                        lock_id
                        and lock_kind == "preview"
                        and lock_id in item_meta
                        and preview_items_remaining[item_meta[lock_id]["type"]] > 0
                        and lock_id not in reserved_items_for_assignment
                        and not self._item_pick_blocked(lock_id, round_number)
                    ):
                        candidate_ids.append(lock_id)

                    for iid, meta in item_meta.items():
                        if iid == lock_id:
                            continue
                        if iid in reserved_items_for_assignment:
                            continue
                        if iid in target_locks_by_other and self.bot_targets.get(bid) != iid:
                            continue
                        if preview_items_remaining[meta["type"]] <= 0:
                            continue
                        if self._item_pick_blocked(iid, round_number):
                            continue
                        candidate_ids.append(iid)

                    if not candidate_ids:
                        continue

                    scored_local = []
                    for iid in candidate_ids:
                        meta = item_meta[iid]
                        d_to_item = self._best_approach_dist(dmap, meta["approaches"])
                        if d_to_item >= 10**8:
                            continue
                        # Preview can be farther, but not absurdly far near endgame
                        if rounds_left < (d_to_item + 8):
                            continue
                        penalty = 0
                        if not carries_previewish and active_need_total > 0:
                            penalty += 4
                        if self.bot_targets.get(bid) == iid:
                            penalty -= 3
                        scored_local.append((d_to_item + penalty, iid))
                    if not scored_local:
                        continue
                    scored_local.sort(key=lambda t: (t[0], t[1]))
                    cost, iid = scored_local[0]
                    score = 500 - (cost * 8) - len(b["inventory"])
                    if carries_previewish:
                        score += 12
                    if best is None or score > best[0] or (score == best[0] and cost < best[1]):
                        best = (score, cost, bid, iid)

                if best is None:
                    break
                _, _, bid, iid = best
                t = item_meta[iid]["type"]
                if preview_items_remaining[t] <= 0:
                    continue
                assignments[bid] = ("preview", iid)
                reserved_items_for_assignment.add(iid)
                preview_items_remaining[t] -= 1
                assigned_preview_count += 1

        # Action planning with dynamic reservations
        reserved_next: set[tuple[int, int]] = set()
        reserved_edges: set[tuple[tuple[int, int], tuple[int, int]]] = set()
        actions_by_id: dict[int, dict] = {}
        reserved_items_runtime: set[str] = set()

        # Process order: dropoffs, blockers, delivery movers, assigned pickers, then the rest.
        def prio_key(b: dict) -> tuple:
            bid = b["id"]
            pos = tuple(b["position"])
            useful_count = self._delivery_count(useful_delivery_alloc.get(bid, Counter()))
            at_drop = pos == drop_off
            has_assign = bid in assignments
            assign_kind = assignments.get(bid, ("", ""))[0]
            return (
                0 if (useful_count > 0 and at_drop) else
                1 if bid in clear_blockers else
                2 if useful_count > 0 else
                3 if (has_assign and assign_kind == "active") else
                4 if (has_assign and assign_kind == "preview") else
                5,
                drop_dists.get(pos, 10**9),
                b["id"],
            )

        for bot in sorted(bots, key=prio_key):
            bid = bot["id"]
            pos = tuple(bot["position"])
            inv = list(bot.get("inventory", []))
            useful_alloc = useful_delivery_alloc.get(bid, Counter())
            useful_count = self._delivery_count(useful_alloc)
            task_kind, task_item_id = assignments.get(bid, ("", ""))

            action = self._decide_single(
                bot=bot,
                round_number=round_number,
                state=state,
                drop_off=drop_off,
                ring1=ring1,
                ring2=ring2,
                occupied_now=occupied_now,
                reserved_next=reserved_next,
                reserved_edges=reserved_edges,
                items_by_id=items_by_id,
                item_meta=item_meta,
                active_missing=active_missing,
                active_pick_need=active_pick_need,
                preview_pick_need=preview_pick_need,
                useful_alloc=useful_alloc,
                useful_count=useful_count,
                task_kind=task_kind,
                task_item_id=task_item_id,
                clear_blocker=(bid in clear_blockers),
                queue_to_dropoff=(bid in queue_to_dropoff),
                stage_near_dropoff=(bid in stage_near_dropoff),
                reserved_items=reserved_items_runtime,
            )

            actions_by_id[bid] = action
            self.last_action[bid] = action["action"]
            if action["action"] == "pick_up":
                item_id = action.get("item_id")
                if isinstance(item_id, str) and item_id:
                    self.last_pick_item[bid] = item_id
                    reserved_items_runtime.add(item_id)
            else:
                self.last_pick_item.pop(bid, None)

        # Cleanup stale locks for vanished bots/items
        live_bot_ids = {b["id"] for b in bots}
        live_item_ids = set(items_by_id.keys())
        for bid in list(self.bot_targets.keys()):
            if bid not in live_bot_ids:
                self.bot_targets.pop(bid, None)
                self.bot_target_kind.pop(bid, None)
                continue
            iid = self.bot_targets.get(bid)
            if iid and iid not in live_item_ids:
                self.bot_targets.pop(bid, None)
                self.bot_target_kind.pop(bid, None)

        return [actions_by_id[b["id"]] for b in bots]

    def _decide_single(
        self,
        bot: dict,
        round_number: int,
        state: dict,
        drop_off: tuple[int, int],
        ring1: set[tuple[int, int]],
        ring2: set[tuple[int, int]],
        occupied_now: set[tuple[int, int]],
        reserved_next: set[tuple[int, int]],
        reserved_edges: set[tuple[tuple[int, int], tuple[int, int]]],
        items_by_id: dict[str, dict],
        item_meta: dict[str, dict],
        active_missing: Counter,
        active_pick_need: Counter,
        preview_pick_need: Counter,
        useful_alloc: Counter,
        useful_count: int,
        task_kind: str,
        task_item_id: str,
        clear_blocker: bool,
        queue_to_dropoff: bool,
        stage_near_dropoff: bool,
        reserved_items: set[str],
    ) -> dict:
        bid = bot["id"]
        pos = tuple(bot["position"])
        inv = list(bot.get("inventory", []))
        rounds_left = max(0, 300 - max(0, round_number))

        # Resolve lock validity
        if task_item_id:
            if task_item_id not in item_meta:
                task_item_id = ""
                task_kind = ""
            else:
                target_type = item_meta[task_item_id]["type"]
                if task_kind == "active" and active_pick_need[target_type] <= 0:
                    task_item_id = ""
                    task_kind = ""
                if task_kind == "preview" and preview_pick_need[target_type] <= 0:
                    task_item_id = ""
                    task_kind = ""

        # Immediate drop-off if carrying anything useful and on the cell
        if useful_count > 0 and pos == drop_off:
            # Avoid spamming drop_off if server applies one-round update lag
            if self.last_drop_round.get(bid) != round_number - 1:
                self.last_drop_round[bid] = round_number
                self.bot_targets.pop(bid, None)
                self.bot_target_kind.pop(bid, None)
                return {"bot": bid, "action": "drop_off"}

        # Clear the drop-off and ring1 for incoming deliverers
        if clear_blocker:
            # Move outward, away from dropoff, prefer ring2/outer cells
            goals = [p for p in self._neighbors_static(pos) if p in self._walkable_cells and p not in ring1 and p != drop_off]
            if not goals:
                goals = [p for p in self._neighbors_static(pos) if p in self._walkable_cells and p != drop_off]
            if goals:
                move = self._move_toward(
                    bot_id=bid,
                    start=pos,
                    goals=set(goals),
                    state=state,
                    occupied_now=occupied_now,
                    reserved_next=reserved_next,
                    reserved_edges=reserved_edges,
                    allow_occupied_goals=False,
                    relax=True,
                )
                if move["action"] != "wait":
                    return move

        # Opportunistic adjacent pick-up (active first)
        if len(inv) < 3:
            pick = self._pick_if_adjacent_scored(
                bot=bot,
                state=state,
                reserved_items=reserved_items,
                active_pick_need=active_pick_need,
                preview_pick_need=preview_pick_need,
                round_number=round_number,
                allow_preview=(round_number < 265),
            )
            if pick is not None:
                iid = pick["item_id"]
                kind = "active" if items_by_id[iid]["type"] in active_pick_need and active_pick_need[items_by_id[iid]["type"]] > 0 else "preview"
                self.bot_targets.pop(bid, None)
                self.bot_target_kind.pop(bid, None)
                return pick

        # Delivery / batching behaviour
        if useful_count > 0:
            # If bot still has free slot and active assignment is cheap, batch one more before delivery.
            if len(inv) < 3 and task_kind == "active" and task_item_id in item_meta:
                dmap = self._dist_from(pos)
                to_drop = self._dist_from(drop_off).get(pos, 10**9)
                meta = item_meta[task_item_id]
                d_to_item = self._best_approach_dist(dmap, meta["approaches"])
                est_via_item = d_to_item + 1 + meta["dist_item_to_drop"] + 1
                est_direct = to_drop + 1
                if d_to_item < 10**8 and est_via_item <= est_direct + 7 and rounds_left > est_via_item + 1:
                    act = self._move_to_item_approach(
                        bot_id=bid,
                        start=pos,
                        item_id=task_item_id,
                        item_meta=item_meta,
                        state=state,
                        occupied_now=occupied_now,
                        reserved_next=reserved_next,
                        reserved_edges=reserved_edges,
                    )
                    if act["action"] != "wait":
                        self.bot_targets[bid] = task_item_id
                        self.bot_target_kind[bid] = "active"
                        return act

            # Queue discipline near dropoff to reduce pile-ups
            if stage_near_dropoff and pos not in ring1 and pos != drop_off:
                # stage on ring2 rather than join queue immediately
                stage_goals = {p for p in ring2 if p not in reserved_next}
                if stage_goals:
                    staged = self._move_toward(
                        bot_id=bid,
                        start=pos,
                        goals=stage_goals,
                        state=state,
                        occupied_now=occupied_now,
                        reserved_next=reserved_next,
                        reserved_edges=reserved_edges,
                        allow_occupied_goals=False,
                        relax=True,
                    )
                    if staged["action"] != "wait":
                        return staged

            # Deliver now
            return self._move_toward(
                bot_id=bid,
                start=pos,
                goals={drop_off},
                state=state,
                occupied_now=occupied_now,
                reserved_next=reserved_next,
                reserved_edges=reserved_edges,
                allow_occupied_goals=True,
                relax=True,
            )

        # No useful inventory. If full of preview/non-useful, keep clear of dropoff and stage.
        if len(inv) >= 3 and useful_count == 0:
            if pos == drop_off or pos in ring1:
                outer_goals = {p for p in ring2} or {p for p in self._walkable_cells if self._manhattan(p, drop_off) >= 4}
                move = self._move_toward(
                    bot_id=bid,
                    start=pos,
                    goals=outer_goals,
                    state=state,
                    occupied_now=occupied_now,
                    reserved_next=reserved_next,
                    reserved_edges=reserved_edges,
                    allow_occupied_goals=False,
                    relax=True,
                )
                if move["action"] != "wait":
                    return move
            return self._wait_or_nudge(
                bot_id=bid,
                pos=pos,
                state=state,
                occupied_now=occupied_now,
                reserved_next=reserved_next,
                reserved_edges=reserved_edges,
            )

        # Follow assigned task if any
        if task_item_id and task_item_id in item_meta and len(inv) < 3:
            kind = task_kind
            meta = item_meta[task_item_id]
            t = meta["type"]
            if kind == "active" and active_pick_need[t] > 0 and not self._item_pick_blocked(task_item_id, round_number):
                self.bot_targets[bid] = task_item_id
                self.bot_target_kind[bid] = "active"
                return self._move_to_item_approach(
                    bot_id=bid,
                    start=pos,
                    item_id=task_item_id,
                    item_meta=item_meta,
                    state=state,
                    occupied_now=occupied_now,
                    reserved_next=reserved_next,
                    reserved_edges=reserved_edges,
                )
            if kind == "preview" and preview_pick_need[t] > 0 and round_number < 265 and not self._item_pick_blocked(task_item_id, round_number):
                self.bot_targets[bid] = task_item_id
                self.bot_target_kind[bid] = "preview"
                return self._move_to_item_approach(
                    bot_id=bid,
                    start=pos,
                    item_id=task_item_id,
                    item_meta=item_meta,
                    state=state,
                    occupied_now=occupied_now,
                    reserved_next=reserved_next,
                    reserved_edges=reserved_edges,
                )

        # Fallback: if active needed exists, chase nearest active item by real path
        if len(inv) < 3 and sum(active_pick_need.values()) > 0:
            nearest = self._nearest_item_for_needs(
                bot=bot,
                item_meta=item_meta,
                need=active_pick_need,
                round_number=round_number,
                preferred_kind="active",
                exclude_ids=reserved_items,
            )
            if nearest is not None:
                iid = nearest
                self.bot_targets[bid] = iid
                self.bot_target_kind[bid] = "active"
                return self._move_to_item_approach(
                    bot_id=bid,
                    start=pos,
                    item_id=iid,
                    item_meta=item_meta,
                    state=state,
                    occupied_now=occupied_now,
                    reserved_next=reserved_next,
                    reserved_edges=reserved_edges,
                )

        # Secondary fallback: preview prefetch
        if len(inv) < 3 and round_number < 265 and sum(preview_pick_need.values()) > 0:
            nearest = self._nearest_item_for_needs(
                bot=bot,
                item_meta=item_meta,
                need=preview_pick_need,
                round_number=round_number,
                preferred_kind="preview",
                exclude_ids=reserved_items,
            )
            if nearest is not None:
                iid = nearest
                self.bot_targets[bid] = iid
                self.bot_target_kind[bid] = "preview"
                return self._move_to_item_approach(
                    bot_id=bid,
                    start=pos,
                    item_id=iid,
                    item_meta=item_meta,
                    state=state,
                    occupied_now=occupied_now,
                    reserved_next=reserved_next,
                    reserved_edges=reserved_edges,
                )

        # Otherwise keep aisles clear and avoid ring1
        staging = self._stage_idle(
            bot_id=bid,
            pos=pos,
            drop_off=drop_off,
            ring1=ring1,
            state=state,
            occupied_now=occupied_now,
            reserved_next=reserved_next,
            reserved_edges=reserved_edges,
        )
        if staging is not None:
            return staging

        return self._wait_or_nudge(
            bot_id=bid,
            pos=pos,
            state=state,
            occupied_now=occupied_now,
            reserved_next=reserved_next,
            reserved_edges=reserved_edges,
        )

    # ---------- State tracking ----------

    def _update_static_map(self, state: dict) -> None:
        # Shelves are item positions; static across the map.
        for item in state.get("items", []):
            self.shelves.add(tuple(item["position"]))

        width = state["grid"]["width"]
        height = state["grid"]["height"]
        walls = tuple(sorted(tuple(w) for w in state["grid"]["walls"]))
        key = (width, height, walls, tuple(sorted(self.shelves)))
        if key == self._grid_cache_key:
            return

        self._grid_cache_key = key
        wall_set = set(walls)
        self._walkable_cells = set()
        for x in range(width):
            for y in range(height):
                p = (x, y)
                if p in wall_set or p in self.shelves:
                    continue
                self._walkable_cells.add(p)

        self._neighbors_cache = {}
        for p in self._walkable_cells | self.shelves | set(walls):
            self._neighbors_cache[p] = [
                n for n in self._neighbors(p)
                if 0 <= n[0] < width and 0 <= n[1] < height
            ]
        self._all_pairs_dropoff_cache = {}

    def _update_pick_retry_state(self, bots: list[dict], round_number: int) -> None:
        active_ids = {b["id"] for b in bots}
        for bot in bots:
            bot_id = bot["id"]
            prev_action = self.last_action.get(bot_id)
            prev_size = self.last_inventory_size.get(bot_id)
            current_size = len(bot.get("inventory", []))
            if prev_action == "pick_up":
                attempted_item_id = self.last_pick_item.get(bot_id)
                if attempted_item_id and prev_size is not None:
                    if current_size <= prev_size:
                        streak = self.pick_fail_streak.get(attempted_item_id, 0) + 1
                        self.pick_fail_streak[attempted_item_id] = streak
                        cooldown_rounds = min(20, 4 + ((streak - 1) * 2))
                        until_round = round_number + cooldown_rounds
                        self.pick_block_until_round[attempted_item_id] = max(
                            self.pick_block_until_round.get(attempted_item_id, -1), until_round
                        )
                        for lock_bot_id, lock_item_id in list(self.bot_targets.items()):
                            if lock_item_id == attempted_item_id:
                                self.bot_targets.pop(lock_bot_id, None)
                                self.bot_target_kind.pop(lock_bot_id, None)
                    else:
                        self.pick_fail_streak.pop(attempted_item_id, None)
                        self.pick_block_until_round.pop(attempted_item_id, None)
            self.last_inventory_size[bot_id] = current_size

        for bid in list(self.last_inventory_size.keys()):
            if bid not in active_ids:
                self.last_inventory_size.pop(bid, None)
                self.last_pick_item.pop(bid, None)

        for iid, until_round in list(self.pick_block_until_round.items()):
            if until_round < round_number:
                self.pick_block_until_round.pop(iid, None)
                self.pick_fail_streak.pop(iid, None)

    def _update_motion_state(self, bots: list[dict]) -> None:
        active_ids = {b["id"] for b in bots}
        for b in bots:
            bid = b["id"]
            pos = tuple(b["position"])
            prev_pos = self.last_observed_pos.get(bid)
            prev_action = self.last_action.get(bid)
            moved = prev_pos is None or prev_pos != pos

            if prev_action == "wait" and not moved:
                self.wait_streak[bid] = self.wait_streak.get(bid, 0) + 1
            else:
                self.wait_streak[bid] = 0

            if prev_action in {"move_up", "move_down", "move_left", "move_right"} and not moved:
                self.stuck_streak[bid] = self.stuck_streak.get(bid, 0) + 1
            else:
                self.stuck_streak[bid] = 0

            self.last_observed_pos[bid] = pos

        for bid in list(self.last_observed_pos.keys()):
            if bid not in active_ids:
                self.last_observed_pos.pop(bid, None)
                self.wait_streak.pop(bid, None)
                self.stuck_streak.pop(bid, None)
                self.last_action.pop(bid, None)
                self.bot_targets.pop(bid, None)
                self.bot_target_kind.pop(bid, None)

    def _item_pick_blocked(self, item_id: str, round_number: int) -> bool:
        until_round = self.pick_block_until_round.get(item_id)
        return until_round is not None and round_number <= until_round

    # ---------- Orders / needs ----------

    def _get_order_by_status(self, state: dict, status: str) -> Optional[dict]:
        return next((o for o in state.get("orders", []) if o.get("status") == status), None)

    def _required_minus_delivered(self, order: Optional[dict]) -> Counter:
        if order is None:
            return Counter()
        return Counter(order.get("items_required", [])) - Counter(order.get("items_delivered", []))

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
            c = Counter()
            for t in b.get("inventory", []):
                if left[t] > 0:
                    c[t] += 1
                    left[t] -= 1
            alloc[bid] = c
        return alloc, left

    # ---------- Assignment / target helpers ----------

    def _nearest_item_for_needs(
        self,
        bot: dict,
        item_meta: dict[str, dict],
        need: Counter,
        round_number: int,
        preferred_kind: str,
        exclude_ids: set[str],
    ) -> Optional[str]:
        bid = bot["id"]
        pos = tuple(bot["position"])
        dmap = self._dist_from(pos)
        lock_id = self.bot_targets.get(bid)
        lock_kind = self.bot_target_kind.get(bid)

        best_iid = None
        best_cost = 10**9

        def consider(iid: str) -> None:
            nonlocal best_iid, best_cost
            meta = item_meta.get(iid)
            if not meta:
                return
            if need[meta["type"]] <= 0:
                return
            if self._item_pick_blocked(iid, round_number):
                return
            d = self._best_approach_dist(dmap, meta["approaches"])
            if d < best_cost:
                best_cost = d
                best_iid = iid

        if lock_id and lock_kind == preferred_kind:
            consider(lock_id)

        for iid, meta in item_meta.items():
            if iid == lock_id:
                continue
            if iid in exclude_ids:
                continue
            if need[meta["type"]] <= 0:
                continue
            consider(iid)

        return best_iid

    def _pick_if_adjacent_scored(
        self,
        bot: dict,
        state: dict,
        reserved_items: set[str],
        active_pick_need: Counter,
        preview_pick_need: Counter,
        round_number: int,
        allow_preview: bool,
    ) -> Optional[dict]:
        pos = tuple(bot["position"])
        if len(bot.get("inventory", [])) >= 3:
            return None

        active_cands: list[dict] = []
        preview_cands: list[dict] = []
        for item in state.get("items", []):
            iid = item["id"]
            if iid in reserved_items:
                continue
            if self._item_pick_blocked(iid, round_number):
                continue
            if self._manhattan(pos, tuple(item["position"])) != 1:
                continue
            t = item["type"]
            if active_pick_need[t] > 0:
                active_cands.append(item)
            elif allow_preview and preview_pick_need[t] > 0:
                preview_cands.append(item)

        chosen = None
        kind = ""
        if active_cands:
            # prefer item type that is scarcer in need (higher remaining need first is simpler)
            active_cands.sort(key=lambda it: (-active_pick_need[it["type"]], it["id"]))
            chosen = active_cands[0]
            kind = "active"
        elif preview_cands:
            preview_cands.sort(key=lambda it: (-preview_pick_need[it["type"]], it["id"]))
            chosen = preview_cands[0]
            kind = "preview"

        if chosen is None:
            return None

        reserved_items.add(chosen["id"])
        if kind == "active":
            active_pick_need[chosen["type"]] = max(0, active_pick_need[chosen["type"]] - 1)
        else:
            preview_pick_need[chosen["type"]] = max(0, preview_pick_need[chosen["type"]] - 1)
        return {"bot": bot["id"], "action": "pick_up", "item_id": chosen["id"]}

    # ---------- Pathfinding / movement ----------

    def _dist_from(self, start: tuple[int, int]) -> dict[tuple[int, int], int]:
        # BFS over static walkable geometry only (ignore moving bots).
        if start not in self._walkable_cells:
            # drop_off is walkable, bot positions are walkable. If not, return empty.
            return {}
        q = deque([start])
        dist = {start: 0}
        while q:
            cur = q.popleft()
            nd = dist[cur] + 1
            for nxt in self._neighbors_cache.get(cur, []):
                if nxt in dist:
                    continue
                if nxt not in self._walkable_cells:
                    continue
                dist[nxt] = nd
                q.append(nxt)
        return dist

    @staticmethod
    def _best_approach_dist(dmap: dict[tuple[int, int], int], approaches: list[tuple[int, int]]) -> int:
        best = 10**9
        for a in approaches:
            d = dmap.get(a)
            if d is not None and d < best:
                best = d
        return best if best < 10**9 else 10**9

    def _move_to_item_approach(
        self,
        bot_id: int,
        start: tuple[int, int],
        item_id: str,
        item_meta: dict[str, dict],
        state: dict,
        occupied_now: set[tuple[int, int]],
        reserved_next: set[tuple[int, int]],
        reserved_edges: set[tuple[tuple[int, int], tuple[int, int]]],
    ) -> dict:
        meta = item_meta.get(item_id)
        if meta is None:
            return {"bot": bot_id, "action": "wait"}
        return self._move_toward(
            bot_id=bot_id,
            start=start,
            goals=set(meta["approaches"]),
            state=state,
            occupied_now=occupied_now,
            reserved_next=reserved_next,
            reserved_edges=reserved_edges,
            allow_occupied_goals=False,
            relax=True,
        )

    def _move_toward(
        self,
        bot_id: int,
        start: tuple[int, int],
        goals: set[tuple[int, int]],
        state: dict,
        occupied_now: set[tuple[int, int]],
        reserved_next: set[tuple[int, int]],
        reserved_edges: set[tuple[tuple[int, int], tuple[int, int]]],
        allow_occupied_goals: bool,
        relax: bool = False,
    ) -> dict:
        if not goals:
            return {"bot": bot_id, "action": "wait"}

        blocked = (occupied_now - {start}) | reserved_next
        if allow_occupied_goals:
            blocked = blocked - goals

        step = self._bfs_first_step_dynamic(
            start=start,
            goals=goals,
            state=state,
            blocked=blocked,
            reserved_edges=reserved_edges,
        )

        if step is None and relax:
            # Try without reserved_next but keep current occupancy.
            blocked2 = occupied_now - {start}
            if allow_occupied_goals:
                blocked2 = blocked2 - goals
            step = self._bfs_first_step_dynamic(
                start=start,
                goals=goals,
                state=state,
                blocked=blocked2,
                reserved_edges=reserved_edges,
            )

        if step is None and relax and self.stuck_streak.get(bot_id, 0) >= 1:
            nudge = self._random_nudge(bot_id, start, state, occupied_now, reserved_next, reserved_edges)
            if nudge is not None:
                return nudge

        if step is None:
            return {"bot": bot_id, "action": "wait"}

        # Edge-swap prevention: reserve both destination and traversed edge.
        reserved_next.add(step)
        reserved_edges.add((start, step))
        return {"bot": bot_id, "action": self._action_from_step(start, step)}

    def _bfs_first_step_dynamic(
        self,
        start: tuple[int, int],
        goals: set[tuple[int, int]],
        state: dict,
        blocked: set[tuple[int, int]],
        reserved_edges: set[tuple[tuple[int, int], tuple[int, int]]],
    ) -> Optional[tuple[int, int]]:
        if start in goals:
            return None
        if not goals:
            return None

        width = state["grid"]["width"]
        height = state["grid"]["height"]
        walls = {tuple(w) for w in state["grid"]["walls"]}

        def passable(cur: tuple[int, int], nxt: tuple[int, int]) -> bool:
            x, y = nxt
            if not (0 <= x < width and 0 <= y < height):
                return False
            if nxt in walls or nxt in self.shelves:
                return False
            if nxt in blocked:
                return False
            # prevent head-on swap if another bot has reserved nxt->cur
            if (nxt, cur) in reserved_edges:
                return False
            return True

        q: deque[tuple[int, int]] = deque([start])
        prev: dict[tuple[int, int], Optional[tuple[int, int]]] = {start: None}

        while q:
            cur = q.popleft()
            for nxt in self._neighbors(cur):
                if nxt in prev:
                    continue
                if not passable(cur, nxt):
                    continue
                prev[nxt] = cur
                if nxt in goals:
                    return self._unwind_first_step(start, nxt, prev)
                q.append(nxt)
        return None

    def _stage_idle(
        self,
        bot_id: int,
        pos: tuple[int, int],
        drop_off: tuple[int, int],
        ring1: set[tuple[int, int]],
        state: dict,
        occupied_now: set[tuple[int, int]],
        reserved_next: set[tuple[int, int]],
        reserved_edges: set[tuple[tuple[int, int], tuple[int, int]]],
    ) -> Optional[dict]:
        # Prefer nearby walkable cells that are not on dropoff/ring1 and not too close to walls of flow.
        candidates = []
        for cell in self._walkable_cells:
            if cell == pos:
                continue
            if cell == drop_off or cell in ring1:
                continue
            d_from_pos = self._manhattan(pos, cell)
            if d_from_pos > 6:
                continue
            # Prefer center-ish but not on dropoff
            score = d_from_pos + abs(self._manhattan(cell, drop_off) - 4)
            candidates.append((score, cell))
        if not candidates:
            return None
        candidates.sort(key=lambda t: (t[0], t[1][0], t[1][1]))
        for _, goal in candidates[:8]:
            act = self._move_toward(
                bot_id=bot_id,
                start=pos,
                goals={goal},
                state=state,
                occupied_now=occupied_now,
                reserved_next=reserved_next,
                reserved_edges=reserved_edges,
                allow_occupied_goals=False,
                relax=True,
            )
            if act["action"] != "wait":
                return act
        return None

    def _wait_or_nudge(
        self,
        bot_id: int,
        pos: tuple[int, int],
        state: dict,
        occupied_now: set[tuple[int, int]],
        reserved_next: set[tuple[int, int]],
        reserved_edges: set[tuple[tuple[int, int], tuple[int, int]]],
    ) -> dict:
        if self.wait_streak.get(bot_id, 0) >= 1 or self.stuck_streak.get(bot_id, 0) >= 1:
            nudge = self._random_nudge(bot_id, pos, state, occupied_now, reserved_next, reserved_edges)
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
        reserved_edges: set[tuple[tuple[int, int], tuple[int, int]]],
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
            if (n, pos) in reserved_edges:
                continue
            options.append(n)
        if not options:
            return None

        # Move away from the dropoff when jammed if possible
        options.sort(key=lambda p: (random.random(), p[0], p[1]))
        step = options[0]
        reserved_next.add(step)
        reserved_edges.add((pos, step))
        return {"bot": bot_id, "action": self._action_from_step(pos, step)}

    # ---------- Generic helpers ----------

    def _neighbors_static(self, p: tuple[int, int]) -> list[tuple[int, int]]:
        return self._neighbors_cache.get(p, self._neighbors(p))

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
        # Deterministic order helps repeatability. Horizontal-first often behaves better in aisle maps.
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
