# OctoPrint-FlexCableAligner

Joystick-based jogging for a dual-carriage (XYZ/ABC) printer using pygame on the OctoPrint server.

Mappings
- Planar: axes 0/1 => X/Y (carriage 1) or A/B (carriage 2)
- Z/C: D-pad/Hat vertical
- Speed: axis 3 sets max speed between base and 20000 mm/min
- Buttons:
  - 0: Home XY (G28)
  - 1: Toggle carriage (1 <-> 2)
  - 2: Save current position
  - 4: Go to last saved position

Notes
- The plugin runs headless and uses M410 to stop long jog moves, mirroring the desktop app.
- Ensure the OctoPrint host has access to the joystick device. For headless Linux, SDL_VIDEODRIVER=dummy is used.
- Requires pygame 2.x.

Installation
1) On the OctoPrint host:
   - Zip this folder (setup.py + octoprint_flex_cable_aligner)
   - In OctoPrint: Settings -> Plugin Manager -> Get More -> ... from an uploaded file
2) Or pip install in the OctoPrint venv:
   pip install .
