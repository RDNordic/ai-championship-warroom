"""WebSocket game runner — extracted from run_*.py.

Usage:
    python runner.py --difficulty expert
    python runner.py --difficulty hard
"""

from __future__ import annotations

import asyncio
import argparse
import base64
import csv
import json
import os
import sys
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional
from urllib.parse import parse_qs, urlparse

from dotenv import load_dotenv
import websockets

# Add parent to path for module imports
sys.path.insert(0, str(Path(__file__).parent))

from bot import GroceryBot, load_config

BASE_DIR = Path(__file__).resolve().parent
LOG_DIR = BASE_DIR / "logs"
RUN_HISTORY_CSV = LOG_DIR / "run_history.csv"

VALID_ACTIONS = {
    "move_up", "move_down", "move_left", "move_right",
    "pick_up", "drop_off", "wait",
}

TOKEN_ENV_MAP = {
    "easy": "GROCERY_BOT_TOKEN_EASY",
    "medium": "GROCERY_BOT_TOKEN_MEDIUM",
    "hard": "GROCERY_BOT_TOKEN_HARD",
    "expert": "GROCERY_BOT_TOKEN_EXPERT",
    "nightmare": "GROCERY_BOT_TOKEN_NIGHTMARE",
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
        self._write_line({
            "event": "game_state",
            "round": state.get("round"),
            "score": state.get("score"),
            "data": state,
        })

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


async def run_game(difficulty: str) -> None:
    load_dotenv()

    env_key = TOKEN_ENV_MAP.get(difficulty)
    if not env_key:
        raise SystemExit(f"Unknown difficulty: {difficulty}")

    raw = (os.getenv(env_key) or "").strip()
    if not raw:
        raise SystemExit(f"Missing {env_key} in .env")

    ws_url, token = resolve_connection(raw)
    claims = decode_token_claims(token)

    expired, exp_dt = token_is_expired(claims)
    if expired:
        raise SystemExit(
            f"Token expired at {exp_dt.isoformat()} UTC. "
            "Click Play to get a fresh token and update .env."
        )

    config = load_config(difficulty)
    bot = GroceryBot(config)
    logger = RunLogger(claims)

    print(f"Connecting to Grocery Bot server ({difficulty})...", flush=True)
    try:
        async with websockets.connect(ws_url) as ws:
            print("Connected. Running game loop...", flush=True)
            while True:
                msg = json.loads(await ws.recv())
                if msg.get("type") == "game_over":
                    summary = logger.finish(msg)
                    print(f"Game over: score={msg.get('score', 0)} "
                          f"items={msg.get('items_delivered', 0)} "
                          f"orders={msg.get('orders_completed', 0)}")
                    print(f"Replay: {LOG_DIR / summary['replay_file']}")
                    return

                if "round" in msg and msg["round"] % 25 == 0:
                    print(f"Round {msg['round']} | score={msg.get('score', 0)}", flush=True)

                logger.log_state(msg)
                round_start = time.monotonic()

                try:
                    planned = bot.decide(msg)
                except Exception as exc:
                    print(f"Planner error round {msg.get('round')}: {exc}. Wait fallback.", flush=True)
                    planned = all_wait_actions(msg)

                if (time.monotonic() - round_start) > 1.8:
                    print(f"Round {msg.get('round')} planning >1.8s. Wait fallback.", flush=True)
                    planned = all_wait_actions(msg)

                actions = sanitize_actions(msg, planned)
                logger.log_actions(int(msg.get("round", -1)), actions)
                await ws.send(json.dumps({"actions": actions}))
    finally:
        logger.close()


def main():
    parser = argparse.ArgumentParser(description="Grocery Bot Runner")
    parser.add_argument(
        "--difficulty", "-d",
        default="expert",
        choices=list(TOKEN_ENV_MAP.keys()),
        help="Difficulty level (default: expert)",
    )
    args = parser.parse_args()
    asyncio.run(run_game(args.difficulty))


if __name__ == "__main__":
    main()
