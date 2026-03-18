# Usage

## Running the application
```bash
python main.py
```
The program will:
1. Connect to the printer via WebSocket (URL taken from `config.json`).
2. Open a Tkinter UI where you can load a CSV file containing trace coordinates.
3. After loading, click **Set Landmarks** to define machine zero points using the two landmark rows in the CSV.
4. Use the jog controls or keyboard shortcuts to move the carriages and verify positions.
5. Click **Done / Next Row** to step through each point pair, automatically moving both carriages to the target locations.

## Configuration options (`config.json`)
- `url`: WebSocket endpoint for the printer controller.
- `default_step_size`: Initial jog step size (mm).
- `default_feed_rate`: Default movement speed (mm/min).
- `collision_distance`: Minimum distance between C1 and C2 before collision avoidance is triggered.
- `park_position`: Coordinates where carriage 2 is parked during a collision scenario.

You can edit these values directly in `config.json` or modify them at runtime via the **URL** entry field in the toolbar.
