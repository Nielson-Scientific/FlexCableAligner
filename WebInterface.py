import sys
from PySide6.QtWidgets import (QApplication, QWidget, QHBoxLayout, QVBoxLayout, 
                               QPushButton, QLabel, QTabWidget, QLineEdit, QFormLayout)
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtCore import QUrl
from Wrappers.ToolWrapper import ToolWrapper
from Wrappers.ToolSingleton import ToolSingleton
from CSVInterface import CSVInterface

BASE_URL = "10.34.243.54"

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

        # ==========================================
        # 1. Left Panel (Sidebar)
        # ==========================================
        side_panel = QVBoxLayout()
        side_panel.addWidget(QLabel("<b>Sidebar Controls</b>"))
        
        self.btn_carriage_1 = QPushButton("Select Carriage 1")
        self.btn_carriage_1.clicked.connect(self.handle_carriage_1)
        side_panel.addWidget(self.btn_carriage_1)
        
        self.btn_carriage_2 = QPushButton("Select Carriage 2")
        self.btn_carriage_2.clicked.connect(self.handle_carriage_2)
        side_panel.addWidget(self.btn_carriage_2)

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
        web_layout.addWidget(browser)

        tabs.addTab(tab_web, "Manual Control")

        # --- Tab 2: Native Qt Widgets ---
        tab_native = CSVInterface(self) # This is our custom QWidget with native controls
        

        tabs.addTab(tab_native, "Automatic Control")

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

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = WebInterface()
    window.show()
    sys.exit(app.exec())
