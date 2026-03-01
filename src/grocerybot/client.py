"""Async WebSocket client loop with deadline enforcement.

Connects to the game server, runs the strategy, enforces the 1.8s
per-round time budget, and logs the game to a replay file.
"""

from __future__ import annotations

import json

import websockets

from grocerybot.models import (
    BotResponse,
    GameOver,
    GameState,
    WaitAction,
    parse_server_message,
)
from grocerybot.strategies.base import Strategy
from grocerybot.util.logger import ReplayWriter, log_game_over, log_round
from grocerybot.util.timer import TimeBudget

DEFAULT_WS_URL = "wss://game.ainm.no/ws"


async def play(
    token: str,
    strategy: Strategy,
    ws_url: str = DEFAULT_WS_URL,
) -> GameOver:
    """Connect to the game server and run the strategy until game over."""
    url = f"{ws_url}?token={token}"
    replay = ReplayWriter()

    try:
        async with websockets.connect(url) as ws:
            while True:
                raw = await ws.recv()
                data = json.loads(raw)
                replay.write(data)

                msg = parse_server_message(data)

                if isinstance(msg, GameOver):
                    log_game_over(
                        score=msg.score,
                        rounds_used=msg.rounds_used,
                        items_delivered=msg.items_delivered,
                        orders_completed=msg.orders_completed,
                    )
                    strategy.on_game_over(msg)
                    return msg

                state: GameState = msg

                if state.round == 0:
                    strategy.on_game_start(state)

                with TimeBudget(limit=1.8) as timer:
                    actions = strategy.decide(state)

                if timer.exceeded:
                    actions = [WaitAction(bot=b.id) for b in state.bots]

                response = BotResponse(actions=actions)
                response_data = json.loads(response.model_dump_json())
                replay.write(response_data)
                await ws.send(response.model_dump_json())

                log_round(
                    round_num=state.round,
                    max_rounds=state.max_rounds,
                    score=state.score,
                    elapsed_ms=timer.elapsed * 1000,
                    bot_count=len(state.bots),
                )
    finally:
        replay.close()
