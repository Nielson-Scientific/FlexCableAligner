import cv2
import numpy as np
import time
from datetime import datetime
from pathlib import Path
from PositionSchema import Position

# Perhaps it would be best to move this insdie of the Camera Control class.
# The main advantage of doing so is that it enables us to use the same camera feed as the rest of the program
# This is enabled by easy access to the movement ToolController vial the ToolController singleton 

HIGH = 20
LOW = 10
BROAD_STEP = 0.05
FINE_STEP = 0.01
FINER_STEP = 0.001

class Autofocus:
    @staticmethod
    def thorough_autofocus(
        cam_handle, 
        tool_handle, 
        carriage, 
        high=HIGH, 
        low=LOW, 
        broad_pass_step = BROAD_STEP, 
        fine_pass_step = FINE_STEP,  
        finer_pass_step = FINER_STEP, 
        show_plots = False
    ):
        print(f"Beginning Thorough AutoFocus Test, Carriage = {carriage}, High = {high}, Low = {low}, Broad Step = {broad_pass_step}, Fine Step = {fine_pass_step}")
        broad_best = Autofocus.autofocus(cam_handle, tool_handle, carriage, high, low, broad_pass_step, show_plot = show_plots)
        fine_high = broad_best + broad_pass_step
        fine_low = broad_best - broad_pass_step
        fine_best = Autofocus.autofocus(cam_handle, tool_handle, carriage, fine_high, fine_low, fine_pass_step, show_plot=show_plots)
        if finer_pass_step is None:
            best = fine_best
        else:
            finer_high = fine_best + fine_pass_step
            finer_low = fine_best - fine_pass_step
            best =  Autofocus.autofocus(cam_handle, tool_handle, carriage, finer_high, finer_low, finer_pass_step, show_plot=show_plots)        
        return best



    @staticmethod
    def autofocus(
        cam_handle, 
        tool_handle, 
        carriage, 
        high, 
        low, 
        step_size = FINER_STEP, 
        show_plot = False
    ):
        print(f"Beginning AutoFocus Test, Carriage = {carriage}, High = {high}, Low = {low}, Step Size = {step_size}")        # Initialize data for loop
        focus_dict = {}
        heights = Autofocus.generate_heights(high, low, step_size)
        if carriage == 1:
            positions = [Position(z1 = h) for h in heights]
        else:
            positions = [Position(z2 = h) for h in heights]
        optimal_height = None

        # Start Camera Feed
        try:
            # Start stepping through heights
            for position in reversed(positions):
                tool_handle.move(position)
                time.sleep(0.5)
                frame = Autofocus.wait_for_fresh_frame(cam_handle, timeout_s=2.0)
                time.sleep(0.5)
                if frame is None:
                    z_target = position.z1 if carriage == 1 else position.z2
                    raise RuntimeError(f"No camera frame received at z={z_target:.3f}mm within timeout.")
                focus_val = Autofocus.get_sharpness_tenengrad(frame.image_bgr)
                z_key = position.z1 if carriage == 1 else position.z2
                focus_dict[float(z_key)] = float(focus_val)

            # Extract best
            max_focus_val = max(focus_dict.values())
            optimal_height = max(focus_dict, key=focus_dict.get)
            print(f"Best focus {max_focus_val:.3f} at z={optimal_height:.3f}")

            # Go to best
            if carriage == 1:
                tool_handle.move(Position(z1 = optimal_height))
            else:
                tool_handle.move(Position(z2 = optimal_height))
        finally:
            if show_plot: Autofocus.plot_focus_curve(focus_dict)
        return optimal_height
    
    def fast_autofocus(
        tool_handle, 
        cam_handle, 
        carriage, 
        high=HIGH, 
        low=LOW, 
    ):
        # Conceptually this one is different:
        # Rather than sending one g code per move, we are going to continuously move at a slow speed and capture frames in a loop until we reach the target low/high positions.
        print(f"Beginning Fast AutoFocus, Carriage = {carriage}, High = {high}, Low = {low}")
        # Go to starting position
        if carriage == 1:
            tool_handle.move(Position(z1 = LOW))
        else:
            tool_handle.move(Position(z2 = LOW))

        # Start NonBlocking move
        if carriage == 1:
            tool_handle.move_non_blocking(Position(z1 = HIGH), speed=0.5)
        else:
            tool_handle.move_non_blocking(Position(z2 = HIGH), speed=0.5)
        
        # Start camera feed loop (the dict is a time stamped log of images )
        pics_dict = {}


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
    def wait_for_fresh_frame(cam_control, timeout_s: float = 2.0):
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
    
    
    

    
