from utils.AutoFocus import Autofocus
from Controllers.ToolController import ToolController
from Controllers.CameraControl import CameraControl, CAM_ID_1, CAM_ID_2
from PositionSchema import Position

HIGH = 16
LOW = 11
BROAD_STEP = 0.05
FINE_STEP = 0.01
FINER_STEP = 0.001

X_1 = 245
Y_1 = 47.5

class exp_result:
    def __init__(self, feedrate, fine_factor, z_val, duration):
        self.feedrate = feedrate
        self.fine_factor = fine_factor
        self.duration = duration
        self.z_val = z_val

    def get_result(self):
        return {
            'feedrate': self.feedrate,
            'fine_factor': self.fine_factor,
            'z_val': self.z_val,
            'duration': self.duration
        }

if __name__ == "__main__":
    print('Creating Toolhandling instance')
    tool_handle = ToolController()

    print('Creating CameraControl instance 1')
    cam_handle_1 = CameraControl(CAM_ID_1)
    cam_handle_1.start()

    test_feeds = [50, 100, 150, 200, 250, 300, 350, 400]
    test_fine_factors = [0.05, 0.1, 0.2, 0.3, 0.4, 0.5]
    
    experiment_results = []

    for i_feed in test_feeds:
        for i_fine_factor in test_fine_factors:
            print(f"Testing feedrate: {i_feed} mm/min, fine_factor: {i_fine_factor}")
            z_val, duration = Autofocus.fast_autofocus(
                tool_handle=tool_handle, 
                cam_handle=cam_handle_1,
                carriage=1,
                high             =HIGH, 
                low              =LOW, 
                AF_speed         =i_feed, # Feedrate (mm/min)
                fine_factor      =i_fine_factor
            )
            experiment_results.append(exp_result(feedrate=i_feed, fine_factor=i_fine_factor, z_val=z_val, duration=duration))


    print("Experiment completed. Results:")
    for result in experiment_results:
        print(f"{result.get_result()}\n")



    cam_handle_1.stop()
