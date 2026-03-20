from __future__ import annotations

import os
from pathlib import Path

from tripletex_agent.config import AppSettings


def test_app_settings_loads_from_environment(monkeypatch) -> None:
    monkeypatch.setenv("TRIPLETEX_BASE_URL", "https://kkpqfuj-amager.tripletex.dev/v2")
    monkeypatch.setenv("TRIPLETEX_SESSION_TOKEN", "secret-token")
    monkeypatch.setenv("PORT", "9000")

    settings = AppSettings.load()

    assert settings.tripletex_base_url == "https://kkpqfuj-amager.tripletex.dev/v2"
    assert settings.tripletex_session_token == "secret-token"
    assert settings.planner_model == "claude-haiku-4-5-20251001"
    assert settings.enable_api_call_plan is False
    assert settings.port == 9000


def test_tripletex_credentials_require_presence(monkeypatch) -> None:
    monkeypatch.delenv("TRIPLETEX_BASE_URL", raising=False)
    monkeypatch.delenv("TRIPLETEX_SESSION_TOKEN", raising=False)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "placeholder")

    settings = AppSettings(
        tripletex_base_url=None,
        tripletex_session_token=None,
        planner_model="claude-haiku-4-5-20251001",
        enable_keyword_fallback=True,
        enable_api_call_plan=False,
        api_call_plan_model="claude-haiku-4-5-20251001",
        anthropic_api_key=os.getenv("ANTHROPIC_API_KEY"),
        llm_executor_model="claude-haiku-4-5-20251001",
        enable_llm_executor=False,
        host="0.0.0.0",
        port=8000,
        log_level="INFO",
        solve_event_log_path=Path("logs/solve-events.jsonl"),
    )

    try:
        settings.tripletex_credentials()
    except ValueError as exc:
        assert "TRIPLETEX_BASE_URL" in str(exc)
    else:
        raise AssertionError("Expected missing credentials to raise ValueError")
