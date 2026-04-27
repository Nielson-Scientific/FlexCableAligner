import cv2
import numpy as np
from datetime import datetime
from pathlib import Path


class Autofocus:
    @staticmethod
    def get_sharpness_score(img):
        """Return focus sharpness via variance of the Laplacian."""
        return Autofocus.get_sharpness_laplacian(img)

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
    def try_all_sharpnesses(img):
        lap = Autofocus.get_sharpness_laplacian(img)
        ten = Autofocus.get_sharpness_tenengrad(img)
        bre = Autofocus.get_sharpness_brenner(img)
        return lap,ten,bre
    
    
if __name__ == '__main__':
    root = Path("test_images")
    exts = {".png",}

    image_paths = sorted(
        p for p in root.rglob("*")
        if p.is_file() and p.suffix.lower() in exts
    )

    focused_imgs = []
    unfocused_imgs = []
    semifocused_imgs = []

    for p in image_paths:
        img = cv2.imread(str(p))
        if img is not None:
            label = p.parent.name
            match(label):
                case 'unfocused':
                    unfocused_imgs.append(img)
                case 'focused':
                    focused_imgs.append(img)
                case 'semifocused':
                    semifocused_imgs.append(img)
    

    unfocus_vals =  [Autofocus.try_all_sharpnesses(img) for img in unfocused_imgs]
    unfocus_avgs = np.mean(unfocus_vals, axis=0).tolist()

    focus_vals =  [Autofocus.try_all_sharpnesses(img) for img in focused_imgs]
    focus_avgs = np.mean(focus_vals, axis=0).tolist()

    semifocus_vals =  [Autofocus.try_all_sharpnesses(img) for img in semifocused_imgs]
    semifocus_avgs = np.mean(semifocus_vals, axis=0).tolist()

    LAP_IDX = 0
    TEN_IDX = 1
    BRE_IDX = 2
    def result_print(title, foc, semifoc, unfoc, idx):
        print(f"{title} Focused: {foc[idx]:.2f} | Semifocused: {semifoc[idx]:.2f} | Unfocused {unfoc[idx]:.2f}")

    
    # Print LAP Comparison
    result_print("LAPLACIAN", focus_avgs, semifocus_avgs, unfocus_avgs, LAP_IDX)
    result_print("TENENGRED", focus_avgs, semifocus_avgs, unfocus_avgs, TEN_IDX)
    result_print("BRENNER  ", focus_avgs, semifocus_avgs, unfocus_avgs, BRE_IDX)
    
