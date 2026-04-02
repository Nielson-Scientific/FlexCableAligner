from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel, QPushButton
from PySide6.QtCore import Qt

class TooCloseInterface(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.root = parent
        self.setWindowTitle("Action Required")
        
        # Ensure it appears as a separate non-modal window even if a parent is passed
        self.setWindowFlags(Qt.WindowType.Window)

        # Set up the layout
        layout = QVBoxLayout(self)

        # Generic text label
        self.label = QLabel("Please choose a position:")
        layout.addWidget(self.label)

        # Stacked buttons
        self.btn_pos1 = QPushButton("Position 1")
        layout.addWidget(self.btn_pos1)

        self.btn_pos2 = QPushButton("Position 2")
        layout.addWidget(self.btn_pos2)

        # Done button
        self.btn_done = QPushButton("Done")
        self.btn_done.clicked.connect(self.handle_done)
        layout.addWidget(self.btn_done)

        # Optional: Close the window when Done is clicked
        self.btn_done.clicked.connect(self.handle_done)

    def handle_done(self):
        self.root.other_process_running = False
        self.close()

