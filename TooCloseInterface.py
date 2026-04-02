from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel, QPushButton
from PySide6.QtCore import Qt
from Wrappers.ToolSingleton import ToolSingleton
from PositionSchema import Position

class TooCloseInterface(QWidget):
    def __init__(self, parent=None, pos1=None, pos2=None):
        super().__init__(parent)
        self.root = parent
        self.pos1, self.pos2 = pos1, pos2
        self.tool = ToolSingleton.tool_wrapper
        self.setWindowTitle("Action Required")
        
        # Ensure it appears as a separate non-modal window even if a parent is passed
        self.setWindowFlags(Qt.WindowType.Window)

        # Set up the layout
        layout = QVBoxLayout(self)

        # Generic text label
        self.label = QLabel("The selected points are too close. Please manually probe:")
        layout.addWidget(self.label)

        # Stacked buttons
        self.btn_pos1 = QPushButton("Position 1")
        self.btn_pos1.clicked.connect(self.move_to_pos1)
        layout.addWidget(self.btn_pos1)

        self.btn_pos2 = QPushButton("Position 2")
        self.btn_pos2.clicked.connect(self.move_to_pos2)
        layout.addWidget(self.btn_pos2)

        # Done button
        self.btn_done = QPushButton("Done")
        layout.addWidget(self.btn_done)

        # Optional: Close the window when Done is clicked
        self.btn_done.clicked.connect(self.handle_done)

        self.tool.park_carriage(1)

    def move_to_pos1(self):
        if self.pos1:
            self.tool.move(self.pos1)

    def move_to_pos2(self):
        if self.pos2:
            self.tool.move(self.pos2)
        

    def handle_done(self):
        self.root.other_process_running = False
        self.root.mark_current_row_as_done()
        self.close()

