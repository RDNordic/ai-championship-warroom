"""Test pydantic model parsing against spec/examples/ JSON files."""

from __future__ import annotations

from typing import Any

from grocerybot.models import (
    BotResponse,
    GameOver,
    GameState,
    WaitAction,
    parse_server_message,
)

EXPECTED_BOTS = {"easy": 1, "medium": 3, "hard": 5, "expert": 10}
EXPECTED_GRID = {
    "easy": (12, 10),
    "medium": (16, 12),
    "hard": (22, 14),
    "expert": (28, 18),
}


# --- GameState parsing ---


def test_parse_game_state(game_state_data: dict[str, Any]) -> None:
    """All example game_state.json files parse without error."""
    state = GameState.model_validate(game_state_data)
    assert state.type == "game_state"
    assert 0 <= state.round <= 299
    assert state.max_rounds == 300
    assert state.score >= 0
    assert len(state.orders) >= 1


def test_game_state_bot_count(game_state_with_level: tuple[str, dict[str, Any]]) -> None:
    """Bot count matches the level specification."""
    level, data = game_state_with_level
    state = GameState.model_validate(data)
    assert len(state.bots) == EXPECTED_BOTS[level]


def test_game_state_grid_size(game_state_with_level: tuple[str, dict[str, Any]]) -> None:
    """Grid dimensions match the level specification."""
    level, data = game_state_with_level
    state = GameState.model_validate(data)
    w, h = EXPECTED_GRID[level]
    assert state.grid.width == w
    assert state.grid.height == h


def test_game_state_positions_are_tuples(easy_game_state_data: dict[str, Any]) -> None:
    """Positions are coerced from [x,y] lists to (x,y) tuples."""
    state = GameState.model_validate(easy_game_state_data)
    assert isinstance(state.drop_off, tuple)
    assert isinstance(state.bots[0].position, tuple)
    assert isinstance(state.items[0].position, tuple)
    for wall in state.grid.walls:
        assert isinstance(wall, tuple)


def test_game_state_orders(easy_game_state_data: dict[str, Any]) -> None:
    """Orders have correct structure and status values."""
    state = GameState.model_validate(easy_game_state_data)
    statuses = {o.status for o in state.orders}
    assert "active" in statuses
    for order in state.orders:
        assert order.status in ("active", "preview")
        assert len(order.items_required) > 0


def test_game_state_inventory_items(easy_game_state_data: dict[str, Any]) -> None:
    """Bot inventory contains strings and respects max length."""
    state = GameState.model_validate(easy_game_state_data)
    for bot in state.bots:
        assert len(bot.inventory) <= 3
        for item in bot.inventory:
            assert isinstance(item, str)


# --- GameOver parsing ---


def test_parse_game_over(game_over_data: dict[str, Any]) -> None:
    """All example game_over.json files parse without error."""
    result = GameOver.model_validate(game_over_data)
    assert result.type == "game_over"
    assert result.score >= 0
    assert 1 <= result.rounds_used <= 300
    assert result.items_delivered >= 0
    assert result.orders_completed >= 0


def test_game_over_score_formula(game_over_data: dict[str, Any]) -> None:
    """Score = items_delivered * 1 + orders_completed * 5."""
    result = GameOver.model_validate(game_over_data)
    expected = result.items_delivered + result.orders_completed * 5
    assert result.score == expected


# --- BotResponse parsing ---


def test_parse_response(response_data: dict[str, Any]) -> None:
    """All example response.json files parse without error."""
    response = BotResponse.model_validate(response_data)
    assert len(response.actions) >= 1


# --- parse_server_message ---


def test_parse_server_message_game_state(easy_game_state_data: dict[str, Any]) -> None:
    """parse_server_message correctly dispatches game_state."""
    msg = parse_server_message(easy_game_state_data)
    assert isinstance(msg, GameState)


def test_parse_server_message_game_over(game_over_data: dict[str, Any]) -> None:
    """parse_server_message correctly dispatches game_over."""
    msg = parse_server_message(game_over_data)
    assert isinstance(msg, GameOver)


def test_parse_server_message_unknown() -> None:
    """parse_server_message raises on unknown type."""
    import pytest

    with pytest.raises(ValueError, match="Unknown message type"):
        parse_server_message({"type": "bogus"})


# --- WaitAction default ---


def test_wait_action_default() -> None:
    """WaitAction auto-fills action='wait'."""
    w = WaitAction(bot=0)
    assert w.action == "wait"
    assert w.bot == 0


# --- BotResponse serialization ---


def test_bot_response_round_trip() -> None:
    """BotResponse serializes to valid JSON matching the protocol."""
    import json

    actions = [WaitAction(bot=0), WaitAction(bot=1)]
    response = BotResponse(actions=actions)
    data = json.loads(response.model_dump_json())
    assert "actions" in data
    assert len(data["actions"]) == 2
    assert data["actions"][0] == {"bot": 0, "action": "wait"}
