from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from urllib import error, request


BASE_URL = "https://api.ainm.no/astar-island"
ROOT = Path(__file__).resolve().parent
TOKEN_PATH = ROOT / ".token"


def load_token() -> str:
    if not TOKEN_PATH.exists():
        raise SystemExit(
            "Missing solutions/astar-island/.token. "
            "Copy .token.example to .token and paste the JWT on one line."
        )

    token = TOKEN_PATH.read_text(encoding="utf-8").strip()
    if not token:
        raise SystemExit("solutions/astar-island/.token is empty.")

    if token.startswith("access_token:"):
        token = token[len("access_token:") :].strip()

    if token.startswith('"') and token.endswith('"') and len(token) >= 2:
        token = token[1:-1].strip()

    if "." not in token:
        raise SystemExit("Token does not look like a JWT.")

    return token


def api_get(path: str, auth: bool = False) -> Any:
    headers = {"Accept": "application/json"}
    if auth:
        headers["Authorization"] = f"Bearer {load_token()}"

    req = request.Request(f"{BASE_URL}{path}", headers=headers, method="GET")
    try:
        with request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise SystemExit(f"HTTP {exc.code} calling {path}\n{body}") from exc
    except error.URLError as exc:
        raise SystemExit(f"Network error calling {path}: {exc}") from exc


def print_json(data: Any) -> None:
    print(json.dumps(data, indent=2, ensure_ascii=True))


def get_active_round(rounds: list[dict[str, Any]]) -> dict[str, Any] | None:
    for round_info in rounds:
        if round_info.get("status") == "active":
            return round_info
    return None


def summarize_predictions(predictions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    summary: list[dict[str, Any]] = []
    for item in predictions:
        summary.append(
            {
                "seed_index": item.get("seed_index"),
                "score": item.get("score"),
                "submitted_at": item.get("submitted_at"),
            }
        )
    return summary


def main() -> None:
    rounds = api_get("/rounds", auth=False)
    active_round = get_active_round(rounds)

    print("Rounds:")
    print_json(rounds)
    print()

    if not active_round:
        print("No active round found.")
        return

    round_id = active_round["id"]
    print(f"Active round: {round_id}")
    print()

    detail = api_get(f"/rounds/{round_id}", auth=False)
    print("Round detail:")
    print_json(detail)
    print()

    budget = api_get("/budget", auth=True)
    print("Team budget:")
    print_json(budget)
    print()

    predictions = api_get(f"/my-predictions/{round_id}", auth=True)
    print("Team predictions for active round:")
    print_json(summarize_predictions(predictions))


if __name__ == "__main__":
    main()
