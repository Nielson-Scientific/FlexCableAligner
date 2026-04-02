from PySide6.QtWidgets import (QWidget, QHBoxLayout, QVBoxLayout, 
                               QPushButton, QLabel, QProgressBar, QFileDialog, QErrorMessage, QMessageBox)
from PySide6.QtGui import QPainter, QColor, QBrush
from PySide6.QtCore import Qt, QPointF
from Wrappers.CSVWrapper import CSVWrapper, TestPair
from Wrappers.ToolSingleton import ToolSingleton
import os

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
    def __init__(self):
        super().__init__()
        
        main_layout = QHBoxLayout(self)
        
        # Left side: Preview Canvas
        self.preview_canvas = PreviewCanvas()
        self.error_message = QErrorMessage()
        main_layout.addWidget(self.preview_canvas, stretch=1)
        
        # Right side: Controls
        right_layout = QVBoxLayout()
        
        self.btn_load_csv = QPushButton("Load CSV")
        self.btn_load_csv.clicked.connect(self.load_csv)
        self.btn_cal_land = QPushButton("Cal. Land")
        self.btn_cal_land.clicked.connect(self.calibrate_landmarks)
        self.progress_bar = QProgressBar()
        self.progress_bar.setValue(0)
        self.lbl_current_row = QLabel("Current Row: 0")
        self.lbl_current_file = QLabel("No file loaded")
        self.btn_next = QPushButton("Next")
        self.btn_done = QPushButton("Done")
        
        right_layout.addWidget(self.btn_load_csv)
        right_layout.addWidget(self.btn_cal_land)
        right_layout.addWidget(self.progress_bar)
        right_layout.addWidget(self.lbl_current_row)
        right_layout.addWidget(self.lbl_current_file)
        right_layout.addWidget(self.btn_next)
        right_layout.addWidget(self.btn_done)
        right_layout.addStretch()
        
        main_layout.addLayout(right_layout)
        self.set_max_x(200)
        self.set_max_y(200)
        self.plot_red(50, 50)
        self.plot_blue(150, 150)

        # Variables for actual functionality
        self.file_path = None
        self.csv_wrapper = None
        self.tool = ToolSingleton.tool_wrapper

    def load_csv(self):
        file_dialog = QFileDialog()
        file_path, _ = file_dialog.getOpenFileName(self, "Open CSV", "", "CSV Files (*.csv)")
        if file_path:
            self.file_path = file_path
            self.lbl_current_file.setText(f"Current File: {os.path.basename(file_path)[:20]}")
            try:
                self.csv_wrapper = CSVWrapper(file_path)
                self.plot_csv_points()
            except Exception as e:
                self.error_message.showMessage(f"Error loading CSV: {str(e)}")

    def plot_csv_points(self):
        if not self.csv_wrapper:
            return
        
        self.remove_all()
        
        land1, land2 = self.csv_wrapper.get_landmarks()
        self.plot_green(*land1)
        self.plot_green(*land2)
        self.set_max_x(max(land1[0], land2[0]) * 1.25)
        self.set_max_y(max(land1[1], land2[1]) * 1.25)
        
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
        if x == 0 and y == 0:
            x, y = 0.5, 0.5
        self.preview_canvas.plot_green(x, y)

    def plot_blue(self, x, y):
        self.preview_canvas.plot_blue(x, y)

    def remove_all(self):
        self.preview_canvas.remove_all()

    def calibrate_landmarks(self):
        if not self.csv_wrapper:
            self.error_message.showMessage("No CSV file loaded.")
            return
        
        land1, land2 = self.csv_wrapper.get_landmarks()
        self.tool.select_carriage(1)
        self.tool.park_carriage(2)  # Park the second carriage to avoid interference
        QMessageBox.information(self, "Calibration", "Please move carriage 1 to Landmark 1 (green point) and click OK.")
        
