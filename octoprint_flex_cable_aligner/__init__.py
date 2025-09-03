from __future__ import annotations

import os
import time
import threading
from collections import deque
from typing import Optional, Tuple

import octoprint.plugin
from flask import jsonify


class FlexCableAlignerPlugin(
    octoprint.plugin.StartupPlugin,
    octoprint.plugin.ShutdownPlugin,
    octoprint.plugin.SettingsPlugin,
    octoprint.plugin.TemplatePlugin,
    octoprint.plugin.AssetPlugin,
    octoprint.plugin.SimpleApiPlugin,
):
    """OctoPrint plugin for joystick-based jogging (pygame).

    Keeps the axis and button mappings from the standalone app:
    - Axes 0/1 control planar motion (X/Y for carriage 1, A/B for carriage 2)
    - D-pad/Hat vertical controls Z/C
    - Axis 3 controls max speed (base..20000 mm/min)
    - Button 0: Home XY
    - Button 1: Toggle carriage (1 <-> 2)
    - Button 2: Save current position
    - Button 4: Go to last saved position (assumption in headless mode)
    """

    def __init__(self):
        # Threads and libs
        self._thread: Optional[threading.Thread] = None
        self._running = threading.Event()
        self._joystick = None
        self._pygame = None

        # Motion/joystick state
        self._selected_carriage = 1  # 1 -> XYZ, 2 -> ABC
        self._last_dir_sent = {1: (0, 0, 0), 2: (0, 0, 0)}
        self._last_feed_sent = {1: 0.0, 2: 0.0}
        self._last_button_times: dict[str, float] = {}

        # Positions and saved positions (integrated locally, like the GUI)
        self._positions = {k: 0.0 for k in ("x", "y", "z", "a", "b", "c")}
        self._positions_list: list[Tuple[float, float, float, float, float, float]] = []
        self._last_update_time = time.time()

        # UI state (exposed via SimpleApiPlugin)
        self._ui_feed = 0.0
        self._ui_dir = (0, 0, 0)
        self._last_stop_sent = 0.0

    # ----- Settings -----
    def get_settings_defaults(self):
        return dict(
            base_speed=5000.0,
            max_speed=20000.0,
            deadzone=0.20,
            z_speed_scale=0.33,
        )

    # Sidebar panel UI to show carriage and velocity
    def get_template_configs(self):
        return [
            dict(type="sidebar", name="Flex Cable Aligner", template="flex_cable_aligner_sidebar.jinja2", custom_bindings=True)
        ]

    def get_assets(self):
        return {
            "js": ["js/flex_cable_aligner.js"],
            "css": ["css/flex_cable_aligner.css"],
        }

    # Simple GET API for polling status
    def on_api_get(self, request):
        try:
            data = dict(
                carriage=self._selected_carriage,
                feed=self._ui_feed,
                dir=self._ui_dir,
                operational=self._is_operational(),
            )
            return jsonify(data)
        except Exception as e:
            self._logger.warning("Status API error: %s", e)
            return jsonify(dict(error=str(e))), 500

    # route name for SimpleApiPlugin
    def get_api_commands(self):
        return dict()

    # ----- Lifecycle -----
    def on_after_startup(self):
        self._logger.info("FlexCableAligner: starting joystick thread")
        self._running.set()
        self._thread = threading.Thread(target=self._loop, name="fca-joystick", daemon=True)
        self._thread.start()

    def on_shutdown(self):
        self._logger.info("FlexCableAligner: stopping joystick thread")
        self._running.clear()
        try:
            if self._thread and self._thread.is_alive():
                self._thread.join(timeout=2.0)
        except Exception:
            pass
        self._shutdown_joystick()

    # ----- Joystick init/shutdown -----
    def _init_joystick(self) -> bool:
        if self._joystick is not None:
            return True

        # Allow pygame to run without a display
        os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
        os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
        os.environ.setdefault("SDL_JOYSTICK_ALLOW_BACKGROUND_EVENTS", "1")

        try:
            import pygame  # Lazy import so OctoPrint can load without pygame at install time
            self._pygame = pygame
        except Exception as e:
            self._logger.error(f"FlexCableAligner: pygame import failed: {e}")
            return False
        try:
            self._pygame.init()
            self._pygame.joystick.init()
            count = self._pygame.joystick.get_count()
            if count == 0:
                self._logger.warning("FlexCableAligner: no joystick detected")
                return False
            self._joystick = self._pygame.joystick.Joystick(0)
            self._joystick.init()
            self._logger.info(
                "FlexCableAligner: joystick connected: %s (axes=%s, buttons=%s, hats=%s)",
                self._joystick.get_name(),
                self._joystick.get_numaxes(),
                self._joystick.get_numbuttons(),
                self._joystick.get_numhats(),
            )
            return True
        except Exception as e:
            self._logger.error(f"FlexCableAligner: joystick init error: {e}")
            self._shutdown_joystick()
            return False

    def _shutdown_joystick(self):
        try:
            if self._joystick:
                self._joystick.quit()
        except Exception:
            pass
        try:
            if self._pygame:
                self._pygame.joystick.quit()
        except Exception:
            pass
        self._joystick = None

    # ----- Core loop -----
    def _loop(self):
        # Keep trying to initialize a joystick
        next_retry = 0.0
        last_dir = (0, 0, 0)
        last_feed = 0.0
        while self._running.is_set():
            now = time.time()
            if self._joystick is None and now >= next_retry:
                if not self._init_joystick():
                    next_retry = now + 5.0
                    time.sleep(1.0)
                    continue

            # If still no joystick, wait and retry
            if self._joystick is None:
                time.sleep(0.5)
                continue

            # Pump events
            try:
                self._pygame.event.pump()
            except Exception:
                time.sleep(0.2)
                continue

            # Update max speed from axis 3
            max_speed = float(self._settings.get(["max_speed"]))
            base_speed = float(self._settings.get(["base_speed"]))
            try:
                ax3 = -float(self._joystick.get_axis(3))
            except Exception:
                ax3 = 0.0
            norm = (ax3 + 1.0) / 2.0
            max_speed = base_speed + norm * (20000.0 - base_speed)

            # Direction + feed
            dir_tuple, feed = self._dir_and_feed_from_joystick(max_speed)

            # Handle buttons (homing, carriage toggle, save/goto)
            self._handle_buttons()

            # Capture UI state
            self._ui_feed = float(feed)
            self._ui_dir = tuple(dir_tuple)

            # Send jog/stop on change and ensure stop in deadzone
            if self._is_operational():
                if dir_tuple == (0, 0, 0) or feed < 5.0:
                    # Always ensure M410 when in deadzone: send immediately on first entry
                    # then at most every 0.25s while staying in deadzone
                    now_t = time.time()
                    if last_dir != (0, 0, 0) or self._last_stop_sent == 0.0 or (now_t - self._last_stop_sent) > 0.25:
                        self._stop_jog()
                        self._last_stop_sent = now_t
                    last_dir = (0, 0, 0)
                    last_feed = 0.0
                else:
                    if dir_tuple != last_dir or abs(feed - last_feed) > 50.0:
                        self._jog(dir_tuple, feed)
                        last_dir = dir_tuple
                        last_feed = feed

            # Integrate positions for saved position feature
            dt = self._integrate_positions(dir_tuple, feed)

            # Dynamic sleep based on speed similar to original config
            sleep_min = 0.05
            sleep_max = 0.1
            max_v = feed
            if abs(max_v) < 0.1:
                interval = sleep_max
            else:
                # Normalize by max of 20000
                norm_v = min(1.0, abs(max_v) / 20000.0)
                interval = sleep_max - (sleep_max - sleep_min) * norm_v
            time.sleep(max(0.01, interval))

        # ensure stop
        try:
            self._stop_jog()
        except Exception:
            pass

    # ----- Helpers -----
    def _is_operational(self) -> bool:
        try:
            return bool(self._printer and self._printer.is_operational())
        except Exception:
            return False

    def _handle_buttons(self):
        def debounce(key: str, interval: float) -> bool:
            t = time.time()
            last = self._last_button_times.get(key, 0.0)
            if t - last > interval:
                self._last_button_times[key] = t
                return True
            return False

        j = self._joystick
        if j is None:
            return

        try:
            # Button 0: Home XY
            if j.get_button(0) and debounce('home', 0.3):
                self._stop_jog()
                self._send_commands(['G28'])
                # Reset XY positions to 0
                self._positions['x'] = 0.0
                self._positions['y'] = 0.0

            # Button 1: Toggle carriage
            if j.get_button(1) and debounce('toggle_car', 0.2):
                self._selected_carriage = 2 if self._selected_carriage == 1 else 1
                self._stop_jog()

            # Button 2: Save position
            if j.get_button(2) and debounce('save', 0.2):
                tup = (
                    self._positions['x'], self._positions['y'], self._positions['z'],
                    self._positions['a'], self._positions['b'], self._positions['c']
                )
                self._positions_list.append(tup)
                self._logger.info("Saved position #%d: %s", len(self._positions_list), tup)

            # Button 4: Goto last saved position (assumption)
            if j.get_button(4) and debounce('goto', 0.2):
                if self._positions_list:
                    self._goto_saved_position(self._positions_list[-1])
                else:
                    self._logger.info("No saved positions yet")
        except Exception as e:
            self._logger.warning("Button handling error: %s", e)

    def _goto_saved_position(self, pos: Tuple[float, float, float, float, float, float]):
        # Carriage 1 deltas
        dx = pos[0] - self._positions['x']
        dy = pos[1] - self._positions['y']
        dz = pos[2] - self._positions['z']
        if any(abs(v) > 1e-6 for v in (dx, dy, dz)):
            self._move_relative((dx, dy, dz), carriage=1, feedrate=self._settings.get_float(["max_speed"]))
            self._positions['x'], self._positions['y'], self._positions['z'] = pos[0], pos[1], pos[2]

        # Carriage 2 deltas
        da = pos[3] - self._positions['a']
        db = pos[4] - self._positions['b']
        dc = pos[5] - self._positions['c']
        if any(abs(v) > 1e-6 for v in (da, db, dc)):
            self._move_relative((da, db, dc), carriage=2, feedrate=self._settings.get_float(["max_speed"]))
            self._positions['a'], self._positions['b'], self._positions['c'] = pos[3], pos[4], pos[5]

    def _send_commands(self, lines: list[str]):
        if not self._is_operational():
            return
        try:
            self._printer.commands(lines)
        except Exception as e:
            self._logger.warning("Failed to send commands: %s", e)

    def _jog(self, dir_tuple: Tuple[int, int, int], feed: float):
        # Map carriage to axes
        axes = ('X', 'Y', 'Z') if self._selected_carriage == 1 else ('A', 'B', 'C')
        # Unit direction components (+/-1 or 0)
        comps = [1 if d > 0 else (-1 if d < 0 else 0) for d in dir_tuple]
        if comps == [0, 0, 0] or feed <= 0:
            self._stop_jog()
            return
        # Stop any ongoing moves first (planner reset)
        self._send_commands(['M410'])
        # Long relative move along active axes; M410 will stop immediately when needed
        dist = 1000.0
        parts = []
        for comp, axis in zip(comps, axes):
            if comp != 0:
                parts.append(f"{axis}{dist * comp:.3f}")
        if not parts:
            return
        gcode = [f"G91", f"G1 {' '.join(parts)} F{int(max(1, feed))}"]
        self._logger.debug("Jog %s feed=%s -> %s", comps, feed, gcode[-1])
        self._send_commands(gcode)

    def _stop_jog(self):
        self._send_commands(['M410'])

    def _move_relative(self, dxyz: Tuple[float, float, float], carriage: int, feedrate: float):
        axes = ('X', 'Y', 'Z') if carriage == 1 else ('A', 'B', 'C')
        parts = [f"{a}{v:.4f}" for a, v in zip(axes, dxyz) if abs(v) > 1e-6]
        if not parts:
            return
        self._send_commands(["G91", f"G1 {' '.join(parts)} F{int(max(1, feedrate))}"])

    def _dir_and_feed_from_joystick(self, max_speed: float) -> Tuple[Tuple[int, int, int], float]:
        # Default neutral
        if self._joystick is None:
            return (0, 0, 0), max_speed
        j = self._joystick
        dead = float(self._settings.get(["deadzone"]))
        z_scale = float(self._settings.get(["z_speed_scale"]))

        # Axes 0/1 planar
        try:
            ax0 = float(j.get_axis(0))
            ax1 = float(j.get_axis(1))
        except Exception:
            ax0 = 0.0
            ax1 = 0.0

        # Hat vertical for Z/C (same sign logic as original)
        try:
            _hx, hy = j.get_hat(0)
        except Exception:
            hy = 0
        hy = -int(hy)
        dz = 1 if hy > 0 else (-1 if hy < 0 else 0)

        dx = 1 if ax0 > dead else (-1 if ax0 < -dead else 0)
        dy = 1 if ax1 > dead else (-1 if ax1 < -dead else 0)

        feed = float(max_speed)
        if dz != 0:
            feed *= z_scale
        return (dx, dy, dz), feed

    def _integrate_positions(self, dir_tuple: Tuple[int, int, int], feed: float) -> float:
        now = time.time()
        dt = now - self._last_update_time
        self._last_update_time = now
        vx, vy, vz = self._components_from_dir_and_feed(dir_tuple, feed)

        dx = (vx / 60.0) * dt
        dy = (vy / 60.0) * dt
        dz = (vz / 60.0) * dt
        if self._selected_carriage == 1:
            self._positions['x'] += dx
            self._positions['y'] += dy
            self._positions['z'] += dz
        else:
            self._positions['a'] += dx
            self._positions['b'] += dy
            self._positions['c'] += dz
        return dt

    @staticmethod
    def _components_from_dir_and_feed(dir_tuple: Tuple[int, int, int], feed: float) -> Tuple[float, float, float]:
        ax = [float(d) for d in dir_tuple]
        active = [i for i, d in enumerate(ax) if d != 0.0]
        if not active or feed <= 0:
            return 0.0, 0.0, 0.0
        n = len(active) ** 0.5
        comps = [0.0, 0.0, 0.0]
        for i in active:
            comps[i] = (ax[i] / n) * feed
        return comps[0], comps[1], comps[2]


__plugin_name__ = "Flex Cable Aligner Joystick Control"
__plugin_pythoncompat__ = ">=3,<4"


def __plugin_load__():
    global __plugin_implementation__
    __plugin_implementation__ = FlexCableAlignerPlugin()
