from img_processing.AprilTagDetector import AprilTagDetector
from schema.PositionSchema import Position
import time
TAG_SIDE_LENGTH_MM = 0.5
STEP_SIZE_MM = TAG_SIDE_LENGTH_MM/2

class SearchRoutines:
    @staticmethod
    def spiral_search(cam_handle, tool_handle, carriage_index, depth = 8, step_size_mm = STEP_SIZE_MM, pause_at_each_point = 0):
        detector = AprilTagDetector()
        start_pos = tool_handle.get_position()
        start_x = start_pos.x1 if carriage_index == 1 else start_pos.x2
        start_y = start_pos.y1 if carriage_index == 1 else start_pos.y2

        x = start_x
        y = start_y

        def next_position(x,y):
            if carriage_index == 1:
                return Position(x1 = x, y1 = y)
            if carriage_index == 2:
                return Position(x2 = x, y2 = y) 
            raise ValueError(f"Carriage index must be 1 or 2, carraige index was :{carriage_index}")
        
        def scan_position():
            if pause_at_each_point > 0:
                time.sleep(pause_at_each_point)
            frame = cam_handle.get_latest_frame()
            if frame is None:
                return False
            if len(detector.check_for_april_tag(frame.image_bgr)) > 0:
                return True
            return False
        
        def scan_row(x, y, segments, scan_up = True):
            for i in segments:
                if scan_up:
                    x += STEP_SIZE_MM 
                else:
                    x -= STEP_SIZE_MM

                tool_handle.move(next_position(x, y))
                if scan_position():return True, x, y
            return False, x, y

        def scan_column(x, y, segments, scan_right = True):
            for i in segments:
                if scan_right:
                    y += STEP_SIZE_MM 
                else:
                    y -= STEP_SIZE_MM
                tool_handle.move(next_position(x, y))
                if scan_position():return True, x, y
            return False, x, y
        
        

        for i in range(depth):
            # SCAN UP AND RIGHT: 2 * i + 1
            segments = 2 * i + 1
            found, x, y = scan_row(segments, x, y)
            if found: return True
            found, x, y = scan_column(segments, x, y)
            if found: return True
            
            # SCAN DOWN AND LEFT: 2 * i + 2
            segments = 2 * i + 2
            found, x, y = scan_row(segments, x, y, scan_up=False)
            if found: return True
            found, x, y = scan_column(segments, x, y, sacn_right=False)
            if found: return True
            
        # return to starting position
        tool_handle.move(start_pos)
        return False
