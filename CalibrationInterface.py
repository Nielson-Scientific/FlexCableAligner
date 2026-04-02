from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel, QPushButton
from PySide6.QtCore import Qt
from typing import Callable, Optional

class CalibrationInterface(QWidget):
    def __init__(self, parent=None, on_clicked: Optional[Callable] = None, text: Optional[str] = None):
        super().__init__(parent)
        self.root = parent
        self.on_clicked = on_clicked
        self.text = text or "Please choose a position:"

        self.setWindowTitle("Calibration Sequence")
        
        # Ensure it appears as a separate non-modal window even if a parent is passed
        self.setWindowFlags(Qt.WindowType.Window)

        # Set up the layout
        layout = QVBoxLayout(self)

        # Generic text label
        self.label = QLabel(self.text)
        layout.addWidget(self.label)

        # Done button
        self.btn_done = QPushButton("Done")
        layout.addWidget(self.btn_done)
        self.btn_done.clicked.connect(self.handle_done)

    def handle_done(self):
        if self.on_clicked:
            self.on_clicked()
        self.close()

