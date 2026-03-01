"""Pydantic v2 models for the Grocery Bot WebSocket protocol.

Source of truth: spec/schemas_global.json
"""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, Field, field_validator

Position = tuple[int, int]


def _coerce_pos(v: object) -> tuple[int, int]:
    """Convert [x, y] JSON list to (x, y) tuple."""
    if isinstance(v, (list, tuple)) and len(v) == 2:
        return (int(v[0]), int(v[1]))
    msg = f"Expected [x, y], got {v!r}"
    raise ValueError(msg)


class Grid(BaseModel):
    width: int
    height: int
    walls: list[Position]

    @field_validator("walls", mode="before")
    @classmethod
    def _coerce_walls(cls, v: object) -> list[tuple[int, int]]:
        if isinstance(v, list):
            return [_coerce_pos(w) for w in v]
        msg = f"Expected list of positions, got {type(v)}"
        raise ValueError(msg)


class Bot(BaseModel):
    id: int
    position: Position
    inventory: list[str]

    @field_validator("position", mode="before")
    @classmethod
    def _coerce_position(cls, v: object) -> tuple[int, int]:
        return _coerce_pos(v)


class Item(BaseModel):
    id: str
    type: str
    position: Position

    @field_validator("position", mode="before")
    @classmethod
    def _coerce_position(cls, v: object) -> tuple[int, int]:
        return _coerce_pos(v)


class Order(BaseModel):
    id: str
    items_required: list[str]
    items_delivered: list[str]
    complete: bool
    status: Literal["active", "preview"]


class GameState(BaseModel):
    type: Literal["game_state"]
    round: int = Field(ge=0, le=299)
    max_rounds: int = 300
    grid: Grid
    bots: list[Bot] = Field(min_length=1, max_length=10)
    items: list[Item]
    orders: list[Order] = Field(min_length=1, max_length=2)
    drop_off: Position
    score: int = Field(ge=0)
    active_order_index: int = Field(ge=0)
    total_orders: int = Field(ge=1)

    @field_validator("drop_off", mode="before")
    @classmethod
    def _coerce_drop_off(cls, v: object) -> tuple[int, int]:
        return _coerce_pos(v)


class GameOver(BaseModel):
    type: Literal["game_over"]
    score: int = Field(ge=0)
    rounds_used: int = Field(ge=1, le=300)
    items_delivered: int = Field(ge=0)
    orders_completed: int = Field(ge=0)


# --- Actions (outbound) ---


class MoveAction(BaseModel):
    bot: int = Field(ge=0)
    action: Literal["move_up", "move_down", "move_left", "move_right"]


class PickUpAction(BaseModel):
    bot: int = Field(ge=0)
    action: Literal["pick_up"]
    item_id: str


class DropOffAction(BaseModel):
    bot: int = Field(ge=0)
    action: Literal["drop_off"]


class WaitAction(BaseModel):
    bot: int = Field(ge=0)
    action: Literal["wait"] = "wait"


BotAction = Annotated[
    MoveAction | PickUpAction | DropOffAction | WaitAction,
    Field(discriminator="action"),
]


class BotResponse(BaseModel):
    actions: list[
        Annotated[
            MoveAction | PickUpAction | DropOffAction | WaitAction,
            Field(discriminator="action"),
        ]
    ] = Field(min_length=1, max_length=10)


# --- Inbound message parsing ---

ServerMessage = GameState | GameOver


def parse_server_message(data: dict[str, object]) -> ServerMessage:
    """Parse a raw JSON dict into GameState or GameOver."""
    msg_type = data.get("type")
    if msg_type == "game_state":
        return GameState.model_validate(data)
    if msg_type == "game_over":
        return GameOver.model_validate(data)
    msg = f"Unknown message type: {msg_type}"
    raise ValueError(msg)
