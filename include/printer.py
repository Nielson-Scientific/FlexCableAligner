import json
import socket
import threading
import time
from typing import Optional, Any


class Printer:
    """Synchronous Klipper JSON-RPC client over Unix Domain Socket (UDS).

    Keeps the same public interface as the previous WebSocket client: send G-Code,
    relative mode, basic moves, and simple helpers. Intended to run on the same
    Raspberry Pi as Klipper with the API server enabled (-a /tmp/klippy_uds).
    """

    ETX = b"\x03"  # message terminator per Klipper API server

    def __init__(self, uds_path: str = "/home/nielson-scientific/printer_data/comms/klippy.sock"):
        self.uds_path = uds_path
        self.sock: Optional[socket.socket] = None
        self._recv_buffer = bytearray()
        self.message_id = 1
        self.lock = threading.Lock()  # ensure request/response pairing
        self.connected = False
        self.last_error: Optional[str] = None
        self.uv_carriage_prefix = "SET_DUAL_CARRIAGE CARRIAGE=x2\nSET_DUAL_CARRIAGE CARRIAGE=y2\n"
        self.xy_carriage_prefix = "SET_DUAL_CARRIAGE CARRIAGE=x\nSET_DUAL_CARRIAGE CARRIAGE=y\n"

    # ---- Connection management ----
    def connect(self) -> bool:
        try:
            s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            s.settimeout(5.0)
            s.connect(self.uds_path)
            self.sock = s
            self.connected = True
            # Say hello and switch to relative mode
            try:
                self._rpc("info", {"client_info": {"name": "FlexCableAligner", "version": "uds"}}, timeout=2.0)
            except Exception:
                pass  # non-fatal
            # Switch to relative move mode so jogs are easy
            self.send_gcode("G91", timeout=2.0)
            return True
        except Exception as e:
            self.last_error = str(e)
            self.connected = False
            self.sock = None
            return False

    def disconnect(self):
        try:
            if self.sock:
                try:
                    self.sock.shutdown(socket.SHUT_RDWR)
                except Exception:
                    pass
                self.sock.close()
        finally:
            self.sock = None
            self.connected = False
            self._recv_buffer = bytearray()

    # ---- Low level JSON-RPC over UDS ----
    def _send(self, data: dict):
        if not self.connected or not self.sock:
            raise RuntimeError("Not connected")
        encoded = json.dumps(data, separators=(",", ":")).encode("utf-8") + self.ETX
        self.sock.sendall(encoded)

    def _recv_until_message(self, timeout: float) -> Optional[dict]:
        if not self.connected or not self.sock:
            raise RuntimeError("Not connected")
        end_time = time.time() + timeout
        self.sock.settimeout(max(0.01, timeout))
        while time.time() < end_time:
            # Check if there's a complete message already buffered
            idx = self._recv_buffer.find(self.ETX)
            if idx != -1:
                raw = self._recv_buffer[:idx]
                del self._recv_buffer[: idx + 1]
                if not raw:
                    continue
                try:
                    return json.loads(raw.decode("utf-8"))
                except json.JSONDecodeError:
                    continue
            try:
                chunk = self.sock.recv(4096)
                if not chunk:
                    # socket closed
                    self.disconnect()
                    return None
                self._recv_buffer.extend(chunk)
            except socket.timeout:
                # allow loop to re-check time and buffer
                pass
            except Exception:
                self.disconnect()
                return None
        return None

    def _rpc(self, method: str, params: Optional[dict] = None, timeout: float = 2.0) -> dict:
        if not self.connected or not self.sock:
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
                msg = self._recv_until_message(max(0.0, end_time - time.time()))
                if not msg:
                    break
                # Responses contain an id; notifications don't
                if msg.get("id") == req_id:
                    if "error" in msg:
                        raise RuntimeError(msg["error"].get("message", str(msg["error"])) )
                    return msg
                # ignore async notifications or other responses
            raise TimeoutError(f"RPC {method} timed out")

    # ---- GCode helpers ----
    def send_gcode(self, script: str, timeout: float = 2.0) -> bool:
        try:
            # Klipper UDS uses gcode/script; result is an object (often empty)
            _ = self._rpc("gcode/script", {"script": script}, timeout=timeout)
            return True
        except Exception as e:
            self.last_error = str(e)
            return False

    def home_xy(self) -> bool:
        return self.send_gcode("G28 X Y")

    def emergency_stop(self):
        try:
            self._rpc("emergency_stop", {}, timeout=1.0)
        except Exception as e:
            self.last_error = str(e)

    # Movement utilities use relative moves (G91 already set)
    def move_xy(self, dx: float, dy: float, feedrate: float) -> bool:
        g = f"G1 X{dx:.4f} Y{dy:.4f} F{feedrate:.0f}"
        return self.send_gcode(g)

    def move_uv(self, du: float, dv: float, feedrate: float) -> bool:
        # Carriage selection then move
        script = (
            "SET_DUAL_CARRIAGE CARRIAGE=x2\n"
            "SET_DUAL_CARRIAGE CARRIAGE=y2\n"
            f"G1 X{du:.4f} Y{dv:.4f} F{feedrate:.0f}"
        )
        return self.send_gcode(script)

    def move_xy_with_carriage(self, dx: float, dy: float, feedrate: float) -> bool:
        script = (
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
        try:
            resp = self._rpc(
                "objects/query",
                {"objects": {"toolhead": ["position"]}},
                timeout=0.5,
            )
            pos = resp["result"]["status"]["toolhead"]["position"]
            print('Position object:', resp)
            return {"x": pos[0], "y": pos[1], "z": pos[2], "e": pos[3] if len(pos) > 3 else 0.0}
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
