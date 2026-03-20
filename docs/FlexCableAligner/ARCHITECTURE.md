# Architecture

```mermaid
graph TD;
    subgraph UI[User Interface]
        App[App (Tkinter GUI)] --> CSVHandler[CSVHandler];
        App --> Controller[CarriageController];
        App --> WSClient[AsyncWebSocketClient];
    end;
    subgraph Core[Core Logic]
        CSVHandler --> Model[Data Model];
        Controller --> Validator[PositionValidator];
        Controller --> Printer[Klipper Printer (via WebSocket)];
        Validator --> Bounds[machine_bounds.json];
    end;
    WSClient --> Printer;
    Model -.-> CSVHandler;
```

## Module Overview
- **[`src/App.py`](src/App.py:9)** – Main Tkinter application handling UI, user interactions, and event bindings.
- **[`src/CSVHandler.py`](src/CSVHandler.py:4)** – Loads and validates CSV files containing trace coordinates and landmarks.
- **[`src/CarriageController.py`](src/CarriageController.py:4)** – Sends G‑code commands to the printer via the WebSocket client, manages carriage positions, handles collision avoidance logic, and integrates bounds checking.
- **[`src/PositionValidator.py`](src/PositionValidator.py:6)** – Validates move coordinates against machine bounds defined in `machine_bounds.json`; clips out-of-bounds positions with warning logs.
- **[`include/AsyncWebClient.py`](include/AsyncWebSocketClient.py:6)** – Asynchronous WebSocket client that communicates with the Klipper API, providing request/response handling and notification callbacks.
- **`main.py`** – Entry point that wires together the UI, CSV handler, controller, and WebSocket client, then starts the asyncio event loop.

The diagram shows how the UI layer interacts with the core logic and ultimately communicates with the printer hardware through the asynchronous WebSocket client. The PositionValidator provides independent bounds checking to prevent moves that exceed physical limits.