import math
import time
import tkinter as tk
from tkinter import ttk, messagebox, Canvas, Frame, Entry, Button
from collections import deque
from threading import Lock, Thread

from pynput import keyboard

try:
    import pygame
except Exception:  # pygame is optional; keyboard mode still works
    pygame = None

from .config import JogConfig
from .printer import Printer
from JoyStickController import JoyStickController
from KeyBoardController import KeyBoardController


# Simple UI constants
TABLE_COL_CNT = 2
TABLE_INDEX_COL_W = 8
TABLE_POS_COL_W = 42
TITLE_ROW_COLOR = '#e6e6e6'
SELECTED_ROW_COLOR = '#b3d9ff'

#TODO: brad says slow needs to be slower still (factor of 10?)
#TODO: invert placement of y+ and y- buttons to match vimba display
#TODO: button on gui to switch
#TODO: have another fine adjust button group for other carriage


class FlexAlignerGUI:
    def __init__(self):
        self.config = JogConfig()
        self.printer = Printer(port='COM6')
        self.connected = False
        self.fine_mode = False
        self.range_error_counter = 0

        # State
        self.positions = {'x': 0.0, 'y': 0.0, 'z': 0.0, 'a': 0.0, 'b': 0.0, 'c': 0.0}
        # Display-only current velocities (mm/min components)
        self.current_vel = {'x': 0.0, 'y': 0.0, 'z': 0.0, 'a': 0.0, 'b': 0.0, 'c': 0.0}
        self.last_update_time = time.time()
        self.running = True

        # Z/C movement is intentionally slower than planar
        self.z_speed_scale = 0.25
        # Saved positions (x,y,z,a,b,c)
        self.positions_list = []
        self.row_list = []
        self.selected_row_index = None
        self.current_row_index = 0
        self.loops_since_update = 0

        # Performance log
        self.movement_history = deque(maxlen=100)

        # Input state
        self._listener = None
        self._pos_lock = Lock()
        self._poller_thread = None

        # Controller / carriage state
        self.joystick_controller = JoyStickController(deadzone=self.config.deadzone)
        self.keyboard_controller = KeyBoardController()
        self.input_controller = self.joystick_controller if pygame else self.keyboard_controller

        self._last_button_times = {}
        self.selected_carriage = 1  # 1 -> XYZ, 2 -> ABC
        # Track last jog command to avoid resends and latency
        self._last_dir_sent = {1: (0, 0, 0), 2: (0, 0, 0)}
        self._last_feed_sent = {1: 0.0, 2: 0.0}

        # Build GUI and start input
        self._build_gui()
        self._start_keyboard_listener()
        self._update_displays()
        self._schedule_loop()
        self._start_position_poller()

    # ---------------- GUI BUILD -----------------
    def _build_gui(self):
        self.root = tk.Tk()
        self.root.title("Flex Cable Aligner Controller (Marlin USB)")
        self.root.geometry("900x700")

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

        # Input mode + controller info
        ctrl = ttk.LabelFrame(main, text="Controller", padding=10)
        ctrl.grid(row=1, column=0, sticky='ew', pady=5)
        ttk.Label(ctrl, text="Input:").grid(row=0, column=0, padx=(0, 6))
        self.input_var = tk.StringVar(value='Controller')
        self.input_combo = ttk.Combobox(ctrl, textvariable=self.input_var, values=['Keyboard', 'Controller'], state='readonly', width=12)
        self.input_combo.grid(row=0, column=1, padx=(0, 8))
        self.input_combo.bind('<<ComboboxSelected>>', self._on_input_mode_change)
        self.controller_label = ttk.Label(ctrl, text="Controller: Keyboard (pynput)")
        self.controller_label.grid(row=0, column=2, sticky='w')
        # Show current carriage selection
        self.mapping_label = ttk.Label(ctrl, text="Carriage: 1 (XYZ)")
        self.mapping_label.grid(row=1, column=0, columnspan=3, sticky='w', pady=(6, 0))

        # Saved positions
        saved = ttk.LabelFrame(main, text="Saved Positions", padding=10)
        saved.grid(row=1, column=1, sticky='ew', padx=10, pady=5)
        canvas = Canvas(saved, width=300, height=120)
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
        if self.input_controller.get_label() == "Keyboard Controller":
            self.speed_var = tk.DoubleVar(value=self.config.max_speed)
        else:
            # Map controller axis to speed on first render if available
            try:
                norm = (self.input_controller.read_speed_knob() + 1.0) / 2.0
                guess = self.config.base_speed + norm * (self.config.max_speed - self.config.base_speed)
            except Exception:
                guess = self.config.max_speed
            self.speed_var = tk.DoubleVar(value=guess)
        self.speed_scale = ttk.Scale(settings, from_=self.config.base_speed, to=self.config.max_speed, variable=self.speed_var, command=self._update_speed)
        self.speed_scale.grid(row=1, column=1, sticky='ew')
        self.speed_label = ttk.Label(settings, text=f"{self.config.max_speed:.0f} mm/min")
        self.speed_label.grid(row=1, column=2)

        # Simple step move controls (increment + 4 buttons for X/Y)
        step = ttk.LabelFrame(settings, text="Step Move", padding=8)
        step.grid(row=2, column=0, columnspan=3, sticky='ew', pady=(10, 0))
        ttk.Label(step, text="Increment (mm):").grid(row=0, column=0, padx=(0, 6), sticky='w')
        self.increment_var = tk.DoubleVar(value=1.0)
        self.increment_entry = ttk.Entry(step, textvariable=self.increment_var, width=8)
        self.increment_entry.grid(row=0, column=1, sticky='w')
        # Axis buttons laid out like arrows
        b_opts = {'width': 6}
        ttk.Button(step, text="-Y", command=lambda: self._move_step('y', -1), **b_opts).grid(row=1, column=1, pady=4)
        ttk.Button(step, text="-X", command=lambda: self._move_step('x', -1), **b_opts).grid(row=2, column=0, padx=4)
        ttk.Button(step, text="+X", command=lambda: self._move_step('x', +1), **b_opts).grid(row=2, column=2, padx=4)
        ttk.Button(step, text="+Y", command=lambda: self._move_step('y', +1), **b_opts).grid(row=3, column=1, pady=4)

        # Position / velocity displays
        pos_frame = ttk.LabelFrame(main, text="Positions", padding=10)
        pos_frame.grid(row=3, column=0, columnspan=2, sticky='ew', pady=5)
        self.pos_text = tk.Text(pos_frame, height=8, width=50)
        self.pos_text.grid(row=0, column=0)
        vel_frame = ttk.LabelFrame(main, text="Velocities", padding=10)
        vel_frame.grid(row=3, column=1, sticky='ew')
        self.vel_text = tk.Text(vel_frame, height=8, width=30)
        self.vel_text.grid(row=0, column=0)

        self.root.bind('<Escape>', lambda e: self.emergency_stop())
        self.root.bind('<space>', lambda e: self.reset_velocities())

    # -------------- Connection -----------------
    def connect(self):
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
        max_v = max(abs(v) for v in self.current_vel.values())
        interval = self.config.get_dynamic_interval(max_v)
        self.root.after(int(interval * 1000), self._loop_iteration)

    def _loop_iteration(self):
        if not self.running:
            return
        now = time.time()
        self.root.update()
        dt = now - self.last_update_time
        self.last_update_time = now

        if self.loops_since_update > 20 and self.connected:
            pos = self.printer.get_position()
            if pos is not None:
                self.positions = pos
                self._update_displays()
                self.loops_since_update = 0

        # Input handling
        self._handle_input_buttons()
        self.process_actions_queue()
        self._read_joystick_speed()
        dir_tuple, feed = self.input_controller.get_dir_and_feed()

        # map feed to speed
        feed = feed * self.config.max_speed

        # Execute continuous jog only on changes; integrate display positions
        if self.connected:
            self._execute_jog(dt, dir_tuple, feed)

        # If there is no direction, stop the jog
        if dir_tuple == (0, 0, 0) and self.printer.is_moving:
            self.printer.stop_jog(block=False)

        self.loops_since_update += 1
        self._schedule_loop()

    def _execute_jog(self, dt, dir_tuple: tuple[int, int, int], feed: float):
        # Apply global scaling once to feed
        feed = max(0.0, float(feed))
        self.printer.set_carriage(self.selected_carriage)

        # Decide if we need to send/stop
        last_dir = self._last_dir_sent[self.selected_carriage]
        last_feed = self._last_feed_sent[self.selected_carriage]
        changed_dir = dir_tuple != last_dir
        changed_feed = abs(feed - last_feed) > 50.0  # only resend if speed moved meaningfully

        if dir_tuple == (0, 0, 0) or feed < self.config.velocity_stop_threshold:
            if last_dir != (0, 0, 0):
                self.printer.stop_jog()
                self._last_dir_sent[self.selected_carriage] = (0, 0, 0)
                self._last_feed_sent[self.selected_carriage] = 0.0
            # Zero display velocities
            self._set_display_velocities(0.0, 0.0, 0.0)
            return

        # Update positions and display velocities (approximate components)
        vx, vy, vz = self._components_from_dir_and_feed(dir_tuple, feed)
        self._integrate_positions(dt, vx, vy, vz)
        self._set_display_velocities(vx, vy, vz)

        # Only command on meaningful change
        if changed_dir or changed_feed:
            # We only need the signs; Printer.jog uses sign and feed
            sx, sy, sz = (1 if d > 0 else (-1 if d < 0 else 0) for d in dir_tuple)
            self.printer.jog(sx, sy, sz, max(1.0, feed))
            self._last_dir_sent[self.selected_carriage] = dir_tuple
            self._last_feed_sent[self.selected_carriage] = feed

    def _components_from_dir_and_feed(self, dir_tuple: tuple[int, int, int], feed: float) -> tuple[float, float, float]:
        # Distribute vector speed across active axes uniformly (unit vector over active axes)
        ax = [float(d) for d in dir_tuple]
        active = [i for i, d in enumerate(ax) if d != 0.0]
        if not active or feed <= 0:
            return 0.0, 0.0, 0.0
        # unit components: each active axis gets 1/sqrt(n) with sign
        n = math.sqrt(len(active))
        comps = [0.0, 0.0, 0.0]
        for i in active:
            comps[i] = (ax[i] / n) * feed
        return comps[0], comps[1], comps[2]

    def _integrate_positions(self, dt: float, vx: float, vy: float, vz: float):
        dx = (vx / 60.0) * dt
        dy = (vy / 60.0) * dt
        dz = (vz / 60.0) * dt
        if self.selected_carriage == 1:
            self.positions['x'] += dx
            self.positions['y'] += dy
            self.positions['z'] += dz
        else:
            self.positions['a'] += dx
            self.positions['b'] += dy
            self.positions['c'] += dz

    def _set_display_velocities(self, vx: float, vy: float, vz: float):
        if self.selected_carriage == 1:
            self.current_vel['x'] = vx
            self.current_vel['y'] = vy
            self.current_vel['z'] = vz
            self.current_vel['a'] = 0.0
            self.current_vel['b'] = 0.0
            self.current_vel['c'] = 0.0
        else:
            self.current_vel['a'] = vx
            self.current_vel['b'] = vy
            self.current_vel['c'] = vz
            self.current_vel['x'] = 0.0
            self.current_vel['y'] = 0.0
            self.current_vel['z'] = 0.0

    def _recompute_target_vel_locked(self):
        # No-op kept for compatibility; keyboard direction is computed per-loop
        return


    # -------------- Controller handling --------------------
    def _handle_input_buttons(self):
        button_states = self.input_controller.get_button_states()
        # home XY
        if button_states.home_xy:
            self.printer.set_carriage(1)
            self.printer.stop_jog()
            self.printer.home_xy()
            self.positions['x'] = self.positions['y'] = 0.0

        # toggle carriage 1 <-> 2
        if button_states.toggle_carriages:
            self.selected_carriage = 2 if self.selected_carriage == 1 else 1
            if getattr(self, 'mapping_label', None):
                text = 'Carriage: 1 (XYZ)' if self.selected_carriage == 1 else 'Carriage: 2 (ABC)'
                self.mapping_label.config(text=text)
            self.reset_velocities()
            self.printer.stop_jog()

        # save position
        if button_states.save_position:
            self.positions_list.append((self.positions['x'], self.positions['y'], self.positions['z'],
                                        self.positions['a'], self.positions['b'], self.positions['c']))
            self._add_row()

        # goto selected position
        if button_states.goto_saved:
            if self.selected_row_index is not None and self.selected_row_index < len(self.positions_list):
                self.goto_saved_position()

        # Get current position
        if button_states.get_current_pos:
            pos = self.printer.get_position()
            self.positions = pos
            self._update_displays()

        # increase speed
        if button_states.speed_inc:
            self.config.max_speed = min(self.config.max_speed + 100, 20000)
            self.speed_var.set(self.config.max_speed)
            self.speed_label.config(text=f"{self.config.max_speed:.0f} mm/min")

        # decrease speed
        if button_states.speed_dec:
            self.config.max_speed = max(100, self.config.max_speed - 100)
            self.speed_var.set(self.config.max_speed)
            self.speed_label.config(text=f"{self.config.max_speed:.0f} mm/min")

        # toggle fine
        if button_states.toggle_fine:
            self.fine_mode = not self.fine_mode
            # In this simplified mode, fine toggles just clamp max speed for the slider
            self.config.max_speed = 1000 if self.fine_mode else 20000
            self.speed_var.set(self.config.max_speed)
            self.speed_label.config(text=f"{self.config.max_speed:.0f} mm/min")
            self.mode_label.config(text=f"Fine Mode: {'ON' if self.fine_mode else 'OFF'}")
            with self._keys_lock:
                self._recompute_target_vel_locked()

    # -------------- Input Mode switching ------------------
    def _on_input_mode_change(self, _event=None):
        choice = self.input_var.get().lower()
        if choice.startswith('keyboard'):
            self.input_controller = self.keyboard_controller
        else:
            self.input_controller = self.joystick_controller

    def _read_joystick_speed(self): 
        norm = self.input_controller.read_speed_knob()
        if norm is None:
            return
        new_speed = self.config.base_speed + norm * (1000 - self.config.base_speed)
        if hasattr(self, 'speed_var'):
            try:
                if abs(float(self.speed_var.get()) - new_speed) > 25.0:
                    self.speed_var.set(new_speed)
                    self._update_speed(new_speed)
            except Exception:
                pass

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
        idx = self.current_row_index
        pos = self.positions_list[idx]
        self.table.grid_slaves(row=idx + 1, column=0)[0].insert(0, idx + 1)
        self.table.grid_slaves(row=idx + 1, column=1)[0].insert(0, f"X={pos[0]:.3f}, Y={pos[1]:.3f}, Z={pos[2]:.3f}, A={pos[3]:.3f}, B={pos[4]:.3f}, C={pos[5]:.3f}")
        self.row_list.append(row_entries)
        self.current_row_index += 1
        self.canvas.configure(scrollregion=self.canvas.bbox('all'))

    def _on_click(self, _event, row_index):
        self.selected_row_index = row_index
        for entries in self.row_list:
            for e in entries:
                e.config(state='normal', background='white')
        for e in self.row_list[self.selected_row_index]:
            e.config(state='readonly', readonlybackground=SELECTED_ROW_COLOR)

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
        for _ in self.positions_list:
            self._add_row()
        self.selected_row_index = None

    def goto_saved_position(self):
        pos = self.positions_list[self.selected_row_index]
        # Carriage 1 deltas
        dx = pos[0] - self.positions['x']
        dy = pos[1] - self.positions['y']
        dz = pos[2] - self.positions['z']
        self.printer.set_carriage(1)
        self.printer.stop_jog()
        self.printer.move_relative(dx, dy, dz, feedrate=self.config.max_speed)
        self.positions['x'], self.positions['y'], self.positions['z'] = pos[0], pos[1], pos[2]
        # Carriage 2 deltas
        da = pos[3] - self.positions['a']
        db = pos[4] - self.positions['b']
        dc = pos[5] - self.positions['c']
        self.printer.set_carriage(2)
        self.printer.stop_jog()
        self.printer.move_relative(da, db, dc, feedrate=self.config.max_speed)
        self.positions['a'], self.positions['b'], self.positions['c'] = pos[3], pos[4], pos[5]

    # -------------- GUI updates -----------------
    def _update_speed(self, val):
        self.config.max_speed = float(val)
        self.speed_label.config(text=f"{self.config.max_speed:.0f} mm/min")

    def reset_velocities(self):
        # Zero display velocities
        for k in list(self.current_vel.keys()):
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
        self.pos_text.insert(tk.END, f"Z: {self.positions['z']:.3f}\n")
        self.pos_text.insert(tk.END, f"A: {self.positions['a']:.3f}\n")
        self.pos_text.insert(tk.END, f"B: {self.positions['b']:.3f}\n")
        self.pos_text.insert(tk.END, f"C: {self.positions['c']:.3f}")

        self.vel_text.delete(1.0, tk.END)
        self.vel_text.insert(tk.END, f"X: {self.current_vel['x']:.1f}\n")
        self.vel_text.insert(tk.END, f"Y: {self.current_vel['y']:.1f}\n")
        self.vel_text.insert(tk.END, f"Z: {self.current_vel.get('z', 0.0):.1f}\n")
        self.vel_text.insert(tk.END, f"A: {self.current_vel.get('a', 0.0):.1f}\n")
        self.vel_text.insert(tk.END, f"B: {self.current_vel.get('b', 0.0):.1f}\n")
        self.vel_text.insert(tk.END, f"C: {self.current_vel.get('c', 0.0):.1f}")

        self.root.after(100, self._update_displays)

    def run(self):
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        self.root.mainloop()

    def _on_close(self):
        self.running = False
        self.disconnect()
        try:
            if self._listener:
                self._listener.stop()
        except Exception:
            pass
        self.root.destroy()
        # poller thread is daemon; no need to join, but we can attempt a brief join
        try:
            if self._poller_thread and self._poller_thread.is_alive():
                self._poller_thread.join(timeout=0.2)
        except Exception:
            pass

    # ---- Background position polling (non-blocking UI) ----
    def _start_position_poller(self):
        if self._poller_thread is not None:
            return

        def _run():
            pass # not sure what this is, but here it is

        self._poller_thread = Thread(target=_run, daemon=True)
        self._poller_thread.start()    

    # --------- Step move helpers (UI buttons) ---------
    def _move_step(self, axis: str, sign: int):
        """Move the active carriage by +/-increment along X/A or Y/B based on selection."""
        try:
            inc = abs(float(self.increment_var.get()))
        except Exception:
            messagebox.showerror("Step Move", "Please enter a valid numeric increment (mm)")
            return
        if inc <= 0:
            return
        if not self.connected:
            messagebox.showwarning("Printer", "Not connected to printer")
            return

        # Ensure we're issuing a discrete move (stop any jogging first)
        try:
            if self.printer.is_moving:
                self.printer.stop_jog()
        except Exception:
            pass

        self.printer.set_carriage(self.selected_carriage)
        dx = dy = 0.0
        if axis.lower() == 'x':
            dx = float(sign) * inc
        elif axis.lower() == 'y':
            dy = float(sign) * inc
        else:
            return

        ok = self.printer.move_relative(dx=dx, dy=dy, dz=0.0, feedrate=self.config.max_speed)
        if ok:
            # Keep local display positions in sync
            if self.selected_carriage == 1:
                self.positions['x'] += dx
                self.positions['y'] += dy
            else:
                self.positions['a'] += dx
                self.positions['b'] += dy
