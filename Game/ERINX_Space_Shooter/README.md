# ERINX: STARFALL — Space Shooter

A complete, self-contained 2D arcade space shooter made with Python and Pygame. No image or audio assets required.

## Windows / VS Code quick start

1. Extract the ZIP and open the `ERINX_Space_Shooter` folder in VS Code.
2. Open **Terminal > New Terminal**.
3. Verify Python: `python --version`.
4. Install: `python -m pip install -r requirements.txt`.
5. Run: `python main.py`.

If `python` isn't recognized, install Python from https://www.python.org/downloads/ and ensure Python is added to PATH. You do not need the `py` launcher.

## Controls

- **WASD / Arrow keys** — Fly
- **Space / J** — Fire lasers (hold)
- **P / Esc** — Pause / Resume
- **Enter** — Start or restart

## Features

- 60 FPS movement and neon particle explosions
- Enemy waves and enemy laser attacks
- Elite enemies and **Void Titan** boss each wave
- Hit points, shields, three lives, invincibility frames
- Healing, shield, rapid-fire and triple-shot pickups
- High score automatically saved to `highscore.json`

## Notes

Python 3.10+ recommended. Source code lives in `main.py`. High-score save is created on first new record. This is a local single-player game and requires no network access.
