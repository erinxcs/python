# ERINX: Echoes of the Grove

A complete, small-scale 2D action RPG made with Python and Pygame. Explore a handcrafted forest, defeat roaming slimes, collect crystals, and restore peace to the Grove.

## Features

- Fully playable 960 × 640 game with frame-independent movement
- Tile-based overworld, collision detection, animated slime enemies, and sword combat
- Health, leveling, experience points, coins, healing potions, and inventory
- Quest with Elder Rowan, a merchant, and a completion reward
- Minimap, pause screen, help screen, restart after defeat
- Save and load with JSON (`F5` and `F9`)
- Procedurally drawn pixel-inspired graphics: **no external art assets required**

## Setup in Visual Studio Code

1. Install **Python 3.10 or later** and the **Python extension** for VS Code.
2. Open this folder in VS Code (`File > Open Folder`).
3. Open the integrated terminal (`Terminal > New Terminal`).
4. (Recommended) Create a virtual environment:

   **Windows PowerShell:**
   ```powershell
   py -m venv .venv
   .\.venv\Scripts\python.exe -m pip install -r requirements.txt
   .\.venv\Scripts\python.exe main.py
   ```

   **macOS / Linux:**
   ```bash
   python3 -m venv .venv
   .venv/bin/python -m pip install -r requirements.txt
   .venv/bin/python main.py
   ```

Alternatively, after installing pygame globally (`py -m pip install pygame` on Windows), run `py main.py`.

## Controls

| Key | Action |
| --- | --- |
| WASD / Arrow keys | Move |
| Space / J | Sword attack |
| E | Talk / interact / buy |
| Q | Use a health potion |
| I / Tab | Inventory |
| H | Help |
| M | Toggle minimap |
| Escape | Pause / resume |
| F5 / F9 | Save / load |
| Enter | Start new adventure on title screen |
| L | Load adventure on title screen |
| R | Restart after game over |

## Quest walkthrough

1. Talk to **Rowan**, near the campfire in the northwest, with **E**.
2. Find slimes around the map. Defeat them with **Space**, collecting **3 crystal shards**. Shards drop randomly from defeated slimes; enemies respawn periodically.
3. Talk to Rowan again to finish the quest and receive **100 gold** and **2 potions**.
4. The merchant near the southwest sells healing potions for **25 gold** each.

## Project structure

```text
ERINX_RPG_Adventure/
├── main.py            # Game, world, NPCs, AI, UI, combat, saving
├── requirements.txt   # Python dependency
├── README.md          # Project documentation
├── .gitignore         # Files excluded from version control
└── LICENSE            # MIT License
```

Game saves are created locally as `savegame.json` next to `main.py` and are excluded from Git.

## Extending the game

The implementation is intentionally self-contained so you can trace each subsystem in a single file. The main entry point is `Game.run()`. Try adding new regions to `WORLD`, more quests, equipment, NPC dialogue, sound effects, and enemy types. For a larger RPG, consider separating the game into `world.py`, `entities.py`, `combat.py`, and `ui.py` modules.

## License

MIT; see `LICENSE`.
