# FlexCableAligner

Refactored controller application for the flex cable alignment tool.

## Overview

Responsibilities are now split into:

1. `include/printer.py` – synchronous `Printer` class using Klipper's Unix Domain Socket (UDS) JSON‑RPC to send G‑Code.
2. `include/config.py` – simplified `JogConfig` with a single movement & velocity scale.
3. `include/gui.py` – `FlexAlignerGUI` containing the Tkinter UI, keyboard handling via `pynput`, and the movement loop (scheduled via Tk's `after`).

All asynchronous (`asyncio`) code and separate XY/UV scaling controls were removed.

## Dependencies

Install (PowerShell):

```
pip install -r requirements.txt
```

## Run

```
python main.py
```

## Key Features

- Single velocity & movement scaling slider with quick presets.
- Keyboard jogging using Arrow keys (X/Y) and I/J/K/L (U/V) with smooth start/stop.
- Fine mode toggle (press F) reduces max speed for precision moves.
- Save (P) / select (click in table) / recall (G) positions; Home XY (H); Emergency Stop (Esc, or UI button).
- Relative jogging with smoothing and dynamic update interval.
- Emergency stop (UI button or Escape) triggers Klipper `emergency_stop`.

## Notes

Absolute positions are tracked locally while operating in relative (`G91`) mode. If printer state is lost, home and/or use a saved position to reapply kinematics.

## Klipper UDS

This app connects to Moonraker's WebSocket (default set in `Printer(...)`), sending G‑Code via JSON‑RPC.

