from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest

from tripletex_agent.client import TripletexAPIError, TripletexClient
from tripletex_agent.runtime_context import bind_runtime_context
from tripletex_agent.solve_logging import SolveEventLogger, SolveRequestContext


def _read_events(path: Path) -> list[dict[str, object]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


@pytest.mark.asyncio
async def test_client_records_tripletex_call_event(tmp_path: Path) -> None:
    log_path = tmp_path / "logs" / "solve-events.jsonl"
    request_context = SolveRequestContext(trace_id="trace-123")

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "GET"
        assert request.url.path == "/v2/customer"
        assert request.url.params["email"] == "finance@acme.test"
        return httpx.Response(
            200,
            json={"values": [{"id": 101, "name": "ACME AS"}]},
        )

    with bind_runtime_context(
        request_context=request_context,
        event_logger=SolveEventLogger(log_path),
    ):
        async with TripletexClient(
            base_url="https://example.test/v2",
            session_token="secret-token",
            transport=httpx.MockTransport(handler),
        ) as client:
            payload = await client.get("/customer", params={"email": "finance@acme.test"})

    assert payload == {"values": [{"id": 101, "name": "ACME AS"}]}
    events = _read_events(log_path)
    assert len(events) == 1
    event = events[0]
    assert event["event"] == "tripletex_call"
    assert event["trace_id"] == "trace-123"
    assert event["call"]["method"] == "GET"
    assert event["call"]["path"] == "/customer"
    assert event["call"]["params"] == {"email": "finance@acme.test"}
    assert event["call"]["status_code"] == 200
    assert "secret-token" not in log_path.read_text(encoding="utf-8")


@pytest.mark.asyncio
async def test_client_records_failed_tripletex_call_event(tmp_path: Path) -> None:
    log_path = tmp_path / "logs" / "solve-events.jsonl"
    request_context = SolveRequestContext(trace_id="trace-456")

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "POST"
        assert request.url.path == "/v2/customer"
        return httpx.Response(
            422,
            json={"message": "Missing field"},
        )

    with bind_runtime_context(
        request_context=request_context,
        event_logger=SolveEventLogger(log_path),
    ):
        async with TripletexClient(
            base_url="https://example.test/v2",
            session_token="secret-token",
            transport=httpx.MockTransport(handler),
        ) as client:
            with pytest.raises(TripletexAPIError, match="Tripletex POST /customer failed"):
                await client.post("/customer", json_body={"name": "ACME AS"})

    events = _read_events(log_path)
    assert len(events) == 1
    event = events[0]
    assert event["event"] == "tripletex_call"
    assert event["trace_id"] == "trace-456"
    assert event["call"]["method"] == "POST"
    assert event["call"]["path"] == "/customer"
    assert event["call"]["json_body"] == {"name": "ACME AS"}
    assert event["call"]["status_code"] == 422
    assert event["call"]["response"] == {"message": "Missing field"}
