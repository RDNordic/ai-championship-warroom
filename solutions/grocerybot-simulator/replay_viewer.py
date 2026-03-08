"""Pygame-based interactive replay viewer for Grocery Bot game logs.

Usage:
    cd solutions/grocerybot-simulator
    uv run --with pygame python replay_viewer.py ../grocerybot-trial-vs-code/logs/game_20260308_084409.jsonl
"""

from __future__ import annotations

import sys
import math
import colorsys
from pathlib import Path
from dataclasses import dataclass, field

# Add parent path so we can import parser/engine
sys.path.insert(0, str(Path(__file__).parent))

from parser import parse_replay, ParsedGame, GameConfig
from engine import MOVE_DELTAS

try:
    import pygame
    import pygame.freetype
    HAS_PYGAME = True
except ImportError:
    HAS_PYGAME = False

# ── Window layout ──────────────────────────────────────────────────────────
WIN_W, WIN_H = 1280, 800
GRID_AREA_W, GRID_AREA_H = 880, 680
PANEL_W = WIN_W - GRID_AREA_W  # 400
CONTROL_H = WIN_H - GRID_AREA_H  # 120
GRID_MARGIN = 20

# ── Colors ─────────────────────────────────────────────────────────────────
C_BG = (30, 30, 30)
C_WALL = (60, 60, 70)
C_FLOOR = (200, 200, 190)
C_SHELF = (140, 110, 80)
C_DROPOFF = (80, 180, 80)
C_PANEL_BG = (40, 40, 45)
C_PANEL_TEXT = (220, 220, 220)
C_PANEL_DIM = (140, 140, 140)
C_IDLE_RING = (255, 80, 80)
C_COLLISION = (255, 50, 50)
C_SLIDER_BG = (80, 80, 85)
C_SLIDER_FG = (120, 160, 220)
C_BTN = (70, 70, 80)
C_BTN_HOVER = (90, 90, 105)
C_WHITE = (255, 255, 255)
C_ORDER_ACTIVE = (100, 220, 100)
C_ORDER_PREVIEW = (180, 180, 100)
C_ORDER_DELIVERED = (80, 80, 80)
C_TRAIL_BASE = 0.4  # alpha factor for oldest trail dot

# ── Speed presets ──────────────────────────────────────────────────────────
SPEED_PRESETS = [1, 2, 5, 10, 20]


# ── Analytics ──────────────────────────────────────────────────────────────
@dataclass
class RoundAnalytics:
    idle_bots: list  # bot ids that waited unnecessarily
    collision_bots: list  # bot ids that collided
    score_delta: int
    order_completed: bool  # did active_order_index change this round


def compute_analytics(game: ParsedGame) -> list[RoundAnalytics]:
    """Pre-compute per-round analytics for overlays."""
    config = game.config
    item_positions = {(it["position"][0], it["position"][1]) for it in config.items}
    analytics = []

    for i, rnd in enumerate(game.rounds):
        idle_bots = []
        collision_bots = []
        score_delta = 0
        order_completed = False

        state = rnd.game_state
        bots = state["bots"]
        bot_positions = {b["id"]: tuple(b["position"]) for b in bots}

        # Score delta
        if i > 0:
            score_delta = state["score"] - game.rounds[i - 1].game_state["score"]

        # Order completion
        if i > 0:
            prev_idx = game.rounds[i - 1].game_state["active_order_index"]
            curr_idx = state["active_order_index"]
            if curr_idx > prev_idx:
                order_completed = True

        # Analyze actions from this round
        for action in rnd.actions:
            bot_id = action["bot"]
            act = action["action"]
            bx, by = bot_positions[bot_id]

            if act == "wait":
                # Check if bot has walkable adjacent cells (not wall, not shelf, not another bot)
                has_option = False
                for dx, dy in [(0, -1), (0, 1), (-1, 0), (1, 0)]:
                    nx, ny = bx + dx, by + dy
                    if (0 <= nx < config.width and 0 <= ny < config.height
                            and (nx, ny) not in config.walls
                            and (nx, ny) not in item_positions):
                        # Also not occupied by another bot
                        if not any(tuple(b["position"]) == (nx, ny)
                                   for b in bots if b["id"] != bot_id):
                            has_option = True
                            break
                if has_option:
                    idle_bots.append(bot_id)

            elif act in MOVE_DELTAS:
                # Check collision: bot issued move but didn't actually move
                if i + 1 < len(game.rounds):
                    next_bots = game.rounds[i + 1].game_state["bots"]
                    for nb in next_bots:
                        if nb["id"] == bot_id:
                            next_pos = tuple(nb["position"])
                            if next_pos == (bx, by):
                                # Bot didn't move - collision
                                collision_bots.append(bot_id)
                            break

        analytics.append(RoundAnalytics(
            idle_bots=idle_bots,
            collision_bots=collision_bots,
            score_delta=score_delta,
            order_completed=order_completed,
        ))

    return analytics


