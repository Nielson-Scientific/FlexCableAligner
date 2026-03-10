import tkinter as tk
from tkinter import filedialog, messagebox
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg, NavigationToolbar2Tk
from matplotlib.figure import Figure
from matplotlib.collections import LineCollection
import matplotlib.pyplot as plt

class GUI:
    def __init__(self, root, model, load_dxf_callback):
        self.root = root
        self.model = model
        self.load_dxf_callback = load_dxf_callback
        
        self.state = "IDLE" 
        self.current_pair_p1 = None
        
        self.snap_point = None
        self.mouse_pos = None

        # Optimization: Blitting variables
        self.background = None
        self.dxf_collection = None
        
        self.setup_ui()
        
    def setup_ui(self):
        self.root.title("CSVCreator - High Performance")
        
        # Toolbar
        toolbar_frame = tk.Frame(self.root)
        toolbar_frame.pack(side=tk.TOP, fill=tk.X)
        
        tk.Button(toolbar_frame, text="Load DXF", command=self.load_dxf).pack(side=tk.LEFT)
        tk.Button(toolbar_frame, text="Save CSV", command=self.save_csv).pack(side=tk.LEFT)
        tk.Button(toolbar_frame, text="Set Origin", command=self.start_set_origin).pack(side=tk.LEFT)
        tk.Button(toolbar_frame, text="Add Pair", command=self.start_add_pair).pack(side=tk.LEFT)
        tk.Button(toolbar_frame, text="Undo", command=self.undo).pack(side=tk.LEFT)
        tk.Button(toolbar_frame, text="Clear", command=self.clear).pack(side=tk.LEFT)
        
        self.status_label = tk.Label(toolbar_frame, text="Status: Idle")
        self.status_label.pack(side=tk.RIGHT, padx=10)

        # Figure
        self.fig = Figure(figsize=(8, 6), dpi=100)
        self.ax = self.fig.add_subplot(111)
        self.ax.set_aspect('equal')
        
        self.canvas = FigureCanvasTkAgg(self.fig, master=self.root)
        self.plot_widget = self.canvas.get_tk_widget()
        self.plot_widget.pack(side=tk.TOP, fill=tk.BOTH, expand=1)
        
        # Initialize dynamic artists
        self.cursor_highlight, = self.ax.plot([], [], 'ro', ms=5, animated=True, zorder=10)
        self.rubberband_line, = self.ax.plot([], [], 'b--', lw=1, animated=True, zorder=10)

        # Matplotlib toolbar
        self.mpl_toolbar = NavigationToolbar2Tk(self.canvas, self.root)
        self.mpl_toolbar.update()
        self.canvas._tkcanvas.pack(side=tk.TOP, fill=tk.BOTH, expand=1)
        
        # Events
        self.canvas.mpl_connect("motion_notify_event", self.on_mouse_move)
        self.canvas.mpl_connect("button_press_event", self.on_click)
        self.canvas.mpl_connect("draw_event", self.on_draw)

    def on_draw(self, event):
        """Called upon resize or zoom. We must invalidate the background."""
        self.background = None
        
    def load_dxf(self):
        filepath = filedialog.askopenfilename(filetypes=[("DXF Files", "*.dxf")])
        if filepath:
            try:
                self.status_label.config(text="Loading DXF...")
                self.root.update()
                
                lines, points, kdtree = self.load_dxf_callback(filepath)
                self.model.set_dxf_data(lines, points, kdtree)
                
                self.dxf_collection = LineCollection(lines, colors='k', linewidths=0.5, alpha=0.5)
                
                self.ax.clear()
                self.ax.add_collection(self.dxf_collection)
                self.ax.autoscale()
                
                self.draw_static_background()
                self.status_label.config(text="DXF Loaded")
                
            except Exception as e:
                import traceback
                traceback.print_exc()
                messagebox.showerror("Error", f"Failed to load DXF: {e}")

    def save_csv(self):
        filepath = filedialog.asksaveasfilename(defaultextension=".csv", filetypes=[("CSV Files", "*.csv")])
        if filepath:
            try:
                self.model.export_csv(filepath)
                messagebox.showinfo("Success", "CSV exported successfully")
            except ValueError as e:
                messagebox.showerror("Error", str(e))
            except Exception as e:
                messagebox.showerror("Error", f"Failed to save CSV: {e}")

    def start_set_origin(self):
        self.state = "SET_ORIGIN"
        self.status_label.config(text="Click to set Origin")
        self.draw_static_background()
        
    def start_add_pair(self):
        self.state = "ADD_PAIR_1"
        self.status_label.config(text="Click first point of pair")
        self.draw_static_background()

    def undo(self):
        self.model.undo()
        self.draw_static_background()
        
    def clear(self):
        self.model.clear()
        self.draw_static_background()

    def on_mouse_move(self, event):
        if not event.inaxes:
            return
            
        self.mouse_pos = (event.xdata, event.ydata)
        
        if self.model.dxf_kdtree:
            dist, idx = self.model.dxf_kdtree.query(self.mouse_pos)
            self.snap_point = self.model.dxf_points[idx]
        else:
            self.snap_point = None

        self.draw_dynamic_cursor()

    def on_click(self, event):
        if self.mpl_toolbar.mode != "":
            return     
        if not event.inaxes or event.button != 1:
            return

        target_point = self.snap_point if self.snap_point else (event.xdata, event.ydata)
        
        if self.state == "SET_ORIGIN":
            self.model.set_origin(target_point)
            self.state = "IDLE"
            self.status_label.config(text="Origin Set")
            self.draw_static_background()
            
        elif self.state == "ADD_PAIR_1":
            self.current_pair_p1 = target_point
            self.state = "ADD_PAIR_2"
            self.status_label.config(text="Click second point")
            self.draw_static_background()
            
        elif self.state == "ADD_PAIR_2":
            self.model.add_pair(self.current_pair_p1, target_point)
            self.current_pair_p1 = None
            self.state = "ADD_PAIR_1"
            self.status_label.config(text="Pair added. Click first point of next pair")
            self.draw_static_background()

    def draw_static_background(self):
        """Draws non-animated elements and saves the buffer."""
        self.ax.clear()
        
        if self.dxf_collection:
            self.ax.add_collection(self.dxf_collection)
        
        if self.model.origin:
             self.ax.plot(self.model.origin[0], self.model.origin[1], 'g+', ms=15, mew=2)
             
        for p1, p2 in self.model.current_pairs:
            self.ax.plot([p1[0], p2[0]], [p1[1], p2[1]], 'b-', lw=1.5)
            
        self.cursor_highlight, = self.ax.plot([], [], 'ro', ms=5, animated=True, zorder=10)
        self.rubberband_line, = self.ax.plot([], [], 'b--', lw=1, animated=True, zorder=10)
        
        self.canvas.draw()
        
        self.background = self.canvas.copy_from_bbox(self.ax.bbox)
        
        self.draw_dynamic_cursor()

    def draw_dynamic_cursor(self):
        """Fast redraw of cursor only."""
        if self.background is None:
            self.draw_static_background()
            return

        self.canvas.restore_region(self.background)
        
        target = self.snap_point if self.snap_point is not None else self.mouse_pos
        
        if target is not None:
            self.cursor_highlight.set_data([target[0]], [target[1]])
            self.ax.draw_artist(self.cursor_highlight)

            if self.state == "ADD_PAIR_2" and self.current_pair_p1 is not None:
                self.rubberband_line.set_data(
                    [self.current_pair_p1[0], target[0]], 
                    [self.current_pair_p1[1], target[1]]
                )
                self.ax.draw_artist(self.rubberband_line)
            
        self.canvas.blit(self.ax.bbox)