from utils.AutoFocus import Autofocus
from Controllers.ToolController import ToolController
from Controllers.CameraControl import CameraControl, CAM_ID_1, CAM_ID_2

HIGH = 20
LOW = 10
BROAD_STEP = 0.1
FINE_STEP = 0.01
FINER_STEP = 0.001


if __name__ == "__main__":
    print('Creating Toolhandling instance')
    tool_handle = ToolController()
    tool_handle.home()

    print('Creating CameraControl instance 1')
    cam_handle_1 = CameraControl(CAM_ID_1)
    cam_handle_1.start()
    print('Creating CameraControl instance 2')
    cam_handle_2= CameraControl(CAM_ID_2)
    cam_handle_2.start()

    # Autofocus.fast_autofocus(
    #     tool_handle=tool_handle, 
    #     cam_handle=cam_handle_1,
    #     carriage=1,
    #     high             =HIGH, 
    #     low              =LOW, 
    #     broad_pass_step  =BROAD_STEP, 
    #     fine_pass_step   =FINE_STEP, 
    #     finer_pass_step  =FINER_STEP
    # )

    Autofocus.fast_autofocus(
        tool_handle=tool_handle, 
        cam_handle=cam_handle_2,
        carriage=2,
        high             =HIGH, 
        low              =LOW, 
        broad_pass_step  =BROAD_STEP, 
        fine_pass_step   =FINE_STEP, 
        finer_pass_step  =FINER_STEP
    )

    cam_handle_1.stop()
    cam_handle_2.stop()