from PySide6.QtWidgets import (QWidget, QHBoxLayout, QVBoxLayout, 
                               QPushButton, QLabel, QProgressBar, QFileDialog, QErrorMessage, QMessageBox, QStatusBar)
from PySide6.QtGui import QPainter, QColor, QBrush
from PySide6.QtCore import Qt, QPointF, QTimer
from Wrappers.CSVWrapper import CSVWrapper, Point
from Wrappers.ToolSingleton import ToolSingleton
from schema.PositionSchema import Position, dist_between_points
from TooCloseInterface import TooCloseInterface
from CalibrationInterface import CalibrationInterface
import os

MIN_SAFE_DISTANCE = 50.0

class PreviewCanvas(QWidget):
    def __init__(self):
        super().__init__()
        self.red_points = []
        self.blue_points = []
        self.green_points = []
        self.max_x = 100.0
        self.max_y = 100.0
        self.setMinimumSize(300, 300)
        self.setStyleSheet("background-color: white; border: 1px solid black;")

    def set_max_x(self, max_x):
        self.max_x = float(max_x)
        self.update()

    def set_max_y(self, max_y):
        self.max_y = float(max_y)
        self.update()

    def plot_red(self, x, y):
        self.red_points.append((x, y))
        self.update()

    def plot_blue(self, x, y):
        self.blue_points.append((x, y))
        self.update()

    def plot_green(self, x, y):
        self.green_points.append((x, y))
        self.update()

    def remove_all(self):
        self.red_points.clear()
        self.blue_points.clear()
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        
        w = self.width()
        h = self.height()

        # Draw a set of lines from the red points to the blue points for better visualization
        painter.setPen(QColor("lightgray"))
        for (x1, y1), (x2, y2) in zip(self.red_points, self.blue_points):
            px1 = (x1 / self.max_x) * w if self.max_x else 0
            py1 = h - ((y1 / self.max_y) * h) if self.max_y else h
            px2 = (x2 / self.max_x) * w if self.max_x else 0
            py2 = h - ((y2 / self.max_y) * h) if self.max_y else h
            painter.drawLine(px1, py1, px2, py2)
        
        # Draw red points
        painter.setBrush(QBrush(QColor("red")))
        painter.setPen(Qt.NoPen)
        for x, y in self.red_points:
            px = (x / self.max_x) * w if self.max_x else 0
            py = h - ((y / self.max_y) * h) if self.max_y else h
            painter.drawEllipse(QPointF(px, py), 3, 3)
            
        # Draw blue points
        painter.setBrush(QBrush(QColor("blue")))
        painter.setPen(Qt.NoPen)
        for x, y in self.blue_points:
            px = (x / self.max_x) * w if self.max_x else 0
            py = h - ((y / self.max_y) * h) if self.max_y else h
            painter.drawEllipse(QPointF(px, py), 3, 3)

        # Draw green points
        painter.setBrush(QBrush(QColor("green")))
        painter.setPen(Qt.NoPen)
        for x, y in self.green_points:
            px = (x / self.max_x) * w if self.max_x else 0
            py = h - ((y / self.max_y) * h) if self.max_y else h
            painter.drawEllipse(QPointF(px, py), 3, 3)

