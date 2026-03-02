"""Parse JSONL game replay logs into structured data."""

import json
from pathlib import Path
from dataclasses import dataclass, field


@dataclass
class GameConfig:
    width: int
    height: int
    walls: set  # set of (x,y) tuples
    items: list  # [{"id": str, "type": str, "position": (x,y)}]
    drop_off: tuple  # (x,y)
    max_rounds: int
    total_orders: int
    num_bots: int
    bot_start_positions: list  # [(x,y), ...]


@dataclass
class OrderInfo:
    id: str
    items_required: list  # ["yogurt", "milk", ...]
    first_seen_round: int


@dataclass
class RoundEvent:
    round: int
    game_state: dict  # raw state data
    actions: list  # [{"bot": int, "action": str, ...}]


@dataclass
class ParsedGame:
    config: GameConfig
    rounds: list  # [RoundEvent, ...]
    orders_seen: list  # [OrderInfo, ...] in order of appearance
    final_score: int
    rounds_used: int
    items_delivered: int
    orders_completed: int
    max_inventory_observed: int


def parse_replay(path: str | Path) -> ParsedGame:
    """Parse a .jsonl replay file into structured data."""
    path = Path(path)
    events = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if line:
                events.append(json.loads(line))

    # Extract config from round 0
    first_state = None
    for ev in events:
        if ev["event"] == "game_state":
            first_state = ev["data"]
            break

    grid = first_state["grid"]
    walls = {tuple(w) for w in grid["walls"]}
    items = [
        {"id": it["id"], "type": it["type"], "position": tuple(it["position"])}
        for it in first_state["items"]
    ]

    config = GameConfig(
        width=grid["width"],
        height=grid["height"],
        walls=walls,
        items=items,
        drop_off=tuple(first_state["drop_off"]),
        max_rounds=first_state["max_rounds"],
        total_orders=first_state["total_orders"],
        num_bots=len(first_state["bots"]),
        bot_start_positions=[tuple(b["position"]) for b in first_state["bots"]],
    )

    # Pair up game_state + actions per round
    rounds = []
    state_by_round = {}
    actions_by_round = {}
    game_over_data = None

    for ev in events:
        if ev["event"] == "game_state":
            state_by_round[ev["round"]] = ev["data"]
        elif ev["event"] == "actions":
            actions_by_round[ev["round"]] = ev["actions"]
        elif ev["event"] == "game_over":
            game_over_data = ev["data"]

    for r in sorted(state_by_round.keys()):
        rounds.append(RoundEvent(
            round=r,
            game_state=state_by_round[r],
            actions=actions_by_round.get(r, []),
        ))

    # Track all orders seen across the game (in order of first appearance)
    orders_seen = []
    seen_ids = set()
    for rnd in rounds:
        for o in rnd.game_state["orders"]:
            if o["id"] not in seen_ids:
                seen_ids.add(o["id"])
                orders_seen.append(OrderInfo(
                    id=o["id"],
                    items_required=list(o["items_required"]),
                    first_seen_round=rnd.round,
                ))

    # Track max inventory size observed
    max_inv = 0
    for rnd in rounds:
        for bot in rnd.game_state["bots"]:
            max_inv = max(max_inv, len(bot["inventory"]))

    return ParsedGame(
        config=config,
        rounds=rounds,
        orders_seen=orders_seen,
        final_score=game_over_data["score"] if game_over_data else 0,
        rounds_used=game_over_data["rounds_used"] if game_over_data else 0,
        items_delivered=game_over_data["items_delivered"] if game_over_data else 0,
        orders_completed=game_over_data["orders_completed"] if game_over_data else 0,
        max_inventory_observed=max_inv,
    )


if __name__ == "__main__":
    import sys
    path = sys.argv[1] if len(sys.argv) > 1 else "../grocerybot-trial-vs-code/logs/game_20260301_211903.jsonl"
    game = parse_replay(path)
    print(f"Grid: {game.config.width}x{game.config.height}")
    print(f"Walls: {len(game.config.walls)}")
    print(f"Items: {len(game.config.items)}")
    print(f"Bots: {game.config.num_bots}")
    print(f"Drop-off: {game.config.drop_off}")
    print(f"Rounds: {len(game.rounds)}")
    print(f"Orders seen: {len(game.orders_seen)} / {game.config.total_orders}")
    print(f"Max inventory observed: {game.max_inventory_observed}")
    print(f"Final: score={game.final_score}, items={game.items_delivered}, orders={game.orders_completed}")
    print(f"\nOrder sequence:")
    for o in game.orders_seen:
        print(f"  {o.id}: {o.items_required} (first seen round {o.first_seen_round})")
