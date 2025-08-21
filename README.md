# FlexCableAligner

Refactored controller application for the flex cable alignment tool.

## Overview

Responsibilities are now split into:

1. `include/printer.py` – synchronous `Printer` class using Klipper's Unix Domain Socket (UDS) JSON‑RPC to send G‑Code.
2. `include/config.py` – simplified `JogConfig` with a single movement & velocity scale.
3. `include/gui.py` – `FlexAlignerGUI` containing the Tkinter UI, pygame joystick handling, and the movement loop (scheduled via Tk's `after`).

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
- Fine mode toggle (button 0) adjusts scaling for precision moves.
- Save / select / recall positions (joystick button 1 to save, 3 to goto, 2 to home XY, Escape for E‑Stop).
- Relative jogging with smoothing and dynamic update interval.
- Emergency stop (UI button or Escape) triggers Klipper `emergency_stop`.

## Notes

Absolute positions are tracked locally while operating in relative (`G91`) mode. If printer state is lost, home and/or use a saved position to reapply kinematics.

## Klipper UDS

This app connects directly to Klipper's API Server over a Unix Domain Socket (default: `/tmp/klippy_uds`). Ensure Klipper is started with the `-a /tmp/klippy_uds` option (see Klipper's API Server docs). The app is intended to run on the same Raspberry Pi as Klipper.

