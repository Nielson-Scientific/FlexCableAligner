# Architecture

```mermaid
graph TD;
    subgraph GUI[Graphical User Interface]
        GUIClass[GUI (Tkinter)] --> ModelClass[Model];
        GUIClass --> DXFLoader[DXF Loader];
    end;
    subgraph Core[Core Logic]
        ModelClass --> ExportCSV[Export CSV];
        DXFLoader --> ParseDXF[Parse DXF];
    end;
    ParseDXF --> ModelClass;
```

## Module Overview
- **[`CSVCreator/gui.py`](CSVCreator/gui.py:8)** – Tkinter GUI handling user interaction, canvas drawing, and event callbacks.
- **[`CSVCreator/model.py`](CSVCreator/model.py:4)** – Stores origin, landmarks, point pairs; provides CSV export functionality.
- **[`CSVCreator/dxf_loader.py`](CSVCreator/dxf_loader.py:4)** – Loads DXF files using `ezdxf`, extracts line segments and points, builds a KD‑Tree for snapping.
- **`main.py`** – Entry point that creates the Tkinter root window, instantiates the model and GUI, and starts the main loop.
