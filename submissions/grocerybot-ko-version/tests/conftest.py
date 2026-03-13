"""Shared pytest fixtures — load example JSON files from spec/examples/."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import pytest

# Ensure src/ is on the path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

SPEC_EXAMPLES = Path(__file__).resolve().parent.parent / "spec" / "examples"
LEVELS = ["easy", "medium", "hard", "expert"]


def _load_json(level: str, filename: str) -> dict[str, Any]:
    path = SPEC_EXAMPLES / level / filename
    with open(path, encoding="utf-8") as f:
        return json.load(f)


@pytest.fixture(params=LEVELS)
def game_state_data(request: pytest.FixtureRequest) -> dict[str, Any]:
    """Parametrized: game_state.json for each difficulty level."""
    return _load_json(request.param, "game_state.json")


@pytest.fixture(params=LEVELS)
def game_state_with_level(request: pytest.FixtureRequest) -> tuple[str, dict[str, Any]]:
    """Parametrized: (level_name, game_state data) for each difficulty."""
    return (request.param, _load_json(request.param, "game_state.json"))


@pytest.fixture(params=LEVELS)
def response_data(request: pytest.FixtureRequest) -> dict[str, Any]:
    """Parametrized: response.json for each difficulty level."""
    return _load_json(request.param, "response.json")


@pytest.fixture(params=LEVELS)
def game_over_data(request: pytest.FixtureRequest) -> dict[str, Any]:
    """Parametrized: game_over.json for each difficulty level."""
    return _load_json(request.param, "game_over.json")


@pytest.fixture()
def easy_game_state_data() -> dict[str, Any]:
    """Easy game_state.json (non-parametrized, for targeted tests)."""
    return _load_json("easy", "game_state.json")
