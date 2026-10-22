# ERINX: Little Harvest 🌱

A playable, cozy, mouse-driven **Python + Pygame farming simulator**. No external image/audio files needed — artwork is rendered directly in Pygame.

## Features

- 24 interactive soil plots and four crops: carrots, tomatoes, corn, pumpkins
- Plant → water → sleep → grow → harvest gameplay loop
- Distinct crop growing times, seed costs, and selling prices
- Farmer's market for purchasing seeds and selling harvested products
- Sprinkler upgrade (waters up to 3 adjacent plots for 1 energy)
- Energy upgrade (+6 maximum energy)
- Sunny, cloudy, and rainy weather (rain automatically waters crops)
- Daily stamina refill, animated crops, particle effects, toast notifications
- F5 manual save, F9 load; autosave every three days
- Keyboard shortcuts and in-game help panel

## Setup (Windows PowerShell / VS Code)

Requires **Python 3.10+**. Open this project folder in VS Code. Then run:

```powershell
python --version
python -m pip install -r requirements.txt
python main.py
```

If `python` is not recognized, install Python from https://www.python.org/downloads/ and ensure Python is available on PATH. If Windows recognizes `py` instead, substitute `py` for `python`.

### Optional virtual environment

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe main.py
```

This avoids PowerShell activation restrictions.

## Controls

| Key / mouse | Action |
| --- | --- |
| Left-click plot | Apply current tool |
| 1 / 2 / 3 / 4 | Plant / Water / Harvest / Clear |
| Click seed in sidebar | Select seed variety |
| B | Open/close market |
| N | Sleep / advance to next day |
| H | Toggle help |
| F5 | Save |
| F9 | Load |
| ESC | Pause or close a window |

### First harvest walkthrough

1. Click an empty plot to plant a **carrot** (selected by default).
2. Press **2** to choose Water, then click your carrot.
3. Press **N** to sleep to the next day.
4. Water the carrot again, then sleep; carrots mature in two watered days.
5. Press **3**, click the carrot to harvest it.
6. Press **B**, then click **SELL** next to carrots.
7. Buy more seeds, expand the farm, and save with **F5**.

## Game balance

| Crop | Seed cost | Sell price | Watered days to mature |
| --- | ---: | ---: | ---: |
| Carrot | 4 | 12 | 2 |
| Tomato | 8 | 23 | 3 |
| Corn | 13 | 38 | 4 |
| Pumpkin | 24 | 75 | 5 |

**Note:** You must water a crop before ending the day to advance its growth. Rainy days can water crops automatically. `savegame.json` is created alongside `main.py` when you save.

## Troubleshooting

- `py is not recognized`: Use `python` instead of `py`; check `python --version`.
- `No module named pygame`: Run `python -m pip install -r requirements.txt` using the same Python interpreter that runs `main.py`.
- Game doesn't display: run in a local desktop Python environment with a graphical display, not a headless terminal.

## Files

- `main.py` — full game source
- `requirements.txt` — dependency
- `README.md` — instructions and gameplay guide
- `.gitignore` — keeps save data, caches, and virtual environment out of Git

Created for an educational Python/Pygame game-development project.
