import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import asyncio
import logging
import math
import json
import os

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
        
        # Load Config
        self.config = self.load_config()
        self.step_size = self.config.get("default_step_size", 1.0)
        self.jog_speed = self.config.get("default_feed_rate", 3000.0)
        
        # Origin state
        self.origin = {'x': 0.0, 'y': 0.0}
        self.is_origin_set = False

        # UI Setup
        self.build_ui()
        self.setup_bindings()
        
        # Start connection
        self.after(100, self.connect_to_printer)

    def load_config(self):
        try:
            with open("config.json", "r") as f:
                return json.load(f)
        except Exception as e:
            logging.error(f"Failed to load config: {e}")
            return {
                "collision_distance": 25.0,
                "default_feed_rate": 3000.0,
                "park_position": {"x": 200.0, "y": 0.0},
                "default_step_size": 1.0
            }

    def build_ui(self):
        # --- Toolbar ---
        toolbar = ttk.Frame(self, padding=5)
        toolbar.pack(fill=tk.X)
        
        # URL Entry
        ttk.Label(toolbar, text="URL:").pack(side=tk.LEFT, padx=2)
        default_url = self.config.get("url", "ws://10.34.243.54/websocket?token=4deca56b67664a47bb4d59e4ee628d10")
        self.var_url = tk.StringVar(value=default_url)
        self.ent_url = ttk.Entry(toolbar, textvariable=self.var_url, width=30)
        self.ent_url.pack(side=tk.LEFT, padx=5)
        
        self.btn_connect = ttk.Button(toolbar, text="Connect", command=self.connect_to_printer)
        self.btn_connect.pack(side=tk.LEFT, padx=5)
        
        # Origin Button
        self.btn_origin = ttk.Button(toolbar, text="Set Origin", command=self.set_origin, state=tk.DISABLED)
        self.btn_origin.pack(side=tk.LEFT, padx=5)

        self.btn_load = ttk.Button(toolbar, text="Load CSV", command=self.load_csv, state=tk.DISABLED)
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

        # Speed Control
        speed_frame = ttk.LabelFrame(left_panel, text="Jog Speed", padding=10)
        speed_frame.pack(fill=tk.X, pady=5)
        
        self.var_speed = tk.StringVar(value=f"{int(self.jog_speed)} mm/min")
        ttk.Label(speed_frame, textvariable=self.var_speed).pack(anchor="w")
        
        self.scale_speed = ttk.Scale(speed_frame, from_=500, to=15000, orient=tk.HORIZONTAL, command=self.update_speed)
        self.scale_speed.set(self.jog_speed)
        self.scale_speed.pack(fill=tk.X, pady=5)

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
        # Only allowed if origin NOT set, OR (Origin set AND rows loaded)
        # But wait, logic in jog() handles the state check.
        # But user requested "carriage 1 only has keyboard control enabled from the start"
        # So Carriage 2 should be disabled initially?
        
        self.bind('<Up>', lambda e: self.jog(2, 'Y', 1))
        self.bind('<Down>', lambda e: self.jog(2, 'Y', -1))
        self.bind('<Left>', lambda e: self.jog(2, 'X', -1))
        self.bind('<Right>', lambda e: self.jog(2, 'X', 1))

    def change_step_size(self, event):
        val = self.step_map.get(event.char)
        if val:
            self.step_size = val
            self.var_step_size.set(f"Step: {val} mm")

    def update_speed(self, val):
        self.jog_speed = float(val)
        self.var_speed.set(f"{int(self.jog_speed)} mm/min")

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
                self.btn_origin.config(state=tk.NORMAL)
                
                # Show Homing Dialog
                homing_win = tk.Toplevel(self)
                homing_win.title("Homing...")
                homing_win.geometry("300x100")
                # Center window
                x = self.winfo_x() + (self.winfo_width() // 2) - 150
                y = self.winfo_y() + (self.winfo_height() // 2) - 50
                homing_win.geometry(f"+{x}+{y}")
                homing_win.transient(self)
                homing_win.grab_set()
                ttk.Label(homing_win, text="Homing Axes, please wait...", font=("Arial", 12)).pack(expand=True)
                self.update()
                
                await self.controller.initialize()
                
                homing_win.destroy()
            else:
                self.lbl_status.config(text="Connection Failed", foreground="red")
        except Exception as e:
            self.lbl_status.config(text=f"Error: {e}", foreground="red")
            logging.error(f"Connection error: {e}")

    def set_origin(self):
        # We assume initialized and current position is valid
        # We want to use Carriage 1 (X, Y) as origin.
        x1 = self.controller.positions.get('x1', 0.0)
        y1 = self.controller.positions.get('y1', 0.0)
        
        self.origin = {'x': x1, 'y': y1}
        self.is_origin_set = True
        
        # Disable manual jogging until CSV is loaded
        messagebox.showinfo("Origin Set", f"Origin set to ({x1}, {y1}).\nManual jogging disabled until CSV is loaded.")
        self.btn_load.config(state=tk.NORMAL)

    def load_csv(self):
        if not self.is_origin_set:
            messagebox.showwarning("Origin Required", "Please set the origin before loading a CSV.")
            return

        filename = filedialog.askopenfilename(filetypes=[("CSV Files", "*.csv")])

        if filename:
            try:
                self.rows = self.csv_handler.load_file(filename)
                self.lbl_file.config(text=filename)
                self.current_row_index = -1
                self.draw_preview()
                self.btn_next.config(state=tk.NORMAL)
                
                # Re-enable controls
                self.btn_start_move.config(state=tk.NORMAL)
                
                # Auto-select next row?
                self.next_row() 
                
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
            # Apply origin offset
            ox = self.origin.get('x', 0.0)
            oy = self.origin.get('y', 0.0)
            
            x1 = float(row['x1']) + ox
            y1 = float(row['y1']) + oy
            x2 = float(row['x2']) + ox
            y2 = float(row['y2']) + oy

            # Check for collision
            dist = math.sqrt((x1 - x2)**2 + (y1 - y2)**2)
            collision_threshold = float(self.config.get("collision_distance", 25.0))
            
            if dist < collision_threshold:
                # Collision likely!
                logging.warning(f"Collision detected (dist={dist:.2f} < {collision_threshold}). Park C2 and use single C1.")
                await self.handle_collision_move(x1, y1, x2, y2)
            else:
                await self.controller.move_to_coordinates(x1, y1, x2, y2, speed=self.jog_speed)
        except Exception as e:
            messagebox.showerror("Movement Error", f"Failed to move: {e}")
            logging.error(f"Movement error: {e}")

    async def handle_collision_move(self, x1, y1, x2, y2):
        # Park C2
        try:
            park_cfg = self.config.get("park_position", {"x": 200.0, "y": 0.0})
            # Ensure safe parking
            await self.controller.move_carriage(2, park_cfg['x'], park_cfg['y'], speed=self.jog_speed)
            
            # Show Dialog
            self.show_collision_dialog(x1, y1, x2, y2)
            
        except Exception as e:
            messagebox.showerror("Collision Handling Error", f"Failed to park/init collision mode: {e}")

    def show_collision_dialog(self, x1, y1, x2, y2):
        dialog = tk.Toplevel(self)
        dialog.title("Collision Avoidance Mode")
        dialog.geometry("400x350")
        
        # Center window
        cx = self.winfo_x() + (self.winfo_width() // 2) - 200
        cy = self.winfo_y() + (self.winfo_height() // 2) - 175
        dialog.geometry(f"+{cx}+{cy}")
        
        dialog.transient(self)
        dialog.grab_set()
        
        ttk.Label(dialog, text="⚠ Target points are too close!", font=("Arial", 14, "bold"), foreground="red").pack(pady=15)
        ttk.Label(dialog, text="Carriage 2 has been parked to avoid collision.", font=("Arial", 10)).pack()
        
        content = ttk.Frame(dialog, padding=20)
        content.pack(fill=tk.BOTH, expand=True)

        ttk.Label(content, text="Use buttons below to move Carriage 1:", font=("Arial", 10, "bold")).pack(pady=5)
        
        btn_frame = ttk.Frame(content)
        btn_frame.pack(pady=10)
        
        def move_c1_target(tx, ty):
            self.loop.create_task(self.controller.move_carriage(1, tx, ty, speed=self.jog_speed))
            
        ttk.Button(btn_frame, text="Move to Point A", command=lambda: move_c1_target(x1, y1)).pack(side=tk.LEFT, padx=10)
        ttk.Button(btn_frame, text="Move to Point B", command=lambda: move_c1_target(x2, y2)).pack(side=tk.LEFT, padx=10)
        
        ttk.Separator(content, orient='horizontal').pack(fill='x', pady=15)

        ttk.Label(content, text="Manual Controls:", font=("Arial", 10, "bold")).pack(pady=5)
        ttk.Label(content, text="Use W/A/S/D keys to jog Carriage 1", font=("Arial", 10)).pack()
        
        def on_close():
            dialog.destroy()
            
        ttk.Button(dialog, text="Done / Close", command=on_close).pack(side=tk.BOTTOM, pady=20)
        
        # Bind keys to dialog to pass through to main app jog
        dialog.bind('<Key-w>', lambda e: self.jog(1, 'Y', 1))
        dialog.bind('<Key-s>', lambda e: self.jog(1, 'Y', -1))
        dialog.bind('<Key-a>', lambda e: self.jog(1, 'X', -1))
        dialog.bind('<Key-d>', lambda e: self.jog(1, 'X', 1))
        dialog.bind('<Up>', lambda e: self.jog(1, 'Y', 1))     # Allow arrows for C1 too in this mode? Maybe cleaner
        dialog.bind('<Down>', lambda e: self.jog(1, 'Y', -1))
        dialog.bind('<Left>', lambda e: self.jog(1, 'X', -1))
        dialog.bind('<Right>', lambda e: self.jog(1, 'X', 1))
        
        dialog.focus_set()

    def jog(self, carriage, axis, direction):
        # State Logic:
        # 1. Start: Origin Not Set. 
        #    - Carriage 1 MUST stick to user request "carriage 1 only has keyboard".
        #    - Carriage 2 should be disabled?
        # 2. Origin Set, No CSV.
        #    - "disable keyboard input"
        # 3. CSV Loaded.
        #    - "keyboard control should proceed as normal"
        
        if not self.is_origin_set:
            # Phase 1: Only Carriage 1 allowed
            if carriage == 2:
                logging.warning("Carriage 2 disabled before Origin is set.")
                return 
        elif not self.rows:
             # Phase 2: Origin set, no CSV. All disabled.
             return
        
        dist = self.step_size * direction
        self.loop.create_task(self._safe_jog(carriage, axis, dist))

    async def _safe_jog(self, carriage, axis, dist):
        try:
            await self.controller.jog_axis(carriage, axis, dist, speed=self.jog_speed)
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
