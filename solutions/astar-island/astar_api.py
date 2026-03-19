from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any
from urllib import error, request


BASE_URL = "https://api.ainm.no/astar-island"
ROOT = Path(__file__).resolve().parent
TOKEN_PATH = ROOT / ".token"
MAX_RETRIES = 5


def load_token() -> str:
    if not TOKEN_PATH.exists():
        raise SystemExit(
            "Missing solutions/astar-island/.token. "
            "Paste the access_token JWT on one line."
        )

    token = TOKEN_PATH.read_text(encoding="utf-8").strip()
    if not token:
        raise SystemExit("solutions/astar-island/.token is empty.")

    if token.startswith("access_token:"):
        token = token[len("access_token:") :].strip()

    if token.startswith('"') and token.endswith('"') and len(token) >= 2:
        token = token[1:-1].strip()

    if token.count(".") != 2:
        raise SystemExit("Token does not look like a JWT.")

    return token


def _request(path: str, method: str, auth: bool = False, payload: Any = None) -> Any:
    headers = {"Accept": "application/json"}
    data = None

    if auth:
        headers["Authorization"] = f"Bearer {load_token()}"

    if payload is not None:
        headers["Content-Type"] = "application/json"
        data = json.dumps(payload).encode("utf-8")

    req = request.Request(f"{BASE_URL}{path}", headers=headers, method=method, data=data)
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            with request.urlopen(req, timeout=60) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            if exc.code == 429 and attempt < MAX_RETRIES:
                retry_after = exc.headers.get("Retry-After")
                if retry_after and retry_after.isdigit():
                    sleep_seconds = max(1, int(retry_after))
                else:
                    sleep_seconds = min(30, 5 * attempt)
                time.sleep(sleep_seconds)
                continue
            raise SystemExit(f"HTTP {exc.code} calling {path}\n{body}") from exc
        except error.URLError as exc:
            raise SystemExit(f"Network error calling {path}: {exc}") from exc

    raise SystemExit(f"Exceeded retry budget calling {path}")


def api_get(path: str, auth: bool = False) -> Any:
    return _request(path, "GET", auth=auth)


def api_post(path: str, payload: Any, auth: bool = True) -> Any:
    return _request(path, "POST", auth=auth, payload=payload)


def get_active_round(rounds: list[dict[str, Any]]) -> dict[str, Any] | None:
    for round_info in rounds:
        if round_info.get("status") == "active":
            return round_info
    return None


def dump_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=True), encoding="utf-8")
