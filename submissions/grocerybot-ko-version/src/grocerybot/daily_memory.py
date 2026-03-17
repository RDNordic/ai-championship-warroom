"""Daily memory: persist game snapshots for deterministic replay optimization.

Games on the same day + difficulty are deterministic (same grid, items, order
sequence). This module saves/loads snapshots keyed by date + level so that
subsequent runs can pre-plan optimal routes.
"""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from pathlib import Path

from pydantic import BaseModel

from grocerybot.models import GameState

logger = logging.getLogger(__name__)

DATA_DIR = Path(__file__).resolve().parent.parent.parent / "data"


class OrderRecord(BaseModel):
    """Minimal order data worth persisting (no runtime delivery state)."""

    id: str
    items_required: list[str]


class DailySnapshot(BaseModel):
    """Everything we learn from one day's games on a given difficulty."""

    date: str  # "YYYY-MM-DD"
    level: str  # "easy", "medium", etc.
    grid_width: int
    grid_height: int
    walls: list[list[int]]  # [[x, y], ...] — JSON-friendly
    drop_off: list[int]  # [x, y]
    item_type_to_positions: dict[str, list[list[int]]]  # type -> [[x,y], ...]
    orders: list[OrderRecord]


def snapshot_path(level: str, date: str) -> Path:
    """Return the path for a snapshot file: data/{level}_{date}.json."""
    return DATA_DIR / f"{level}_{date}.json"


def load_snapshot(level: str) -> DailySnapshot | None:
    """Load today's snapshot for the given level, or None if missing/stale."""
    today = datetime.now(tz=UTC).strftime("%Y-%m-%d")
    path = snapshot_path(level, today)
    if not path.exists():
        return None
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        snap = DailySnapshot.model_validate(raw)
        if snap.date != today:
            return None
        return snap
    except (json.JSONDecodeError, ValueError):
        logger.warning("Corrupt snapshot at %s, ignoring", path)
        return None


def build_snapshot_from_state(
    state: GameState, level: str,
) -> DailySnapshot:
    """Build a fresh snapshot from round-0 game state."""
    today = datetime.now(tz=UTC).strftime("%Y-%m-%d")
    type_to_pos: dict[str, list[list[int]]] = {}
    for item in state.items:
        type_to_pos.setdefault(item.type, []).append(
            [item.position[0], item.position[1]],
        )
    return DailySnapshot(
        date=today,
        level=level,
        grid_width=state.grid.width,
        grid_height=state.grid.height,
        walls=[[w[0], w[1]] for w in state.grid.walls],
        drop_off=[state.drop_off[0], state.drop_off[1]],
        item_type_to_positions=type_to_pos,
        orders=[],
    )


def save_snapshot(snap: DailySnapshot) -> None:
    """Persist snapshot to data/{level}_{date}.json."""
    try:
        DATA_DIR.mkdir(exist_ok=True)
        path = snapshot_path(snap.level, snap.date)
        path.write_text(snap.model_dump_json(indent=2), encoding="utf-8")
    except OSError:
        logger.warning("Failed to save snapshot", exc_info=True)


def merge_orders(
    snap: DailySnapshot, seen_orders: list[OrderRecord],
) -> DailySnapshot:
    """Add newly seen orders to the snapshot (deduplicated by id)."""
    existing_ids = {o.id for o in snap.orders}
    new = [o for o in seen_orders if o.id not in existing_ids]
    if not new:
        return snap
    return snap.model_copy(
        update={"orders": snap.orders + new},
    )


def get_item_positions(
    snap: DailySnapshot, item_type: str,
) -> list[tuple[int, int]]:
    """Get shelf positions for an item type as tuples."""
    raw = snap.item_type_to_positions.get(item_type, [])
    return [(p[0], p[1]) for p in raw]
