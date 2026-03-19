from __future__ import annotations

from fastapi.testclient import TestClient

from tripletex_agent.app import create_app


def test_health_endpoint() -> None:
    client = TestClient(create_app())

    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_solve_endpoint_returns_completed() -> None:
    client = TestClient(create_app())

    response = client.post(
        "/solve",
        json={
            "prompt": "Create a customer named ACME AS",
            "files": [],
            "tripletex_credentials": {
                "base_url": "https://tx-proxy.ainm.no/v2",
                "session_token": "secret-token",
            },
        },
    )

    assert response.status_code == 200
    assert response.json() == {"status": "completed"}
