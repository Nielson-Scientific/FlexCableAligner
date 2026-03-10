import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import asyncio
import logging
import math

class App(tk.Tk):
    def __init__(self, loop, csv_handler, carriage_controller, client):
        super().__init__()
        self.loop = loop
        self.csv_handler = csv_handler
        self.controller = carriage_controller
        self.client = client
        
        self.title("FlexCableAligner")
        self.geometry("1000x800")
        
        self.rows = []
        self.current_row_index = -1
        self.step_size = 1.0  # Default step size in mm
        
        # UI Setup
        self.build_ui()
        self.setup_bindings()
        
        # Start connection
        self.after(100, self.connect_to_printer)

    def build_ui(self):
        # --- Toolbar ---
        toolbar = ttk.Frame(self, padding=5)
        toolbar.pack(fill=tk.X)
        
        # URL Entry
        ttk.Label(toolbar, text="URL:").pack(side=tk.LEFT, padx=2)
        self.var_url = tk.StringVar(value="ws://10.34.243.54/websocket?token=4deca56b67664a47bb4d59e4ee628d10")
        self.ent_url = ttk.Entry(toolbar, textvariable=self.var_url, width=30)
        self.ent_url.pack(side=tk.LEFT, padx=5)
        
        self.btn_connect = ttk.Button(toolbar, text="Connect", command=self.connect_to_printer)
        self.btn_connect.pack(side=tk.LEFT, padx=5)
        
        self.btn_load = ttk.Button(toolbar, text="Load CSV", command=self.load_csv)
        self.btn_load.pack(side=tk.LEFT, padx=5)
        
        self.lbl_file = ttk.Label(toolbar, text="No file loaded")
        self.lbl_file.pack(side=tk.LEFT, padx=5)
        
        self.lbl_status = ttk.Label(toolbar, text="Disconnected", foreground="red")
        self.lbl_status.pack(side=tk.RIGHT, padx=5)

        # --- Main Content ---
        content = ttk.PanedWindow(self, orient=tk.HORIZONTAL)
        content.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        # Left Panel: Controls & Info
        left_panel = ttk.Frame(content, padding=10)
        content.add(left_panel, weight=1)
        
        # Info Box
        info_frame = ttk.LabelFrame(left_panel, text="Current Target", padding=10)
        info_frame.pack(fill=tk.X, pady=5)
        
        self.var_row_info = tk.StringVar(value="Row: --")
        # Increase visibility of row info
        ttk.Label(info_frame, textvariable=self.var_row_info, font=("Arial", 20, "bold"), foreground="blue").pack(anchor="w", pady=5)
        
        # Progress Bar
        self.progress_var = tk.DoubleVar()
        self.progress_bar = ttk.Progressbar(info_frame, variable=self.progress_var, maximum=100)
        self.progress_bar.pack(fill=tk.X, pady=5)
        
        self.var_c1_target = tk.StringVar(value="C1 (X,Y): --, --")
        ttk.Label(info_frame, textvariable=self.var_c1_target).pack(anchor="w")
        
        self.var_c2_target = tk.StringVar(value="C2 (X,Y): --, --")
        ttk.Label(info_frame, textvariable=self.var_c2_target).pack(anchor="w")

        # Step Size
        step_frame = ttk.LabelFrame(left_panel, text="Jog Step Size", padding=10)
        step_frame.pack(fill=tk.X, pady=5)
        
        self.var_step_size = tk.StringVar(value="Step: 1.0 mm")
        ttk.Label(step_frame, textvariable=self.var_step_size, font=("Arial", 14, "bold")).pack()
        ttk.Label(step_frame, text="(Press 1-9 to change)").pack()

        # Motion Controls
        motion_frame = ttk.LabelFrame(left_panel, text="Actions", padding=10)
        motion_frame.pack(fill=tk.X, pady=5)
        
        self.btn_start_move = ttk.Button(motion_frame, text="Move to Start Position", command=self.move_to_start, state=tk.DISABLED)
        self.btn_start_move.pack(fill=tk.X, pady=5)
        
        self.btn_next = ttk.Button(motion_frame, text="Done / Next Row", command=self.next_row, state=tk.DISABLED)
        self.btn_next.pack(fill=tk.X, pady=5)

        # Right Panel: Visualization
        right_panel = ttk.Frame(content, padding=10)
        content.add(right_panel, weight=3)
        
        self.canvas = tk.Canvas(right_panel, bg="white")
        self.canvas.pack(fill=tk.BOTH, expand=True)

    def setup_bindings(self):
        # Step sizes map
        self.step_map = {
            '1': 0.01, '2': 0.05, '3': 0.1, '4': 0.5, '5': 1.0,
            '6': 5.0,  '7': 10.0, '8': 50.0, '9': 100.0
        }
        
        # Bind keys
        for key in self.step_map:
            self.bind(key, self.change_step_size)
            
        # Carriage 1 (WASD)
        self.bind('w', lambda e: self.jog(1, 'Y', 1))
        self.bind('s', lambda e: self.jog(1, 'Y', -1))
        self.bind('a', lambda e: self.jog(1, 'X', -1))
        self.bind('d', lambda e: self.jog(1, 'X', 1))

        # Carriage 2 (Arrows)
        self.bind('<Up>', lambda e: self.jog(2, 'Y', 1))
        self.bind('<Down>', lambda e: self.jog(2, 'Y', -1))
        self.bind('<Left>', lambda e: self.jog(2, 'X', -1))
        self.bind('<Right>', lambda e: self.jog(2, 'X', 1))

    def change_step_size(self, event):
        val = self.step_map.get(event.char)
        if val:
            self.step_size = val
            self.var_step_size.set(f"Step: {val} mm")

    def connect_to_printer(self):
        # Update URL from entry
        new_url = self.var_url.get().strip()
        if hasattr(self.client, 'url'):
            self.client.url = new_url
            
        # Run async connect in the event loop layer
        self.lbl_status.config(text="Connecting...", foreground="orange")
        self.loop.create_task(self._async_connect())

    async def _async_connect(self):
        try:
            # Drop old connection if any
            if self.client.connected or self.client.websocket:
                await self.client.disconnect()

            # Assuming client is configured
            connected = await self.client.connect()
            if connected:
                self.lbl_status.config(text="Connected", foreground="green")
                await self.controller.initialize()
            else:
                self.lbl_status.config(text="Connection Failed", foreground="red")
        except Exception as e:
            self.lbl_status.config(text=f"Error: {e}", foreground="red")
            logging.error(f"Connection error: {e}")

    def load_csv(self):
        filename = filedialog.askopenfilename(filetypes=[("CSV Files", "*.csv")])
        if filename:
            try:
                self.rows = self.csv_handler.load_file(filename)
                self.lbl_file.config(text=filename)
                self.current_row_index = -1
                self.draw_preview()
                self.btn_next.config(state=tk.NORMAL)
                self.next_row() # Automatically start first row? Or wait? Let's just enable buttons first.
                self.btn_start_move.config(state=tk.NORMAL)
            except Exception as e:
                messagebox.showerror("Error", f"Failed to load CSV: {e}")

    def draw_preview(self):
        self.canvas.delete("all")
        if not self.rows:
            return
            
        # Find bounds for scaling
        all_x = [r['x1'] for r in self.rows] + [r['x2'] for r in self.rows]
        all_y = [r['y1'] for r in self.rows] + [r['y2'] for r in self.rows]
        min_x, max_x = min(all_x), max(all_x)
        min_y, max_y = min(all_y), max(all_y)
        
        # Add padding
        pad = 20
        width = self.canvas.winfo_width()
        height = self.canvas.winfo_height()
        
        # Avoid div by zero
        range_x = max_x - min_x if max_x != min_x else 1
        range_y = max_y - min_y if max_y != min_y else 1
        
        scale_x = (width - 2*pad) / range_x
        scale_y = (height - 2*pad) / range_y
        scale = min(scale_x, scale_y)
        
        def to_screen(x, y):
            sx = pad + (x - min_x) * scale
            sy = height - (pad + (y - min_y) * scale) # Invert Y
            return sx, sy

        for row in self.rows:
            sx1, sy1 = to_screen(row['x1'], row['y1'])
            sx2, sy2 = to_screen(row['x2'], row['y2'])
            
            # C1 points blue, C2 points red
            self.canvas.create_oval(sx1-2, sy1-2, sx1+2, sy1+2, fill="blue", outline="blue")
            self.canvas.create_oval(sx2-2, sy2-2, sx2+2, sy2+2, fill="red", outline="red")

    def next_row(self):
        if self.current_row_index < len(self.rows) - 1:
            self.current_row_index += 1
            self.update_current_row()
        else:
            messagebox.showinfo("Done", "All rows completed!")
            self.current_row_index = -1
            self.update_current_row()

    def update_current_row(self):
        if self.current_row_index >= 0 and self.current_row_index < len(self.rows):
            row = self.rows[self.current_row_index]
            self.var_row_info.set(f"Row: {self.current_row_index + 1} / {len(self.rows)}")
            
            # Progress bar update
            pct = ((self.current_row_index + 1) / len(self.rows)) * 100
            self.progress_var.set(pct)
            self.var_c1_target.set(f"C1: ({row['x1']}, {row['y1']})")
            self.var_c2_target.set(f"C2: ({row['x2']}, {row['y2']})")
            
            # Highlight on canvas
            self.canvas.delete("highlight")
            # Re-calculating transform is annoying here without persistent transform object.
            # Ideally we refactor draw_preview to save the transform or redraw everything with highlight.
            # For now, let's just reprint the preview which is fast enough.
            self.draw_preview() 
            # (Add highlight logic later if needed)
        else:
            self.var_row_info.set("Row: --")
            self.var_c1_target.set("C1: --")
            self.var_c2_target.set("C2: --")

    def move_to_start(self):
        if self.current_row_index < 0:
            return
        
        row = self.rows[self.current_row_index]
        self.loop.create_task(self._safe_move(row))

    async def _safe_move(self, row):
        try:
            await self.controller.move_to_coordinates(
                row['x1'], row['y1'], row['x2'], row['y2']
            )
        except Exception as e:
            messagebox.showerror("Movement Error", f"Failed to move: {e}")
            logging.error(f"Movement error: {e}")

    def jog(self, carriage, axis, direction):
        if self.current_row_index < 0:
            return
        
        dist = self.step_size * direction
        self.loop.create_task(self._safe_jog(carriage, axis, dist))

    async def _safe_jog(self, carriage, axis, dist):
        try:
            await self.controller.jog_axis(carriage, axis, dist)
        except Exception as e:
            # Maybe don't popup on every jog error, just log?
            logging.error(f"Jog error: {e}")
            self.lbl_status.config(text=f"Jog Error: {e}", foreground="red")

# Asyncio integration for Tkinter
async def run_tk(root, interval=0.05):
    try:
        while True:
            root.update()
            await asyncio.sleep(interval)
    except tk.TclError as e:
        if "application has been destroyed" not in str(e):
            raise
