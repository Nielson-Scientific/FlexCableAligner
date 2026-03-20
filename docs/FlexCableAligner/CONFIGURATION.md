# Configuration Defaults

The FlexCableAligner application reads its settings from `config.json`. Below are the default values provided in the repository:

| Setting | Default Value | Description |
|---|---|---|
| `collision_distance` | `25.0` | Minimum distance (mm) between carriage 1 and carriage 2 before collision avoidance is triggered.
| `default_feed_rate` | `3000.0` | Default movement speed in mm/min for jogging and automated moves.
| `park_position` | `{ "x": 750.0, "y": 0.0 }` | Coordinates where carriage 2 is parked during collision avoidance mode.
| `default_step_size` | `1.0` | Initial jog step size (mm) used by the UI controls.
| `url` | `ws://10.34.243.54/websocket?token=4deca56b67664a47bb4d59e4ee628d10` | WebSocket endpoint for connecting to the printer controller.

These values can be edited directly in `config.json` before launching the application, or overridden at runtime via the URL entry field in the toolbar of the UI.

## Machine Bounds Configuration (`machine_bounds.json`)

The application uses a separate `machine_bounds.json` file to define safe movement limits for each carriage axis. This prevents moves that would exceed the physical bounds of the printer (as defined in Klipper's `printer.cfg`).

### File Location
Place `machine_bounds.json` in the root directory of the FlexCableAligner project.

### Structure
```json
{
    "x1": { "home": 0.0, "min": 0.0, "max": 200.0 },
    "y1": { "home": 0.0, "min": 0.0, "max": 100.0 },
    "x2": { "home": 0.0, "min": 0.0, "max": 200.0 },
    "y2": { "home": 0.0, "min": 0.0, "max": 100.0 }
}
```

### Fields
| Field | Description |
|---|---|
| `home` | The home position for the axis (updated at runtime after homing). |
| `min` | Minimum allowed position (hard limit from printer configuration). |
| `max` | Maximum allowed position (hard limit from printer configuration). |

### Behavior
- When a move command would exceed bounds, the position is **clipped** to the nearest valid value.
- A warning is logged for each clipped coordinate.
- The default values match the Klipper `printer.cfg` configuration for this system:
  - X axes (x1, x2): 0–200 mm
  - Y axes (y1, y2): 0–100 mm

### Modifying Bounds
To change the bounds for a different printer configuration, edit the `min` and `max` values in `machine_bounds.json`. The `home` value is managed automatically by the application.
