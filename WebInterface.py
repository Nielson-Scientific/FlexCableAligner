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

        self.current_carriage_label = QLabel(f"Current Carriage: {self.tool_wrapper.current_carriage}")
        side_panel.addWidget(self.current_carriage_label)
        
        side_panel.addStretch() # Pushes the buttons to the top

        main_layout.addLayout(side_panel, 1) # Stretch factor 1

        # ==========================================
        # 2. Right Panel (The Tabbed View)
        # ==========================================
        tabs = QTabWidget()
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
        tab_native = CSVInterface(tabs) # This is our custom QWidget with native controls
        

        tabs.addTab(tab_native, "Automatic Control")
        self.tabs = tabs # Store reference to tabs for later use in CSVInterface

    def handle_carriage_1(self):
        self.tool_wrapper.select_carriage(1)
        self.current_carriage_label.setText(f"Current Carriage: {self.tool_wrapper.current_carriage}")

    def handle_carriage_2(self):
        self.tool_wrapper.select_carriage(2)
        self.current_carriage_label.setText(f"Current Carriage: {self.tool_wrapper.current_carriage}")


    def handle_run_process(self):
        project_name = self.input_project_name.text()
        print(f"Run Process clicked! Project Name: {project_name}")

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = WebInterface()
    window.show()
    sys.exit(app.exec())