class CSVInterface(QWidget):
    def __init__(self, parent: QWidget):
        super().__init__()
        self.tabs = parent.tabs
        self.current_carriage_label = parent.current_carriage_label
        
        outer_layout = QVBoxLayout(self)
        
        content_layout = QHBoxLayout()
        
        # Left side: Preview Canvas
        self.preview_canvas = PreviewCanvas()
        self.error_message = QErrorMessage()
        self.message_box = QMessageBox()
        content_layout.addWidget(self.preview_canvas, stretch=1)
        
        # Right side: Controls
        right_layout = QVBoxLayout()
        
        self.btn_load_csv = QPushButton("Load CSV")
        self.btn_load_csv.clicked.connect(self.load_csv)
        self.btn_cal_land = QPushButton("Cal. Land")
        self.btn_cal_land.setEnabled(False)
        self.btn_cal_land.clicked.connect(self.calibrate_landmarks)
        self.progress_bar = QProgressBar()
        self.progress_bar.setValue(0)
        self.lbl_current_row = QLabel("Current Row: 0")
        self.lbl_current_file = QLabel("No file loaded")
        self.btn_next = QPushButton("Next")
        self.btn_next.clicked.connect(self.run_next)
        self.btn_next.setEnabled(False)
        self.btn_done = QPushButton("Done")
        self.btn_done.clicked.connect(self.handle_done)
        self.btn_done.setEnabled(False)
        self.status_bar = QStatusBar()
        
        right_layout.addWidget(self.btn_load_csv)
        right_layout.addWidget(self.btn_cal_land)
        right_layout.addWidget(self.progress_bar)
        right_layout.addWidget(self.lbl_current_row)
        right_layout.addWidget(self.lbl_current_file)
        right_layout.addWidget(self.btn_next)
        right_layout.addWidget(self.btn_done)
        right_layout.addStretch()
        
        content_layout.addLayout(right_layout)
        
        outer_layout.addLayout(content_layout)
        outer_layout.addWidget(self.status_bar)
        
        self.set_max_x(200)
        self.set_max_y(200)
        self.plot_red(50, 50)
        self.plot_blue(150, 150)

        # Variables for actual functionality
        self.file_path = None
        self.csv_wrapper = None
        self.tool = ToolSingleton.tool_wrapper
        self.current_row = 0
        self.other_process_running = False

    def load_csv(self):
        file_dialog = QFileDialog()
        file_path, _ = file_dialog.getOpenFileName(self, "Open CSV", "", "CSV Files (*.csv)")
        if file_path:
            self.file_path = file_path
            self.lbl_current_file.setText(f"Current File: {os.path.basename(file_path)[:20]}")
            try:
                self.csv_wrapper = CSVWrapper(file_path)
                self.plot_csv_points()
                self.btn_cal_land.setEnabled(True)
                self.status_bar.showMessage("CSV loaded successfully. You can now calibrate the landmarks", 5000)
            except Exception as e:
                self.error_message.showMessage(f"Error loading CSV: {str(e)}")
                self.btn_cal_land.setEnabled(False)
        else:
            self.error_message.showMessage("No file selected.")
            self.btn_cal_land.setEnabled(False)

    def plot_csv_points(self):
        if not self.csv_wrapper:
            return
        
        self.remove_all()
        
        land1, land2 = self.csv_wrapper.get_landmarks()
        all_x = [tp.x1 for tp in self.csv_wrapper.test_pairs] + [tp.x2 for tp in self.csv_wrapper.test_pairs] + [land1[0], land2[0]]
        all_y = [tp.y1 for tp in self.csv_wrapper.test_pairs] + [tp.y2 for tp in self.csv_wrapper.test_pairs] + [land1[1], land2[1]]
        self.set_max_x(max(all_x) * 1.25)
        self.set_max_y(max(all_y) * 1.25)
        self.plot_green(*land1)
        self.plot_green(*land2)

        
        for test_pair in self.csv_wrapper.test_pairs:
            self.plot_red(test_pair.x1, test_pair.y1)
            self.plot_blue(test_pair.x2, test_pair.y2)


    def set_max_x(self, max_x):
        self.preview_canvas.set_max_x(max_x)

    def set_max_y(self, max_y):
        self.preview_canvas.set_max_y(max_y)

    def plot_red(self, x, y):
        self.preview_canvas.plot_red(x, y)

    def plot_green(self, x, y):
        self.preview_canvas.plot_green(x, y)

    def plot_blue(self, x, y):
        self.preview_canvas.plot_blue(x, y)

    def remove_all(self):
        self.preview_canvas.remove_all()

    def _configure_message_box(self):
        # self.message_box = QMessageBox()
        try:
            self.message_box.buttonClicked.disconnect()
        except RuntimeError:
            pass
        self.message_box.setWindowTitle("Calibration")
        self.message_box.setWindowModality(Qt.WindowModality.NonModal)
        self.message_box.setStandardButtons(QMessageBox.StandardButton.Ok)

    def calibrate_landmarks(self):
        if not self.csv_wrapper:
            self.error_message.showMessage("No CSV file loaded.")
            return
        
        self.status_bar.showMessage("Starting, please wait...", 5000)
        self.tool.set_offsets_to_zero()
        self.tool.park_carriage(2)  # Park the second carriage to avoid interference
        self.tool.select_carriage(1)
        self.current_carriage_label.setText(f"Current Carriage: {self.tool.current_carriage}")
        self.tabs.setCurrentIndex(0)  # Switch to the Manual Control tab for calibration
        text = "Please move carriage 1 to Landmark 1 (green point) and click OK."
        ci = CalibrationInterface(parent=self, on_clicked=lambda: self.on_landmark1_calibrated(), text=text)
        ci.show()

    def on_landmark1_calibrated(self):
        pos1 = self.tool.refresh_absolute_position()
        land1, _ = self.csv_wrapper.get_landmarks()
        self.tool.set_position_as_point(Point(x=land1[0], y=land1[1]), carriage_index=1)
        self.tool.park_carriage(1)
        self.tool.select_carriage(2)
        self.tool.move_absolute(Position(x2=pos1.x1, y2=pos1.y1))  # Move carriage 2 to the same position as carriage 1
        self.current_carriage_label.setText(f"Current Carriage: {self.tool.current_carriage}")
        QTimer.singleShot(0, lambda: self.show_landmark2_message())

    def show_landmark2_message(self):
        text = "Please move carriage 2 to Landmark 1 (green point) and click OK."
        ci = CalibrationInterface(parent=self, on_clicked=lambda: self.on_landmark2_calibrated(), text=text)
        ci.show()

    def on_landmark2_calibrated(self):
        land1, land2 = self.csv_wrapper.get_landmarks()
        self.tool.set_position_as_point(Point(x=land1[0], y=land1[1]), carriage_index=2)
        self.tool.move_pcb_space(Position(x2=land2[0], y2=land2[1]))  # Move carriage 1 to Landmark 2 expected position
        QTimer.singleShot(0, lambda: self.show_landmark3_message())

    def show_landmark3_message(self):
        text = "Please move carriage 2 to Landmark 2 (green point) and click OK."
        ci = CalibrationInterface(parent=self, on_clicked=lambda: self.on_landmark3_calibrated(), text=text)
        ci.show()

    def on_landmark3_calibrated(self):
        true_pos3 = self.tool.refresh_position()
        print("True Position of Landmark 2 (relative coordinates):", true_pos3)
        self.tabs.setCurrentIndex(1)
        _, land2 = self.csv_wrapper.get_landmarks()
        print(f"Expected Position of Landmark 2 (from CSV): {land2}")
        rotation = self.csv_wrapper.get_rotation(Point(x=true_pos3.x2, y=true_pos3.y2), Point(x=land2[0], y=land2[1]))
        print(f"Calculated rotation (radians): {rotation}")
        self.csv_wrapper.apply_rotation(-rotation)
        self.plot_csv_points()
        self.btn_load_csv.setEnabled(False)
        self.btn_cal_land.setEnabled(False)
        self.btn_next.setEnabled(True)
        self.btn_done.setEnabled(True)
        self.status_bar.showMessage("Calibration complete! You can now run the process.", 5000)


    def run_next(self):
        if not self.csv_wrapper:
            self.error_message.showMessage("No CSV file loaded.")
            return
        
        if self.other_process_running:
            self.error_message.showMessage("Please complete the current process before proceeding to the next one.")
            return
        
        if self.current_row >= len(self.csv_wrapper.test_pairs):
            self.message_box.setText("All rows have been processed.")
            self.message_box.setStandardButtons(QMessageBox.StandardButton.Ok)
            self.message_box.buttonClicked.connect(lambda: self.message_box.hide())
            self.message_box.show()
            return
        
        test_pair: Position = self.csv_wrapper.get_nth_test_pair(self.current_row)
        if dist_between_points(test_pair) < MIN_SAFE_DISTANCE:
            pos1 = Position(x2=test_pair.x1, y2=test_pair.y1)
            pos2=Position(x2=test_pair.x2, y2=test_pair.y2)
            x = TooCloseInterface(self, pos1=pos1, pos2=pos2)
            self.other_process_running = True
            x.show()
            return
        self.tool.move_pcb_space(test_pair)
        self.mark_current_row_as_done()

    def mark_current_row_as_done(self):
        self.current_row += 1
        self.lbl_current_row.setText(f"Current Row: {self.current_row}")
        progress = int((self.current_row / len(self.csv_wrapper.test_pairs)) * 100)
        self.progress_bar.setValue(progress)

    def handle_done(self):
        self.btn_load_csv.setEnabled(True)
        self.btn_cal_land.setEnabled(False)
        self.btn_next.setEnabled(False)
        self.btn_done.setEnabled(False)
        self.current_row = 0
        self.csv_wrapper = None
        self.file_path = None
        self.progress_bar.setValue(0)
        self.lbl_current_row.setText("Current Row: 0")
        self.tool.set_offsets_to_zero()

