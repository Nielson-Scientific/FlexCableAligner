import sys
import os
from PySide6.QtWidgets import (QApplication, QWidget, QHBoxLayout, QVBoxLayout, 
                               QPushButton, QLabel, QTabWidget, QLineEdit, QFormLayout, QSpacerItem, QSizePolicy)
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtCore import QUrl, QTimer, Qt
from PySide6.QtGui import QImage, QPixmap
from Wrappers.ToolWrapper import ToolWrapper
from Wrappers.ToolSingleton import ToolSingleton
from CSVInterface import CSVInterface
from JogModeDialog import JogModeDialog
from CameraControl import CameraControl, CameraControlError

with open('config/base_url.txt', 'r') as f:
    BASE_URL = f.read().strip()

# Fill these in with your actual Vimba camera IDs.
CAMERA_1_ID = "DEV_1AB22C071903"
CAMERA_2_ID = "DEV_1AB22C089E02"

CAMERA_PREVIEW_HEIGHT_PX = 700
CAMERA_BIG_PREVIEW_MIN_WIDTH_PX = 420
CAMERA_UI_REFRESH_MS = 75
CAMERA_BAR_HEIGHT_PX = 750

class WebInterface(QWidget):
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

        self.current_carriage_label = QLabel(f"Current Carriage: {self.tool_wrapper.current_carriage}")
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

        

        # ==========================================
        # 2. Right Panel (The Tabbed View)
        # ==========================================
        tabs = QTabWidget()
        self.tabs = tabs # Store reference to tabs for later use in CSVInterface
        main_layout.addWidget(tabs, 4) # Stretch factor 4 makes it much wider than the sidebar

        # --- Tab 1: The Web Browser ---
        # We create a generic QWidget to act as the tab's container
        tab_web = QWidget()
        web_layout = QVBoxLayout(tab_web)
        web_layout.setContentsMargins(0, 0, 0, 0) # Removes the border so the web view fills the tab completely

        browser = QWebEngineView()
        browser.setUrl(QUrl(f"http://{BASE_URL}"))

        # Horizontal camera bar below the website.
        camera_bar = QWidget()
        camera_bar.setFixedHeight(CAMERA_BAR_HEIGHT_PX)
        camera_bar_layout = QHBoxLayout(camera_bar)
        camera_bar_layout.setContentsMargins(8, 8, 8, 8)

        self.camera1_big_label = QLabel("Camera 1: Feed stopped")
        self.camera1_big_label.setAlignment(Qt.AlignCenter)
        # Ignore pixmap size hints so the viewport doesn't slowly grow over time.
        self.camera1_big_label.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Ignored)
        camera_bar_layout.addWidget(self.camera1_big_label)

        self.camera2_big_label = QLabel("Camera 2: Feed stopped")
        self.camera2_big_label.setAlignment(Qt.AlignCenter)
        self.camera2_big_label.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Ignored)
        camera_bar_layout.addWidget(self.camera2_big_label)

        web_layout.addWidget(browser, 1)
        web_layout.addWidget(camera_bar, 0)

        tabs.addTab(tab_web, "Manual Control")

        # --- Tab 2: Native Qt Widgets ---
        tab_native = CSVInterface(self) # This is our custom QWidget with native controls
        

        tabs.addTab(tab_native, "Automatic Control")

        self._camera_timer = QTimer(self)
        self._camera_timer.setInterval(CAMERA_UI_REFRESH_MS)
        self._camera_timer.timeout.connect(self._update_camera_previews)

    def handle_jog_mode(self):
        dlg = JogModeDialog(self.tool_wrapper, parent=self)
        dlg.exec()

    def handle_carriage_1(self):
        self.tool_wrapper.select_carriage(1)
        self.current_carriage_label.setText(f"Current Carriage: {self.tool_wrapper.current_carriage}")

    def handle_carriage_2(self):
        self.tool_wrapper.select_carriage(2)
        self.current_carriage_label.setText(f"Current Carriage: {self.tool_wrapper.current_carriage}")

    def handle_avoid_home(self):
        self.tool_wrapper.avoid_home()
        # After sending the avoid home command, we can refresh the position to update the UI
        self.tool_wrapper.refresh_position()


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

            self.camera1_big_label.setText("Camera 1: Starting...")
            self.camera2_big_label.setText("Camera 2: Starting...")

            if not self._camera_timer.isActive():
                self._camera_timer.start()
        except CameraControlError as exc:
            self.camera1_big_label.setText(f"Camera 1: {exc}")
            self.camera2_big_label.setText(f"Camera 2: {exc}")
        except Exception as exc:
            self.camera1_big_label.setText(f"Camera 1: {type(exc).__name__}: {exc}")
            self.camera2_big_label.setText(f"Camera 2: {type(exc).__name__}: {exc}")

    def _update_camera_previews(self):
        self._update_camera_preview(self.camera1, self.camera1_big_label, "Camera 1")
        self._update_camera_preview(self.camera2, self.camera2_big_label, "Camera 2")

    def _update_camera_preview(self, camera: CameraControl, label: QLabel, title: str):
        if camera is None or not camera.is_running:
            # Keep last pixmap if present; just update text if nothing is shown.
            if label.pixmap() is None:
                label.setText(f"{title}: Feed stopped")
            return

        frame = camera.get_latest_frame()
        if frame is None:
            if label.pixmap() is None:
                label.setText(f"{title}: No frames yet")
            return

        img = frame.image_rgb
        try:
            # Rotate 90 degrees clockwise for vertical cameras.
            import numpy as np

            img = np.rot90(img, k=-1).copy()
            # Flip vertically so the feed is upside down.
            img = np.flipud(img).copy()
            img = np.fliplr(img).copy()
            height, width, channels = img.shape
            if channels != 3:
                label.setText(f"{title}: Unsupported frame")
                return
            bytes_per_line = int(img.strides[0])

            qimg = QImage(img.data, width, height, bytes_per_line, QImage.Format_BGR888).copy()
            pix = QPixmap.fromImage(qimg)
            target_size = label.contentsRect().size()
            if target_size.width() <= 0 or target_size.height() <= 0:
                return
            scaled = pix.scaled(target_size, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            label.setPixmap(scaled)
        except Exception:
            # If something goes wrong (unexpected dtype/shape), keep UI alive.
            label.setText(f"{title}: Frame error")

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
