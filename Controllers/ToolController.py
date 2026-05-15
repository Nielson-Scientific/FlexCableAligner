import time
from pathlib import Path

from Wrappers.WebSocketWrapper import WebSocketWrapper
from schema.PositionSchema import Position
from Controllers.GCodeCommands import GCodeCMD

FEEDRATE = 3000
DEF_URL = "ws://10.34.243.54:7125/websocket"
PROFILE_MOVE = False
PROFILE_LOG_TO_CONSOLE = False
PROFILE_LOG_PATH = Path("logs/motion_profile.log")

class ToolController:
    def __init__(self, ws_url = DEF_URL):
        self.ws_wrapper = WebSocketWrapper(ws_url)
        self.ws_wrapper.connect()
        self.selected_carriage = 1
        self.select_carriage(self.selected_carriage, force = True) # Default to carriage 1
        self.ws_wrapper.send_gcode(GCodeCMD.ABSOLUTE_POSITIONING())  # Set to absolute positioning
        self.position: Position = self.refresh_position()

        

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
        current_carriage = self.selected_carriage
        self.select_carriage(1)
        carriage_1_pos = self.ws_wrapper.get_position_data()
        self.select_carriage(2)
        carriage_2_pos = self.ws_wrapper.get_position_data()
        self.select_carriage(current_carriage)

        # This code is a little wierd, but trust :)
        self.position = Position(
            x1 = carriage_1_pos.x1,
            y1 = carriage_1_pos.y1,
            z1 = carriage_1_pos.z1,
            x2 = carriage_2_pos.x1,
            y2 = carriage_2_pos.y1,
            z2 = carriage_2_pos.z2,
        )
        return self.position
    
    def select_carriage(self, carriage_number, force = False):
        if carriage_number not in [1, 2]:
            print("Invalid carriage number. Must be 1 or 2.")
            return
        if carriage_number == self.selected_carriage and not force:
            return
        gcode = GCodeCMD.SELECT_CARRAIGE(carriage_number)
        self.selected_carriage = carriage_number
        self.ws_wrapper.send_gcode_and_wait(gcode)
    
    def move(self, move: Position, absolute=True, blocking=True, verify_mov = True, set_speed = None):
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

        # Set the movement speed manually, otherwise default to the FEEDRATE
        move_speed = FEEDRATE if set_speed is None else set_speed


        if move.x1 is not None or move.y1 is not None or move.z1 is not None:
            t0 = time.perf_counter()
            self.select_carriage(1)
            gcode = GCodeCMD.MOVE(move, carriage = 1, feed = move_speed)
            self.ws_wrapper.send_gcode(gcode)
            if PROFILE_MOVE:
                self._profile_log(f"[MOVE PROFILE] queue carriage1 cmd took {(time.perf_counter() - t0)*1000:.1f} ms")

        if move.x2 is not None or move.y2 is not None or move.z2 is not None:
            t0 = time.perf_counter()
            self.select_carriage(2)
            gcode = GCodeCMD.MOVE(move, carriage = 2, feed = move_speed)
            self.ws_wrapper.send_gcode(gcode)
            if PROFILE_MOVE:
                self._profile_log(f"[MOVE PROFILE] queue carriage2 cmd took {(time.perf_counter() - t0)*1000:.1f} ms")

        print(f"Sent move command: {move} (absolute={absolute})")

        if blocking:
            # Always block on queued motion completion; this also catches manual_stepper macro moves.
            t_wait = time.perf_counter()
            self.wait_for_moves()
            if PROFILE_MOVE:
                self._profile_log(f"[MOVE PROFILE] wait_for_moves took {(time.perf_counter() - t_wait)*1000:.1f} ms")

            if not z_only_move:
                t_vel = time.perf_counter()
                vel_checks = 0
                while self.is_toolhead_moving():
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
        gcode = GCodeCMD.HOME_ALL()
        self.ws_wrapper.send_gcode(gcode)
        # self.wait_for(5)
        while self.is_toolhead_moving():
            time.sleep(0.1)
        self.refresh_position()

    def avoid_home(self):
        gcode = GCodeCMD.AVOID_HOME(self.position)
        self.ws_wrapper.send_gcode(gcode)

    def is_toolhead_moving(self):
        current_carriage = self.selected_carriage
        moving = False
        self.select_carriage(1)
        if self.ws_wrapper.get_velocity_data() > 0:
            moving = True
        self.select_carriage(2)
        if moving or self.ws_wrapper.get_velocity_data() > 0:
            moving = True
        self.select_carriage(current_carriage)
        return moving
    
    def wait_for_moves(self):
        self.ws_wrapper.send_gcode_and_wait(GCodeCMD.WAIT_FOR_MOVES(), timeout=30)    

if __name__ == "__main__":
    url = "ws://10.34.243.54:7125/websocket"
    tool_controller = ToolController(url)
    print("Current Position:", tool_controller.get_position())
    new_position = Position(x1=100, y1=10, x2=500, y2=20)
    tool_controller.move(new_position)
