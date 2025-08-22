import math
import time
import tkinter as tk
from tkinter import ttk, messagebox, Canvas, Frame, Entry, Button
from collections import deque

import pygame

from include.config import JogConfig
from include.printer import Printer


TABLE_COL_CNT = 2
TABLE_INDEX_COL_W = 5
TABLE_POS_COL_W = 40

TITLE_ROW_COLOR = 'lightgrey'
SELECTED_ROW_COLOR = 'lightblue'


class FlexAlignerGUI:
    """GUI + joystick loop (synchronous)"""

    def __init__(self):
        self.config = JogConfig()
        self.printer = Printer()
        self.connected = False
        self.fine_mode = False

        # State
        self.positions = {'x': 0.0, 'y': 0.0, 'u': 0.0, 'v': 0.0}
        self.target_vel = {'x': 0.0, 'y': 0.0, 'u': 0.0, 'v': 0.0}
        self.current_vel = {'x': 0.0, 'y': 0.0, 'u': 0.0, 'v': 0.0}
        self.last_update_time = time.time()
        self.last_movement_time = time.time()
        self.running = True

        # Saved positions
        self.positions_list = []
        self.row_list = []
        self.selected_row_index = None
        self.current_row_index = 0

        # Performance log
        self.movement_history = deque(maxlen=100)

        # Pygame init
        pygame.init()
        pygame.joystick.init()
        self.joystick = None

        self._build_gui()

    # ---------------- GUI BUILD -----------------
    def _build_gui(self):
        self.root = tk.Tk()
        self.root.title("Flex Cable Aligner Controller")
        self.root.geometry("850x650")

        main = ttk.Frame(self.root, padding=10)
        main.grid(sticky='nsew')
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)

        # Connection frame
        conn = ttk.LabelFrame(main, text="Connection", padding=10)
        conn.grid(row=0, column=0, columnspan=3, sticky='ew')
        self.connect_btn = ttk.Button(conn, text="Connect", command=self.connect)
        self.connect_btn.grid(row=0, column=0, padx=5)
        self.disconnect_btn = ttk.Button(conn, text="Disconnect", command=self.disconnect, state=tk.DISABLED)
        self.disconnect_btn.grid(row=0, column=1, padx=5)
        self.estop_btn = ttk.Button(conn, text="EMERGENCY STOP", command=self.emergency_stop)
        self.estop_btn.grid(row=0, column=2, padx=5)
        self.status_label = ttk.Label(conn, text="Status: Disconnected", foreground='red')
        self.status_label.grid(row=1, column=0, columnspan=3, pady=5)

        # Controller info
        ctrl = ttk.LabelFrame(main, text="Controller", padding=10)
        ctrl.grid(row=1, column=0, sticky='ew', pady=5)
        self.controller_label = ttk.Label(ctrl, text="Controller: Not detected")
        self.controller_label.grid(row=0, column=0, sticky='w')

        # Saved positions
        saved = ttk.LabelFrame(main, text="Saved Positions", padding=10)
        saved.grid(row=1, column=1, sticky='ew', padx=10, pady=5)
        canvas = Canvas(saved, width=250, height=100)
        scrollbar = ttk.Scrollbar(saved, orient='vertical', command=canvas.yview)
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.grid(row=0, column=0, sticky='nsew')
        scrollbar.grid(row=0, column=1, sticky='ns')
        self.table = Frame(canvas)
        self.table.grid()
        self.canvas = canvas
        canvas.create_window((0, 0), window=self.table, anchor='nw')
        for col in range(TABLE_COL_CNT):
            e = Entry(self.table)
            e.grid(row=0, column=col)
            if col == 0:
                e.config(width=TABLE_INDEX_COL_W)
            else:
                e.config(width=TABLE_POS_COL_W)
        self.table.grid_slaves(row=0, column=0)[0].insert(0, "Index")
        self.table.grid_slaves(row=0, column=1)[0].insert(0, "Position")
        self.table.grid_slaves(row=0, column=0)[0].configure(state='readonly', readonlybackground=TITLE_ROW_COLOR)
        self.table.grid_slaves(row=0, column=1)[0].configure(state='readonly', readonlybackground=TITLE_ROW_COLOR)
        btns = Frame(saved)
        btns.grid(row=1, column=0, columnspan=2, sticky='ew', pady=5)
        Button(btns, text="Remove Selected", command=self._remove_selected_pos).grid(row=0, column=0, padx=5, sticky='ew')
        Button(btns, text="Clear All", command=self._clear_pos_list).grid(row=0, column=1, padx=5, sticky='ew')

        # Mode & Settings
        settings = ttk.LabelFrame(main, text="Mode & Settings", padding=10)
        settings.grid(row=2, column=0, columnspan=2, sticky='ew', pady=5)
        self.mode_label = ttk.Label(settings, text="Fine Mode: OFF")
        self.mode_label.grid(row=0, column=0, sticky='w')
        ttk.Label(settings, text="Max Speed:").grid(row=1, column=0, sticky='w')
        self.speed_var = tk.DoubleVar(value=self.config.max_speed)
        self.speed_scale = ttk.Scale(settings, from_=500, to=3000, variable=self.speed_var, command=self._update_speed)
        self.speed_scale.grid(row=1, column=1, sticky='ew')
        self.speed_label = ttk.Label(settings, text=f"{self.config.max_speed:.0f} mm/min")
        self.speed_label.grid(row=1, column=2)
        ttk.Label(settings, text="Scale:").grid(row=2, column=0, sticky='w')
        self.scale_var = tk.DoubleVar(value=self.config.movement_scale)
        self.scale_scale = ttk.Scale(settings, from_=0.1, to=2.0, variable=self.scale_var, command=self._update_scale)
        self.scale_scale.grid(row=2, column=1, sticky='ew')
        self.scale_label = ttk.Label(settings, text=f"{self.config.movement_scale:.2f}x")
        self.scale_label.grid(row=2, column=2)

        preset = ttk.Frame(settings)
        preset.grid(row=3, column=0, columnspan=3, pady=5)
        for val in [0.5, 0.75, 1.0, 1.25, 1.5]:
            ttk.Button(preset, text=f"{int(val*100)}%", command=lambda v=val: self._set_preset(v)).pack(side=tk.LEFT, padx=2)

        # Position / velocity displays
        pos_frame = ttk.LabelFrame(main, text="Positions", padding=10)
        pos_frame.grid(row=3, column=0, columnspan=2, sticky='ew', pady=5)
        self.pos_text = tk.Text(pos_frame, height=5, width=50)
        self.pos_text.grid(row=0, column=0)
        vel_frame = ttk.LabelFrame(main, text="Velocities", padding=10)
        vel_frame.grid(row=3, column=1, sticky='ew')
        self.vel_text = tk.Text(vel_frame, height=5, width=30)
        self.vel_text.grid(row=0, column=0)

        self.root.bind('<Escape>', lambda e: self.emergency_stop())
        self.root.bind('<space>', lambda e: self.reset_velocities())

        self._update_displays()
        self._schedule_loop()

    # -------------- Connection -----------------
    def connect(self):
        # Controller
        if pygame.joystick.get_count() == 0:
            messagebox.showerror("Controller", "No joystick detected")
            return
        self.joystick = pygame.joystick.Joystick(0)
        self.joystick.init()
        self.controller_label.config(text=f"Controller: {self.joystick.get_name()}")
        # Printer
        if not self.printer.connect():
            messagebox.showerror("Printer", f"Failed to connect: {self.printer.last_error}")
            return
        self.connected = True
        self.status_label.config(text="Status: Connected", foreground='green')
        self.connect_btn.config(state=tk.DISABLED)
        self.disconnect_btn.config(state=tk.NORMAL)

    def disconnect(self):
        if self.connected:
            self.printer.disconnect()
        self.connected = False
        self.status_label.config(text="Status: Disconnected", foreground='red')
        self.connect_btn.config(state=tk.NORMAL)
        self.disconnect_btn.config(state=tk.DISABLED)

    # -------------- Movement Loop --------------
    def _schedule_loop(self):
        # dynamic interval based on current max velocity
        max_v = max(abs(v) for v in self.current_vel.values())
        interval = self.config.get_dynamic_interval(max_v)
        self.root.after(int(interval * 1000), self._loop_iteration)

    def _loop_iteration(self):
        if not self.running:
            return
        now = time.time()
        dt = now - self.last_update_time
        self.last_update_time = now

        # Read joystick
        pygame.event.pump()
        if self.joystick:
            axes = [
                self.joystick.get_axis(0),
                -self.joystick.get_axis(1),
                self.joystick.get_axis(2),
                -self.joystick.get_axis(3),
            ]
            keys = ['x', 'y', 'u', 'v']
            for key, val in zip(keys, axes):
                self.target_vel[key] = self.config.get_velocity_curve(val, self.fine_mode)
            self._handle_buttons()

        # Smooth
        for axis in self.current_vel:
            self.current_vel[axis] = self._smooth(self.current_vel[axis], self.target_vel[axis], dt)

        # Execute relative moves
        if self.connected:
            self._execute_moves(dt)
            pos = self.printer.get_position()
            if pos is not None:
                self.positions = pos

        self._schedule_loop()

    def _smooth(self, current, target, dt):
        if abs(target) < 0.1:
            # aggressive decay
            alpha = 1.0 - math.exp(-dt / (self.config.velocity_smoothing * 0.15))
            decay = max(alpha, 0.3)
            new_v = current * (1 - decay)
        else:
            alpha = 1.0 - math.exp(-dt / self.config.velocity_smoothing)
            new_v = current + alpha * (target - current)
        if abs(new_v) < self.config.velocity_stop_threshold:
            new_v = 0.0
        return new_v

    def _execute_moves(self, dt):
        # XY
        dx = (self.current_vel['x'] / 60.0) * dt * self.config.movement_scale
        dy = (self.current_vel['y'] / 60.0) * dt * self.config.movement_scale
        if abs(dx) > self.config.min_move_threshold or abs(dy) > self.config.min_move_threshold:
            vel_mag = math.sqrt(dx*dx + dy*dy) / dt * 60 if dt > 0 else 0
            feed = max(100, min(self.config.max_speed, vel_mag))
            ok = self.printer.move_xy_with_carriage(dx, dy, feed)
            if ok:
                self.positions['x'] += dx
                self.positions['y'] += dy
                self._log_move(dx, dy, feed)
            else:
                print(self.printer.last_error)
                print('Failed to move, resetting kinematic position')
                print(self.printer.set_kinematic_position(self.positions['x'], self.positions['y'], self.positions['u'], self.positions['v']))
        # UV
        du = (self.current_vel['u'] / 60.0) * dt * self.config.movement_scale
        dv = (self.current_vel['v'] / 60.0) * dt * self.config.movement_scale
        if abs(du) > self.config.min_move_threshold or abs(dv) > self.config.min_move_threshold:
            vel_mag = math.sqrt(du*du + dv*dv) / dt * 60 if dt > 0 else 0
            feed = max(100, min(self.config.max_speed, vel_mag))
            ok = self.printer.move_uv(du, dv, feed)
            if ok:
                self.positions['u'] += du
                self.positions['v'] += dv
                self._log_move(du, dv, feed)

    def _log_move(self, dx, dy, feed):
        self.movement_history.append({'time': time.time(), 'distance': math.sqrt(dx*dx + dy*dy), 'feed': feed})

    # -------------- Buttons --------------------
    def _handle_buttons(self):
        t = time.time()
        # Button mapping similar to original (indices may vary by controller)
        # 0: toggle fine mode
        if self.joystick.get_button(0):
            if not hasattr(self, '_last_fine') or t - self._last_fine > 0.1:
                self.fine_mode = not self.fine_mode
                if self.fine_mode:
                    self.config.velocity_scale = 0.3
                    self.config.movement_scale = 0.3
                else:
                    self.config.velocity_scale = 1.5
                    self.config.movement_scale = 1.5
                self.scale_var.set(self.config.movement_scale)
                self.scale_label.config(text=f"{self.config.movement_scale:.2f}x")
                self.mode_label.config(text=f"Fine Mode: {'ON' if self.fine_mode else 'OFF'}")
                self._last_fine = t
        # 1: save position
        if self.joystick.get_button(1):
            if not hasattr(self, '_last_save') or t - self._last_save > 0.1:
                self.positions_list.append((self.positions['x'], self.positions['y'], self.positions['u'], self.positions['v']))
                self._add_row()
                self._last_save = t
        # 3: goto selected position
        if self.joystick.get_button(3) and self.selected_row_index is not None and self.selected_row_index < len(self.positions_list):
            if not hasattr(self, '_last_goto') or t - self._last_goto > 0.1:
                self.goto_saved_position()
                self._last_goto = t
        # 2: home XY
        if self.joystick.get_button(2):
            if not hasattr(self, '_last_home') or t - self._last_home > 0.2:
                self.printer.home_xy()
                self.positions['x'] = self.positions['y'] = 0.0
                self._last_home = t

        # 8: spiral search pattern for left microscope
        if self.joystick.get_button(8):
            if not hasattr(self, 'last_search_xy') or t - self.last_search_xy > 0.5:
                self.spiral_search(self.positions['x'],self.positions['y'], 8)
                self.last_search_xy = t

        # 9: Spiral search pattern for right microscope
        if self.joystick.get_button(9):
            if not hasattr(self, 'last_search_uv') or t - self.last_search_uv > 0.5:
                self.spiral_search(self.positions['u'], self.positions['v'], 9)
                self.last_search_uv = t

        # 5: Search interrupt
        if self.joystick.get_button(5):
            if not hasattr(self, 'last_stop') or t - self.last_stop > 0.5:
                self.search_interrupt()
                self.last_stop = t
