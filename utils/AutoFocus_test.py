from utils.AutoFocus import Autofocus
from ToolController import ToolController
from CameraControl import CameraControl
from PositionSchema import Position
import matplotlib.pyplot as plt
import time



import numpy as np

HIGH = 10
LOW = 1
STEP_SIZE = 0.5

X = 0
Y = 0.5

TOOL_CTRL_URL = "ws://10.34.243.54:7125/websocket"


def plot_focus_curve(z_to_focus: dict[float, float], *, title: str = "Focus vs Z"):
    if not z_to_focus:
        raise ValueError("z_to_focus is empty")

    # Sort by z so the line is drawn left-to-right correctly
    zs = sorted(z_to_focus.keys())
    focus_vals = [z_to_focus[z] for z in zs]

    plt.figure(figsize=(7, 4))
    plt.plot(zs, focus_vals, marker="o")
    plt.xlabel("Z (mm)")
    plt.ylabel("Focus Value")
    plt.title(title)
    plt.grid(True, alpha=0.3)
    plt.tight_layout()
    plt.show()

def generate_heights(high: float, low: float, step_size: float) -> np.ndarray:
    if step_size <= 0:
        raise ValueError("step_size must be > 0")
    direction = 1 if low >= high else -1
    step = direction * abs(step_size)
    return np.arange(high, low + step, step, dtype=float)

def wait_for_fresh_frame(cam_control: CameraControl, timeout_s: float = 2.0):
    deadline = time.time() + timeout_s
    latest = None
    while time.time() < deadline:
        frame = cam_control.get_latest_frame()
        if frame is None:
            if latest is not None:
                break
            time.sleep(0.01)
            continue
        latest = frame
    return latest


if __name__ == '__main__':
    print(f"Beginning AutoFocus Test, High = {HIGH}, Low = {LOW}, Step Size = {STEP_SIZE}")

    # Instantiate Camera Control
    print('Creating CameraControl instance')
    cam_control = CameraControl("DEV_1AB22C071903")
    print('CameraControl instance created')
    focus_dict = {}
    heights = generate_heights(HIGH, LOW, STEP_SIZE)
    positions = [Position(x1 = X, y1 = Y, z1 = h) for h in heights]

    # Instantiate Movement and get Position
    tool_controller = ToolController(TOOL_CTRL_URL)
    tool_controller.home()
    print("Current Position:", tool_controller.get_position())
    
    # Start Camera Feed
    print('Starting camera feed')
    cam_control.start()
    try:
        # Start stepping through heights
        for position, height in zip(positions, heights):
            tool_controller.move(position)
            frame = wait_for_fresh_frame(cam_control, timeout_s=2.0)
            if frame is None:
                raise RuntimeError(f"No camera frame received at z={height}")
            focus_val = Autofocus.get_sharpness_tenengrad(frame.image_bgr)
            focus_dict[float(height)] = float(focus_val)

        # Extract best
        max_focus_val = max(focus_dict.values())
        optimal_height = max(focus_dict, key=focus_dict.get)
        print(f"Best focus {max_focus_val:.3f} at z={optimal_height:.3f}")

        # Go to best
        tool_controller.move(Position(x1 = X, y1 = Y, z1 = optimal_height))
        
        # Plot Curve
        plot_focus_curve(focus_dict)
    finally:
        # Stop Camera Stream
        cam_control.stop()
