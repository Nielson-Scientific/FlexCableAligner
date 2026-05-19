import sys
import os
import threading
from datetime import datetime
from PySide6.QtWidgets import (QApplication, QWidget, QHBoxLayout, QVBoxLayout, 
                               QPushButton, QLabel, QTabWidget, QLineEdit, QFormLayout, QSpacerItem, QSizePolicy, QFileDialog)
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtCore import QUrl, QTimer, Qt, Signal
from PySide6.QtGui import QImage, QPixmap
from Wrappers.ToolWrapper import ToolWrapper
from Wrappers.ToolSingleton import ToolSingleton
from CSVInterface import CSVInterface
from JogModeDialog import JogModeDialog
from Controllers.CameraControl import CameraControl, CameraControlError

from localization.LocalizationInterface import LocalizationInterface

from utils.AutoFocus import Autofocus

with open('config/base_url.txt', 'r') as f:
    BASE_URL = f.read().strip()

# Fill these in with your actual Vimba camera IDs.
CAMERA_1_ID = "DEV_1AB22C071903"
CAMERA_2_ID = "DEV_1AB22C089E02"

CAMERA_PREVIEW_HEIGHT_PX = 180
CAMERA_BIG_PREVIEW_MIN_WIDTH_PX = 420
CAMERA_UI_REFRESH_MS = 75
DEFAULT_CAPTURE_DIR = "test_images/via_captures"

