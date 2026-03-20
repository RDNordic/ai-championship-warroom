#!/usr/bin/env python3
"""Read-only sandbox smoke test for Tripletex credentials."""

from __future__ import annotations

import base64
import json
import sys
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from tripletex_agent.config import AppSettings  # noqa: E402


def build_auth_header(session_token: str) -> str:
    raw = f"0:{session_token}".encode("utf-8")
    return "Basic " + base64.b64encode(raw).decode("ascii")


def main() -> int:
    settings = AppSettings.load()
    credentials = settings.tripletex_credentials()

    query = urlencode(
        {
            "from": 0,
            "count": 1,
            "fields": "id,firstName,lastName,displayName",
        }
    )
    url = f"{credentials.base_url}/employee?{query}"
    request = Request(
        url,
        headers={
            "Authorization": build_auth_header(credentials.basic_auth_password()),
            "Accept": "application/json",
        },
        method="GET",
    )

    try:
        with urlopen(request, timeout=20) as response:
            body = response.read().decode("utf-8")
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        print(f"Tripletex smoke test failed with HTTP {exc.code}", file=sys.stderr)
        if detail:
            print(detail, file=sys.stderr)
        return 1
    except URLError as exc:
        print(f"Tripletex smoke test failed: {exc}", file=sys.stderr)
        return 1

    payload = json.loads(body)
    values = payload.get("values", []) if isinstance(payload, dict) else []

    print("Tripletex read-only smoke test succeeded.")
    print(f"Base URL: {credentials.base_url}")
    print(f"Employee records returned: {len(values)}")
    if values:
        first = values[0]
        identifier = first.get("id")
        display_name = first.get("displayName") or " ".join(
            part for part in [first.get("firstName"), first.get("lastName")] if part
        )
        print(f"Sample employee: id={identifier}, name={display_name}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
