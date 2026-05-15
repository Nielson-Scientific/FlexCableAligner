from img_processing.AprilTagDetector import AprilTagDetector
from schema.PositionSchema import Position
import time
TAG_SIDE_LENGTH_MM = 500
STEP_SIZE_MM = TAG_SIDE_LENGTH_MM

class SearchRoutines:
    @staticmethod
    def spiral_search(cam_handle, tool_handle, carriage_index, depth = 8, step_size_mm = STEP_SIZE_MM, pause_at_each_point = 0):
        detector = AprilTagDetector()
        start_pos = tool_handle.get_position()
        start_x = start_pos.x1 if carriage_index == 1 else start_pos.x2
        start_y = start_pos.y1 if carriage_index == 1 else start_pos.y2

        def next_position(offset_x, offset_y):
            if carriage_index == 1:
                return Position(x1 = start_x + offset_x, y1 = start_y + offset_y)
            if carriage_index == 2:
                return Position(x2 = start_x + offset_x, y2 = start_y + offset_y) 
            raise ValueError(f"Carriage index must be 1 or 2, carraige index was :{carriage_index}")
        
        def scan_position():
            if pause_at_each_point > 0:
                time.sleep(pause_at_each_point)
            img = cam_handle.get_latest_frame()
            if len(detector.check_for_april_tag(img)) > 0:
                return True
            return False

        for i in range(depth):
            # move up 2 * i + 1
            offset = (2 * i + 1) * step_size_mm
            tool_handle.move(next_position(offset_x = 0, offset_y = offset))
            # check for tag
            if scan_position(): return True
            # move right 2 * i + 1
            tool_handle.move(next_position(offset_x = offset, offset_y = 0))
            # check for tag
            if scan_position(): return True
            # move down 2 * i + 2
            offset = -1 * (2 * i + 2) * step_size_mm
            tool_handle.move(next_position(offset_x = 0, offset_y = offset))
            # check for tag
            if scan_position(): return True
            # move left 2 * i + 2
            tool_handle.move(next_position(offset_x = offset, offset_y = 0))
            # check for tag
            if scan_position(): return True
            #final check
        return False

