import cv2
from pathlib import Path

class FileUtils:
    @staticmethod
    def load_test_images(img_dir: str, count = None):
        """Load all images in img_dir as OpenCV image objects."""
        img_dir = Path(img_dir)
        if not img_dir.exists() or not img_dir.is_dir():
            print("File Utils: invalid dir")
            return []

        valid_exts = {".jpg", ".jpeg", ".png", ".bmp", ".tif", ".tiff", ".webp"}
        images = []
        img_count = 0
        for img_path in sorted(p for p in img_dir.iterdir() if p.is_file() and p.suffix.lower() in valid_exts):
            image = cv2.imread(str(img_path))
            if image is not None:
                images.append(image)
                img_count += 1
            if count is not None and img_count >= count:
                break
        return images
            



    @staticmethod
    def load_test_images_with_titles(img_dir):
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