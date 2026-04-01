# Configuration Defaults

The FlexCableAligner application reads its settings from `config.json`. Below are the default values provided in the repository:

| Setting | Default Value | Description |
|---|---|---|
| `collision_distance` | `25.0` | Minimum distance (mm) between carriage 1 and carriage 2 before collision avoidance is triggered.
| `default_feed_rate` | `3000.0` | Default movement speed in mm/min for jogging and automated moves.
| `park_position` | `{ "x": 1000.0, "y": 0.0 }` | Coordinates where carriage 2 is parked during collision avoidance mode.
| `default_step_size` | `1.0` | Initial jog step size (mm) used by the UI controls.
| `url` | `ws://172.16.55.2:7125/websocket?token=4deca56b67664a47bb4d59e4ee628d10` | WebSocket endpoint for connecting to the printer controller.

These values can be edited directly in `config.json` before launching the application, or overridden at runtime via the URL entry field in the toolbar of the UI.
