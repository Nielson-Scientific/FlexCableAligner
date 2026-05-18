from Controllers.ToolController import ToolController
from schema.PositionSchema import Position, ParkPosition
import numpy as np
from Wrappers.CSVWrapper import Point
from utils.Translator import Translator

"""
This wraps ToolController and adds the functionality of having a seperate local coordinate system that can be set and used for moves.
This allows for using a coordinate system for each PCB to test
"""
CONFIG_PATH = "config/config.json"

class ToolWrapper(ToolController):
    def __init__(self, ws_url):
        self.offsets = Position(x1=0, y1=0, z1=0, x2=0, y2=0, z2=0)
        super().__init__(ws_url)
        self.park_positions = ParkPosition(CONFIG_PATH)
        self.carriage_1_translator = None
        self.carriage_2_translator = None
        self.carriage_1_tps_pairs = []
        self.carriage_2_tps_pairs = []

    @staticmethod
    def _sub_optional(value, offset):
        if value is None:
            return None
        return value - (offset or 0)

    def get_position(self):
        pos = super().get_position()
        p = Position(
            x1=self._sub_optional(pos.x1, self.offsets.x1),
            y1=self._sub_optional(pos.y1, self.offsets.y1),
            z1=self._sub_optional(pos.z1, self.offsets.z1),
            x2=self._sub_optional(pos.x2, self.offsets.x2),
            y2=self._sub_optional(pos.y2, self.offsets.y2),
            z2=self._sub_optional(pos.z2, self.offsets.z2)
        )
        return p
    
    def refresh_position(self):
        pos = super().refresh_position()
        p = Position(
            x1=self._sub_optional(pos.x1, self.offsets.x1),
            y1=self._sub_optional(pos.y1, self.offsets.y1),
            z1=self._sub_optional(pos.z1, self.offsets.z1),
            x2=self._sub_optional(pos.x2, self.offsets.x2),
            y2=self._sub_optional(pos.y2, self.offsets.y2),
            z2=self._sub_optional(pos.z2, self.offsets.z2)
        )
        return p
    
    def get_absolute_position(self):
        return super().get_position()
    
    def refresh_absolute_position(self):
        return super().refresh_position()
    
    def move_absolute(self, move: Position, blocking=True, set_speed=None):
        return super().move(move, absolute=True, blocking=blocking, set_speed=set_speed)
    
    def move_pcb_space(self, move: Position, absolute=True, blocking=True):
        self.move(move, absolute=absolute, blocking=blocking)

    def get_position_pcb_space(self):
        return self.get_position()
    
    def get_position_cable_space(self, carriage_index):
        if carriage_index == 1:
            if self.carriage_1_translator is None:
                print("Carriage 1 translator not set. Cannot get position in cable space.")
                return None
            return self.carriage_1_translator.get_cable_point_from_stage_point(self.get_position())
        elif carriage_index == 2:
            if self.carriage_2_translator is None:
                print("Carriage 2 translator not set. Cannot get position in cable space.")
                return None
            return self.carriage_2_translator.get_cable_point_from_stage_point(self.get_position())
        else:
            print("Invalid carriage index. Must be 1 or 2.")
            return None
        
    def move_cable_space(self, move: Position, carriage_index, absolute=True, blocking=True):
        if carriage_index == 1:
            if self.carriage_1_translator is None:
                print("Carriage 1 translator not set. Cannot get position in cable space.")
                return None
            stage_point = self.carriage_1_translator.get_stage_point_from_cable_point((move.x1, move.y1))
            stage_position = Position(x1 = stage_point[0], y1 = stage_point[1])
            return self.move(stage_position, absolute=absolute, blocking=blocking)
        elif carriage_index == 2:
            if self.carriage_2_translator is None:
                print("Carriage 2 translator not set. Cannot get position in cable space.")
                return None
            stage_point = self.carriage_2_translator.get_stage_point_from_cable_point((move.x2, move.y2))
            stage_position = Position(x2 = stage_point[0], y2 = stage_point[1])
            return self.move(stage_position, absolute=absolute, blocking=blocking)
        else:
            print("Invalid carriage index. Must be 1 or 2.")
            return None

    def refresh_position_pcb_space(self):
        return self.refresh_position()
    
    def set_offset(self, offset: Position):
        self.offsets = offset

    def park_carriage(self, carriage_index):
        if carriage_index == 1:
            super().move(self.park_positions.park1_position) # Move to park position in the native coordinate system
        elif carriage_index == 2:
            super().move(self.park_positions.park2_position)
        else:
            print("Invalid carriage index. Must be 1 or 2.")

    def move(self, move: Position, absolute=True, blocking=True, set_speed = None):
        if absolute:
            target = Position(
                x1=move.x1 + self.offsets.x1 if move.x1 is not None else None,
                y1=move.y1 + self.offsets.y1 if move.y1 is not None else None,
                z1=move.z1 + self.offsets.z1 if move.z1 is not None else None,
                x2=move.x2 + self.offsets.x2 if move.x2 is not None else None,
                y2=move.y2 + self.offsets.y2 if move.y2 is not None else None,
                z2=move.z2 + self.offsets.z2 if move.z2 is not None else None
            )
        else:
            target = move

        return super().move(target, absolute, blocking, set_speed = set_speed)
    
    def set_position_as_point(self, point: Point, carriage_index: float):
        if carriage_index not in [1, 2]:
            print("Invalid carriage index. Must be 1 or 2.")
            return
        current_pos = super().get_position()
        if carriage_index == 1:
            self.offsets.x1 = current_pos.x1 - point.x
            self.offsets.y1 = current_pos.y1 - point.y
        elif carriage_index == 2:
            self.offsets.x2 = current_pos.x2 - point.x
            self.offsets.y2 = current_pos.y2 - point.y
        else:
            print("Invalid carriage index. Must be 1 or 2.")
    
    def set_position_as_zero(self, carriage_index):
        if carriage_index not in [1, 2]:
            print("Invalid carriage index. Must be 1 or 2.")
            return
        
        current_pos = super().get_position()
        if carriage_index == 1:
            self.offsets.x1 = current_pos.x1
            self.offsets.y1 = current_pos.y1
        else:
            self.offsets.x2 = current_pos.x2
            self.offsets.y2 = current_pos.y2

    def set_offsets_to_zero(self):
        self.offsets = Position(x1=0, y1=0, z1=0, x2=0, y2=0, z2=0)

    def set_carriage_translator(self, carriage_index, c1, c2, s1, s2, invert_x=False, invert_y=False):
        translator = Translator(c1, c2, s1, s2, invert_x=invert_x, invert_y=invert_y)
        if carriage_index == 1:
            self.carriage_1_translator = translator
            self.carriage_1_tps_pairs = []
            self.carriage_1_translator.set_use_tps(False)
        elif carriage_index == 2:
            self.carriage_2_translator = translator
            self.carriage_2_tps_pairs = []
            self.carriage_2_translator.set_use_tps(False)
        else:
            print("Invalid carriage index. Must be 1 or 2.")

    def add_carriage_tps_pair(self, carriage_index, cable_xy, stage_xy):
        pair = (
            (float(cable_xy[0]), float(cable_xy[1])),
            (float(stage_xy[0]), float(stage_xy[1])),
        )
        if carriage_index == 1:
            self.carriage_1_tps_pairs.append(pair)
        elif carriage_index == 2:
            self.carriage_2_tps_pairs.append(pair)
        else:
            raise ValueError("Invalid carriage index. Must be 1 or 2.")

    def fit_carriage_tps(self, carriage_index):
        if carriage_index == 1:
            translator = self.carriage_1_translator
            pairs = self.carriage_1_tps_pairs
        elif carriage_index == 2:
            translator = self.carriage_2_translator
            pairs = self.carriage_2_tps_pairs
        else:
            raise ValueError("Invalid carriage index. Must be 1 or 2.")

        if translator is None:
            raise RuntimeError(f"Carriage {carriage_index} translator not set. Run base calibration first.")
        if len(pairs) < 3:
            raise RuntimeError(
                f"Carriage {carriage_index} needs at least 3 TPS point pairs; currently {len(pairs)}."
            )

        cable_points = [p[0] for p in pairs]
        stage_points = [p[1] for p in pairs]
        translator.fit_tps(cable_points, stage_points)
        translator.set_use_tps(True)

    def set_carriage_use_tps(self, carriage_index, enabled: bool):
        if carriage_index == 1:
            if self.carriage_1_translator is None:
                raise RuntimeError("Carriage 1 translator not set.")
            self.carriage_1_translator.set_use_tps(enabled)
        elif carriage_index == 2:
            if self.carriage_2_translator is None:
                raise RuntimeError("Carriage 2 translator not set.")
            self.carriage_2_translator.set_use_tps(enabled)
        else:
            raise ValueError("Invalid carriage index. Must be 1 or 2.")

    def get_carriage_tps_pair_count(self, carriage_index):
        if carriage_index == 1:
            return len(self.carriage_1_tps_pairs)
        if carriage_index == 2:
            return len(self.carriage_2_tps_pairs)
        raise ValueError("Invalid carriage index. Must be 1 or 2.")


if __name__ == "__main__":
    tool_wrapper = ToolWrapper("ws://10.34.243.54:7125/websocket")
    tool_wrapper.home()
    tool_wrapper.set_position_as_zero(1)
    tool_wrapper.set_position_as_zero(2)
    print("Current Position (should be 0,0 for both carriages):", tool_wrapper.get_position())
    move_success = tool_wrapper.move(Position(x1=10, y1=10, x2=-20, y2=20))
    if move_success:
        print("Move successful. Current Position:", tool_wrapper.get_position())
    else:
        print("Move failed. Current Position:", tool_wrapper.get_position())
