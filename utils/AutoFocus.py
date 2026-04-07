import cv2
from datetime import datetime
from pathlib import Path


class Autofocus:
    @staticmethod
    def get_sharpness_score(img):
        """Return focus sharpness via variance of the Laplacian."""
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        lap = cv2.Laplacian(gray, cv2.CV_64F)
        return float(lap.var())

    @staticmethod
    def test_capture_image(img, output_dir="test_images"):
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
