"""Offline game engine that simulates the Grocery Bot game rules.

Scoring formula (reverse-engineered from replays):
  - 1 point per matching item delivered to an order
  - 5 bonus points when an order is fully completed
  - On drop_off: all inventory consumed, matching items go to active order,
    overflow items cascade to the next order

Pickup rules:
  - Bot must be adjacent (Manhattan distance 1) to the item
  - Items have infinite stock (same item can be picked up multiple times)

Drop-off rules:
  - Bot must be ON the drop_off cell
  - All inventory is consumed
  - Items matching active order requirements are delivered
  - If active order completes, remaining items overflow to next order

Movement:
  - Cardinal directions only (up/down/left/right)
  - Blocked by walls and grid boundaries
  - y=0 is top, y increases downward
"""

from __future__ import annotations
from dataclasses import dataclass, field
from collections import Counter
from parser import GameConfig, OrderInfo


MOVE_DELTAS = {
    "move_up": (0, -1),
    "move_down": (0, 1),
    "move_left": (-1, 0),
    "move_right": (1, 0),
}

ITEM_SCORE = 1
ORDER_BONUS = 5


@dataclass
class BotState:
    id: int
    position: tuple  # (x, y)
    inventory: list  # [item_type, ...]

    def copy(self):
        return BotState(self.id, self.position, list(self.inventory))


@dataclass
class OrderState:
    id: str
    items_required: list  # full list of required item types
    items_delivered: list  # items delivered so far
    complete: bool = False

    @property
    def items_remaining(self) -> list:
        remaining = list(self.items_required)
        for item in self.items_delivered:
            if item in remaining:
                remaining.remove(item)
        return remaining

    def copy(self):
        return OrderState(self.id, list(self.items_required),
                          list(self.items_delivered), self.complete)


@dataclass
class GameState:
    config: GameConfig
    round: int
    score: int
    bots: list  # [BotState, ...]
    orders: list  # [OrderState, ...] all orders in sequence
    active_order_index: int
    inventory_cap: int

    def copy(self):
        return GameState(
            config=self.config,
            round=self.round,
            score=self.score,
            bots=[b.copy() for b in self.bots],
            orders=[o.copy() for o in self.orders],
            active_order_index=self.active_order_index,
            inventory_cap=self.inventory_cap,
        )


def create_initial_state(config: GameConfig, all_orders: list[OrderInfo],
                          inventory_cap: int = 3) -> GameState:
    """Create the initial game state from config and full order list."""
    bots = [
        BotState(id=i, position=pos, inventory=[])
        for i, pos in enumerate(config.bot_start_positions)
    ]
    orders = [
        OrderState(id=o.id, items_required=list(o.items_required),
                   items_delivered=[])
        for o in all_orders
    ]
    return GameState(
        config=config,
        round=0,
        score=0,
        bots=bots,
        orders=orders,
        active_order_index=0,
        inventory_cap=inventory_cap,
    )


def is_walkable(config: GameConfig, x: int, y: int) -> bool:
    """Check if a cell is within bounds and not a wall."""
    if x < 0 or x >= config.width or y < 0 or y >= config.height:
        return False
    return (x, y) not in config.walls


def get_adjacent_items(config: GameConfig, pos: tuple) -> list[dict]:
    """Get all items adjacent (Manhattan distance 1) to position."""
    x, y = pos
    adjacent = []
    for item in config.items:
        ix, iy = item["position"]
        if abs(x - ix) + abs(y - iy) == 1:
            adjacent.append(item)
    return adjacent


