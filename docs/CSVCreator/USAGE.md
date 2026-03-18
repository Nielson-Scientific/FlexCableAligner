# Usage

## Launching the GUI
```bash
python main.py
```
This starts the CSVCreator graphical interface.

## Workflow
1. **Load DXF** – Click *Load DXF* and select a `.dxf` file. The drawing is displayed on the canvas.
2. **Set Origin** – Click *Set Origin*, then click a point in the canvas to define the origin (used as reference for all exported coordinates).
3. **Set Landmarks** – Use *Set Landmark 1* and *Set Landmark 2* to mark two physical points that FlexCableAligner will use to calculate machine zero.
4. **Add Point Pairs** – Click *Add Pair*, then click the first point (C1) followed by the second point (C2). Repeat for all required pairs.
5. **Export CSV** – Once all points are added, click *Save CSV* and choose a destination file. The generated CSV follows the format expected by FlexCableAligner (`Index,x1,y1,x2,y2,manual`).

## Keyboard shortcuts
- `Ctrl+Z` – Undo last pair.
- `Del` – Clear all points.
- Mouse wheel – Zoom in/out of the canvas.
