"""Parse raw game_state JSON dict into typed structures."""

from __future__ import annotations

from collections import Counter
from typing import Optional

from .types import Coord, Grid


def parse_grid(state: dict, existing: Optional[Grid] = None) -> Grid:
    """Parse grid from state. Reuses existing Grid if already initialized."""
    if existing is not None:
        existing.update_shelves(state["items"])
        return existing

    grid = Grid(
        width=state["grid"]["width"],
        height=state["grid"]["height"],
        walls=frozenset(tuple(w) for w in state["grid"]["walls"]),
    )
    grid.update_shelves(state["items"])
    return grid


def parse_bots(state: dict) -> list[dict]:
    """Return bots sorted by ID."""
    return sorted(state["bots"], key=lambda b: b["id"])


def parse_items(state: dict) -> dict[str, dict]:
    """Return items indexed by item ID."""
    return {item["id"]: item for item in state["items"]}


def parse_orders(state: dict) -> tuple[Optional[dict], Optional[dict]]:
    """Return (active_order, preview_order)."""
    active = next((o for o in state["orders"] if o.get("status") == "active"), None)
    preview = next((o for o in state["orders"] if o.get("status") == "preview"), None)
    return active, preview


def required_minus_delivered(order: Optional[dict]) -> Counter:
    if order is None:
        return Counter()
    return Counter(order["items_required"]) - Counter(order["items_delivered"])


def needed_counts_for_order(order: Optional[dict], bots: list[dict]) -> Counter:
    """Items still needed after subtracting what bots already carry."""
    if order is None:
        return Counter()
    needed = required_minus_delivered(order)
    carried = Counter()
    for bot in bots:
        for item_type in bot["inventory"]:
            carried[item_type] += 1
    for item_type, count in carried.items():
        if needed[item_type] > 0:
            needed[item_type] = max(0, needed[item_type] - count)
    return needed


def occupied_positions(bots: list[dict]) -> set[Coord]:
    return {tuple(b["position"]) for b in bots}
