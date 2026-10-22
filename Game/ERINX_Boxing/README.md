# ERINX BOXING — Neon Fight Night

A playable, asset-free 2D arcade boxing game made in **Python + Pygame**. Fight an AI opponent in a best-of-three-round match. Features jabs, hooks, blocking, dodging, stamina, knockouts, sparks, ring graphics, and a start/pause/replay menu.

## Requirements

- Windows, macOS or Linux with Python 3.10+
- Pygame 2.5+

## Run in VS Code (Windows PowerShell)

1. Extract this ZIP and open the **ERINX_Boxing** folder in VS Code.
2. Open **Terminal > New Terminal**.
3. Verify Python: `python --version` (some installations use `py --version`).
4. Optional but recommended, create a virtual environment:

   ```powershell
   python -m venv .venv
   .\.venv\Scripts\python.exe -m pip install -r requirements.txt
   .\.venv\Scripts\python.exe main.py
   ```

   This approach **does not need** virtual environment activation or the `py` launcher.

   Alternatively, without a virtual environment:

   ```powershell
   python -m pip install -r requirements.txt
   python main.py
   ```

If `python` is also not recognized, install Python from https://www.python.org/downloads/ and ensure it is added to PATH, then restart VS Code. Test using `python --version`.

## Controls

| Key | Action |
| --- | --- |
| A / D or left/right arrows | Walk |
| J or Z | Jab (quick punch) |
| K or X | Hook (powerful punch) |
| L or S | Block (reduces damage) |
| Space or Shift | Dodge backward (brief invulnerability) |
| Enter | Start / replay / resume |
| Esc | Pause / menu |

## Rules

- Each round lasts up to **45 seconds**.
- **First to win 2 rounds** takes the match; knockouts immediately end the match.
- When time runs out, the fighter with more HP wins (hits are the tiebreaker).
- Attacking and dodging cost stamina. Stamina regenerates automatically.

## Folder

```text
ERINX_Boxing/
├── main.py
├── requirements.txt
├── README.md
└── .gitignore
```

All visual art is drawn in code, so there are no asset downloads.
