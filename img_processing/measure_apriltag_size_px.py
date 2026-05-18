from math import dist
from pathlib import Path

from img_processing.AprilTagDetector import AprilTagDetector


TRUE_TAG_SIDE_MM = 0.5
TEST_IMG_DIR = Path("test_images/tag_imgs")


def side_lengths_px(corners):
    a, b, c, d = corners
    return [
        dist(a, b),
        dist(b, c),
        dist(c, d),
        dist(d, a),
    ]


def main():
    detector = AprilTagDetector()
    images = AprilTagDetector.load_test_images_with_titles(TEST_IMG_DIR)
    if not images:
        raise RuntimeError(f"No images found in {TEST_IMG_DIR}")

    per_detection_avgs = []
    total_detections = 0

    for title, image in images:
        detections = detector.check_for_april_tag(image)
        if not detections:
            print(f"{title}: no tags detected")
            continue

        for det in detections:
            lengths = side_lengths_px(det.corners)
            avg_len = sum(lengths) / len(lengths)
            per_detection_avgs.append(avg_len)
            total_detections += 1
            print(
                f"{title} | tag_id={det.tag_id} | "
                f"sides_px={[round(v, 3) for v in lengths]} | avg_side_px={avg_len:.3f}"
            )

    if not per_detection_avgs:
        raise RuntimeError("No AprilTag detections were found in the image set.")

    overall_avg_px = sum(per_detection_avgs) / len(per_detection_avgs)
    px_per_mm = overall_avg_px / TRUE_TAG_SIDE_MM
    mm_per_px = TRUE_TAG_SIDE_MM / overall_avg_px

    print("\n--- Summary ---")
    print(f"Detections: {total_detections}")
    print(f"Average tag side length: {overall_avg_px:.6f} px")
    print(f"Estimated PX_PER_MM: {px_per_mm:.6f}")
    print(f"Estimated MM_PER_PX: {mm_per_px:.9f}")
    print(f"(Using TRUE_TAG_SIDE_MM={TRUE_TAG_SIDE_MM})")


if __name__ == "__main__":
    main()

