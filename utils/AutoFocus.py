import cv2
import numpy as np
import time
import threading
import os
from concurrent.futures import ProcessPoolExecutor
from datetime import datetime
from pathlib import Path
if __name__ != "__main__": from PositionSchema import Position

# Perhaps it would be best to move this insdie of the Camera Control class.
# The main advantage of doing so is that it enables us to use the same camera feed as the rest of the program
# This is enabled by easy access to the movement ToolController vial the ToolController singleton 

HIGH = 16
LOW = 11
BROAD_STEP = 0.05
FINE_STEP = 0.01
FINER_STEP = 0.001

FAST_AF_SAMPLES_PER_SECOND = 12.5
FAST_AF_FEEDRATE = 125

TYPICAL_FAST_ERROR = 0.5

TYPICAL_QUICK_ERROR = 0.2


class Autofocus:

    @staticmethod
    def percise_autofocus_singlepass(
        cam_handle, 
        tool_handle, 
        carriage, 
        high, 
        low, 
        step_size = FINER_STEP, 
        show_plot = False
    ):
        print(f"Beginning AutoFocus Test, Carriage = {carriage}, High = {high}, Low = {low}, Step Size = {step_size}")        # Initialize data for loop
        
        if cam_handle is None:
            raise ValueError("cam_handle cannot be None")
        
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
                time.sleep(0.25)
                frame = Autofocus.wait_for_fresh_frame(cam_handle, timeout_s=2.0)
                time.sleep(0.25)
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
    
    @staticmethod
    def fast_autofocus_singlepass(
        cam_handle, 
        tool_handle, 
        carriage,
        high=HIGH, 
        low=LOW,
        AF_speed = FAST_AF_FEEDRATE , # Feedrate (mm/min)
        samples_per_second = FAST_AF_SAMPLES_PER_SECOND,
        show_plots = False,
        save_samples = False,
    ):
        # Conceptually this one is different:
        # Rather than sending one g code per move, we are going to continuously move at a slow speed and capture frames in a loop until we reach the target low/high positions.
        print(f"Beginning Fast AutoFocus, Carriage = {carriage}, High = {high}, Low = {low}")
       
        if cam_handle is None:
            raise ValueError("cam_handle cannot be None")

        start_z = float(low)
        end_z = float(high)
        start_pos = Position(z1=start_z) if carriage == 1 else Position(z2=start_z)
        target_pos = Position(z1=end_z) if carriage == 1 else Position(z2=end_z)

         # Go to starting position
        tool_handle.move(start_pos)
        time.sleep(1.0)  # Allow time to settle


        # Start moving towards target at slow speed
        tool_handle.move(target_pos, set_speed=AF_speed, blocking = False)

        # Start timing
        FUDGEFACTOR = 10  # I think our real feed values are wrong)
        estimated_time_to_complete = 60 * (abs(end_z - start_z) / AF_speed) * FUDGEFACTOR
        print(f"Estimated time to complete move: {estimated_time_to_complete:.2f} seconds")
        t_start = time.time()
        t_end = t_start + estimated_time_to_complete

        # Frame Capture Loop
        samples = []
        print(f"Start Capturing frames for Fast AutoFocus...")
        while time.time() < t_end:
            frame = Autofocus.wait_for_fresh_frame(cam_handle, timeout_s=2.0)
            if frame is not None:
                # Copy to decouple from any underlying camera buffer reuse.
                samples.append((time.time(), frame.image_bgr.copy()))
            time.sleep(1.0 / samples_per_second)
        print(f"Completed capturing frames. Total frames: {len(samples)}")

        if save_samples and samples:
            sample_dir = Path("af_fast_samples")
            sample_dir.mkdir(parents=True, exist_ok=True)
            for ts, img in samples:
                cv2.imwrite(str(sample_dir / f"{ts:.6f}.png"), img)

        if not samples:
            raise RuntimeError("No samples collected during fast_autofocus")
        # Score image sharpness, find best
        scored = Autofocus.fast_af_score(samples)
        best_ts, _ = max(scored, key=lambda s: s[1])

        if show_plots:
            z_to_focus = {}
            span_t = t_end - t_start
            for ts, focus_val in scored:
                sample_frac = (ts - t_start) / span_t
                sample_frac = 0.0 if sample_frac < 0.0 else 1.0 if sample_frac > 1.0 else sample_frac
                z = start_z + (end_z - start_z) * sample_frac
                z_to_focus[float(z)] = float(focus_val)
            if z_to_focus:
                Autofocus.plot_focus_curve(z_to_focus, title="Fast Autofocus Focus vs Z")

        # EStimate Z based on best time stamp, start time, end time, start pos, end pos
        frac = (best_ts - t_start) / (t_end - t_start)
        frac = 0.0 if frac < 0.0 else 1.0 if frac > 1.0 else frac
        est_best_z = start_z + (end_z - start_z) * frac

        # Go to best estimated Z
        if carriage == 1:
            tool_handle.move(Position(z1=est_best_z))
        else:
            tool_handle.move(Position(z2=est_best_z))
        return est_best_z, estimated_time_to_complete
    
    @staticmethod
    def thorough_autofocus_routine(
        cam_handle, 
        tool_handle, 
        carriage,
        high=HIGH, 
        low=LOW,
        AF_speed = FAST_AF_FEEDRATE , # Feedrate (mm/min)
        fine_factor = 0.1,
        show_plots = False,
        save_samples = False,
    ):
        fast_pass1_z, pass_1_duration = Autofocus.fast_autofocus_singlepass(
            cam_handle=cam_handle,
            tool_handle=tool_handle,
            carriage=carriage,
            high=high,
            low=low,
            AF_speed = AF_speed,
        )
        
        percise_pass1_z = Autofocus.percise_autofocus_singlepass(
            cam_handle=cam_handle,
            tool_handle=tool_handle,
            carriage=carriage,
            high=min(high, fast_pass1_z + TYPICAL_FAST_ERROR),
            low=max(low, fast_pass1_z - TYPICAL_FAST_ERROR),
            step_size = BROAD_STEP,
        )
        percise_pass2_z = Autofocus.percise_autofocus_singlepass(
            cam_handle=cam_handle,
            tool_handle=tool_handle,
            carriage=carriage,
            high=min(high, percise_pass1_z + BROAD_STEP),
            low=max(low, percise_pass1_z - BROAD_STEP),
            step_size = FINE_STEP,
            show_plot=True
        )
        return    


    def quick_autofocus_routine(
        cam_handle, 
        tool_handle, 
        carriage,
        current_height,
        high=HIGH, 
        low=LOW,
        AF_speed = FAST_AF_FEEDRATE , # Feedrate (mm/min)
        fine_factor = 0.1,
        show_plots = False,
        save_samples = False,
    ):
        percise_pass1_z = Autofocus.percise_autofocus_singlepass(
            cam_handle=cam_handle,
            tool_handle=tool_handle,
            carriage=carriage,
            high=min(high, current_height + TYPICAL_QUICK_ERROR),
            low=max(low, current_height - TYPICAL_QUICK_ERROR),
            step_size = BROAD_STEP,
        )
        percise_pass2_z = Autofocus.percise_autofocus_singlepass(
            cam_handle=cam_handle,
            tool_handle=tool_handle,
            carriage=carriage,
            high=min(high, percise_pass1_z + BROAD_STEP),
            low=max(low, percise_pass1_z - BROAD_STEP),
            step_size = FINE_STEP,
            show_plot=True
        )




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
    
    @staticmethod
    def fast_af_score(
        samples: list[tuple[float, "object"]],
        workers: int = 1,
        refine_top_fraction: float = 0.10,
    ) -> list[tuple[float, float]]:
        if not samples:
            return []

        ts_list = [ts for ts, _ in samples]
        imgs = [img for _, img in samples]
        max_workers = max(1, min(int(workers), os.cpu_count() or 1))

        if max_workers == 1 or len(imgs) < 8:
            coarse_scores = [Autofocus.get_sharpness_laplacian(img) for img in imgs]
        else:
            with ProcessPoolExecutor(max_workers=max_workers) as ex:
                coarse_scores = list(ex.map(Autofocus.get_sharpness_laplacian, imgs, chunksize=8))

        scored = list(zip(ts_list, coarse_scores))

        if refine_top_fraction <= 0:
            return scored

        refine_n = max(1, int(len(scored) * refine_top_fraction))
        top_idxs = sorted(range(len(scored)), key=lambda i: scored[i][1], reverse=True)[:refine_n]
        top_imgs = [imgs[i] for i in top_idxs]

        if max_workers == 1 or len(top_imgs) < 8:
            refined_scores = [Autofocus.get_sharpness_tenengrad(img) for img in top_imgs]
        else:
            with ProcessPoolExecutor(max_workers=max_workers) as ex:
                refined_scores = list(ex.map(Autofocus.get_sharpness_tenengrad, top_imgs, chunksize=4))

        for idx, refined in zip(top_idxs, refined_scores):
            scored[idx] = (scored[idx][0], float(refined))

        return scored
    
