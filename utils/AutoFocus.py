import cv2
import numpy as np
from abc import ABC, abstractmethod



class Autofocus:

    @abstractmethod
    def get_sharpness_score(img):
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        lap = cv2.Laplacian(gray, cv2.CV_64F)
        return lap.var()
