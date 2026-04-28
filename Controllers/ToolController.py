from Wrappers.WebSocketWrapper import WebSocketWrapper
from PositionSchema import Position
import time

FEEDRATE = 9000
DEF_URL = "ws://10.34.243.54:7125/websocket"

class ToolController:
    def __init__(self, ws_url):
        self.ws_wrapper = WebSocketWrapper(ws_url)
        self.ws_wrapper.connect()
        self.position: Position = self.ws_wrapper.get_position()
        self.ws_wrapper.send_gcode('G90')  # Set to absolute positioning
        self.ws_wrapper.select_carriage(1) # Default to carriage 1
        self.current_carriage = 1

    def wait_for(self, seconds):
        time.sleep(seconds)

    def get_position(self):
        return self.position
    
    def refresh_position(self):
        self.position = self.ws_wrapper.get_position()
        return self.position
    
    def select_carriage(self, carriage_number):
        self.ws_wrapper.select_carriage(carriage_number)
        self.current_carriage = carriage_number
    
    def move(self, move: Position, absolute=True, blocking=True, verify_mov = True):
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
            self.ws_wrapper.select_carriage(1)
            gcode = "COMPENSATED_ABS_MV"
            if move.x1 is not None:
                gcode += f" X={move.x1}"
            if move.y1 is not None:
                gcode += f" Y={move.y1}"
            if move.z1 is not None:
                gcode += f" Z={move.z1}"
            gcode += f" F={FEEDRATE}"
            self.ws_wrapper.send_gcode(gcode)

        if move.x2 is not None or move.y2 is not None or move.z2 is not None:
            self.ws_wrapper.select_carriage(2)
            gcode = "COMPENSATED_ABS_MV"
            if move.x2 is not None:
                gcode += f" X={move.x2}"
            if move.y2 is not None:
                gcode += f" Y={move.y2}"
            if move.z2 is not None:
                gcode += f" Z={move.z2}"
            gcode += f" F={FEEDRATE}"
            self.ws_wrapper.send_gcode(gcode)

        print(f"Sent move command: {move} (absolute={absolute})")

        if blocking:
            while self.ws_wrapper.is_toolhead_moving():
                time.sleep(0.01)
            if verify_mov:
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
        else:
            return True # Don't verify position for relative moves
    
    def home(self):
        self.ws_wrapper.send_gcode("G28 X Y")
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
