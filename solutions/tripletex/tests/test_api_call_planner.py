from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from tripletex_agent.api_call_plan import ApiCallPlan, ApiCallStep
from tripletex_agent.api_call_planner import OpenAIApiCallPlanner, build_default_api_call_planner
from tripletex_agent.config import AppSettings
from tripletex_agent.task_plan import Operation, TaskFamily, TaskPlan


class _FakeResponses:
    def __init__(self, parsed: ApiCallPlan) -> None:
        self.parsed = parsed
        self.calls: list[dict[str, object]] = []

    def parse(self, **kwargs):  # noqa: ANN003
        self.calls.append(kwargs)
        return SimpleNamespace(output_parsed=self.parsed)


class _FakeOpenAIClient:
    def __init__(self, *, parsed: ApiCallPlan) -> None:
        self.responses = _FakeResponses(parsed)


def test_build_default_api_call_planner_requires_flag_and_api_key(tmp_path: Path) -> None:
    settings = AppSettings(
        tripletex_base_url=None,
        tripletex_session_token=None,
        openai_api_key="placeholder",
        openai_model="gpt-5-mini",
        enable_api_call_plan=False,
        api_call_plan_model="gpt-5-mini",
        host="0.0.0.0",
        port=8000,
        log_level="INFO",
        solve_event_log_path=tmp_path / "solve-events.jsonl",
    )

    assert build_default_api_call_planner(settings) is None


def test_openai_api_call_planner_returns_structured_plan(monkeypatch) -> None:
    parsed = ApiCallPlan(
        task_family=TaskFamily.TRAVEL_EXPENSES,
        operation=Operation.CREATE,
        primary_goal="Register a travel expense report",
        steps=[
            ApiCallStep(
                step_id="create_report",
                purpose="Create the report",
                method="POST",
                path="/travelExpense",
            )
        ],
        confidence=0.71,
    )
    fake_client = _FakeOpenAIClient(parsed=parsed)
    monkeypatch.setattr(
        "tripletex_agent.api_call_planner.OpenAI",
        lambda api_key: fake_client,
    )

    planner = OpenAIApiCallPlanner(api_key="placeholder", model="gpt-5-mini")
    base_plan = TaskPlan(
        task_family=TaskFamily.TRAVEL_EXPENSES,
        operation=Operation.UNKNOWN,
        confidence=0.85,
    )

    result = planner.plan(
        'Registre una nota de gastos de viaje para Pablo Rodríguez',
        [],
        base_plan,
    )

    assert result == parsed
    assert len(fake_client.responses.calls) == 1
    payload = fake_client.responses.calls[0]
    assert payload["model"] == "gpt-5-mini"
    assert payload["text_format"] is ApiCallPlan
