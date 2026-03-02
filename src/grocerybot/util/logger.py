"""Structured logging and replay file writer.

Writes game state + actions to .jsonl for post-game analysis.
Rich console output for live monitoring.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from rich.console import Console

console = Console()


class ReplayWriter:
    """Appends JSON objects to a .jsonl replay file, one per line."""

    def __init__(self, path: Path | None = None, level: str | None = None) -> None:
        if path is None:
            ts = datetime.now(tz=UTC).strftime("%Y%m%d_%H%M%S")
            level_part = (level or "unknown").lower()
            path = Path(f"game_{level_part}_{ts}.jsonl")
        self.path = path
        self._file = open(path, "a", encoding="utf-8")  # noqa: SIM115

    def write(self, data: dict[str, Any]) -> None:
        """Write a single JSON object as one line."""
        self._file.write(json.dumps(data, separators=(",", ":")) + "\n")
        self._file.flush()

    def close(self) -> None:
        self._file.close()


def log_round(
    round_num: int,
    max_rounds: int,
    score: int,
    elapsed_ms: float,
    bot_count: int,
) -> None:
    """Print a concise round summary to the console."""
    console.print(
        f"[dim]R[/dim] {round_num:>3}/{max_rounds}"
        f"  [green]score[/green] {score:>4}"
        f"  [cyan]{elapsed_ms:>6.1f}ms[/cyan]"
        f"  [dim]bots={bot_count}[/dim]"
    )


def log_game_over(
    score: int,
    rounds_used: int,
    items_delivered: int,
    orders_completed: int,
) -> None:
    """Print game-over summary."""
    console.print()
    console.rule("[bold red]Game Over[/bold red]")
    console.print(f"  Score:            [bold]{score}[/bold]")
    console.print(f"  Rounds used:      {rounds_used}")
    console.print(f"  Items delivered:  {items_delivered}")
    console.print(f"  Orders completed: {orders_completed}")
    console.print()