def test_speed_metrics():
    def slow_af_score (samples):
        return [(sample[0], Autofocus.get_sharpness_tenengrad(sample[1])) for sample in samples]

    image_root = Path(__file__).resolve().parent.parent / "test_images"
    image_paths = []
    for bucket in ("focused", "semifocused", "unfocused"):
        image_paths.extend((image_root / bucket).glob("*"))

    imgs = []
    for p in image_paths:
        img = cv2.imread(str(p))
        if img is not None:
            imgs.append(img)

    if not imgs:
        raise RuntimeError(f"No readable images found under: {image_root}")

    rng = np.random.default_rng(42)
    ts = rng.uniform(0.0, 10_000.0, size=len(imgs))
    samples = list(zip(ts.tolist(), imgs))

    # make data set bigger for better test
    for i in range(6):
        samples.extend(samples)

    t0 = time.perf_counter()
    slow_scores = slow_af_score(samples)
    slow_elapsed = time.perf_counter() - t0

    t1 = time.perf_counter()
    w1_fast_scores = Autofocus.fast_af_score(samples, workers=1)
    w1_fast_elapsed = time.perf_counter() - t1

    t1 = time.perf_counter()
    w2_fast_scores = Autofocus.fast_af_score(samples, workers=2)
    w2_fast_elapsed = time.perf_counter() - t1

    t1 = time.perf_counter()
    w3_fast_scores = Autofocus.fast_af_score(samples, workers=3)
    w3_fast_elapsed = time.perf_counter() - t1

    t1 = time.perf_counter()
    w4_fast_scores = Autofocus.fast_af_score(samples, workers=4)
    w4_fast_elapsed = time.perf_counter() - t1

    print(f"Images: {len(samples)}")
    print(f"slow_af_score: {slow_elapsed:.4f}s")
    print(f"fast_af_score (workers=1): {w1_fast_elapsed:.4f}s")
    print(f"fast_af_score (workers=2): {w2_fast_elapsed:.4f}s")
    print(f"fast_af_score (workers=3): {w3_fast_elapsed:.4f}s")
    print(f"fast_af_score (workers=4): {w4_fast_elapsed:.4f}s")


    print(f"Outputs: slow={len(slow_scores)}, fast={len(w4_fast_scores)}")

if __name__ == "__main__":
    test_speed_metrics()
    