# A13 541
    # -------------- Saved Positions -------------
    def _add_row(self):
        row_entries = []
        for col in range(TABLE_COL_CNT):
            e = Entry(self.table)
            if col == 0:
                e.config(width=TABLE_INDEX_COL_W)
            else:
                e.config(width=TABLE_POS_COL_W)
            e.grid(row=self.current_row_index + 1, column=col)
            e.bind('<Button-1>', lambda ev, idx=self.current_row_index: self._on_click(ev, idx))
            row_entries.append(e)
        # fill
        idx = self.current_row_index
        pos = self.positions_list[idx]
        self.table.grid_slaves(row=idx + 1, column=0)[0].insert(0, idx + 1)
        self.table.grid_slaves(row=idx + 1, column=1)[0].insert(0, f"X={pos[0]:.3f}, Y={pos[1]:.3f}, U={pos[2]:.3f}, V={pos[3]:.3f}")
        self.row_list.append(row_entries)
        self.current_row_index += 1
        self.canvas.configure(scrollregion=self.canvas.bbox('all'))

    def _on_click(self, _event, row_index):
        self.selected_row_index = row_index
        for r, entries in enumerate(self.row_list):
            for e in entries:
                if r == row_index:
                    e.config(readonlybackground=SELECTED_ROW_COLOR)
                else:
                    e.config(readonlybackground='lightblue')

    def _remove_selected_pos(self):
        if self.selected_row_index is None:
            return
        self.positions_list.pop(self.selected_row_index)
        self._rebuild_table()

    def _clear_pos_list(self):
        self.positions_list = []
        self._rebuild_table()

    def _rebuild_table(self):
        for row in self.row_list:
            for e in row:
                e.destroy()
        self.row_list = []
        self.current_row_index = 0
        for pos in self.positions_list:
            self._add_row()
        self.selected_row_index = None

    def goto_saved_position(self):
        pos = self.positions_list[self.selected_row_index]
        # Absolute like move via setting kinematics then nothing moves physically; instead we issue relative moves required
        # Simplest: set kinematic so display matches saved
        self.printer.set_kinematic_position(pos[0], pos[1], pos[2], pos[3])
        self.positions['x'], self.positions['y'], self.positions['u'], self.positions['v'] = pos

    # ------------- Spiral Search ----------------
    def spiral_search(self, x, y, button):
        """Perform search pattern smoothly"""
        self.is_searching = True
        import math

        def spiral_coords(x, y, final_radius=5, loops=5, points_per_loop=50):
            coords = []
            total_points = loops * points_per_loop
            b = final_radius / (2 * math.pi * loops)  # spiral spacing so that r = 5 mm at the end

            for i in range(total_points + 1):
                theta = 2 * math.pi * i / points_per_loop
                r = b * theta
                new_x = x + r * math.cos(theta)
                new_y = y + r * math.sin(theta)
                coords.append((new_x, new_y))

            return coords
        # def spiral_coords(x,y):
        #     spiral_factor = -3.4
        #     initial_step = 0.005
        #     total_loops = 5
        #     coords = []
        #     for loop in range(total_loops):
        #         if loop == 0:
        #             new_x = x + initial_step
        #             new_y = y + initial_step
        #             coords.append((new_x, y))
        #             coords.append((new_x, new_y))
        #             x = new_x
        #             y = new_y
        #         else:
        #             initial_step = initial_step * spiral_factor
        #             new_x = x + initial_step
        #             new_y = y * initial_step
        #             coords.append((new_x, y))
        #             coords.append((new_x, new_y))
        #             x = new_x
        #             y = new_y
        #     return coords

        self.spiral_coordinates = spiral_coords(x,y)
        if button == 8:
            for coord in self.spiral_coordinates:
                gcode = f"""G90
        SET_DUAL_CARRIAGE CARRIAGE=x
        SET_DUAL_CARRIAGE CARRIAGE=y
        G0 X{coord[0]:.3f} Y{coord[1]:.3f} F{self.config.base_speed}
        """
                
                try:
                    self.printer.send_gcode(gcode)
                    self.positions['x'] = coord[0]
                    self.positions['y'] = coord[1]
                except Exception as e:
                    print(f"Error in search: {e}")
        else:
            for coord in self.spiral_coordinates:
                gcode = f"""G90
        SET_DUAL_CARRIAGE CARRIAGE=x2
        SET_DUAL_CARRIAGE CARRIAGE=y2
        G0 X{coord[0]:.3f} Y{coord[1]:.3f} F{self.config.base_speed}
        """
                
                try:
                    self.printer.send_gcode(gcode)
                    self.positions['u'] = coord[0]
                    self.positions['v'] = coord[1]
                except Exception as e:
                    print(f"Error in search: {e}")
        self.is_searching = False

    def search_interrupt(self):
        if self.is_searching == False:
            pass
        else:
            self.reset_velocities()
            self.spiral_coordinates = []

    # -------------- GUI updates -----------------
    def _update_speed(self, val):
        self.config.max_speed = float(val)
        self.speed_label.config(text=f"{self.config.max_speed:.0f} mm/min")

    def _update_scale(self, val):
        self.config.movement_scale = float(val)
        self.config.velocity_scale = float(val)
        self.scale_label.config(text=f"{self.config.movement_scale:.2f}x")

    def _set_preset(self, v):
        self.config.movement_scale = self.config.velocity_scale = v
        self.scale_var.set(v)
        self.scale_label.config(text=f"{v:.2f}x")

    def reset_velocities(self):
        for k in self.target_vel:
            self.target_vel[k] = 0.0
            self.current_vel[k] = 0.0

    def emergency_stop(self):
        self.reset_velocities()
        if self.connected:
            self.printer.emergency_stop()
        messagebox.showwarning("Emergency Stop", "All motion halted")

    def _update_displays(self):
        self.pos_text.delete(1.0, tk.END)
        self.pos_text.insert(tk.END, f"X: {self.positions['x']:.3f}\n")
        self.pos_text.insert(tk.END, f"Y: {self.positions['y']:.3f}\n")
        self.pos_text.insert(tk.END, f"U: {self.positions['u']:.3f}\n")
        self.pos_text.insert(tk.END, f"V: {self.positions['v']:.3f}")
        self.vel_text.delete(1.0, tk.END)
        self.vel_text.insert(tk.END, f"X: {self.current_vel['x']:.1f}\n")
        self.vel_text.insert(tk.END, f"Y: {self.current_vel['y']:.1f}\n")
        self.vel_text.insert(tk.END, f"U: {self.current_vel['u']:.1f}\n")
        self.vel_text.insert(tk.END, f"V: {self.current_vel['v']:.1f}")
        self.root.after(100, self._update_displays)

    # -------------- Lifecycle -------------------
    def run(self):
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        self.root.mainloop()

    def _on_close(self):
        self.running = False
        self.disconnect()
        self.root.destroy()
