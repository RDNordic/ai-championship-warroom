"""Patch easy plan: keep rounds 0-240 from optimizer, replace 241-299 with Log 2's actual actions."""

import json
from pathlib import Path

PLAN_PATH = Path("data/easy_2026-03-04_plan.json")

with open(PLAN_PATH, "r") as f:
    plan = json.load(f)

# Keep actions for rounds 0-240 from the plan
old_actions = plan["actions"]
kept = [a for a in old_actions if a["round"] <= 240]

# Log 2's actual actions for rounds 241-299
log2_actions = [
    {"round": 241, "bot": 0, "action": "move_right"},
    {"round": 242, "bot": 0, "action": "move_right"},
    {"round": 243, "bot": 0, "action": "pick_up", "item_type": "butter"},
    {"round": 244, "bot": 0, "action": "move_down"},
    {"round": 245, "bot": 0, "action": "move_left"},
    {"round": 246, "bot": 0, "action": "move_left"},
    {"round": 247, "bot": 0, "action": "drop_off"},
    {"round": 248, "bot": 0, "action": "move_up"},
    {"round": 249, "bot": 0, "action": "move_up"},
    {"round": 250, "bot": 0, "action": "move_up"},
    {"round": 251, "bot": 0, "action": "move_right"},
    {"round": 252, "bot": 0, "action": "move_right"},
    {"round": 253, "bot": 0, "action": "pick_up", "item_type": "cheese"},
    {"round": 254, "bot": 0, "action": "pick_up", "item_type": "cheese"},
    {"round": 255, "bot": 0, "action": "pick_up", "item_type": "cheese"},
    {"round": 256, "bot": 0, "action": "move_left"},
    {"round": 257, "bot": 0, "action": "move_left"},
    {"round": 258, "bot": 0, "action": "move_down"},
    {"round": 259, "bot": 0, "action": "move_down"},
    {"round": 260, "bot": 0, "action": "move_down"},
    {"round": 261, "bot": 0, "action": "drop_off"},
    {"round": 262, "bot": 0, "action": "move_up"},
    {"round": 263, "bot": 0, "action": "move_right"},
    {"round": 264, "bot": 0, "action": "move_right"},
    {"round": 265, "bot": 0, "action": "move_right"},
    {"round": 266, "bot": 0, "action": "move_right"},
    {"round": 267, "bot": 0, "action": "move_right"},
    {"round": 268, "bot": 0, "action": "move_right"},
    {"round": 269, "bot": 0, "action": "pick_up", "item_type": "milk"},
    {"round": 270, "bot": 0, "action": "pick_up", "item_type": "milk"},
    {"round": 271, "bot": 0, "action": "move_left"},
    {"round": 272, "bot": 0, "action": "move_left"},
    {"round": 273, "bot": 0, "action": "pick_up", "item_type": "yogurt"},
    {"round": 274, "bot": 0, "action": "move_down"},
    {"round": 275, "bot": 0, "action": "move_left"},
    {"round": 276, "bot": 0, "action": "move_left"},
    {"round": 277, "bot": 0, "action": "move_left"},
    {"round": 278, "bot": 0, "action": "move_left"},
    {"round": 279, "bot": 0, "action": "drop_off"},
    {"round": 280, "bot": 0, "action": "move_up"},
    {"round": 281, "bot": 0, "action": "move_right"},
    {"round": 282, "bot": 0, "action": "move_right"},
    {"round": 283, "bot": 0, "action": "move_right"},
    {"round": 284, "bot": 0, "action": "move_right"},
    {"round": 285, "bot": 0, "action": "move_right"},
    {"round": 286, "bot": 0, "action": "move_right"},
    {"round": 287, "bot": 0, "action": "pick_up", "item_type": "milk"},
    {"round": 288, "bot": 0, "action": "pick_up", "item_type": "milk"},
    {"round": 289, "bot": 0, "action": "move_left"},
    {"round": 290, "bot": 0, "action": "move_left"},
    {"round": 291, "bot": 0, "action": "pick_up", "item_type": "yogurt"},
    {"round": 292, "bot": 0, "action": "move_down"},
    {"round": 293, "bot": 0, "action": "move_left"},
    {"round": 294, "bot": 0, "action": "move_left"},
    {"round": 295, "bot": 0, "action": "move_left"},
    {"round": 296, "bot": 0, "action": "move_left"},
    {"round": 297, "bot": 0, "action": "drop_off"},
    {"round": 298, "bot": 0, "action": "move_up"},
    {"round": 299, "bot": 0, "action": "move_right"},
]

new_actions = kept + log2_actions

# Update summary to fit within 300 rounds
plan["summary"]["optimal_rounds"] = 300
plan["summary"]["rounds_saved"] = 0
plan["summary"]["optimal_rounds_for_current_run_orders"] = 300
plan["summary"]["rounds_saved_for_current_run_orders"] = 0
plan["meta"]["orders_planned"] = 17

# Keep orders 0-13 (all complete by round 240), replace 14-16 with Log 2 timings
updated_orders = [o for o in plan["orders"] if o["order_index"] <= 13]
updated_orders.append({
    "order_index": 14, "order_id": "order_14",
    "items_required": ["yogurt", "cheese", "butter"],
    "start_inventory": [], "end_inventory": [],
    "start_round": 240, "end_round_exclusive": 262, "ticks_used": 22,
})
updated_orders.append({
    "order_index": 15, "order_id": "order_15",
    "items_required": ["milk", "cheese", "milk", "cheese"],
    "start_inventory": [], "end_inventory": [],
    "start_round": 262, "end_round_exclusive": 280, "ticks_used": 18,
})
updated_orders.append({
    "order_index": 16, "order_id": "order_16",
    "items_required": ["milk", "yogurt", "milk", "yogurt"],
    "start_inventory": [], "end_inventory": [],
    "start_round": 280, "end_round_exclusive": 298, "ticks_used": 18,
})
plan["orders"] = updated_orders
plan["actions"] = new_actions

with open(PLAN_PATH, "w") as f:
    json.dump(plan, f, indent=2)

print(f"Plan updated: {len(new_actions)} actions (rounds 0-{new_actions[-1]['round']})")
print(f"Orders: {len(updated_orders)}")
