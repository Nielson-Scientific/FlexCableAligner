from img_processing.AprilTagDetector import AprilTagDetector


def main():
    detector = AprilTagDetector()
    images = AprilTagDetector.load_test_images_with_titles()
    if not images:
        raise RuntimeError("No images found in test_images/tag_imgs")

    for title, image in images:
        detections = detector.check_for_april_tag(image)
        if not detections:
            print(f"{title}: no tags detected")
            continue

        for det in detections:
            dx_mm, dy_mm = detector.get_tag_offset_from_center_mm(det)
            print(
                f"{title} | tag_id={det.tag_id} | "
                f"offset_mm=({dx_mm:.6f}, {dy_mm:.6f})"
            )


if __name__ == "__main__":
    main()

