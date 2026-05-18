from pathlib import Path

import cv2
import threading
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QImage, QPixmap
from PySide6.QtWidgets import (
    QComboBox,
    QCheckBox,
    QFileDialog,
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
from utils.SearchRoutines import SearchRoutines
from schema.PositionSchema import Position


TAG_CSV_PATH = Path("test_data/tag16h5_10x3_500mm_15m_offset_framed_centers.csv")
CAMERA_REFRESH_MS = 100


class LocalizationInterface(QWidget):
    def __init__(self, parent: QWidget):
        super().__init__(parent)
        self.parent_ui = parent
        self.detector = AprilTagDetector()
        self.saved_scans = []
        self.tag_coordinates_by_id = {}
        self.slot_data = {
            "c1_p1": None,
            "c1_p2": None,
            "c2_p1": None,
            "c2_p2": None,
        }

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
        self.points_table.setHorizontalHeaderLabels(["Tag ID", "X (mm)", "Y (mm)", "Test"])
        self.points_table.horizontalHeader().setStretchLastSection(True)
        self.points_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)

        layout.addWidget(self.points_table)
        return box

    def _build_action_pane(self):
        box = QGroupBox("Localization Actions")
        layout = QVBoxLayout(box)

        self.load_csv_btn = QPushButton("Load CSV")
        self.load_csv_btn.clicked.connect(self._load_csv_from_dialog)

        self.spiral_search_btn = QPushButton("Run Spiral Search")
        self.spiral_search_btn.clicked.connect(self._run_spiral_search)

        self.btn_set_c1_p1 = QPushButton("Set Carriage 1 P1")
        self.btn_set_c1_p1.clicked.connect(lambda: self._save_slot_from_scan("c1_p1"))
        self.lbl_c1_p1 = QLabel("")
        self.lbl_c1_p1.setWordWrap(True)

        self.btn_set_c1_p2 = QPushButton("Set Carriage 1 P2")
        self.btn_set_c1_p2.clicked.connect(lambda: self._save_slot_from_scan("c1_p2"))
        self.lbl_c1_p2 = QLabel("")
        self.lbl_c1_p2.setWordWrap(True)

        self.btn_set_c2_p1 = QPushButton("Set Carriage 2 P1")
        self.btn_set_c2_p1.clicked.connect(lambda: self._save_slot_from_scan("c2_p1"))
        self.lbl_c2_p1 = QLabel("")
        self.lbl_c2_p1.setWordWrap(True)

        self.btn_set_c2_p2 = QPushButton("Set Carriage 2 P2")
        self.btn_set_c2_p2.clicked.connect(lambda: self._save_slot_from_scan("c2_p2"))
        self.lbl_c2_p2 = QLabel("")
        self.lbl_c2_p2.setWordWrap(True)

        self.btn_cal_c1 = QPushButton("Calibrate Carraige 1")
        self.btn_cal_c1.clicked.connect(lambda: self._run_calibration(1))
        self.chk_inv_y_c1 = QCheckBox("Invert Y for Carraige 1")
        self.chk_inv_y_c1.setChecked(True)
        self.btn_cal_c2 = QPushButton("Calibrate Carraige 2")
        self.btn_cal_c2.clicked.connect(lambda: self._run_calibration(2))
        self.chk_inv_y_c2 = QCheckBox("Invert Y for Carraige 2")
        self.chk_inv_y_c2.setChecked(True)

        self.scan_status = QLabel("No scans yet")
        self.scan_status.setWordWrap(True)

        layout.addWidget(self.load_csv_btn)
        layout.addWidget(self.spiral_search_btn)
        layout.addWidget(self.btn_set_c1_p1)
        layout.addWidget(self.lbl_c1_p1)
        layout.addWidget(self.btn_set_c1_p2)
        layout.addWidget(self.lbl_c1_p2)
        layout.addWidget(self.btn_set_c2_p1)
        layout.addWidget(self.lbl_c2_p1)
        layout.addWidget(self.btn_set_c2_p2)
        layout.addWidget(self.lbl_c2_p2)
        layout.addWidget(self.btn_cal_c1)
        layout.addWidget(self.chk_inv_y_c1)
        layout.addWidget(self.btn_cal_c2)
        layout.addWidget(self.chk_inv_y_c2)
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
        self._load_points_from_csv(TAG_CSV_PATH)

    def _load_csv_from_dialog(self):
        file_path, _ = QFileDialog.getOpenFileName(self, "Open Tag CSV", "test_data", "CSV Files (*.csv)")
        if not file_path:
            return
        self._load_points_from_csv(Path(file_path))

    def _load_points_from_csv(self, csv_path: Path):
        if not csv_path.exists():
            self.scan_status.setText(f"Missing CSV: {csv_path}")
            return

        rows = FU.csv_to_array(str(csv_path))
        if not rows:
            self.points_table.setRowCount(0)
            self.scan_status.setText(f"Loaded 0 tag points from {csv_path.name}")
            return
        header = [h.strip().lower() for h in rows[0]]
        csv_points = rows[1:]
        self.tag_coordinates_by_id = {}

        points = []
        for row in csv_points:
            if len(row) < 5:
                continue
            try:
                if "tag_id" in header and "center_x_mm" in header and "center_y_mm" in header:
                    tag_id = row[header.index("tag_id")]
                    x = row[header.index("center_x_mm")]
                    y = row[header.index("center_y_mm")]
                    test = row[header.index("test")] if "test" in header and header.index("test") < len(row) else ""
                else:
                    tag_id = row[0]
                    x = row[3]
                    y = row[4]
                    test = row[5] if len(row) > 5 else ""

                tag_id_int = int(tag_id)
                x_mm = float(x) / 1000
                y_mm = float(y) / 1000
            except (ValueError, IndexError):
                continue
            self.tag_coordinates_by_id[tag_id_int] = (x_mm, y_mm)
            points.append((tag_id_int, f"{x_mm:.6f}", f"{y_mm:.6f}", test))

        self.points_table.setRowCount(len(points))
        for r, (tag_id, x_m, y_m, test) in enumerate(points):
            self.points_table.setItem(r, 0, QTableWidgetItem(str(tag_id)))
            self.points_table.setItem(r, 1, QTableWidgetItem(x_m))
            self.points_table.setItem(r, 2, QTableWidgetItem(y_m))
            self.points_table.setItem(r, 3, QTableWidgetItem(str(test)))
        self.scan_status.setText(f"Loaded {len(points)} tag points from {csv_path.name}")

    def _selected_camera(self):
        idx = self.camera_selector.currentIndex()
        return self.parent_ui.camera1 if idx == 0 else self.parent_ui.camera2

    def _run_spiral_search(self):
        camera = self._selected_camera()
        if camera is None or not camera.is_running:
            self.scan_status.setText("Selected camera is not running")
            return

        tool = ToolSingleton.tool_wrapper
        if tool is None:
            self.scan_status.setText("Tool handle unavailable")
            return

        carriage_index = self.camera_selector.currentIndex() + 1
        self.spiral_search_btn.setEnabled(False)
        self.scan_status.setText(f"Running spiral search for carriage {carriage_index}...")

        def _job():
            try:
                found = SearchRoutines.spiral_search(camera, tool, carriage_index)
                QTimer.singleShot(0, lambda: self.scan_status.setText(
                    f"Spiral search finished for carriage {carriage_index} | found_tag={found}"
                ))
            except Exception as exc:
                QTimer.singleShot(0, lambda: self.scan_status.setText(
                    f"Spiral search failed: {type(exc).__name__}: {exc}"
                ))
            finally:
                QTimer.singleShot(0, lambda: self.spiral_search_btn.setEnabled(True))

        threading.Thread(target=_job, daemon=True).start()

    def _update_camera_preview(self):
        camera = self._selected_camera()
        if camera is None or not camera.is_running:
            if self.camera_label.pixmap() is None:
                self.camera_label.setText("Feed not running")
            return

        frame = camera.get_latest_frame()
        if frame is None:
            return

        img = frame.image_bgr
        try:
            # Rotate 90 degrees clockwise for vertical cameras (same model as WebInterface preview).
            import numpy as np

            img = np.rot90(img, k=-1).copy()
            height, width, channels = img.shape
            if channels != 3:
                return

            bytes_per_line = int(img.strides[0])
            qimg = QImage(img.data, width, height, bytes_per_line, QImage.Format_BGR888).copy()
            pix = QPixmap.fromImage(qimg)
            self.camera_label.setPixmap(
                pix.scaled(
                    self.camera_label.size(),
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
            )
        except Exception:
            # Keep UI alive if frames arrive in an unexpected shape/dtype.
            return

    def _capture_tag_observation(self):
        camera = self._selected_camera()
        if camera is None or not camera.is_running:
            self.scan_status.setText("Selected camera is not running")
            return None

        frame = camera.get_latest_frame()
        if frame is None:
            self.scan_status.setText("No frame available from selected camera")
            return None

        detections = self.detector.check_for_april_tag(frame.image_bgr)
        if not detections:
            self.scan_status.setText("No AprilTag detected")
            return None

        detection = detections[0]
        tag_offsets_from_center_xy = self.detector.get_tag_offset_from_center_mm(detection)
        tool = ToolSingleton.tool_wrapper
        pos = tool.refresh_absolute_position() if tool is not None else None

        if pos is None:
            self.scan_status.setText("Tool position unavailable")
            return None

        dx, dy = tag_offsets_from_center_xy
        if self.camera_selector.currentIndex() == 0:
            tag_position_xy = (pos.x1 + dx, pos.y1 + dy)
        else:
            tag_position_xy = (pos.x2 + dx, pos.y2 + dy)

        tag_id = int(detection.tag_id)
        cable_xy = self.tag_coordinates_by_id.get(tag_id)

        saved = {
            "tag_id": tag_id,
            "position_stage_xy": tag_position_xy,
            "position_absolute": pos,
            "position_cable_xy": cable_xy,
            "tag_offsets_from_center_xy": tag_offsets_from_center_xy,
            "camera": self.camera_selector.currentText(),
        }
        self.saved_scans.append(saved)
        return saved

    def _save_slot_from_scan(self, slot_key: str):
        saved = self._capture_tag_observation()
        if saved is None:
            return

        self.slot_data[slot_key] = saved
        slot_labels = {
            "c1_p1": self.lbl_c1_p1,
            "c1_p2": self.lbl_c1_p2,
            "c2_p1": self.lbl_c2_p1,
            "c2_p2": self.lbl_c2_p2,
        }
        cable_xy = saved["position_cable_xy"]
        cable_str = "N/A (load CSV with this tag ID)" if cable_xy is None else f"({cable_xy[0]:.6f}, {cable_xy[1]:.6f})"
        slot_labels[slot_key].setText(
            f"ID: {saved['tag_id']}\n"
            f"Stage XY: ({saved['position_stage_xy'][0]:.3f}, {saved['position_stage_xy'][1]:.3f})\n"
            f"Cable XY: {cable_str}"
        )
        self.scan_status.setText(
            f"{slot_key.upper()} saved | Tag ID={saved['tag_id']} | "
            f"Stage XY=({saved['position_stage_xy'][0]:.3f}, {saved['position_stage_xy'][1]:.3f}) | "
            f"Cable XY={cable_str}"
        )

    def _calibrate_carriage(self, carriage_index):
        pos1 = self.slot_data[f"c{carriage_index}_p1"]
        pos2 = self.slot_data[f"c{carriage_index}_p2"]

        if pos1 is None or pos2 is None:
            raise ValueError(f"Missing calibration slots for carriage {carriage_index}. Set both P1 and P2 first.")

        pos_1_cable_xy = pos1.get("position_cable_xy")
        pos_2_cable_xy = pos2.get("position_cable_xy")
        pos_1_stage_xy = pos1.get("position_stage_xy")
        pos_2_stage_xy = pos2.get("position_stage_xy")

        if (
            pos_1_cable_xy is None or
            pos_2_cable_xy is None or
            pos_1_stage_xy is None or
            pos_2_stage_xy is None
        ):
            raise ValueError(
                f"Incomplete calibration data for carriage {carriage_index}. "
                "Each slot needs Stage XY and Cable XY values."
            )

        tool = ToolSingleton.tool_wrapper
        if tool is None:
            raise RuntimeError("Tool handle unavailable.")

        tool.set_carriage_translator(
            carriage_index= carriage_index,
            c1 = pos_1_cable_xy,
            c2 = pos_2_cable_xy,
            s1 = pos_1_stage_xy,
            s2 = pos_2_stage_xy,
            invert_y = self.chk_inv_y_c1.isChecked() if carriage_index == 1 else self.chk_inv_y_c2.isChecked(),
        )

    def _run_calibration(self, carriage_index):
        try:
            self._calibrate_carriage(carriage_index)
            self.scan_status.setText(f"Calibrated carriage {carriage_index} successfully.")
        except Exception as exc:
            self.scan_status.setText(f"Calibration failed for carriage {carriage_index}: {type(exc).__name__}: {exc}")
