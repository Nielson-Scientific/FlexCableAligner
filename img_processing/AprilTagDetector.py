from pathlib import Path
import os

import cv2
import numpy as np
from pupil_apriltags import Detector
if __name__ == "__main__": import matplotlib.pyplot as plt


APRIL_TEST_IMG_DIR = Path("test_images/tag_imgs")

PIXELS_TO_MM = float(930 / 20)

CENTER_X_PXL = 1296
CENTER_Y_PXL = 972


class AprilTagDetector:
    def __init__(self):
        self.detector = Detector(families="tag16h5", quad_decimate=8.0)

    def check_for_april_tag(self, input_img):
        preprocessed_img = AprilTagDetector._april_tag_preprocessing(input_img)
        detections = self.detector.detect(preprocessed_img)
        return detections
    
    def display_marked_image(self, image, detections):
        boxed = image.copy()
        for det in detections:
            corners = det.corners
            pts = np.array(corners, dtype=np.int32).reshape((-1, 1, 2))
            cv2.polylines(
                boxed,
                [pts],
                isClosed=True,
                color=(0, 0, 255),  # red in OpenCV BGR
                thickness=2
            )
            center_x, center_y = self.get_detection_center(det)
            if len(detections) == 1:
                cv2.drawMarker(
                    boxed,
                    (int(center_x), int(center_y)),
                    color=(0, 255, 0),  # green
                    markerType=cv2.MARKER_CROSS,
                    markerSize=55,
                    thickness=5,
                )

        # Convert BGR -> RGB for matplotlib
        boxed_rgb = cv2.cvtColor(boxed, cv2.COLOR_BGR2RGB)
        title_string = "title"
        if detections is None:
            title_string = "No april tag ids detected"
        elif len(detections) ==1:
            title_string = f"April Tag ID = {detections[0].tag_id}"
        else:
            title_string = f"Detected IDs: {[det.tag_id for det in detections]}"
        plt.imshow(boxed_rgb)
        plt.axis("off")
        plt.title(title_string)
        plt.show()

    def get_detection_center(self, detection):
        a, b, c, d, = detection.corners
        x = (a[0] + b[0] + c[0] + d[0]) / 4
        y = (a[1] + b[1] + c[1] + d[1]) / 4
        return x,y
    
    def get_tag_offset_from_center_mm(self, detection):
        x_pxl, y_pxl = self.get_detection_center(detection)
        x_pxl_offset = x_pxl - CENTER_X_PXL
        y_pxl_offset = y_pxl - CENTER_Y_PXL
        x_mm_offset = x_pxl_offset * PIXELS_TO_MM
        y_mm_offset = y_pxl_offset * PIXELS_TO_MM
        return x_mm_offset, y_mm_offset

    @staticmethod
    def _april_tag_preprocessing(img):
        # GrayScale
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

        # 1. Improve local contrast
        clahe = cv2.createCLAHE(
            clipLimit=2.0,
            tileGridSize=(8, 8)
        )
        img = clahe.apply(gray)

        # 2. Light blur to suppress dirt/noise
        img = cv2.GaussianBlur(img, (5, 5), 0)

        # 3. Adaptive threshold for uneven lighting
        _, img = cv2.threshold(
            img,
            120,
            255,
            cv2.THRESH_BINARY
        )

        # 4. Morphology cleanup
        kernel = np.ones((3, 3), np.uint8)

        # Fill small breaks in the tag border (close = dilate -> erode)
        img = cv2.dilate(img, kernel, iterations=4)
        img = cv2.erode(img, kernel, iterations=4)

        # Remove tiny speckles (open = erode -> dilate)
        img = cv2.erode(img, kernel, iterations=1)
        img = cv2.dilate(img, kernel, iterations=1)

        return img



# TEST FUNCTIONS #

    @staticmethod
    def load_test_images(img_dir=APRIL_TEST_IMG_DIR):
        """Load all images in img_dir as OpenCV image objects."""
        img_dir = Path(img_dir)
        if not img_dir.exists() or not img_dir.is_dir():
            return []

        valid_exts = {".jpg", ".jpeg", ".png", ".bmp", ".tif", ".tiff", ".webp"}
        images = []

        for img_path in sorted(p for p in img_dir.iterdir() if p.is_file() and p.suffix.lower() in valid_exts):
            image = cv2.imread(str(img_path))
            if image is not None:
                images.append(image)

        return images

    @staticmethod
    def load_test_images_with_titles(img_dir=APRIL_TEST_IMG_DIR):
        """Load all images and return (title, image) where title is filename without extension."""
        img_dir = Path(img_dir)
        if not img_dir.exists() or not img_dir.is_dir():
            return []

        valid_exts = {".jpg", ".jpeg", ".png", ".bmp", ".tif", ".tiff", ".webp"}
        titled_images = []

        for img_path in sorted(p for p in img_dir.iterdir() if p.is_file() and p.suffix.lower() in valid_exts):
            image = cv2.imread(str(img_path))
            if image is not None:
                titled_images.append((img_path.stem, image))

        return titled_images
    
if __name__ == "__main__":
    images = AprilTagDetector.load_test_images_with_titles()
    if not images:
        raise RuntimeError(f"No images found in {APRIL_TEST_IMG_DIR}")

    detector = AprilTagDetector()
    for _, image in images:
        detections = detector.check_for_april_tag(image)
        detector.display_marked_image(image, detections)
