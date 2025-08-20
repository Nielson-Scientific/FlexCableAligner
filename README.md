# FlexCableAligner

Refactored controller application for the flex cable alignment tool.

## Overview

Responsibilities are now split into:

1. `include/printer.py` – synchronous `Printer` class (WebSocket JSON‑RPC) to send G‑Code.
2. `include/config.py` – simplified `JogConfig` with a single movement & velocity scale.
3. `include/gui.py` – `FlexAlignerGUI` containing the Tkinter UI, pygame joystick handling, and the movement loop (scheduled via Tk's `after`).

All asynchronous (`asyncio`) code and separate XY/UV scaling controls were removed.

## Dependencies

Install (PowerShell):

```
pip install pygame websocket-client
```

## Run

```
python main.py
```

## Key Features

- Single velocity & movement scaling slider with quick presets.
- Fine mode toggle (button 0) adjusts scaling for precision moves.
- Save / select / recall positions (joystick button 1 to save, 3 to goto, 2 to home XY, Escape for E‑Stop).
- Relative jogging with smoothing and dynamic update interval.
- Emergency stop (UI button or Escape) sends `M112`.

## Notes

Absolute positions are tracked locally while operating in relative (`G91`) mode. If printer state is lost, home and/or use a saved position to reapply kinematics.

