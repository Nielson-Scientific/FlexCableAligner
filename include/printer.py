import os
import threading
import time
from typing import Optional

import serial  # pyserial


class Printer:
    """Marlin over USB serial with continuous jogging.

    Changes vs previous implementation:
    - Talks to Marlin via a serial COM port (USB CDC)
    - Uses relative positioning (G91) for all moves
    - Two carriages mapped to XYZ (carriage 1) and ABC (carriage 2)
    - Jogging sends one long G1 in the current direction; change/stop via M410
    """

    def __init__(self, port: str | None = None, baud: int = 250000, read_timeout: float = 0.2):
        # Allow env var override for convenience on Linux/Mac: MARLIN_PORT=/dev/ttyACM0
        env_port = os.environ.get('MARLIN_PORT')
        self.port = port or env_port  # e.g., '/dev/ttyACM0' on Linux, 'COM4' on Windows
        self.baud = baud
        self.read_timeout = read_timeout

        # Serial connection state
        self.ser: Optional[serial.Serial] = None
        self.connected = False
        self.last_error: Optional[str] = None
        self.is_moving = False

        # Jog state: track last commanded long move per carriage to avoid spam
        self._carriage = 1  # 1 or 2
        self._last_dir = {1: (0.0, 0.0, 0.0), 2: (0.0, 0.0, 0.0)}
        self._last_feed = 0.0

        # I/O lock (re-entrant) to serialize serial access across threads
        self._io_lock = threading.RLock()

    # ---- Connection ----
    def connect(self) -> bool:
        try:
            if self.ser and self.ser.is_open:
                self.disconnect()

            # Auto-detect a likely COM port if not provided (Windows only quick pass)
            if self.port is None:
                try:
                    import serial.tools.list_ports as lp
                    ports = [p.device for p in lp.comports()]
                except Exception:
                    ports = []
                # naive pick: first with 'USB' or 'ACM' or any
                choice = None
                for p in ports:
                    if 'USB' in p.upper() or 'ACM' in p.upper() or 'COM' in p.upper():
                        choice = p
                        break
                self.port = choice or (ports[0] if ports else None)
            if not self.port:
                self.last_error = 'No serial port found. Please set Printer.port before connect().'
                return False

            self.ser = serial.Serial(self.port, self.baud, timeout=self.read_timeout)
            self.connected = True

            # Marlin resets on connect; wait a moment and clear buffer
            time.sleep(1.5)
            self._drain_input()

            # Relative moves and units
            self.send_gcode('G21')  # mm
            self.send_gcode('G91')  # relative
            self.send_gcode('M114')  # prime comms
            return True
        except Exception as e:
            self.last_error = str(e)
            self.connected = False
            try:
                if self.ser:
                    self.ser.close()
            except Exception:
                pass
            self.ser = None
            return False

    def disconnect(self):
        try:
            if self.ser:
                try:
                    self.ser.close()
                except Exception:
                    pass
        finally:
            self.ser = None
            self.connected = False

    # ---- I/O helpers ----
    def _drain_input(self):
        if not self.ser:
            return
        try:
            self.ser.reset_input_buffer()
        except Exception:
            # fallback: read whatever is pending
            try:
                while self.ser.in_waiting:
                    _ = self.ser.readline()
            except Exception:
                pass

    def _write_line(self, line: str):
        if not self.connected or not self.ser:
            raise RuntimeError('Not connected')
        data = (line.strip() + "\n").encode('ascii', errors='ignore')
        with self._io_lock:
            self.ser.write(data)
            self.ser.flush()
        print(f"DEBUG_CB: Serial Buffer written and flushed: {line.strip()}")

    def _read_until_ok(self, timeout: float = 2.0) -> bool:
        if not self.ser:
            return False
        end = time.time() + max(0.01, timeout)
        ok = False
        while time.time() < end:
            try:
                line = self.ser.readline().decode('utf-8', errors='ignore').strip()
            except Exception:
                line = ''
            if not line:
                continue
            if line.lower().startswith('error'):
                self.last_error = line
            if line.lower() == 'ok' or line.endswith('ok'):
                ok = True
                break
        return ok

    # ---- Public API ----
    def send_gcode(self, gcode: str, wait_ok: bool = True, timeout: float = 2.0) -> bool:
        try:
            with self._io_lock:
                for line in gcode.splitlines():
                    if not line.strip():
                        continue
                    self._write_line(line)
                    
                return self._read_until_ok(timeout) if wait_ok else True
        except Exception as e:
            self.last_error = str(e)
            return False

    def emergency_stop(self):
        try:
            self.send_gcode('M112', wait_ok=False)
        except Exception as e:
            self.last_error = str(e)

    def home_xy(self) -> bool:
        return self.send_gcode('G28')

    # Carriage selection (1 -> XYZ, 2 -> ABC)
    def set_carriage(self, which: int):
        self._carriage = 1 if which != 2 else 2

    # Continuous jog control
    def jog(self, vx: float, vy: float, vz: float, feedrate: float) -> bool:
        print(f"DEBUG_CB: Jogging on {self._carriage}: vx={vx}, vy={vy}, vz={vz}, feedrate={feedrate}")
        """Start/maintain a long move for current carriage in given direction/speed.

        - Uses G91 relative mode.
        - If direction or feed changes, issues M410 then a new long G1.
        - vx,vy,vz are signed velocities in mm/min (converted into a unit direction).
        """
        if not self.connected:
            return False

        # Map components to axes by carriage
        if self._carriage == 1:
            ax = ('X', 'Y', 'Z')
        else:
            ax = ('A', 'B', 'C')

        # Direction vector
        dir_tuple = (
            1.0 if vx > 0 else (-1.0 if vx < 0 else 0.0),
            1.0 if vy > 0 else (-1.0 if vy < 0 else 0.0),
            1.0 if vz > 0 else (-1.0 if vz < 0 else 0.0),
        )

        # If all zero -> stop
        if dir_tuple == (0.0, 0.0, 0.0) or feedrate <= 0:
            return self.stop_jog()

        # Only (re)issue when direction or feed changed
        if dir_tuple == self._last_dir[self._carriage] and abs(feedrate - self._last_feed) < 1e-6:
            return True

        # Stop existing motion immediately
        if self.is_moving:
            self.send_gcode('M410', wait_ok=False)

        # Large distance along each active axis (kept small but sufficient; M410 will stop it)
        dist = 1000.0  # mm
        parts = []
        for comp, axis in zip(dir_tuple, ax):
            if comp != 0.0:
                parts.append(f"{axis}{dist * comp:.3f}")
        if not parts:
            return True
        g1 = f"G1 {' '.join(parts)} F{max(1,int(feedrate))}"
        # For latency: don't wait for ok on long jog G1; M410 will stop immediately when needed
        print(f"DEBUG_CB: Sending G1 on {self._carriage}: {g1}")
        ok = self.send_gcode(g1, wait_ok=True)
        self.is_moving = ok
        print(f"DEBUG_CB: sent")
        if ok:
            self._last_dir[self._carriage] = dir_tuple
            self._last_feed = feedrate
        return ok

    def stop_jog(self) -> bool:
        # Immediate stop of planner queue
        ok = self.send_gcode('M410')
        self.is_moving = False
        self._last_dir[self._carriage] = (0.0, 0.0, 0.0)
        self._last_feed = 0.0
        print("DEBUG_CB: Stopped jogging")
        return ok

    # Direct small moves (optional)
    def move_relative(self, dx: float = 0.0, dy: float = 0.0, dz: float = 0.0, feedrate: float = 1000.0) -> bool:
        if self._carriage == 2:
            axes = [('A', dx), ('B', dy), ('C', dz)]
        else:
            axes = [('X', dx), ('Y', dy), ('Z', dz)]
        parts = [f"{a}{v:.4f}" for a, v in axes if abs(v) > 1e-6]
        if not parts:
            return True
        return self.send_gcode(f"G91\nG1 {' '.join(parts)} F{max(1,int(feedrate))}")

    # Basic position query (Marlin M114 parsing is heuristic)
    def get_position(self) -> Optional[dict[str, float]]:
        if not self.connected:
            return None
        # Try non-blocking to avoid interfering with motion commands
        acquired = self._io_lock.acquire(blocking=False)
        if not acquired:
            return None
        try:
            self._write_line('M114')
            end = time.time() + 0.2
            line = ''
            while time.time() < end:
                try:
                    s = self.ser.readline().decode('utf-8', errors='ignore').strip()
                except Exception:
                    s = ''
                if s:
                    line = s
                    if 'ok' in s.lower():
                        break
            # Example: "X:0.00 Y:0.00 Z:0.00 E:0.00 Count X:0 Y:0 Z:0"
            vals: dict[str, float] = {}
            for token in line.replace(',', ' ').split():
                if ':' in token:
                    k, v = token.split(':', 1)
                    try:
                        vals[k.lower()] = float(v)
                    except Exception:
                        pass
            # Map to our axes; Marlin won't report A/B/C; return current XYZ only
            return {
                'x': vals.get('x', 0.0),
                'y': vals.get('y', 0.0),
                'z': vals.get('z', 0.0),
            }
        except Exception as e:
            self.last_error = str(e)
            return None
        finally:
            try:
                self._io_lock.release()
            except Exception:
                pass
