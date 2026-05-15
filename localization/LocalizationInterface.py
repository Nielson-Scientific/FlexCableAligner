from pathlib import Path

import cv2
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QImage, QPixmap
from PySide6.QtWidgets import (
    QComboBox,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from Wrappers.ToolSingleton import ToolSingleton
from img_processing.AprilTagDetector import AprilTagDetector
from utils.FileUtils import FileUtils as FU


TAG_CSV_PATH = Path("test_data/tag16h5_10x3_500mm_15m_offset_framed_centers.csv")
CAMERA_REFRESH_MS = 100


class LocalizationInterface(QWidget):
    def __init__(self, parent: QWidget):
        super().__init__(parent)
        self.parent_ui = parent
        self.detector = AprilTagDetector()
        self.saved_scans = []

        outer = QHBoxLayout(self)

        left_pane = self._build_points_pane()
        center_pane = self._build_action_pane()
        right_pane = self._build_camera_pane()

        outer.addWidget(left_pane, 3)
        outer.addWidget(center_pane, 2)
        outer.addWidget(right_pane, 3)

        self._load_points_table()

        self._timer = QTimer(self)
        self._timer.setInterval(CAMERA_REFRESH_MS)
        self._timer.timeout.connect(self._update_camera_preview)
        self._timer.start()

    def _build_points_pane(self):
        box = QGroupBox("CSV Tag Points")
        layout = QVBoxLayout(box)

        self.points_table = QTableWidget(0, 4)
        self.points_table.setHorizontalHeaderLabels(["Tag ID", "X (m)", "Y (m)", "Test"])
        self.points_table.horizontalHeader().setStretchLastSection(True)
        self.points_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)

        layout.addWidget(self.points_table)
        return box

    def _build_action_pane(self):
        box = QGroupBox("Localization Actions")
        layout = QVBoxLayout(box)

        self.scan_btn = QPushButton("Scan Tag and Save Position")
        self.scan_btn.clicked.connect(self._scan_tag_and_save_position)

        self.scan_status = QLabel("No scans yet")
        self.scan_status.setWordWrap(True)

        layout.addWidget(self.scan_btn)
        layout.addWidget(self.scan_status)
        layout.addStretch()
        return box

    def _build_camera_pane(self):
        box = QGroupBox("Camera Feed")
        layout = QVBoxLayout(box)

        self.camera_selector = QComboBox()
        self.camera_selector.addItems(["Camera 1", "Camera 2"])

        self.camera_label = QLabel("Feed not running")
        self.camera_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.camera_label.setMinimumSize(360, 260)

        layout.addWidget(QLabel("Select Camera:"))
        layout.addWidget(self.camera_selector)
        layout.addWidget(self.camera_label, 1)
        return box

    def _load_points_table(self):
        if not TAG_CSV_PATH.exists():
            self.scan_status.setText(f"Missing CSV: {TAG_CSV_PATH}")
            return

        rows = FU.csv_to_array(str(TAG_CSV_PATH))
        csv_points = rows[1:]

        points = []
        for row in csv_points:
            if len(row) < 6:
                continue
            tag_id, _, _, x, y, test = row[:6]
            points.append((tag_id, f"{float(x)/1000:.6f}", f"{float(y)/1000:.6f}", test))

        self.points_table.setRowCount(len(points))
        for r, (tag_id, x_m, y_m, test) in enumerate(points):
            self.points_table.setItem(r, 0, QTableWidgetItem(str(tag_id)))
            self.points_table.setItem(r, 1, QTableWidgetItem(x_m))
            self.points_table.setItem(r, 2, QTableWidgetItem(y_m))
            self.points_table.setItem(r, 3, QTableWidgetItem(str(test)))

    def _selected_camera(self):
        idx = self.camera_selector.currentIndex()
        return self.parent_ui.camera1 if idx == 0 else self.parent_ui.camera2

    def _update_camera_preview(self):
        camera = self._selected_camera()
        if camera is None or not camera.is_running:
            if self.camera_label.pixmap() is None:
                self.camera_label.setText("Feed not running")
            return

        frame = camera.get_latest_frame()
        if frame is None:
            return

        rgb = cv2.cvtColor(frame.image_bgr, cv2.COLOR_BGR2RGB)
        h, w, c = rgb.shape
        qimg = QImage(rgb.data, w, h, c * w, QImage.Format.Format_RGB888)
        pix = QPixmap.fromImage(qimg)
        self.camera_label.setPixmap(
            pix.scaled(self.camera_label.size(), Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
        )

    def _scan_tag_and_save_position(self):
        camera = self._selected_camera()
        if camera is None or not camera.is_running:
            self.scan_status.setText("Selected camera is not running")
            return

        frame = camera.get_latest_frame()
        if frame is None:
            self.scan_status.setText("No frame available from selected camera")
            return

        detections = self.detector.check_for_april_tag(frame.image_bgr)
        if not detections:
            self.scan_status.setText("No AprilTag detected")
            return

        detection = detections[0]
        tool = ToolSingleton.tool_wrapper
        pos = tool.refresh_absolute_position() if tool is not None else None

        saved = {
            "tag_id": int(detection.tag_id),
            "position": pos,
            "camera": self.camera_selector.currentText(),
        }
        self.saved_scans.append(saved)

        if pos is None:
            self.scan_status.setText(
                f"Saved tag {saved['tag_id']} from {saved['camera']} (tool position unavailable)"
            )
            return

        self.scan_status.setText(
            f"Saved tag {saved['tag_id']} from {saved['camera']} at "
            f"C1({pos.x1}, {pos.y1}, {pos.z1}) C2({pos.x2}, {pos.y2}, {pos.z2})"
        )
