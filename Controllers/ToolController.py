from Wrappers.WebSocketWrapper import WebSocketWrapper
from PositionSchema import Position
import time
from pathlib import Path

FEEDRATE = 3000
DEF_URL = "ws://10.34.243.54:7125/websocket"
PROFILE_MOVE = True
PROFILE_LOG_TO_CONSOLE = True
PROFILE_LOG_PATH = Path("logs/motion_profile.log")

class ToolController:
    def __init__(self, ws_url = DEF_URL):
        self.ws_wrapper = WebSocketWrapper(ws_url)
        self.ws_wrapper.connect()
        self.position: Position = self.ws_wrapper.get_position()
        self.ws_wrapper.send_gcode('G90')  # Set to absolute positioning
        self.ws_wrapper.select_carriage(1) # Default to carriage 1
        self.current_carriage = 1

    def wait_for(self, seconds):
        time.sleep(seconds)

    def _profile_log(self, msg):
        if PROFILE_LOG_TO_CONSOLE:
            print(msg)
        ts = time.strftime("%Y-%m-%d %H:%M:%S")
        PROFILE_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        with PROFILE_LOG_PATH.open("a", encoding="utf-8") as f:
            f.write(f"{ts} {msg}\n")

    def get_position(self):
        return self.position
    
    def refresh_position(self):
        self.position = self.ws_wrapper.get_position()
        return self.position
    
    def select_carriage(self, carriage_number):
        self.ws_wrapper.select_carriage(carriage_number)
        self.current_carriage = carriage_number
    
    def move(self, move: Position, absolute=True, blocking=True, verify_mov = True):
        move_t0 = time.perf_counter()
        xy_move_requested = any(v is not None for v in (move.x1, move.y1, move.x2, move.y2))
        z_move_requested = move.z1 is not None or move.z2 is not None
        z_only_move = z_move_requested and not xy_move_requested
        if not absolute:
            move = Position(
                x1=move.x1 + self.position.x1 if move.x1 is not None else None,
                y1=move.y1 + self.position.y1 if move.y1 is not None else None,
                z1=move.z1 + self.position.z1 if move.z1 is not None else None,
                x2=move.x2 + self.position.x2 if move.x2 is not None else None,
                y2=move.y2 + self.position.y2 if move.y2 is not None else None,
                z2=move.z2 + self.position.z2 if move.z2 is not None else None
            )

        if move.x1 is not None or move.y1 is not None or move.z1 is not None:
            t0 = time.perf_counter()
            self.ws_wrapper.select_carriage(1)
            gcode = "COMPENSATED_ABS_MV"
            if move.x1 is not None:
                gcode += f" X={move.x1}"
            if move.y1 is not None:
                gcode += f" Y={move.y1}"
            if move.z1 is not None:
                gcode += f" Z={move.z1} Z_AXIS=1"
            gcode += f" F={FEEDRATE}"
            self.ws_wrapper.send_gcode(gcode)
            if PROFILE_MOVE:
                self._profile_log(f"[MOVE PROFILE] queue carriage1 cmd took {(time.perf_counter() - t0)*1000:.1f} ms")

        if move.x2 is not None or move.y2 is not None or move.z2 is not None:
            t0 = time.perf_counter()
            self.ws_wrapper.select_carriage(2)
            gcode = "COMPENSATED_ABS_MV"
            if move.x2 is not None:
                gcode += f" X={move.x2}"
            if move.y2 is not None:
                gcode += f" Y={move.y2}"
            if move.z2 is not None:
                gcode += f" Z={move.z2} Z_AXIS=2"
            gcode += f" F={FEEDRATE}"
            self.ws_wrapper.send_gcode(gcode)
            if PROFILE_MOVE:
                self._profile_log(f"[MOVE PROFILE] queue carriage2 cmd took {(time.perf_counter() - t0)*1000:.1f} ms")

        print(f"Sent move command: {move} (absolute={absolute})")

        if blocking:
            # Always block on queued motion completion; this also catches manual_stepper macro moves.
            t_wait = time.perf_counter()
            self.ws_wrapper.wait_for_moves()
            if PROFILE_MOVE:
                self._profile_log(f"[MOVE PROFILE] wait_for_moves took {(time.perf_counter() - t_wait)*1000:.1f} ms")

            if not z_only_move:
                t_vel = time.perf_counter()
                vel_checks = 0
                while self.ws_wrapper.is_toolhead_moving():
                    vel_checks += 1
                    time.sleep(0.01)
                if PROFILE_MOVE:
                    self._profile_log(f"[MOVE PROFILE] velocity settle loop took {(time.perf_counter() - t_vel)*1000:.1f} ms ({vel_checks} checks)")
            elif PROFILE_MOVE:
                self._profile_log("[MOVE PROFILE] velocity settle loop skipped for z-only move")

            # Z movement is driven by manual steppers via macro state; wait until reported state converges.
            if z_move_requested:
                timeout_s = 5.0
                deadline = time.time() + timeout_s
                t_z = time.perf_counter()
                z_checks = 0
                while time.time() < deadline:
                    z_checks += 1
                    z1_actual = self.ws_wrapper.get_z_position(1) if move.z1 is not None else None
                    z2_actual = self.ws_wrapper.get_z_position(2) if move.z2 is not None else None
                    z1_ok = (move.z1 is None) or (z1_actual is not None and abs(z1_actual - move.z1) <= 1e-3)
                    z2_ok = (move.z2 is None) or (z2_actual is not None and abs(z2_actual - move.z2) <= 1e-3)
                    if z1_ok and z2_ok:
                        if move.z1 is not None:
                            self.position.z1 = z1_actual
                        if move.z2 is not None:
                            self.position.z2 = z2_actual
                        break
                    time.sleep(0.01)
                if PROFILE_MOVE:
                    self._profile_log(f"[MOVE PROFILE] z convergence loop took {(time.perf_counter() - t_z)*1000:.1f} ms ({z_checks} checks)")

            if verify_mov:
                t_verify = time.perf_counter()
                if z_only_move:
                    z1_actual = self.ws_wrapper.get_z_position(1) if move.z1 is not None else None
                    z2_actual = self.ws_wrapper.get_z_position(2) if move.z2 is not None else None
                    z1_ok = (move.z1 is None) or (z1_actual is not None and abs(z1_actual - move.z1) <= 1e-3)
                    z2_ok = (move.z2 is None) or (z2_actual is not None and abs(z2_actual - move.z2) <= 1e-3)
                    if not (z1_ok and z2_ok):
                        print(f"Warning: Z mismatch after move. Expected: {move}, Actual Z1={z1_actual} Z2={z2_actual}")
                        return False
                else:
                    self.refresh_position()
                    desired = Position()
                    desired.x1 = move.x1 if move.x1 is not None else self.position.x1
                    desired.y1 = move.y1 if move.y1 is not None else self.position.y1
                    desired.z1 = move.z1 if move.z1 is not None else self.position.z1
                    desired.x2 = move.x2 if move.x2 is not None else self.position.x2
                    desired.y2 = move.y2 if move.y2 is not None else self.position.y2
                    desired.z2 = move.z2 if move.z2 is not None else self.position.z2
                    if self.position != desired:
                        print(f"Warning: Position mismatch after move. Expected: {move}, Actual: {self.position}")
                        return False
                if PROFILE_MOVE:
                    self._profile_log(f"[MOVE PROFILE] verify_mov took {(time.perf_counter() - t_verify)*1000:.1f} ms")
            if PROFILE_MOVE:
                self._profile_log(f"[MOVE PROFILE] total move() time {(time.perf_counter() - move_t0)*1000:.1f} ms")
            return True
        else:
            if PROFILE_MOVE:
                self._profile_log(f"[MOVE PROFILE] non-blocking move() queued in {(time.perf_counter() - move_t0)*1000:.1f} ms")
            return True # Don't verify position for relative moves
    
    def home(self):
        self.ws_wrapper.send_gcode("HOME_ALL")
        # self.wait_for(5)
        while self.ws_wrapper.is_toolhead_moving():
            time.sleep(0.1)
        self.refresh_position()

    def avoid_home(self):
        gcode = "SET_DUAL_CARRIAGE CARRIAGE=x\nSET_DUAL_CARRIAGE CARRIAGE=y\n"
        gcode += f"SET_KINEMATIC_POSITION X={self.position.x1} Y={self.position.y1}"
        if self.position.z1 is not None:
            gcode += f" Z={self.position.z1}"
        gcode += "\n"
        gcode += "SET_DUAL_CARRIAGE CARRIAGE=x2\nSET_DUAL_CARRIAGE CARRIAGE=y2\n"
        gcode += f"SET_KINEMATIC_POSITION X={self.position.x2} Y={self.position.y2}"
        if self.position.z2 is not None:
            gcode += f" Z={self.position.z2}"
        gcode += "\n"
        self.ws_wrapper.send_gcode(gcode)

    def is_moving(self):
        return self.ws_wrapper.is_toolhead_moving()
    

if __name__ == "__main__":
    url = "ws://10.34.243.54:7125/websocket"
    tool_controller = ToolController(url)
    print("Current Position:", tool_controller.get_position())
    new_position = Position(x1=100, y1=10, x2=500, y2=20)
    tool_controller.move(new_position)