def apply_action(state: GameState, bot_id: int, action: dict) -> tuple[GameState, dict]:
    """Apply a single action and return (new_state, result_info).

    result_info contains:
      - valid: bool
      - score_delta: int
      - items_delivered: int
      - orders_completed: int
      - detail: str
    """
    state = state.copy()
    bot = state.bots[bot_id]
    act = action["action"]
    result = {"valid": True, "score_delta": 0, "items_delivered": 0,
              "orders_completed": 0, "detail": ""}

    if act in MOVE_DELTAS:
        dx, dy = MOVE_DELTAS[act]
        nx, ny = bot.position[0] + dx, bot.position[1] + dy
        if is_walkable(state.config, nx, ny):
            bot.position = (nx, ny)
            result["detail"] = f"moved to ({nx},{ny})"
        else:
            result["detail"] = f"blocked at ({nx},{ny})"
            # Movement into wall = no-op (bot stays)

    elif act == "pick_up":
        item_id = action.get("item_id")
        if len(bot.inventory) >= state.inventory_cap:
            result["valid"] = False
            result["detail"] = "inventory full"
        elif item_id:
            # Find the specific item
            target = None
            for it in state.config.items:
                if it["id"] == item_id:
                    target = it
                    break
            if target is None:
                result["valid"] = False
                result["detail"] = f"item {item_id} not found"
            else:
                ix, iy = target["position"]
                bx, by = bot.position
                if abs(bx - ix) + abs(by - iy) == 1:
                    bot.inventory.append(target["type"])
                    result["detail"] = f"picked up {target['type']} from {item_id}"
                else:
                    result["valid"] = False
                    result["detail"] = f"not adjacent to {item_id}"
        else:
            # No item_id specified - pick up first adjacent item
            adjacent = get_adjacent_items(state.config, bot.position)
            if adjacent:
                bot.inventory.append(adjacent[0]["type"])
                result["detail"] = f"picked up {adjacent[0]['type']}"
            else:
                result["valid"] = False
                result["detail"] = "no adjacent item"

    elif act == "drop_off":
        if bot.position != state.config.drop_off:
            result["valid"] = False
            result["detail"] = "not at drop-off"
        elif not bot.inventory:
            result["detail"] = "nothing to drop"
        else:
            # Deliver matching items to active order(s), keep non-matching
            score_delta, items_del, orders_comp, leftover = _deliver_items(
                state, list(bot.inventory)
            )
            bot.inventory = leftover
            state.score += score_delta
            result["score_delta"] = score_delta
            result["items_delivered"] = items_del
            result["orders_completed"] = orders_comp
            result["detail"] = f"+{score_delta} pts ({items_del} items, {orders_comp} orders)"

    elif act == "wait":
        result["detail"] = "waited"

    else:
        result["valid"] = False
        result["detail"] = f"unknown action: {act}"

    return state, result


def _deliver_items(state: GameState, inventory: list[str]) -> tuple[int, int, int, list[str]]:
    """Deliver inventory items to active order(s) with overflow.

    Returns (score_delta, items_delivered_count, orders_completed_count, leftover_items).
    Non-matching items are returned in leftover_items (stay in bot inventory).
    """
    total_score = 0
    total_items = 0
    total_orders = 0
    remaining = list(inventory)

    while remaining and state.active_order_index < len(state.orders):
        order = state.orders[state.active_order_index]
        if order.complete:
            state.active_order_index += 1
            continue

        needed = list(order.items_remaining)
        matched = []
        leftover = []

        for item in remaining:
            if item in needed:
                matched.append(item)
                needed.remove(item)
            else:
                leftover.append(item)

        # Deliver matched items
        for item in matched:
            order.items_delivered.append(item)
            total_score += ITEM_SCORE
            total_items += 1

        # Check if order is complete
        if not order.items_remaining:
            order.complete = True
            total_score += ORDER_BONUS
            total_orders += 1
            state.active_order_index += 1
            remaining = leftover  # overflow to next order
        else:
            remaining = leftover  # keep non-matching items
            break  # order not complete, stop

    return total_score, total_items, total_orders, remaining


