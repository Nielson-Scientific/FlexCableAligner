import json
import threading
import time
from typing import Optional, Any

try:
    import websocket  # websocket-client (sync)
except ImportError:  # pragma: no cover
    websocket = None


class Printer:
    """Synchronous WebSocket JSON-RPC client for Moonraker / Klipper.

    Only minimal features needed for this GUI (send gcode, relative mode, basic moves).
    We track positions locally; the printer is driven in relative (G91) mode the whole time.
    """

    def __init__(self, url: str = "ws://products.local:7125/websocket"):
        self.url = url
    # underlying websocket-client connection (typed loosely to avoid import issues)
        self.ws: Optional[Any] = None
        self.message_id = 1
        self.lock = threading.Lock()  # ensure request/response pairing
        self.connected = False
        self.last_error: Optional[str] = None

    def connect(self) -> bool:
        if websocket is None:
            self.last_error = "websocket-client not installed (pip install websocket-client)"
            return False
        try:
            self.ws = websocket.create_connection(self.url, timeout=5)
            self.connected = True
            # Switch to relative mode so we can accumulate locally
            self.send_gcode("G91")
            return True
        except Exception as e:  # pragma: no cover
            self.last_error = str(e)
            self.connected = False
            self.ws = None
            return False

    def disconnect(self):
        try:
            if self.ws:
                self.ws.close()
        finally:
            self.ws = None
            self.connected = False

    # ---- Low level JSON-RPC ----
    def _rpc(self, method: str, params: dict | None = None, timeout: float = 2.0):
        if not self.connected or not self.ws:
            raise RuntimeError("Not connected")
        with self.lock:
            req_id = self.message_id
            self.message_id += 1
            payload = json.dumps({
                "jsonrpc": "2.0",
                "id": req_id,
                "method": method,
                "params": params or {}
            })
            self.ws.send(payload)
            self.ws.settimeout(timeout)
            start = time.time()
            while True:
                resp_txt = self.ws.recv()
                try:
                    data = json.loads(resp_txt)
                except json.JSONDecodeError:
                    continue
                if data.get('id') == req_id:
                    return data
                # ignore stray notifications
                if time.time() - start > timeout:
                    raise TimeoutError(f"RPC {method} timed out")

    # ---- GCode helpers ----
    def send_gcode(self, script: str, timeout: float = 2.0) -> bool:
        try:
            resp = self._rpc("printer.gcode.script", {"script": script}, timeout=timeout)
            if resp.get('result') == 'ok':
                return True
            # If code 400 (not homed) we return False so caller can handle
            if resp.get('error', {}).get('code') == 400:
                print('Not homed')
                return False
            return False
        except Exception as e:
            self.last_error = str(e)
            return False

    def home_xy(self):
        return self.send_gcode("G28 X Y")

    def emergency_stop(self):
        self.send_gcode("M112")

    # Movement utilities use relative moves (G91 already set)
    def move_xy(self, dx: float, dy: float, feedrate: float) -> bool:
        g = f"G1 X{dx:.4f} Y{dy:.4f} F{feedrate:.0f}"
        return self.send_gcode(g)

    def move_uv(self, du: float, dv: float, feedrate: float) -> bool:
        # Carriage selection then move
        script = f"SET_DUAL_CARRIAGE CARRIAGE=x2\nSET_DUAL_CARRIAGE CARRIAGE=y2\nG1 X{du:.4f} Y{dv:.4f} F{feedrate:.0f}"
        return self.send_gcode(script)

    def move_xy_with_carriage(self, dx: float, dy: float, feedrate: float) -> bool:
        script = f"SET_DUAL_CARRIAGE CARRIAGE=x\nSET_DUAL_CARRIAGE CARRIAGE=y\nG1 X{dx:.4f} Y{dy:.4f} F{feedrate:.0f}"
        return self.send_gcode(script)

    def set_kinematic_position(self, x: float, y: float, u: float, v: float):
        script = (f"SET_DUAL_CARRIAGE CARRIAGE=x\nSET_DUAL_CARRIAGE CARRIAGE=y\n"
                  f"SET_KINEMATIC_POSITION X={x:.4f} Y={y:.4f}\n"
                  f"SET_DUAL_CARRIAGE CARRIAGE=x2\nSET_DUAL_CARRIAGE CARRIAGE=y2\n"
                  f"SET_KINEMATIC_POSITION X={u:.4f} Y={v:.4f}")
        return self.send_gcode(script)
