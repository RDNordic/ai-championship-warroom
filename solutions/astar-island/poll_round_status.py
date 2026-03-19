from __future__ import annotations

import argparse
import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from astar_api import ROOT, api_get


POLL_DIR = ROOT / "artifacts" / "poller"
STATE_PATH = POLL_DIR / "latest_state.json"
EVENTS_PATH = POLL_DIR / "events.jsonl"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_json(path: Path) -> Any | None:
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def save_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=True), encoding="utf-8")


def append_event(event_type: str, payload: dict[str, Any]) -> None:
    EVENTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    record = {
        "ts": utc_now(),
        "event_type": event_type,
        "payload": payload,
    }
    with EVENTS_PATH.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, ensure_ascii=True) + "\n")


def try_get(path: str, auth: bool = False) -> tuple[bool, Any]:
    try:
        return True, api_get(path, auth=auth)
    except SystemExit as exc:
        return False, str(exc)


def active_round(rounds: list[dict[str, Any]]) -> dict[str, Any] | None:
    for item in rounds:
        if item.get("status") == "active":
            return item
    return None


def latest_round(rounds: list[dict[str, Any]]) -> dict[str, Any] | None:
    if not rounds:
        return None
    return max(rounds, key=lambda item: item.get("round_number", -1))


def analysis_snapshot(round_id: str, seeds_count: int) -> dict[str, Any]:
    results: dict[str, Any] = {}
    for seed_index in range(seeds_count):
        ok, data = try_get(f"/analysis/{round_id}/{seed_index}", auth=True)
        results[str(seed_index)] = {
            "ok": ok,
            "detail": data if ok else {"error": data},
        }
    return results


def build_state(include_analysis: bool = True) -> dict[str, Any]:
    ok_rounds, rounds_data = try_get("/rounds", auth=False)
    if not ok_rounds:
        return {
            "ts": utc_now(),
            "ok": False,
            "stage": "rounds",
            "error": rounds_data,
        }

    rounds = rounds_data
    active = active_round(rounds)
    latest = latest_round(rounds)

    ok_my_rounds, my_rounds_data = try_get("/my-rounds", auth=True)
    ok_budget, budget_data = try_get("/budget", auth=True)

    state: dict[str, Any] = {
        "ts": utc_now(),
        "ok": ok_my_rounds and ok_budget,
        "rounds": rounds,
        "active_round": active,
        "latest_round": latest,
        "my_rounds": my_rounds_data if ok_my_rounds else {"error": my_rounds_data},
        "budget": budget_data if ok_budget else {"error": budget_data},
    }

    analysis: dict[str, Any] = {"checked": False}
    target_round = active or latest
    if include_analysis and target_round and target_round.get("status") in {"scoring", "completed"}:
        seeds_count = 5
        for item in my_rounds_data if ok_my_rounds and isinstance(my_rounds_data, list) else []:
            if item.get("id") == target_round.get("id"):
                seed_scores = item.get("seed_scores")
                if isinstance(seed_scores, list) and seed_scores:
                    seeds_count = len(seed_scores)
                break
        analysis = {
            "checked": True,
            "round_id": target_round["id"],
            "results": analysis_snapshot(target_round["id"], seeds_count),
        }
    state["analysis"] = analysis
    return state


def emit_changes(prev: dict[str, Any] | None, curr: dict[str, Any]) -> None:
    if prev is None:
        append_event("poller_started", {"state_summary": summarize(curr)})
        return

    prev_active = (prev.get("active_round") or {}).get("id")
    curr_active = (curr.get("active_round") or {}).get("id")
    if prev_active != curr_active:
        append_event(
            "active_round_changed",
            {"from": prev_active, "to": curr_active, "summary": summarize(curr)},
        )

    prev_latest_status = (prev.get("latest_round") or {}).get("status")
    curr_latest_status = (curr.get("latest_round") or {}).get("status")
    prev_latest_id = (prev.get("latest_round") or {}).get("id")
    curr_latest_id = (curr.get("latest_round") or {}).get("id")
    if prev_latest_id != curr_latest_id or prev_latest_status != curr_latest_status:
        append_event(
            "latest_round_status_changed",
            {
                "from": {"id": prev_latest_id, "status": prev_latest_status},
                "to": {"id": curr_latest_id, "status": curr_latest_status},
            },
        )

    prev_budget = prev.get("budget", {})
    curr_budget = curr.get("budget", {})
    if prev_budget != curr_budget:
        append_event("budget_changed", {"from": prev_budget, "to": curr_budget})

    prev_my = prev.get("my_rounds")
    curr_my = curr.get("my_rounds")
    if prev_my != curr_my:
        append_event("my_rounds_changed", {"summary": summarize(curr)})

    prev_analysis = prev.get("analysis")
    curr_analysis = curr.get("analysis")
    if prev_analysis != curr_analysis and curr_analysis.get("checked"):
        append_event("analysis_status_changed", {"analysis": curr_analysis})

    if not prev.get("ok") and curr.get("ok"):
        append_event("auth_restored", {"summary": summarize(curr)})
    if prev.get("ok") and not curr.get("ok"):
        append_event("auth_failed", {"summary": summarize(curr)})


def summarize(state: dict[str, Any]) -> dict[str, Any]:
    latest = state.get("latest_round") or {}
    active = state.get("active_round") or {}
    budget = state.get("budget") if isinstance(state.get("budget"), dict) else {}
    return {
        "ok": state.get("ok"),
        "active_round_id": active.get("id"),
        "active_round_status": active.get("status"),
        "latest_round_id": latest.get("id"),
        "latest_round_status": latest.get("status"),
        "queries_used": budget.get("queries_used"),
        "queries_max": budget.get("queries_max"),
        "analysis_checked": (state.get("analysis") or {}).get("checked", False),
    }


def print_summary(state: dict[str, Any]) -> None:
    print(json.dumps(summarize(state), indent=2, ensure_ascii=True))


def main() -> None:
    parser = argparse.ArgumentParser(description="Read-only Astar round poller.")
    parser.add_argument("--interval-sec", type=int, default=180, help="Polling interval in seconds.")
    parser.add_argument("--once", action="store_true", help="Run a single poll and exit.")
    args = parser.parse_args()

    previous = load_json(STATE_PATH)

    while True:
        current = build_state(include_analysis=True)
        emit_changes(previous, current)
        save_json(STATE_PATH, current)
        print_summary(current)
        previous = current

        if args.once:
            return
        time.sleep(args.interval_sec)


if __name__ == "__main__":
    main()
