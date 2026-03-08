# Grocery Bot Simulator

Offline tools for analyzing and replaying Grocery Bot game logs.

## Replay Viewer

Interactive pygame-based viewer for stepping through game replays visually.

### Setup

```bash
pip install pygame>=2.5
```

### Usage

```bash
cd solutions/grocerybot-simulator
python replay_viewer.py <path_to_jsonl>
```

If no log file is specified, the viewer will try to load the most recent log from `../grocerybot-trial-vs-code/logs/`.

### Controls

| Key | Action |
|-----|--------|
| Space | Play / pause |
| Left / Right | Step back / forward |
| Home / End | Jump to first / last round |
| + / - | Speed up / down (1x, 2x, 5x, 10x, 20x) |
| T | Toggle bot trail overlay |
| I | Toggle idle bot highlight |
| C | Toggle collision markers |
| O | Toggle order completion timeline |
| Q / Esc | Quit |

Mouse controls: click play/pause/step buttons, or drag the round slider.

### Window Layout

- **Grid area** (left): Auto-scaled game board with walls, shelves, items, drop-off zone, and bots
- **Info panel** (right): Round/score, active + preview order checklists, per-bot status table
- **Control bar** (bottom): Playback buttons, speed, round slider

### Overlays

- **Trails**: Shows last 10 positions per bot as fading dots
- **Idle**: Red ring around bots that issued `wait` when they had walkable neighbors
- **Collisions**: Red X on bots that issued a move but didn't change position
- **Order timeline**: Sparkline showing when orders were completed across the game

## Analysis Tools

```bash
python analyze.py <path_to_jsonl>
```

Prints ASCII board, per-order efficiency breakdown, action distribution, and score timeline.
