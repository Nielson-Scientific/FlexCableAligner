from schema.PositionSchema import Position


class GCodeCMD:
    FEEDRATE = 3000
    @staticmethod
    def MOVE(pos: Position, carriage, feed = FEEDRATE):
        if carriage==1:
            gcode = "COMPENSATED_ABS_MV"
            if pos.x1 is not None:
                gcode += f" X={pos.x1}"
            if pos.y1 is not None:
                gcode += f" Y={pos.y1}"
            if pos.z1 is not None:
                gcode += f" Z={pos.z1} Z_AXIS=1"
            gcode += f" F={feed}"
            return gcode
        if carriage==2:
            gcode = "COMPENSATED_ABS_MV"
            if pos.x2 is not None:
                gcode += f" X={pos.x2}"
            if pos.y2 is not None:
                gcode += f" Y={pos.y2}"
            if pos.z2 is not None:
                gcode += f" Z={pos.z2} Z_AXIS=2"
            gcode += f" F={feed}"
            return gcode

    @staticmethod
    def ABSOLUTE_POSITIONING():
        return "G90"
    
    @staticmethod
    def SELECT_CARRAIGE(carriage_num):
        if carriage_num == 1:
            return ("CARRIAGE_L")
        if carriage_num == 2:
            return ("CARRIAGE_R")
        else:
            raise ValueError(f"Carriage number must be 1 or 2, was: {carriage_num}")
    
    @staticmethod  
    def HOME_ALL():
        return "HOME_ALL"
    
    @staticmethod
    def AVOID_HOME(current_pos: Position):
        gcode = "SET_DUAL_CARRIAGE CARRIAGE=x\nSET_DUAL_CARRIAGE CARRIAGE=y\n"
        gcode += f"SET_KINEMATIC_POSITION X={current_pos.x1} Y={current_pos.y1}"
        if current_pos.z1 is not None:
            gcode += f" Z={current_pos.z1}"
        gcode += "\n"
        gcode += "SET_DUAL_CARRIAGE CARRIAGE=x2\nSET_DUAL_CARRIAGE CARRIAGE=y2\n"
        gcode += f"SET_KINEMATIC_POSITION X={current_pos.x2} Y={current_pos.y2}"
        if current_pos.z2 is not None:
            gcode += f" Z={current_pos.z2}"
        gcode += "\n"
        return gcode

    @staticmethod
    def WAIT_FOR_MOVES():
        # M400 blocks until all queued planner moves are completed.
        return "M400"