import json
import threading
import time
from typing import Optional, Any

from websocket import create_connection, WebSocket


class Printer:
    """Synchronous Klipper JSON-RPC client over Moonraker WebSocket.

    Public interface is unchanged: send G-Code, movement helpers, etc.
    Connects to Moonraker (default ws://localhost:7125/websocket).
    """

    def __init__(self, url: str = "ws://nielson-aligner.local:7125/websocket", api_key: Optional[str] = None):
        # Moonraker connection settings
        self.url = url
        self.api_key = api_key

        # WebSocket handle
        self.ws: Optional[WebSocket] = None

        # RPC state
        self.message_id = 1
        self.lock = threading.Lock()  # ensure request/response pairing
        self.connected = False
        self.last_error: Optional[str] = None
        self.uv_carriage_prefix = "SET_DUAL_CARRIAGE CARRIAGE=x2\nSET_DUAL_CARRIAGE CARRIAGE=y2\n"
        self.xy_carriage_prefix = "SET_DUAL_CARRIAGE CARRIAGE=x\nSET_DUAL_CARRIAGE CARRIAGE=y\n"

    # ---- Connection management ----
    def connect(self) -> bool:
        try:
            headers = []
            if self.api_key:
                headers.append(f"X-Api-Key: {self.api_key}")
            # Establish WebSocket connection to Moonraker
            self.ws = create_connection(self.url, header=headers, timeout=5)
            self.connected = True

            # Optional: query server info (non-fatal if it fails)
            try:
                self._rpc("server.info", {}, timeout=2.0)
            except Exception:
                pass

            # Switch to relative move mode so jogs are easy
            self.send_gcode("G91", timeout=2.0)
            return True
        except Exception as e:
            self.last_error = str(e)
            self.connected = False
            self.ws = None
            return False

    def disconnect(self):
        try:
            if self.ws:
                try:
                    self.ws.close()
                except Exception:
                    pass
        finally:
            self.ws = None
            self.connected = False

    # ---- Low level JSON-RPC over Moonraker WebSocket ----
    def _send(self, data: dict):
        if not self.connected or not self.ws:
            raise RuntimeError("Not connected")
        encoded = json.dumps({"jsonrpc": "2.0", **data}, separators=(",", ":"))
        self.ws.send(encoded)

    def _recv_next(self, timeout: float) -> Optional[dict]:
        if not self.connected or not self.ws:
            raise RuntimeError("Not connected")
        # websocket-client raises WebSocketTimeoutException on timeout
        prev_to = getattr(self.ws, 'sock', None)
        self.ws.settimeout(max(0.01, timeout))
        try:
            raw = self.ws.recv()
            if raw is None:
                return None
            if isinstance(raw, (bytes, bytearray)):
                raw = raw.decode("utf-8", errors="ignore")
            try:
                return json.loads(raw)
            except json.JSONDecodeError:
                return None
        except Exception:
            return None

    def _rpc(self, method: str, params: Optional[dict] = None, timeout: float = 2.0) -> dict:
        if not self.connected or not self.ws:
            raise RuntimeError("Not connected")
        with self.lock:
            req_id = self.message_id
            self.message_id += 1
            payload = {
                "id": req_id,
                "method": method,
                "params": params or {},
            }
            self._send(payload)
            end_time = time.time() + timeout
            while time.time() < end_time:
                msg = self._recv_next(max(0.01, end_time - time.time()))
                if not msg:
                    continue
                # Responses contain an id; notifications don't
                if msg.get("id") == req_id:
                    if "error" in msg:
                        err = msg["error"]
                        # Moonraker error format: {code, message}
                        raise RuntimeError(err.get("message", str(err)))
                    return msg
                # ignore async notifications or other responses
            raise TimeoutError(f"RPC {method} timed out")

    # ---- GCode helpers ----
    def send_gcode(self, script: str, timeout: float = 2.0) -> bool:
        try:
            # Moonraker uses method: printer.gcode.script
            _ = self._rpc("printer.gcode.script", {"script": script}, timeout=timeout)
            return True
        except Exception as e:
            self.last_error = str(e)
            return False

    def home_xy(self) -> bool:
        return self.send_gcode("G28 X Y")

    def emergency_stop(self):
        try:
            self._rpc("printer.emergency_stop", {}, timeout=1.0)
        except Exception as e:
            self.last_error = str(e)

    # Movement utilities use relative moves (G91 already set)
    def move_xy(self, dx: float, dy: float, feedrate: float) -> bool:
        g = f"G1 X{dx:.4f} Y{dy:.4f} F{feedrate:.0f}"
        return self.send_gcode(g)

    def move_uv(self, du: float, dv: float, feedrate: float) -> bool:
        # Carriage selection then move
        script = (
            "G91\n"
            "SET_DUAL_CARRIAGE CARRIAGE=x2\n"
            "SET_DUAL_CARRIAGE CARRIAGE=y2\n"
            f"G1 X{du:.4f} Y{dv:.4f} F{feedrate:.0f}"
        )
        return self.send_gcode(script)

    def move_xy_with_carriage(self, dx: float, dy: float, feedrate: float) -> bool:
        script = (
            "G91\n"
            "SET_DUAL_CARRIAGE CARRIAGE=x\n"
            "SET_DUAL_CARRIAGE CARRIAGE=y\n"
            f"G1 X{dx:.4f} Y{dy:.4f} F{feedrate:.0f}"
        )
        return self.send_gcode(script)

    def get_position(self) -> Optional[dict[str, float]]:
        """Query Klipper for current toolhead position via objects/query.

        Returns a dict with keys x, y, z, e (as reported by toolhead.position).
        Note: This reflects the currently active carriage.
        """
        positions = {}
        try:
            # First set carriage to XY mode
            self.send_gcode(self.xy_carriage_prefix)
            resp = self._rpc(
                "printer.objects.query",
                {"objects": {"toolhead": ["position"]}},
                timeout=0.5,
            )
            pos = resp["result"]["status"]["toolhead"]["position"]
            positions["x"] = pos[0]
            positions['y'] = pos[1]

            # Now do the same for UV
            self.send_gcode(self.uv_carriage_prefix)
            resp = self._rpc(
                "printer.objects.query",
                {"objects": {"toolhead": ["position"]}},
                timeout=0.5,
            )
            pos = resp["result"]["status"]["toolhead"]["position"]
            positions["u"] = pos[0]
            positions['v'] = pos[1]
            return positions
        except Exception as e:
            self.last_error = str(e)
            return None

    def set_kinematic_position(self, x: float, y: float, u: float, v: float) -> bool:
        script = (
            "SET_DUAL_CARRIAGE CARRIAGE=x\n"
            "SET_DUAL_CARRIAGE CARRIAGE=y\n"
            f"SET_KINEMATIC_POSITION X={x:.4f} Y={y:.4f}\n"
            "SET_DUAL_CARRIAGE CARRIAGE=x2\n"
            "SET_DUAL_CARRIAGE CARRIAGE=y2\n"
            f"SET_KINEMATIC_POSITION X={u:.4f} Y={v:.4f}"
        )
        return self.send_gcode(script)
    

    def goto_position(self, x: float, y: float, u: float, v: float, feedrate: float = 1500.0) -> bool:
        script = (
            "SET_DUAL_CARRIAGE CARRIAGE=x\n"
            "SET_DUAL_CARRIAGE CARRIAGE=y\n"
            "G90\n"
            f"G1 X{x:.4f} Y{y:.4f} F{feedrate:.0f}\n"
            "SET_DUAL_CARRIAGE CARRIAGE=x2\n"
            "SET_DUAL_CARRIAGE CARRIAGE=y2\n"
            f"G1 X{u:.4f} Y{v:.4f} F{feedrate:.0f}\n"
            "G91\n"
        )
        return self.send_gcode(script)
