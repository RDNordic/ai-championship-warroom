"""Medium strategy: replay simulated offline v5 plan, fallback to medium_v4."""

from __future__ import annotations

import os
from datetime import UTC, datetime
from pathlib import Path

from grocerybot.daily_memory import load_snapshot, snapshot_path
from grocerybot.strategies.optimized_medium_v4 import OptimizedMediumV4Strategy


class OptimizedMediumV5Strategy(OptimizedMediumV4Strategy):
    """Replay robust offline v5 plan prefix for medium, then use medium_v4."""

    def _resolve_plan_path(self) -> Path:
        if self._plan_path_override is not None:
            return self._plan_path_override
        env_path = os.environ.get("GROCERY_BOT_PLAN_PATH")
        if env_path:
            return Path(env_path)
        snap = load_snapshot(self._level)
        if snap is not None:
            date = snap.date
        else:
            date = datetime.now(tz=UTC).strftime("%Y-%m-%d")
        snap_p = snapshot_path(self._level, date)
        return snap_p.with_name(f"{self._level}_{date}_plan_v5.json")