class WebInterface(QWidget):
    autofocus_finished = Signal()
    thorough_autofocus_finished = Signal()

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Tool Control")
        self.resize(1000, 700)
        self.tool_wrapper = ToolWrapper(f"ws://{BASE_URL}:7125/websocket")
        ToolSingleton.set_tool_wrapper(self.tool_wrapper)

        # The main horizontal layout to separate the left sidebar from the right content
        main_layout = QHBoxLayout(self)

        self.saved_positions = []
        self.saved_positions_labels = []

        self.camera1 = None
        self.camera2 = None
        self.latest_camera1_image = None
        self.latest_camera2_image = None
        self.capture_save_dir = os.path.abspath(DEFAULT_CAPTURE_DIR)

        # ==========================================
        # 1. Left Panel (Sidebar)
        # ==========================================
        side_panel = QVBoxLayout()
        self.side_panel = side_panel
        side_panel.addWidget(QLabel("<b>Sidebar Controls</b>"))
        
        self.btn_carriage_1 = QPushButton("Select Carriage 1")
        self.btn_carriage_1.clicked.connect(self.handle_carriage_1)
        side_panel.addWidget(self.btn_carriage_1)
        
        self.btn_carriage_2 = QPushButton("Select Carriage 2")
        self.btn_carriage_2.clicked.connect(self.handle_carriage_2)
        side_panel.addWidget(self.btn_carriage_2)

        self.btn_jog_mode = QPushButton("Jog Mode")
        self.btn_jog_mode.clicked.connect(self.handle_jog_mode)
        side_panel.addWidget(self.btn_jog_mode)

        self.btn_avoid_home = QPushButton("Avoid Home")
        self.btn_avoid_home.clicked.connect(self.handle_avoid_home)
        side_panel.addWidget(self.btn_avoid_home)

        self.btn_autofocus = QPushButton("Autofocus")
        self.btn_autofocus.clicked.connect(self.handle_autofocus)
        self.btn_autofocus.setEnabled(False)
        side_panel.addWidget(self.btn_autofocus)

        self.btn_thorough_autofocus = QPushButton("Thorough Autofocus")
        self.btn_thorough_autofocus.clicked.connect(self.handle_thorough_autofocus)
        self.btn_thorough_autofocus.setEnabled(False)
        side_panel.addWidget(self.btn_thorough_autofocus)

        self.current_carriage_label = QLabel(f"Current Carriage: {self.tool_wrapper.selected_carriage}")
        side_panel.addWidget(self.current_carriage_label)

        self.btn_add_position = QPushButton("Save Current Position")
        self.btn_add_position.clicked.connect(self.handle_add_position)
        side_panel.addWidget(self.btn_add_position)

        self.btn_clear_positions = QPushButton("Clear Saved Positions")
        self.btn_clear_positions.clicked.connect(self.handle_clear_positions)
        side_panel.addWidget(self.btn_clear_positions)

        self.btn_restart_feeds = QPushButton("Restart Feeds")
        self.btn_restart_feeds.clicked.connect(self.handle_restart_feeds)
        side_panel.addWidget(self.btn_restart_feeds)

        side_panel.addStretch() # Pushes the buttons to the top

        main_layout.addLayout(side_panel, 1) # Stretch factor 1

        

        # Spacer that expands: everything after it will be pinned to the bottom.
        # self._sidebar_spacer = QSpacerItem(0, 0, QSizePolicy.Maximum, QSizePolicy.Expanding)
        # side_panel.addItem(self._sidebar_spacer)

        # self.btn_restart_feeds = QPushButton("Restart Feeds")
        # self.btn_restart_feeds.clicked.connect(self.handle_restart_feeds)
        # side_panel.addWidget(self.btn_restart_feeds)

        # self.camera1_label = QLabel("Camera 1: Feed stopped")
        # self.camera1_label.setAlignment(Qt.AlignCenter)
        # self.camera1_label.setFixedHeight(CAMERA_PREVIEW_HEIGHT_PX)
        # self.camera1_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        # side_panel.addWidget(self.camera1_label)

        # self.camera2_label = QLabel("Camera 2: Feed stopped")
        # self.camera2_label.setAlignment(Qt.AlignCenter)
        # self.camera2_label.setFixedHeight(CAMERA_PREVIEW_HEIGHT_PX)
        # self.camera2_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        # side_panel.addWidget(self.camera2_label)

        # main_layout.addLayout(side_panel, 1) # Stretch factor 1

        # ==========================================
        # 2. Right Panel (The Tabbed View)
        # ==========================================
        tabs = QTabWidget()
        self.tabs = tabs # Store reference to tabs for later use in CSVInterface
        main_layout.addWidget(tabs, 4) # Stretch factor 4 makes it much wider than the sidebar

        # --- Tab 1: The Web Browser ---
        # We create a generic QWidget to act as the tab's container
        tab_web = QWidget()
        web_layout = QHBoxLayout(tab_web)
        web_layout.setContentsMargins(0, 0, 0, 0) # Removes the border so the web view fills the tab completely

        browser = QWebEngineView()
        browser.setUrl(QUrl(f"http://{BASE_URL}"))

        camera_panel = QWidget()
        camera_panel.setMinimumWidth(CAMERA_BIG_PREVIEW_MIN_WIDTH_PX)
        camera_panel_layout = QVBoxLayout(camera_panel)
        camera_panel_layout.setContentsMargins(8, 8, 8, 8)

        self.camera1_big_label = QLabel("Camera 1: Feed stopped")
        self.camera1_big_label.setAlignment(Qt.AlignCenter)
        # Important: QLabel's size hints can be dominated by the last pixmap size,
        # which can accidentally force the *window* minimum size and cause repeated
        # geometry warnings on smaller screens.
        self.camera1_big_label.setMinimumSize(1, 1)
        self.camera1_big_label.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Ignored)
        camera_panel_layout.addWidget(self.camera1_big_label, 1)

        self.camera2_big_label = QLabel("Camera 2: Feed stopped")
        self.camera2_big_label.setAlignment(Qt.AlignCenter)
        self.camera2_big_label.setMinimumSize(1, 1)
        self.camera2_big_label.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Ignored)
        camera_panel_layout.addWidget(self.camera2_big_label, 1)

        web_layout.addWidget(browser, 4)
        web_layout.addWidget(camera_panel, 2)

        tabs.addTab(tab_web, "Manual Control")

        # --- Tab 2: Native Qt Widgets ---
        tab_native = CSVInterface(self) # This is our custom QWidget with native controls
        

        tabs.addTab(tab_native, "Automatic Control")

        self._camera_timer = QTimer(self)
        self._camera_timer.setInterval(CAMERA_UI_REFRESH_MS)
        self._camera_timer.timeout.connect(self._update_camera_previews)


        # --- Tab 3: Localization Interface ---
        tab_localization = LocalizationInterface(self)
        tabs.addTab(tab_localization, "Localization")

        # --- Tab 4: Image Capture Interface ---
        tab_capture = QWidget()
        capture_layout = QVBoxLayout(tab_capture)
        capture_layout.setContentsMargins(10, 10, 10, 10)
        capture_layout.setSpacing(8)

        self.capture_dir_label = QLabel(f"Save Directory: {self.capture_save_dir}")
        self.capture_dir_label.setWordWrap(True)
        capture_layout.addWidget(self.capture_dir_label)

        self.btn_choose_capture_dir = QPushButton("Choose Save Directory")
        self.btn_choose_capture_dir.clicked.connect(self.handle_choose_capture_dir)
        capture_layout.addWidget(self.btn_choose_capture_dir)

        self.capture_camera1_label = QLabel("Camera 1: Feed stopped")
        self.capture_camera1_label.setAlignment(Qt.AlignCenter)
        self.capture_camera1_label.setMinimumSize(1, 1)
        self.capture_camera1_label.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Ignored)
        capture_layout.addWidget(self.capture_camera1_label, 1)

        self.btn_save_camera1 = QPushButton("Save Camera 1 Photo")
        self.btn_save_camera1.clicked.connect(lambda: self.handle_save_camera_photo(1))
        capture_layout.addWidget(self.btn_save_camera1)

        self.capture_camera2_label = QLabel("Camera 2: Feed stopped")
        self.capture_camera2_label.setAlignment(Qt.AlignCenter)
        self.capture_camera2_label.setMinimumSize(1, 1)
        self.capture_camera2_label.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Ignored)
        capture_layout.addWidget(self.capture_camera2_label, 1)

        self.btn_save_camera2 = QPushButton("Save Camera 2 Photo")
        self.btn_save_camera2.clicked.connect(lambda: self.handle_save_camera_photo(2))
        capture_layout.addWidget(self.btn_save_camera2)

        tabs.addTab(tab_capture, "Image Capture")

        # Thread-safe UI updates: worker threads emit, UI thread handles.
        self.autofocus_finished.connect(lambda: self.btn_autofocus.setEnabled(True))
        self.thorough_autofocus_finished.connect(lambda: self.btn_thorough_autofocus.setEnabled(True))

    def _clamp_to_screen(self):
        screen = self.screen() or QApplication.primaryScreen()
        if screen is None:
            return

        avail = screen.availableGeometry()
        if avail.isNull():
            return

        # Cap the maximum size so layout changes can't force an off-screen geometry.
        self.setMaximumSize(avail.width(), avail.height())

        geo = self.geometry()
        new_w = min(geo.width(), avail.width())
        new_h = min(geo.height(), avail.height())
        if new_w != geo.width() or new_h != geo.height():
            self.resize(new_w, new_h)

        # Ensure the window's top-left stays within available bounds.
        x = max(avail.left(), min(geo.x(), avail.right() - new_w + 1))
        y = max(avail.top(), min(geo.y(), avail.bottom() - new_h + 1))
        if x != geo.x() or y != geo.y():
            self.move(x, y)

    def showEvent(self, event):
        super().showEvent(event)
        # Run after the first layout pass.
        QTimer.singleShot(0, self._clamp_to_screen)

    def handle_jog_mode(self):
        dlg = JogModeDialog(self.tool_wrapper, parent=self)
        dlg.exec()

    def handle_carriage_1(self):
        self.tool_wrapper.select_carriage(1)
        self.current_carriage_label.setText(f"Current Carriage: {self.tool_wrapper.selected_carriage}")

    def handle_carriage_2(self):
        self.tool_wrapper.select_carriage(2)
        self.current_carriage_label.setText(f"Current Carriage: {self.tool_wrapper.selected_carriage}")

    def handle_avoid_home(self):
        self.tool_wrapper.avoid_home()
        # After sending the avoid home command, we can refresh the position to update the UI
        self.tool_wrapper.refresh_position()

    def handle_autofocus(self):
        current_carriage = self.tool_wrapper.selected_carriage
        af_cam = self.camera1 if current_carriage == 1 else self.camera2
        if af_cam is None or not af_cam.is_running:
            return
        z_pos = self.tool_wrapper.get_absolute_position().z1 if current_carriage == 1 else self.tool_wrapper.refresh_absolute_position().z2
        self.btn_autofocus.setEnabled(False)

        def _job():
            try:
                Autofocus.quick_autofocus_routine(
                    af_cam,
                    self.tool_wrapper,
                    current_carriage,
                    current_height=z_pos,
                )
            finally:
                self.autofocus_finished.emit()

        threading.Thread(target=_job, daemon=True).start()

    def handle_thorough_autofocus(self):
        current_carriage = self.tool_wrapper.selected_carriage
        af_cam = self.camera1 if current_carriage == 1 else self.camera2
        if af_cam is None or not af_cam.is_running:
            return
        self.btn_thorough_autofocus.setEnabled(False)

        def _job():
            try:
                Autofocus.thorough_autofocus_routine(
                    af_cam,
                    self.tool_wrapper,
                    current_carriage,
                )
            finally:
                self.thorough_autofocus_finished.emit()

        threading.Thread(target=_job, daemon=True).start()

    def handle_run_process(self):
        project_name = self.input_project_name.text()
        print(f"Run Process clicked! Project Name: {project_name}")

    def handle_add_position(self):
        current_pos = self.tool_wrapper.refresh_absolute_position()
        self.saved_positions.append(current_pos)
        current_pos_str = f"C1: ({current_pos.x1:.2f}, {current_pos.y1:.2f}), C2: ({current_pos.x2:.2f}, {current_pos.y2:.2f})"
        label = QLabel(current_pos_str)
        self.saved_positions_labels.append(label)
        # Add the new label to the sidebar (just before the stretch)
        self.layout().itemAt(0).layout().insertWidget(self.layout().itemAt(0).layout().count() - 1, label)
        btn = QPushButton(f"Go to Position {len(self.saved_positions)}")
        btn.clicked.connect(lambda _, idx=len(self.saved_positions)-1: self.go_to_position(idx))
        self.layout().itemAt(0).layout().insertWidget(self.layout().itemAt(0).layout().count() - 1, btn)

    def go_to_position(self, position_index):
        if 0 <= position_index < len(self.saved_positions):
            target_pos = self.saved_positions[position_index]
            self.tool_wrapper.move_absolute(target_pos)
        else:
            print("Invalid position index")

    def handle_clear_positions(self):
        self.saved_positions.clear()
        for label in self.saved_positions_labels:
            label.deleteLater() # Remove the label from the UI
        self.saved_positions_labels.clear() # Clear the list of labels
        # Also remove any "Go to Position" buttons
        side_layout = self.layout().itemAt(0).layout()
        for i in reversed(range(side_layout.count())):
            widget = side_layout.itemAt(i).widget()
            if isinstance(widget, QPushButton) and widget.text().startswith("Go to Position"):
                widget.deleteLater()

    def handle_restart_feeds(self):
        try:
            if self.camera1 is None:
                self.camera1 = CameraControl(CAMERA_1_ID)
            if self.camera2 is None:
                self.camera2 = CameraControl(CAMERA_2_ID)

            self.camera1.restart()
            self.camera2.restart()
            self._refresh_autofocus_buttons_enabled()

            self.camera1_big_label.setText("Camera 1: Starting...")
            self.camera2_big_label.setText("Camera 2: Starting...")
            self.capture_camera1_label.setText("Camera 1: Starting...")
            self.capture_camera2_label.setText("Camera 2: Starting...")

            if not self._camera_timer.isActive():
                self._camera_timer.start()
        except CameraControlError as exc:
            self.camera1_big_label.setText(f"Camera 1: {exc}")
            self.camera2_big_label.setText(f"Camera 2: {exc}")
            self._refresh_autofocus_buttons_enabled()
        except Exception as exc:
            self.camera1_big_label.setText(f"Camera 1: {type(exc).__name__}: {exc}")
            self.camera2_big_label.setText(f"Camera 2: {type(exc).__name__}: {exc}")
            self._refresh_autofocus_buttons_enabled()

    def _refresh_autofocus_buttons_enabled(self):
        cams_ready = (
            self.camera1 is not None and self.camera1.is_running and
            self.camera2 is not None and self.camera2.is_running
        )
        self.btn_autofocus.setEnabled(cams_ready)
        self.btn_thorough_autofocus.setEnabled(cams_ready)

    def _update_camera_previews(self):
        frame1 = self._fetch_latest_frame(self.camera1)
        frame2 = self._fetch_latest_frame(self.camera2)
        self.latest_camera1_image = frame1.image_bgr.copy() if frame1 is not None else self.latest_camera1_image
        self.latest_camera2_image = frame2.image_bgr.copy() if frame2 is not None else self.latest_camera2_image

        self._update_camera_preview_from_image(self.camera1, frame1, self.camera1_big_label, "Camera 1")
        self._update_camera_preview_from_image(self.camera1, frame1, self.capture_camera1_label, "Camera 1")
        self._update_camera_preview_from_image(self.camera2, frame2, self.camera2_big_label, "Camera 2")
        self._update_camera_preview_from_image(self.camera2, frame2, self.capture_camera2_label, "Camera 2")

    def _fetch_latest_frame(self, camera: CameraControl):
        if camera is None or not camera.is_running:
            return None
        return camera.get_latest_frame()

    def _update_camera_preview_from_image(self, camera: CameraControl, frame, label: QLabel, title: str):
        if camera is None or not camera.is_running:
            # Keep last pixmap if present; just update text if nothing is shown.
            if label.pixmap() is None:
                label.setText(f"{title}: Feed stopped")
            return

        if frame is None:
            if label.pixmap() is None:
                label.setText(f"{title}: No frames yet")
            return

        img = frame.image_bgr
        try:
            # Rotate 90 degrees clockwise for vertical cameras.
            import numpy as np

            img = np.rot90(img, k=-1).copy()
            height, width, channels = img.shape
            if channels != 3:
                label.setText(f"{title}: Unsupported frame")
                return
            bytes_per_line = int(img.strides[0])

            qimg = QImage(img.data, width, height, bytes_per_line, QImage.Format_BGR888).copy()
            pix = QPixmap.fromImage(qimg)
            scaled = pix.scaled(label.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation)
            label.setPixmap(scaled)
        except Exception:
            # If something goes wrong (unexpected dtype/shape), keep UI alive.
            label.setText(f"{title}: Frame error")

    def handle_choose_capture_dir(self):
        selected = QFileDialog.getExistingDirectory(self, "Select Save Directory", self.capture_save_dir)
        if selected:
            self.capture_save_dir = selected
            self.capture_dir_label.setText(f"Save Directory: {self.capture_save_dir}")

    def handle_save_camera_photo(self, camera_index: int):
        if camera_index == 1:
            image = self.latest_camera1_image
            label = self.capture_camera1_label
            prefix = "cam1"
        else:
            image = self.latest_camera2_image
            label = self.capture_camera2_label
            prefix = "cam2"

        if image is None:
            label.setText(f"Camera {camera_index}: No frame available to save")
            return

        try:
            import cv2

            os.makedirs(self.capture_save_dir, exist_ok=True)
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
            out_path = os.path.join(self.capture_save_dir, f"{prefix}_{timestamp}.png")
            if cv2.imwrite(out_path, image):
                label.setText(f"Camera {camera_index}: Saved {os.path.basename(out_path)}")
            else:
                label.setText(f"Camera {camera_index}: Save failed")
        except Exception as exc:
            label.setText(f"Camera {camera_index}: Save error: {type(exc).__name__}")

    def closeEvent(self, event):
        try:
            if self._camera_timer.isActive():
                self._camera_timer.stop()
            if self.camera1 is not None:
                self.camera1.stop()
            if self.camera2 is not None:
                self.camera2.stop()
        finally:
            super().closeEvent(event)

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = WebInterface()
    window.show()
    sys.exit(app.exec())
