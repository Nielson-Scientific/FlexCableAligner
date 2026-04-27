import cv2
import numpy as np
import time
from datetime import datetime
from pathlib import Path
from Controllers.CameraControl import CameraControl
from Controllers.ToolController import ToolController
from PositionSchema import Position

# Perhaps it would be best to move this insdie of the Camera Control class.
# The main advantage of doing so is that it enables us to use the same camera feed as the rest of the program
# This is enabled by easy access to the movement ToolController vial the ToolController singleton 

class Autofocus:
    @staticmethod
    def fast_autofocus(high, low, broad_pass_step = 0.1, fine_pass_step = 0.01, finer_pass_step = None):
        print(f"Beginning Fast AutoFocus Test, High = {high}, Low = {low}, Broad Step = {broad_pass_step}, Fine Step = {fine_pass_step}")
        print('Creating CameraControl instance')
        cam_control = CameraControl("DEV_1AB22C071903")
        print('CameraControl instance created')
        print('Starting camera feed')
        cam_control.start()
        
        broad_best = Autofocus.autofocus(high, low, broad_pass_step, camera_in=cam_control)
        fine_high = broad_best + broad_pass_step
        fine_low = broad_best - broad_pass_step
        fine_best = Autofocus.autofocus(fine_high, fine_low, fine_pass_step, show_plot=True, camera_in=cam_control)
        if finer_pass_step is None:
            best = fine_best
        else:
            finer_high = fine_best + fine_pass_step
            finer_low = fine_best - fine_pass_step
            best =  Autofocus.autofocus(finer_high, finer_low, finer_pass_step, show_plot=True, camera_in=cam_control)
        
        cam_control.stop()
        return best



    @staticmethod
    def autofocus(high, low, step_size, show_plot = False, camera_in = None):

        print(f"Beginning AutoFocus Test, High = {high}, Low = {low}, Step Size = {step_size}")

        # Instantiate Camera Control
        if camera_in is None:
            print('Creating CameraControl instance')
            cam_control = CameraControl("DEV_1AB22C071903")
            print('CameraControl instance created')
        else:
            cam_control = camera_in

        # Initialize data for loop
        focus_dict = {}
        heights = Autofocus.generate_heights(high, low, step_size)
        positions = [Position(z1 = h) for h in heights]
        optimal_height = None

        # Instantiate Movement and get Position
        TOOL_CTRL_URL = "ws://10.34.243.54:7125/websocket"
        tool_controller = ToolController(TOOL_CTRL_URL)

        # Start Camera Feed
        
        if camera_in is None:
            print('Starting camera feed') 
            cam_control.start()
        try:
            # Start stepping through heights
            for position in reversed(positions):
                tool_controller.move(position, verify_mov=False)
                frame = Autofocus.wait_for_fresh_frame(cam_control, timeout_s=2.0)
                if frame is None:
                    raise RuntimeError(f"No camera frame received at z={position.z1:.3f}mm within timeout.")
                focus_val = Autofocus.get_sharpness_tenengrad(frame.image_bgr)
                focus_dict[float(position.z1)] = float(focus_val)

            # Extract best
            max_focus_val = max(focus_dict.values())
            optimal_height = max(focus_dict, key=focus_dict.get)
            print(f"Best focus {max_focus_val:.3f} at z={optimal_height:.3f}")

            # Go to best
            tool_controller.move(Position(z1 = optimal_height))

        finally:
            # Stop Camera Stream
            if camera_in is None: cam_control.stop()
            # Plot Curve
            if show_plot: Autofocus.plot_focus_curve(focus_dict)
        return optimal_height



    ##########################
    #### HELPER FUNCTIONS ####
    ##########################

    @staticmethod
    def generate_heights(high: float, low: float, step_size: float) -> np.ndarray:
        if step_size <= 0:
            raise ValueError("step_size must be > 0")
        direction = 1 if low >= high else -1
        step = direction * abs(step_size)
        return np.arange(high, low + step, step, dtype=float)

    @staticmethod
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

    @staticmethod
    def plot_focus_curve(z_to_focus: dict[float, float], *, title: str = "Focus vs Z"):
        import matplotlib.pyplot as plt

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



    @staticmethod
    def get_sharpness_laplacian(img):
        """Return focus sharpness via variance of the Laplacian."""
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        lap = cv2.Laplacian(gray, cv2.CV_64F)
        return float(lap.var())
    
    @staticmethod
    def get_sharpness_tenengrad(img, tau_p = 90):
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        gx = cv2.Sobel(gray, cv2.CV_64F, 1, 0, ksize=3)
        gy = cv2.Sobel(gray, cv2.CV_64F, 0, 1, ksize=3)

        g2 = gx**2 + gy**2
        
        tau = np.percentile(g2, tau_p)
        strong = g2[g2 > tau]
        if not strong.size:
            return 0.0
        return float(np.mean(strong))
    
    @staticmethod
    def get_sharpness_brenner(img):
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        return np.sum((gray[:, 2:] - gray[:, :-2])**2)
    
    @staticmethod
    def test_capture_image(img, output_dir="af_test_images"):
        """
        Save an OpenCV image into `output_dir` with a timestamped filename.
        Returns the saved file path.
        """
        if img is None:
            raise ValueError("img cannot be None")

        target_dir = Path(output_dir)
        target_dir.mkdir(parents=True, exist_ok=True)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        output_path = target_dir / f"capture_{timestamp}.png"

        saved = cv2.imwrite(str(output_path), img)
        if not saved:
            raise RuntimeError(f"Failed to save image to: {output_path}")

        return str(output_path)
    
    
    

    
