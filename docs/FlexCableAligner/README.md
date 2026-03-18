# FlexCableAligner

FlexCableAligner is a Python-based tooling control software that automates testing of flexible PCBs using a custom flying probe tool. It provides a graphical interface for loading CSV files with trace coordinates, setting machine landmarks, and moving dual carriages to perform probing operations.

## Quick Start
```bash
python main.py
```

For more details see the documentation in the `docs/FlexCableAligner/` folder.

### Core Components
- [`main entry point`](main.py:1) – orchestrates WebSocket connection and UI.
- [`App class`](src/App.py:9) – Tkinter GUI handling user interaction.
- [`CSVHandler class`](src/CSVHandler.py:4) – CSV parsing and validation.
- [`CarriageController class`](src/CarriageController.py:4) – communication with the printer controller via WebSocket.
- [`AsyncWebClient`](include/AsyncWebClient.py:1) – asynchronous WebSocket client.