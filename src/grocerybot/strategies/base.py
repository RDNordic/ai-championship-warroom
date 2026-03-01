"""Strategy abstract base class."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from grocerybot.models import BotAction, GameState


class Strategy(ABC):
    """Base class for all bot strategies.

    Subclasses must implement:
      - on_game_start: called once on round 0 for setup (grid, caches)
      - decide: called every round, must return one action per bot
    """

    @abstractmethod
    def on_game_start(self, state: GameState) -> None:
        """Called once when the first game_state (round 0) arrives."""

    @abstractmethod
    def decide(self, state: GameState) -> list[BotAction]:
        """Return one action per bot. Must complete within the time budget."""
