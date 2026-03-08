"""Logger strategy: connect, always wait, record everything.

Milestone 1 — validates connectivity, model parsing, and replay logging.
"""

from __future__ import annotations

from grocerybot.models import BotAction, GameState, WaitAction
from grocerybot.strategies.base import Strategy


class LoggerStrategy(Strategy):
    """Emit wait for every bot every round. Pure observer."""

    def on_game_start(self, state: GameState) -> None:
        pass

    def decide(self, state: GameState) -> list[BotAction]:
        return [WaitAction(bot=b.id) for b in state.bots]
