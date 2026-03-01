"""Entry point for running a Grocery Bot game.

Usage:
    python scripts/run.py --level easy --strategy logger
    python scripts/run.py --level medium --strategy greedy
    python scripts/run.py --strategy solo --token eyJ...
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from pathlib import Path

# Add src/ to path so grocerybot package is importable
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from dotenv import load_dotenv

from grocerybot.client import DEFAULT_WS_URL, play
from grocerybot.strategies import get_strategy
from grocerybot.util.logger import console

LEVELS = ("easy", "medium", "hard", "expert")


def _resolve_token(args: argparse.Namespace) -> str | None:
    """Resolve token from --token flag, --level env var, or generic env var."""
    if args.token:
        return args.token
    if args.level:
        env_key = f"GROCERY_BOT_TOKEN_{args.level.upper()}"
        token = os.environ.get(env_key)
        if token:
            return token
    return os.environ.get("GROCERY_BOT_TOKEN")


def main() -> None:
    load_dotenv()

    parser = argparse.ArgumentParser(description="Run a Grocery Bot game")
    parser.add_argument(
        "--level",
        choices=LEVELS,
        default=None,
        help="Difficulty level — selects token from GROCERY_BOT_TOKEN_<LEVEL> env var",
    )
    parser.add_argument(
        "--strategy",
        required=True,
        help="Strategy name (e.g. logger, solo, greedy, coordinated, expert)",
    )
    parser.add_argument(
        "--token",
        default=None,
        help="JWT token directly (overrides --level env var lookup)",
    )
    parser.add_argument(
        "--ws-url",
        default=None,
        help=f"WebSocket base URL (default: {DEFAULT_WS_URL})",
    )
    args = parser.parse_args()

    token = _resolve_token(args)
    if not token:
        console.print("[red]Error:[/red] No token provided.")
        if args.level:
            env_key = f"GROCERY_BOT_TOKEN_{args.level.upper()}"
            console.print(f"Set [bold]{env_key}[/bold] in .env or pass --token")
        else:
            console.print("Pass --level <easy|medium|hard|expert> or --token <jwt>")
        sys.exit(1)

    ws_url = args.ws_url or os.environ.get("GROCERY_BOT_WS_URL", DEFAULT_WS_URL)

    strategy = get_strategy(args.strategy, level=args.level)
    level_str = f" [yellow]{args.level}[/yellow]" if args.level else ""
    console.print(f"Strategy: [bold]{args.strategy}[/bold]{level_str}")
    console.print(f"Endpoint: [dim]{ws_url}[/dim]")
    console.print()

    result = asyncio.run(play(token=token, strategy=strategy, ws_url=ws_url))
    sys.exit(0 if result.score > 0 else 1)


if __name__ == "__main__":
    main()
