from pathlib import Path
import os

import cv2
import numpy as np

if __name__ == "__main__": import matplotlib.pyplot as plt

PAD_DIRECTORY = "test_images/probe_locations"

class PadDetector:
    def __init__(self):
        pass

    def preprocessing(self, img):
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
        # kernel = np.ones((3, 3), np.uint8)
        # img = cv2.morphologyEx(img, cv2.MORPH_OPEN, kernel)
        # img = cv2.morphologyEx(img, cv2.MORPH_CLOSE, kernel)


        # Dilation and Erosion
        SMOOTHING_ITERATIONS = 18
        square_kernel = np.ones((3, 3), np.uint8)
        radius = 7
        k = radius * 2 -1
        circular_kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (k, k)).astype(np.uint8)
        kernel = circular_kernel

        # Fill small breaks in the tag border (close = dilate -> erode)
        FILL_BREAKS_ITERATIONS = int(SMOOTHING_ITERATIONS)
        img = cv2.dilate(img, kernel, iterations=FILL_BREAKS_ITERATIONS)
        img = cv2.erode(img, kernel, iterations=FILL_BREAKS_ITERATIONS)
        # Remove tiny speckles (open = erode -> dilate)
        REMOVE_SPECKLES_ITERATIONS = int(SMOOTHING_ITERATIONS)
        img = cv2.erode(img, kernel, iterations=REMOVE_SPECKLES_ITERATIONS)
        img = cv2.dilate(img, kernel, iterations=REMOVE_SPECKLES_ITERATIONS)
        return img
    
    def parse_pads(self, image, minumum_radius = 450):
        if not isinstance(image, np.ndarray):
            raise TypeError(f"parse_pads expected numpy.ndarray, got {type(image).__name__}")

        # findContours expects a single-channel 8-bit image (CV_8UC1).
        if image.ndim == 3:
            image = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        elif image.ndim != 2:
            raise ValueError(f"Unsupported image shape for parse_pads: {image.shape}")

        if image.dtype != np.uint8:
            image = image.astype(np.uint8)

        # Find connected dark-border regions
        contours, _ = cv2.findContours(
            image,
            cv2.RETR_EXTERNAL,
            cv2.CHAIN_APPROX_SIMPLE
        )

        pads = []

        for cnt in contours:
            area = cv2.contourArea(cnt)

            if area < 50:
                continue
            
            perimeter = cv2.arcLength(cnt, True)
            if perimeter == 0:
                continue
            
            circularity = 4 * np.pi * area / (perimeter * perimeter)

            # 1.0 is a perfect circle
            if circularity < 0.6:
                continue
            
            (x, y), radius = cv2.minEnclosingCircle(cnt)

            if radius < minumum_radius:
                continue
            
            pads.append({
                "center": (float(x), float(y)),
                "radius": float(radius),
                "area": float(area),
                "circularity": float(circularity)
            })
        return pads
        
if __name__ == "__main__":
    show = False
    from utils.FileUtils import FileUtils
    images = FileUtils.load_test_images(PAD_DIRECTORY, count = None)
    pad_detector = PadDetector()
    detections = 0
    for i, image in enumerate(images):
        preprocessed_image = pad_detector.preprocessing(image)
        pads = pad_detector.parse_pads(preprocessed_image)
        if len(pads) == 1:
            cv2.drawMarker(
                    preprocessed_image,
                    (int(pads[0]["center"][0]), int(pads[0]["center"][1])),
                    color=(0, 255, 0),  # green
                    markerType=cv2.MARKER_CROSS,
                    markerSize=55,
                    thickness=7,
                )
        if len(pads) == 1: detections += 1
        if (show):
            plt.imshow(preprocessed_image)
            plt.axis("off")
            plt.show()
    print(f"Successfully able to detect {detections} / {len(images)} pads")