def step(state: GameState, actions: list[dict]) -> tuple[GameState, list[dict]]:
    """Apply all bot actions for one round.

    Movement is resolved against start-of-round positions:
    - A bot cannot move to a cell occupied by another bot at round start.
    - Two bots moving to the same empty cell: both are blocked.

    Non-movement actions (pick_up, drop_off, wait) are applied sequentially.

    Returns (new_state, results) where results[i] corresponds to action i.
    """
    state = state.copy()
    results = []

    # Collect start-of-round bot positions
    start_positions = {b.id: b.position for b in state.bots}
    occupied = set(start_positions.values())

    # First pass: resolve movement (check collisions against start positions)
    move_targets = {}  # bot_id -> target_pos
    for action in actions:
        bot_id = action["bot"]
        act = action["action"]
        if act in MOVE_DELTAS:
            bot = state.bots[bot_id]
            dx, dy = MOVE_DELTAS[act]
            nx, ny = bot.position[0] + dx, bot.position[1] + dy
            target = (nx, ny)
            if is_walkable(state.config, nx, ny):
                # Check: is target occupied by another bot that is NOT this bot?
                other_at_target = any(
                    bid != bot_id and pos == target
                    for bid, pos in start_positions.items()
                )
                if not other_at_target:
                    move_targets[bot_id] = target

    # Check for two bots trying to move to the same cell
    target_counts = {}
    for bid, tgt in move_targets.items():
        target_counts.setdefault(tgt, []).append(bid)
    collision_bots = set()
    for tgt, bids in target_counts.items():
        if len(bids) > 1:
            collision_bots.update(bids)

    # Apply movements
    for bid, tgt in move_targets.items():
        if bid not in collision_bots:
            state.bots[bid].position = tgt

    # Second pass: apply non-movement actions
    for action in actions:
        bot_id = action["bot"]
        act = action["action"]
        result = {"valid": True, "score_delta": 0, "items_delivered": 0,
                  "orders_completed": 0, "detail": ""}

        if act in MOVE_DELTAS:
            if bot_id in move_targets and bot_id not in collision_bots:
                result["detail"] = f"moved to {move_targets[bot_id]}"
            else:
                result["detail"] = "blocked"
        elif act == "pick_up":
            _, result = apply_action(state, bot_id, action)
            # apply_action copies state, we need to apply to our state directly
            # Re-implement inline to avoid double-copy
            bot = state.bots[bot_id]
            item_id = action.get("item_id")
            if len(bot.inventory) >= state.inventory_cap:
                result = {"valid": False, "score_delta": 0, "items_delivered": 0,
                          "orders_completed": 0, "detail": "inventory full"}
            elif item_id:
                target = None
                for it in state.config.items:
                    if it["id"] == item_id:
                        target = it
                        break
                if target is None:
                    result = {"valid": False, "score_delta": 0, "items_delivered": 0,
                              "orders_completed": 0, "detail": f"item {item_id} not found"}
                else:
                    ix, iy = target["position"]
                    bx, by = bot.position
                    if abs(bx - ix) + abs(by - iy) == 1:
                        bot.inventory.append(target["type"])
                        result = {"valid": True, "score_delta": 0, "items_delivered": 0,
                                  "orders_completed": 0, "detail": f"picked up {target['type']}"}
                    else:
                        result = {"valid": False, "score_delta": 0, "items_delivered": 0,
                                  "orders_completed": 0, "detail": f"not adjacent to {item_id}"}
            else:
                adjacent = get_adjacent_items(state.config, bot.position)
                if adjacent:
                    bot.inventory.append(adjacent[0]["type"])
                    result = {"valid": True, "score_delta": 0, "items_delivered": 0,
                              "orders_completed": 0, "detail": f"picked up {adjacent[0]['type']}"}
                else:
                    result = {"valid": False, "score_delta": 0, "items_delivered": 0,
                              "orders_completed": 0, "detail": "no adjacent item"}
        elif act == "drop_off":
            bot = state.bots[bot_id]
            if bot.position != state.config.drop_off:
                result["detail"] = "not at drop-off"
                result["valid"] = False
            elif not bot.inventory:
                result["detail"] = "nothing to drop"
            else:
                score_delta, items_del, orders_comp, leftover = _deliver_items(
                    state, list(bot.inventory)
                )
                bot.inventory = leftover
                state.score += score_delta
                result["score_delta"] = score_delta
                result["items_delivered"] = items_del
                result["orders_completed"] = orders_comp
                result["detail"] = f"+{score_delta} pts"
        elif act == "wait":
            result["detail"] = "waited"
        else:
            result["valid"] = False
            result["detail"] = f"unknown action: {act}"

        results.append(result)

    state.round += 1
    return state, results
