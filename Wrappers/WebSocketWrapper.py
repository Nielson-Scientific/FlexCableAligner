import json
import time
from pathlib import Path
from schema.PositionSchema import Position
from Wrappers.WebSocketClient import WebSocketClient

PROFILE_WS = False
PROFILE_LOG_TO_CONSOLE = False
PROFILE_LOG_PATH = Path("logs/motion_profile.log")

class WebSocketWrapper:
    def __init__(self, url):
        self.url = url
        self.ws = None
        self.connected = False
        self._next_request_id = 10

    def _new_request_id(self):
        rid = self._next_request_id
        self._next_request_id += 1
        return rid

    def _log_timing(self, label, elapsed_s, extra=""):
        if PROFILE_WS:
            suffix = f" | {extra}" if extra else ""
            msg = f"[WS PROFILE] {label}: {elapsed_s*1000:.1f} ms{suffix}"
            if PROFILE_LOG_TO_CONSOLE:
                print(msg)
            self._append_profile_log(msg)

    def _append_profile_log(self, msg):
        ts = time.strftime("%Y-%m-%d %H:%M:%S")
        PROFILE_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        with PROFILE_LOG_PATH.open("a", encoding="utf-8") as f:
            f.write(f"{ts} {msg}\n")

    def connect(self):
        try:
            self.ws = WebSocketClient(self.url)
            self.ws.connect()
            self.connected = True
        except Exception as e:
            print(f"Error connecting to WebSocket: {e}")

    def send_gcode(self, gcode):
        if not self.connected:
            print("WebSocket is not connected.")
            return
        
        req_id = self._new_request_id()
        gcode_req = {
            "jsonrpc": "2.0",
            "method": "printer.gcode.script",
            "params": {
                "script": gcode
            },
            "id": req_id
        }
        self.ws.send(json.dumps(gcode_req))
    
    def send_gcode_and_wait(self, gcode, timeout=10):
        if not self.connected:
            print("WebSocket is not connected.")
            return None

        req_id = self._new_request_id()
        gcode_req = {
            "jsonrpc": "2.0",
            "method": "printer.gcode.script",
            "params": {
                "script": gcode
            },
            "id": req_id
        }
        t0 = time.perf_counter()
        reply = self.ws.send_and_wait_for(json.dumps(gcode_req), req_id, timeout)
        self._log_timing("send_gcode_and_wait", time.perf_counter() - t0, gcode)
        return reply

    def get_z_positions(self):
        t0 = time.perf_counter()
        req_id = self._new_request_id()
        query_req = {
            "jsonrpc": "2.0",
            "method": "printer.objects.query",
            "params": {
                "objects": {
                    "gcode_macro _Z_AXIS_STATE": None
                }
            },
            "id": req_id
        }

        data = self.ws.send_and_wait_for(json.dumps(query_req), req_id, 10)
        if not data:
            self._log_timing("get_z_positions", time.perf_counter() - t0, "no data")
            return [None, None, None, None]
        status = data.get('result', {}).get('status', {})
        state = status.get('gcode_macro _Z_AXIS_STATE', {})

        z1 = state.get('pos_1')
        z2 = state.get('pos_2')
        z3 = state.get('pos_3')
        z4 = state.get('pos_4')

        self._log_timing("get_z_positions", time.perf_counter() - t0, f"z1={z1}, z2={z2}")
        return [z1, z2, z3, z4]

    def get_z_position(self, axis):
        if axis not in (1, 2, 3, 4):
            raise ValueError("axis must be 1, 2, 3, or 4")
        t0 = time.perf_counter()
        z_vals = self.get_z_positions()
        z_val = z_vals[axis - 1]
        self._log_timing("get_z_position", time.perf_counter() - t0, f"axis={axis}, z={z_val}")
        return z_val

    def get_position_data(self):
        t0 = time.perf_counter()
        req_id = self._new_request_id()
        subscribe_req = {
            "jsonrpc": "2.0",
            "method": "printer.objects.query",
            "params": {
                "objects": {
                    "toolhead": ["position"]
                }
            },
            "id": req_id
        }
        def get_carriage_pos():
            data = self.ws.send_and_wait_for(json.dumps(subscribe_req), req_id, 10)
            pos = data.get('result', {}).get('status', {}).get('toolhead', {}).get('position', [None, None, None])
            return pos[:3]
        
        x, y, _ = get_carriage_pos()
        z1, z2, z3, z4 = self.get_z_positions()
        
        pos = Position(
            x1 = x,
            y1 = y,
            z1 = z1,
            z2 = z2,
        )

        self._log_timing("get_position", time.perf_counter() - t0, str(pos))
        return pos

    def get_velocity_data(self):
        req_id = self._new_request_id()
        subscribe_req = {
            "jsonrpc": "2.0",
            "method": "printer.objects.query",
            "params": {
                "objects": {
                    "motion_report": ["live_velocity"]
                }
            },
            "id": req_id
        }
        data = self.ws.send_and_wait_for(json.dumps(subscribe_req), req_id, 10)
        velocity = data.get('result', {}).get('status', {}).get('motion_report', {}).get('live_velocity', 0)
        return velocity

    
        





if __name__ == "__main__":
    url = "ws://10.34.243.54:7125/websocket"
    import sys
    sys.path.append("..") # Add parent directory to path to access WebSocketClient
    ws_wrapper = WebSocketWrapper(url)
    ws_wrapper.connect()
    if ws_wrapper.connected:
        import time
        tt = 0
        it = 5
        for i in range(it):
            t = time.time()
            ws_wrapper.get_position_data()
            tt += time.time() - t
        print(f"Average time taken to get position: {tt/it:.2f} seconds")