# ── Bot color generation ──────────────────────────────────────────────────
def bot_color(bot_id: int, num_bots: int) -> tuple:
    """Generate distinct color for each bot via HSV rotation."""
    if num_bots == 1:
        return (100, 180, 255)  # nice blue for single bot
    hue = (bot_id / num_bots) % 1.0
    r, g, b = colorsys.hsv_to_rgb(hue, 0.7, 0.9)
    return (int(r * 255), int(g * 255), int(b * 255))


def bot_color_dim(bot_id: int, num_bots: int, factor: float = 0.4) -> tuple:
    """Dimmed version of bot color for trails."""
    c = bot_color(bot_id, num_bots)
    return (int(c[0] * factor), int(c[1] * factor), int(c[2] * factor))


# ── Item abbreviation (matches analyze.py convention) ─────────────────────
def item_abbrev(item_type: str) -> str:
    return item_type[:2].upper()


# ── GridRenderer ───────────────────────────────────────────────────────────
class GridRenderer:
    """Renders the game grid with walls, shelves, items, bots, and overlays."""

    def __init__(self, config: GameConfig, area_w: int, area_h: int):
        self.config = config
        self.area_w = area_w
        self.area_h = area_h

        # Compute cell size to fit grid in area
        usable_w = area_w - 2 * GRID_MARGIN
        usable_h = area_h - 2 * GRID_MARGIN
        self.cell_w = usable_w // config.width
        self.cell_h = usable_h // config.height
        self.cell_size = min(self.cell_w, self.cell_h)

        # Center grid in area
        grid_pixel_w = self.cell_size * config.width
        grid_pixel_h = self.cell_size * config.height
        self.offset_x = (area_w - grid_pixel_w) // 2
        self.offset_y = (area_h - grid_pixel_h) // 2

        # Pre-compute item positions set
        self.item_positions = {}
        for it in config.items:
            pos = tuple(it["position"])
            self.item_positions[pos] = it

        # Pre-render static surface (walls, floor, shelves, grid lines)
        self.static_surface = pygame.Surface((area_w, area_h))
        self._render_static()

        # Font for cell labels
        self.font_size = max(10, self.cell_size // 3)
        self.font = pygame.font.SysFont("monospace", self.font_size, bold=True)
        self.font_sm = pygame.font.SysFont("monospace", max(8, self.cell_size // 4))

    def _render_static(self):
        """Pre-render walls, floor, shelves to a surface."""
        surf = self.static_surface
        surf.fill(C_BG)
        config = self.config
        cs = self.cell_size

        for y in range(config.height):
            for x in range(config.width):
                px = self.offset_x + x * cs
                py = self.offset_y + y * cs
                rect = pygame.Rect(px, py, cs, cs)

                if (x, y) in config.walls:
                    pygame.draw.rect(surf, C_WALL, rect)
                elif (x, y) in self.item_positions:
                    pygame.draw.rect(surf, C_SHELF, rect)
                else:
                    pygame.draw.rect(surf, C_FLOOR, rect)

                # Grid line
                pygame.draw.rect(surf, (50, 50, 55), rect, 1)

    def cell_to_pixel(self, x: int, y: int) -> tuple:
        """Get pixel center of a grid cell."""
        cs = self.cell_size
        px = self.offset_x + x * cs + cs // 2
        py = self.offset_y + y * cs + cs // 2
        return px, py

    def render(self, surface: pygame.Surface, round_event, game: ParsedGame,
               analytics: RoundAnalytics | None,
               show_trails: bool, show_idle: bool, show_collisions: bool,
               trail_history: list):
        """Render the full grid for one round."""
        # Blit static background
        surface.blit(self.static_surface, (0, 0))

        cs = self.cell_size
        state = round_event.game_state
        config = self.config

        # Draw drop-off zone
        dx, dy = config.drop_off
        drop_off_zones = state.get("drop_off_zones", None)
        if drop_off_zones:
            for dz in drop_off_zones:
                zx, zy = dz
                px = self.offset_x + zx * cs
                py = self.offset_y + zy * cs
                pygame.draw.rect(surface, C_DROPOFF, pygame.Rect(px, py, cs, cs))
                pygame.draw.rect(surface, (50, 50, 55), pygame.Rect(px, py, cs, cs), 1)
                label = self.font_sm.render("DO", True, C_WHITE)
                surface.blit(label, (px + cs // 2 - label.get_width() // 2,
                                     py + cs // 2 - label.get_height() // 2))
        else:
            px = self.offset_x + dx * cs
            py = self.offset_y + dy * cs
            pygame.draw.rect(surface, C_DROPOFF, pygame.Rect(px, py, cs, cs))
            pygame.draw.rect(surface, (50, 50, 55), pygame.Rect(px, py, cs, cs), 1)
            label = self.font_sm.render("DO", True, C_WHITE)
            surface.blit(label, (px + cs // 2 - label.get_width() // 2,
                                 py + cs // 2 - label.get_height() // 2))

        # Draw item labels on shelves
        for it in config.items:
            ix, iy = it["position"]
            px, py = self.cell_to_pixel(ix, iy)
            abbr = item_abbrev(it["type"])
            label = self.font_sm.render(abbr, True, C_WHITE)
            surface.blit(label, (px - label.get_width() // 2,
                                 py - label.get_height() // 2))

        # Draw trails
        if show_trails and trail_history:
            num_bots = config.num_bots
            trail_len = len(trail_history)
            for ti, positions in enumerate(trail_history):
                alpha = 0.3 + 0.7 * (ti / max(trail_len - 1, 1))
                for bot_id, pos in positions.items():
                    bc = bot_color(bot_id, num_bots)
                    dimmed = (int(bc[0] * alpha), int(bc[1] * alpha), int(bc[2] * alpha))
                    cx, cy = self.cell_to_pixel(pos[0], pos[1])
                    radius = max(3, cs // 8)
                    pygame.draw.circle(surface, dimmed, (cx, cy), radius)

        # Draw bots
        bots = state["bots"]
        num_bots = config.num_bots
        for b in bots:
            bid = b["id"]
            bx, by = b["position"]
            cx, cy = self.cell_to_pixel(bx, by)
            bc = bot_color(bid, num_bots)

            # Bot circle
            radius = max(6, cs // 3)
            pygame.draw.circle(surface, bc, (cx, cy), radius)
            pygame.draw.circle(surface, C_WHITE, (cx, cy), radius, 2)

            # Bot ID label
            id_label = self.font.render(str(bid), True, C_BG)
            surface.blit(id_label, (cx - id_label.get_width() // 2,
                                    cy - id_label.get_height() // 2))

            # Inventory count badge
            inv_count = len(b["inventory"])
            if inv_count > 0:
                badge_x = cx + radius - 2
                badge_y = cy - radius
                badge_r = max(5, cs // 7)
                pygame.draw.circle(surface, (220, 180, 50), (badge_x, badge_y), badge_r)
                inv_txt = self.font_sm.render(str(inv_count), True, C_BG)
                surface.blit(inv_txt, (badge_x - inv_txt.get_width() // 2,
                                       badge_y - inv_txt.get_height() // 2))

        # Overlay: idle bots
        if show_idle and analytics:
            for bid in analytics.idle_bots:
                for b in bots:
                    if b["id"] == bid:
                        cx, cy = self.cell_to_pixel(b["position"][0], b["position"][1])
                        radius = max(8, cs // 3 + 4)
                        pygame.draw.circle(surface, C_IDLE_RING, (cx, cy), radius, 3)

        # Overlay: collisions
        if show_collisions and analytics:
            for bid in analytics.collision_bots:
                for b in bots:
                    if b["id"] == bid:
                        cx, cy = self.cell_to_pixel(b["position"][0], b["position"][1])
                        size = max(6, cs // 4)
                        # Draw X
                        pygame.draw.line(surface, C_COLLISION,
                                         (cx - size, cy - size), (cx + size, cy + size), 3)
                        pygame.draw.line(surface, C_COLLISION,
                                         (cx + size, cy - size), (cx - size, cy + size), 3)


# ── InfoPanel ──────────────────────────────────────────────────────────────
class InfoPanel:
    """Right-side info panel: game info, orders, bot status."""

    def __init__(self, x: int, y: int, w: int, h: int):
        self.rect = pygame.Rect(x, y, w, h)
        self.font = pygame.font.SysFont("monospace", 14)
        self.font_sm = pygame.font.SysFont("monospace", 12)
        self.font_title = pygame.font.SysFont("monospace", 16, bold=True)

    def render(self, surface: pygame.Surface, game: ParsedGame, round_idx: int,
               speed_idx: int, analytics: list, show_order_timeline: bool):
        """Draw the info panel."""
        pygame.draw.rect(surface, C_PANEL_BG, self.rect)
        pygame.draw.line(surface, (60, 60, 65),
                         (self.rect.left, self.rect.top),
                         (self.rect.left, self.rect.bottom), 2)

        rnd = game.rounds[round_idx]
        state = rnd.game_state
        x0 = self.rect.left + 12
        y = self.rect.top + 10

        # Title
        self._text(surface, "GAME INFO", x0, y, self.font_title, C_PANEL_TEXT)
        y += 24

        # Round / Score / Speed
        self._text(surface, f"Round: {rnd.round}/{game.config.max_rounds}", x0, y)
        y += 18
        self._text(surface, f"Score: {state['score']}", x0, y)
        y += 18
        speed = SPEED_PRESETS[speed_idx]
        self._text(surface, f"Speed: {speed}x", x0, y)
        y += 18

        # Analytics for this round
        ana = analytics[round_idx] if round_idx < len(analytics) else None
        if ana and ana.score_delta:
            self._text(surface, f"Score +{ana.score_delta} this round", x0, y,
                       color=(100, 255, 100))
        y += 22

        # Separator
        pygame.draw.line(surface, (70, 70, 75), (x0, y), (self.rect.right - 12, y))
        y += 8

        # Find active and preview orders by status field
        # (the server only sends 2 orders at a time, so active_order_index
        #  is NOT an array index into this list)
        orders = state["orders"]
        active_order = None
        preview_order = None
        for o in orders:
            if o.get("status") == "active":
                active_order = o
            elif o.get("status") == "preview":
                preview_order = o

        self._text(surface, "ACTIVE ORDER", x0, y, self.font_title, C_ORDER_ACTIVE)
        y += 20

        if active_order:
            self._text(surface, f"{active_order['id']}", x0, y, color=C_ORDER_ACTIVE)
            y += 16
            # Items checklist
            required = list(active_order["items_required"])
            delivered = list(active_order.get("items_delivered", []))
            for item in required:
                if item in delivered:
                    mark = "[x]"
                    delivered.remove(item)
                    color = C_ORDER_DELIVERED
                else:
                    mark = "[ ]"
                    color = C_PANEL_TEXT
                self._text(surface, f"  {mark} {item}", x0, y, self.font_sm, color)
                y += 14
        else:
            self._text(surface, "  All orders done!", x0, y, color=C_ORDER_ACTIVE)
            y += 16

        y += 8

        # Preview order
        if preview_order:
            self._text(surface, "PREVIEW ORDER", x0, y, self.font_title, C_ORDER_PREVIEW)
            y += 20
            self._text(surface, f"{preview_order['id']}", x0, y, color=C_ORDER_PREVIEW)
            y += 16
            for item in preview_order["items_required"]:
                self._text(surface, f"  - {item}", x0, y, self.font_sm, C_PANEL_DIM)
                y += 14

        y += 12
        pygame.draw.line(surface, (70, 70, 75), (x0, y), (self.rect.right - 12, y))
        y += 8

        # Bot status table
        self._text(surface, "BOT STATUS", x0, y, self.font_title, C_PANEL_TEXT)
        y += 20

        self._text(surface, f"{'ID':<4}{'Pos':<10}{'Inv':<6}{'Action'}", x0, y,
                   self.font_sm, C_PANEL_DIM)
        y += 16

        bots = state["bots"]
        actions = rnd.actions
        action_map = {a["bot"]: a["action"] for a in actions}

        for b in bots:
            bid = b["id"]
            pos = f"({b['position'][0]},{b['position'][1]})"
            inv = str(len(b["inventory"]))
            act = action_map.get(bid, "-")
            bc = bot_color(bid, game.config.num_bots)
            self._text(surface, f"B{bid:<3}{pos:<10}{inv:<6}{act}", x0, y,
                       self.font_sm, bc)
            y += 15
            # Show inventory items
            if b["inventory"]:
                inv_str = ", ".join(b["inventory"])
                if len(inv_str) > 40:
                    inv_str = inv_str[:37] + "..."
                self._text(surface, f"     [{inv_str}]", x0, y, self.font_sm, C_PANEL_DIM)
                y += 14

        y += 12

        # Order timeline sparkline
        if show_order_timeline and analytics:
            pygame.draw.line(surface, (70, 70, 75), (x0, y), (self.rect.right - 12, y))
            y += 8
            self._text(surface, "ORDER COMPLETIONS", x0, y, self.font_title, C_PANEL_TEXT)
            y += 20

            # Draw mini timeline
            timeline_w = self.rect.width - 36
            timeline_h = 30
            timeline_rect = pygame.Rect(x0, y, timeline_w, timeline_h)
            pygame.draw.rect(surface, (50, 50, 55), timeline_rect)

            total_rounds = len(analytics)
            if total_rounds > 0:
                # Mark order completions as green ticks
                for ri, ana in enumerate(analytics):
                    if ana.order_completed:
                        tick_x = x0 + int(ri / total_rounds * timeline_w)
                        pygame.draw.line(surface, C_ORDER_ACTIVE,
                                         (tick_x, y), (tick_x, y + timeline_h), 2)

                # Current position marker
                curr_x = x0 + int(round_idx / total_rounds * timeline_w)
                pygame.draw.line(surface, C_WHITE,
                                 (curr_x, y), (curr_x, y + timeline_h), 2)

            y += timeline_h + 4
            self._text(surface, f"Orders: {state['active_order_index']}/{game.config.total_orders}",
                       x0, y, self.font_sm, C_PANEL_DIM)

    def _text(self, surface, text, x, y, font=None, color=None):
        if font is None:
            font = self.font
        if color is None:
            color = C_PANEL_TEXT
        rendered = font.render(text, True, color)
        surface.blit(rendered, (x, y))


# ── ControlBar ─────────────────────────────────────────────────────────────
class ControlBar:
    """Bottom control bar: play/pause, step, speed, slider."""

    def __init__(self, x: int, y: int, w: int, h: int, total_rounds: int):
        self.rect = pygame.Rect(x, y, w, h)
        self.total_rounds = total_rounds
        self.font = pygame.font.SysFont("monospace", 14, bold=True)
        self.font_sm = pygame.font.SysFont("monospace", 12)

        # Button rects
        btn_y = y + 15
        btn_h = 36
        btn_w = 50
        gap = 8
        bx = x + 20

        self.btn_prev = pygame.Rect(bx, btn_y, btn_w, btn_h)
        bx += btn_w + gap
        self.btn_play = pygame.Rect(bx, btn_y, btn_w + 10, btn_h)
        bx += btn_w + 10 + gap
        self.btn_next = pygame.Rect(bx, btn_y, btn_w, btn_h)
        bx += btn_w + gap + 20

        # Speed label area
        self.speed_x = bx
        bx += 80

        # Slider
        slider_margin = 20
        self.slider_x = bx
        self.slider_w = w - bx - 120
        self.slider_y = btn_y + btn_h // 2
        self.slider_h = 8

        # Round label area
        self.round_label_x = self.slider_x + self.slider_w + 15

        self.dragging_slider = False

    def render(self, surface: pygame.Surface, round_idx: int, playing: bool,
               speed_idx: int):
        """Draw control bar."""
        pygame.draw.rect(surface, C_PANEL_BG, self.rect)
        pygame.draw.line(surface, (60, 60, 65),
                         (self.rect.left, self.rect.top),
                         (self.rect.right, self.rect.top), 2)

        mouse_pos = pygame.mouse.get_pos()

        # Buttons
        self._draw_button(surface, self.btn_prev, "<", mouse_pos)
        play_text = "||" if playing else ">>"
        self._draw_button(surface, self.btn_play, play_text, mouse_pos)
        self._draw_button(surface, self.btn_next, ">", mouse_pos)

        # Speed
        speed = SPEED_PRESETS[speed_idx]
        speed_txt = self.font.render(f"Speed:{speed}x", True, C_PANEL_TEXT)
        surface.blit(speed_txt, (self.speed_x, self.rect.top + 25))

        # Slider track
        slider_rect = pygame.Rect(self.slider_x, self.slider_y - self.slider_h // 2,
                                   self.slider_w, self.slider_h)
        pygame.draw.rect(surface, C_SLIDER_BG, slider_rect, border_radius=4)

        # Slider filled portion
        if self.total_rounds > 1:
            fill_w = int(round_idx / (self.total_rounds - 1) * self.slider_w)
        else:
            fill_w = 0
        fill_rect = pygame.Rect(self.slider_x, self.slider_y - self.slider_h // 2,
                                 fill_w, self.slider_h)
        pygame.draw.rect(surface, C_SLIDER_FG, fill_rect, border_radius=4)

        # Slider handle
        handle_x = self.slider_x + fill_w
        handle_r = 8
        pygame.draw.circle(surface, C_WHITE, (handle_x, self.slider_y), handle_r)

        # Round label
        rnd_txt = self.font_sm.render(f"Rnd {round_idx}/{self.total_rounds - 1}",
                                       True, C_PANEL_TEXT)
        surface.blit(rnd_txt, (self.round_label_x, self.rect.top + 25))

        # Overlay toggles hint
        hint = self.font_sm.render("[T]rail [I]dle [C]ollision [O]rder  [Q]uit",
                                    True, C_PANEL_DIM)
        surface.blit(hint, (self.rect.left + 20, self.rect.top + 65))

    def _draw_button(self, surface, rect, text, mouse_pos):
        hover = rect.collidepoint(mouse_pos)
        color = C_BTN_HOVER if hover else C_BTN
        pygame.draw.rect(surface, color, rect, border_radius=6)
        pygame.draw.rect(surface, C_PANEL_DIM, rect, 1, border_radius=6)
        txt = self.font.render(text, True, C_WHITE)
        surface.blit(txt, (rect.centerx - txt.get_width() // 2,
                           rect.centery - txt.get_height() // 2))

    def handle_click(self, pos) -> str | None:
        """Returns action string or None."""
        if self.btn_prev.collidepoint(pos):
            return "prev"
        if self.btn_play.collidepoint(pos):
            return "toggle_play"
        if self.btn_next.collidepoint(pos):
            return "next"

        # Check slider click
        slider_area = pygame.Rect(self.slider_x - 10,
                                   self.slider_y - 15,
                                   self.slider_w + 20, 30)
        if slider_area.collidepoint(pos):
            self.dragging_slider = True
            return "slider"
        return None

    def get_slider_round(self, mouse_x: int) -> int:
        """Convert mouse x position to round index."""
        ratio = (mouse_x - self.slider_x) / max(self.slider_w, 1)
        ratio = max(0.0, min(1.0, ratio))
        return int(ratio * (self.total_rounds - 1))


# ── ReplayViewer ───────────────────────────────────────────────────────────
class ReplayViewer:
    """Main replay viewer application."""

    def __init__(self, game: ParsedGame):
        if not HAS_PYGAME:
            print("pygame is required. Install with: pip install pygame>=2.5")
            print("Or run with: uv run --with pygame python replay_viewer.py <logfile>")
            sys.exit(1)

        self.game = game
        self.total_rounds = len(game.rounds)

        pygame.init()
        pygame.display.set_caption(
            f"Grocery Bot Replay - {game.config.width}x{game.config.height} "
            f"- {game.config.num_bots} bot(s) - Score: {game.final_score}"
        )
        self.screen = pygame.display.set_mode((WIN_W, WIN_H))
        self.clock = pygame.time.Clock()

        # Components
        self.grid = GridRenderer(game.config, GRID_AREA_W, GRID_AREA_H)
        self.panel = InfoPanel(GRID_AREA_W, 0, PANEL_W, GRID_AREA_H)
        self.controls = ControlBar(0, GRID_AREA_H, WIN_W, CONTROL_H, self.total_rounds)

        # State
        self.round_idx = 0
        self.playing = False
        self.speed_idx = 0  # index into SPEED_PRESETS
        self.accumulator = 0.0  # for timing playback

        # Overlays
        self.show_trails = False
        self.show_idle = False
        self.show_collisions = False
        self.show_order_timeline = True

        # Trail history: list of dicts {bot_id: (x,y)} for last N rounds
        self.trail_history = []
        self.trail_length = 10

        # Pre-compute analytics
        print("Computing analytics...")
        self.analytics = compute_analytics(game)
        print(f"Loaded {self.total_rounds} rounds. Ready.")

    def _update_trail(self):
        """Update trail history for current round."""
        rnd = self.game.rounds[self.round_idx]
        positions = {}
        for b in rnd.game_state["bots"]:
            positions[b["id"]] = tuple(b["position"])

        # Build trail from recent rounds rather than accumulating
        self.trail_history = []
        start = max(0, self.round_idx - self.trail_length)
        for ri in range(start, self.round_idx):
            r = self.game.rounds[ri]
            pos = {}
            for b in r.game_state["bots"]:
                pos[b["id"]] = tuple(b["position"])
            self.trail_history.append(pos)

    def run(self):
        """Main event loop."""
        running = True
        while running:
            dt = self.clock.tick(60) / 1000.0  # seconds

            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    running = False
                elif event.type == pygame.KEYDOWN:
                    running = self._handle_key(event.key)
                elif event.type == pygame.MOUSEBUTTONDOWN:
                    if event.button == 1:
                        self._handle_click(event.pos)
                elif event.type == pygame.MOUSEBUTTONUP:
                    if event.button == 1:
                        self.controls.dragging_slider = False
                elif event.type == pygame.MOUSEMOTION:
                    if self.controls.dragging_slider:
                        self.round_idx = self.controls.get_slider_round(event.pos[0])

            # Auto-advance when playing
            if self.playing:
                speed = SPEED_PRESETS[self.speed_idx]
                # At speed Nx, advance N rounds per second (at 1x = ~4 rounds/sec for watchability)
                rounds_per_sec = speed * 4
                self.accumulator += dt * rounds_per_sec
                steps = int(self.accumulator)
                if steps > 0:
                    self.accumulator -= steps
                    self.round_idx = min(self.round_idx + steps, self.total_rounds - 1)
                    if self.round_idx >= self.total_rounds - 1:
                        self.playing = False

            # Update trail
            self._update_trail()

            # Render
            self.screen.fill(C_BG)

            rnd = self.game.rounds[self.round_idx]
            ana = self.analytics[self.round_idx] if self.round_idx < len(self.analytics) else None

            self.grid.render(self.screen, rnd, self.game, ana,
                             self.show_trails, self.show_idle, self.show_collisions,
                             self.trail_history)

            self.panel.render(self.screen, self.game, self.round_idx,
                              self.speed_idx, self.analytics, self.show_order_timeline)

            self.controls.render(self.screen, self.round_idx, self.playing,
                                 self.speed_idx)

            pygame.display.flip()

        pygame.quit()

    def _handle_key(self, key) -> bool:
        """Handle keyboard input. Returns False to quit."""
        if key in (pygame.K_q, pygame.K_ESCAPE):
            return False
        elif key == pygame.K_SPACE:
            self.playing = not self.playing
        elif key == pygame.K_LEFT:
            self.round_idx = max(0, self.round_idx - 1)
            self.playing = False
        elif key == pygame.K_RIGHT:
            self.round_idx = min(self.total_rounds - 1, self.round_idx + 1)
            self.playing = False
        elif key in (pygame.K_PLUS, pygame.K_EQUALS, pygame.K_KP_PLUS):
            self.speed_idx = min(len(SPEED_PRESETS) - 1, self.speed_idx + 1)
        elif key in (pygame.K_MINUS, pygame.K_KP_MINUS):
            self.speed_idx = max(0, self.speed_idx - 1)
        elif key == pygame.K_t:
            self.show_trails = not self.show_trails
        elif key == pygame.K_i:
            self.show_idle = not self.show_idle
        elif key == pygame.K_c:
            self.show_collisions = not self.show_collisions
        elif key == pygame.K_o:
            self.show_order_timeline = not self.show_order_timeline
        elif key == pygame.K_HOME:
            self.round_idx = 0
            self.playing = False
        elif key == pygame.K_END:
            self.round_idx = self.total_rounds - 1
            self.playing = False
        return True

    def _handle_click(self, pos):
        """Handle mouse click."""
        action = self.controls.handle_click(pos)
        if action == "prev":
            self.round_idx = max(0, self.round_idx - 1)
            self.playing = False
        elif action == "next":
            self.round_idx = min(self.total_rounds - 1, self.round_idx + 1)
            self.playing = False
        elif action == "toggle_play":
            self.playing = not self.playing
        elif action == "slider":
            self.round_idx = self.controls.get_slider_round(pos[0])


# ── Main ───────────────────────────────────────────────────────────────────
def main():
    if len(sys.argv) < 2:
        # Try to find most recent log
        log_dir = Path(__file__).parent / ".." / "grocerybot-trial-vs-code" / "logs"
        logs = sorted(log_dir.glob("game_*.jsonl"))
        if logs:
            path = logs[-1]
            print(f"No log specified, using most recent: {path}")
        else:
            print("Usage: python replay_viewer.py <path_to_jsonl>")
            print("   or: uv run --with pygame python replay_viewer.py <logfile>")
            sys.exit(1)
    else:
        path = Path(sys.argv[1])

    if not path.exists():
        print(f"File not found: {path}")
        sys.exit(1)

    print(f"Loading replay: {path}")
    game = parse_replay(path)
    print(f"Grid: {game.config.width}x{game.config.height}, "
          f"Bots: {game.config.num_bots}, "
          f"Rounds: {len(game.rounds)}, "
          f"Score: {game.final_score}")

    viewer = ReplayViewer(game)
    viewer.run()


if __name__ == "__main__":
    main()
