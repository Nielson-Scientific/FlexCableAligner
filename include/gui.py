import math
import time
import tkinter as tk
from tkinter import ttk, messagebox, Canvas, Frame, Entry, Button
from collections import deque
from threading import Lock

try:
    import pygame
except Exception:  # pygame is optional; keyboard mode still works
    pygame = None
from pynput import keyboard

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

        # Keyboard input state
        self._pressed_keys = set()  # tokens like 'left', 'a', 'up'
        self._keys_lock = Lock()
        self._action_queue = deque()  # (action_name, args)
        self._listener = None

        # Search / controller state
        self.is_searching = False
        self.joystick = None
        self._last_button_times = {}
        self._fine_pressed = False
        self.input_mode = 'keyboard'  # 'keyboard' | 'controller'
        # Controller axes group selection: 'xy' or 'uv' (axes 0/1 control selected group)
        self.controller_axes_group = 'xy'

        # Key bindings (keyboard mode)
        self._axis_bindings = {
            # XY with arrows
            'left': ('x', -1),
            'right': ('x', +1),
            'down': ('y', -1),
            'up': ('y', +1),
            # UV with IJKL
            'j': ('u', -1),
            'l': ('u', +1),
            'k': ('v', -1),
            'i': ('v', +1),
        }

        self._action_bindings = {
            'f': ('toggle_fine', ()),
            'p': ('save_position', ()),
            'g': ('goto_saved', ()),
            'h': ('home_xy', ()),
            '1': ('spiral_xy', ()),
            '2': ('spiral_uv', ()),
            'c': ('search_interrupt', ()),
            '-': ('speed_dec', ()),
            '=': ('speed_inc', ()),
            '+': ('speed_inc', ()),
        }

        # Build GUI and start default input
        self._build_gui()
        self._start_keyboard_listener()
        self._update_displays()
        self._schedule_loop()

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

        # Input mode + controller info
        ctrl = ttk.LabelFrame(main, text="Controller", padding=10)
        ctrl.grid(row=1, column=0, sticky='ew', pady=5)
        ttk.Label(ctrl, text="Input:").grid(row=0, column=0, padx=(0,6))
        self.input_var = tk.StringVar(value='Keyboard')
        self.input_combo = ttk.Combobox(ctrl, textvariable=self.input_var, values=['Keyboard', 'Controller'], state='readonly', width=12)
        self.input_combo.grid(row=0, column=1, padx=(0,8))
        self.input_combo.bind('<<ComboboxSelected>>', self._on_input_mode_change)
        self.controller_label = ttk.Label(ctrl, text="Controller: Keyboard (pynput)")
        self.controller_label.grid(row=0, column=2, sticky='w')
        # Show current controller axes mapping (XY or UV)
        self.mapping_label = ttk.Label(ctrl, text="Axes: XY")
        self.mapping_label.grid(row=1, column=0, columnspan=3, sticky='w', pady=(6,0))

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
        if self.input_mode == 'keyboard':
            self.speed_var = tk.DoubleVar(value=self.config.max_speed)
        else:
            self.speed_var = tk.DoubleVar(value=((0.1 + ((self.joystick.get_axis(3) + 1.0) / 2.0)) * (40000 - 500)))
        self.speed_scale = ttk.Scale(settings, from_=500, to=40000, variable=self.speed_var, command=self._update_speed)
        self.speed_scale.grid(row=1, column=1, sticky='ew')
        self.speed_label = ttk.Label(settings, text=f"{self.config.max_speed:.0f} mm/min")
        self.speed_label.grid(row=1, column=2)
        ttk.Label(settings, text="Scale:").grid(row=2, column=0, sticky='w')
        self.scale_var = tk.DoubleVar(value=self.config.movement_scale)
        self.scale_scale = ttk.Scale(settings, from_=0.1, to=2.0, variable=self.scale_var, command=self._update_scale)
        self.scale_scale.grid(row=2, column=1, sticky='ew')
        self.scale_label = ttk.Label(settings, text=f"{self.config.movement_scale:.2f}x")
        self.scale_label.grid(row=2, column=2)

        # preset = ttk.Frame(settings)
        # preset.grid(row=3, column=0, columnspan=3, pady=5)
        # for val in [0.5, 0.75, 1.0, 1.25, 1.5]:
        #     ttk.Button(preset, text=f"{int(val*100)}%", command=lambda v=val: self._set_preset(v)).pack(side=tk.LEFT, padx=2)

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

    # -------------- Connection -----------------
    def connect(self):
        # Printer only
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

        # Input handling
        if self.input_mode == 'keyboard':
            # Process any queued actions from keyboard thread
            self._process_actions()
        else:
            # Controller mode
            self._read_joystick()
            self._handle_joystick_buttons()

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
                if self.printer.last_error.startswith("Move out of range"):
                    messagebox.showerror('Move out of range', 'Move out of range!')
                else:
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
            else:
                print(self.printer.last_error)
                if self.printer.last_error.startswith('Move out of range'):
                    messagebox.showerror('Move out of range', 'Move out of range!')
                else:
                    print('Move failed possibly due to homing issue, resetting kinematic position')
                    print(self.printer.set_kinematic_position(self.positions['x'], self.positions['y'], self.positions['u'], self.positions['v']))

    def _log_move(self, dx, dy, feed):
        self.movement_history.append({'time': time.time(), 'distance': math.sqrt(dx*dx + dy*dy), 'feed': feed})


    # -------------- Keyboard handling --------------------
    def _start_keyboard_listener(self):
        if self._listener:
            return
        self._listener = keyboard.Listener(on_press=self._on_key_press, on_release=self._on_key_release)
        self._listener.start()

    def _key_to_token(self, key) -> str | None:
        try:
            # Special keys
            if isinstance(key, keyboard.Key):
                special = {
                    keyboard.Key.left: 'left',
                    keyboard.Key.right: 'right',
                    keyboard.Key.up: 'up',
                    keyboard.Key.down: 'down',
                    keyboard.Key.space: 'space',
                    keyboard.Key.esc: 'esc',
                }
                return special.get(key)
            # Character keys
            if isinstance(key, keyboard.KeyCode):
                if key.char is None:
                    return None
                return key.char.lower()
        except Exception:
            return None
        return None

    def _on_key_press(self, key):
        token = self._key_to_token(key)
        if token is None:
            return
        first_press = False
        with self._keys_lock:
            if token not in self._pressed_keys:
                self._pressed_keys.add(token)
                first_press = True
            # Recompute target velocity for held keys
            self._recompute_target_vel_locked()
        # Queue one-shot actions only on first keydown
        if first_press and token in self._action_bindings:
            name, args = self._action_bindings[token]
            self._enqueue_action(name, *args)

    def _on_key_release(self, key):
        token = self._key_to_token(key)
        if token is None:
            return
        with self._keys_lock:
            if token in self._pressed_keys:
                self._pressed_keys.remove(token)
            self._recompute_target_vel_locked()

    def _recompute_target_vel_locked(self):
        # Build per-axis input from pressed keys
        axis_input = {"x": 0.0, "y": 0.0, "u": 0.0, "v": 0.0}
        for tok in self._pressed_keys:
            bind = self._axis_bindings.get(tok)
            if not bind:
                continue
            axis, direction = bind
            axis_input[axis] += direction
        # Clamp and translate to target velocities using the same curve
        for axis, val in axis_input.items():
            val = max(-1.0, min(1.0, val))
            self.target_vel[axis] = self.config.get_velocity_curve(val, self.fine_mode)

    def _enqueue_action(self, name: str, *args):
        with self._keys_lock:
            self._action_queue.append((name, args))

    def _process_actions(self):
        # Execute queued actions on the Tk main thread
        while True:
            with self._keys_lock:
                if not self._action_queue:
                    break
                name, args = self._action_queue.popleft()
            try:
                if name == 'toggle_fine':
                    self.fine_mode = not self.fine_mode
                    self.config.max_speed = 1000 if self.fine_mode else 3000
                    self.speed_var.set(self.config.max_speed)
                    self.speed_label.config(text=f"{self.config.max_speed:.0f} mm/min")
                    self.mode_label.config(text=f"Fine Mode: {'ON' if self.fine_mode else 'OFF'}")
                    # Recompute to apply new limits
                    with self._keys_lock:
                        self._recompute_target_vel_locked()
                elif name == 'save_position':
                    self.positions_list.append((self.positions['x'], self.positions['y'], self.positions['u'], self.positions['v']))
                    self._add_row()
                elif name == 'goto_saved':
                    if self.selected_row_index is not None and self.selected_row_index < len(self.positions_list):
                        self.goto_saved_position()
                elif name == 'home_xy':
                    self.printer.home_xy()
                    self.positions['x'] = self.positions['y'] = 0.0
                elif name == 'spiral_xy':
                    self.spiral_search(self.positions['x'], self.positions['y'], 8)
                elif name == 'spiral_uv':
                    self.spiral_search(self.positions['u'], self.positions['v'], 9)
                elif name == 'search_interrupt':
                    self.search_interrupt()
                elif name == 'speed_inc':
                    self.config.max_speed = min(self.config.max_speed + 100, 3000)
                    self.speed_var.set(self.config.max_speed)
                    self.speed_label.config(text=f"{self.config.max_speed:.0f} mm/min")
                elif name == 'speed_dec':
                    self.config.max_speed = max(100, self.config.max_speed - 100)
                    self.speed_var.set(self.config.max_speed)
                    self.speed_label.config(text=f"{self.config.max_speed:.0f} mm/min")
            except Exception as e:
                print(f"Action '{name}' failed: {e}")
            
    # -------------- Controller handling --------------------
    def _init_joystick(self) -> bool:
        if pygame is None:
            self.controller_label.config(text="Controller: pygame not available")
            return False
        try:
            pygame.init()
            pygame.joystick.init()
            if pygame.joystick.get_count() == 0:
                self.controller_label.config(text="Controller: Not detected")
                return False
            self.joystick = pygame.joystick.Joystick(0)
            self.joystick.init()
            self.controller_label.config(text=f"Controller: {self.joystick.get_name()}")
            return True
        except Exception as e:
            self.controller_label.config(text=f"Controller error: {e}")
            return False

    def _shutdown_joystick(self):
        if pygame is None:
            self.joystick = None
            return
        try:
            if self.joystick:
                try:
                    self.joystick.quit()
                except Exception:
                    pass
            pygame.joystick.quit()
            try:
                pygame.quit()
            except Exception:
                pass
        finally:
            self.joystick = None

    def _read_joystick(self):
        if pygame is None:
            return
        try:
            pygame.event.pump()
        except Exception:
            return
        if not self.joystick:
            return
        # Axes mapping: [x, y, u, v]
        # Read axes 0/1 only and map to current group (XY or UV)
        try:
            ax0 = self.joystick.get_axis(0)
            ax1 = -self.joystick.get_axis(1)
        except Exception:
            ax0 = 0.0
            ax1 = 0.0

        # Zero all targets first
        self.target_vel['x'] = 0.0
        self.target_vel['y'] = 0.0
        self.target_vel['u'] = 0.0
        self.target_vel['v'] = 0.0

        if self.controller_axes_group == 'xy':
            self.target_vel['x'] = self.config.get_velocity_curve(ax0, self.fine_mode)
            self.target_vel['y'] = self.config.get_velocity_curve(ax1, self.fine_mode)
        else:  # 'uv'
            self.target_vel['u'] = self.config.get_velocity_curve(ax0, self.fine_mode)
            self.target_vel['v'] = self.config.get_velocity_curve(ax1, self.fine_mode)
        
        # Axis 3 controls overall velocity/movement scale smoothly (controller mode only)
        try:
            ax3 = -self.joystick.get_axis(3)  # invert so pushing up increases speed
        except Exception:
            ax3 = 0.0
        # Normalize [-1..1] -> [0..1]
        norm = (ax3 + 1.0) / 2.0
        # Map to the same range as the UI scale slider [0.1 .. 2.0]
        new_speed = 0.1 + norm * (40000 - 500)
        # Reflect in UI
        if hasattr(self, 'speed_var'):
            try:
                self.speed_var.set(new_speed)
                self.speed_label.config(text=f"{self.config.max_speed:.0f} mm/min")
                self._update_speed(new_speed)
            except Exception:
                pass

    def _handle_joystick_buttons(self):
        if not self.joystick:
            return
        t = time.time()
        def debounce(key, interval):
            last = self._last_button_times.get(key, 0)
            if t - last > interval:
                self._last_button_times[key] = t
                return True
            return False

        # 0: home XY
        if self.joystick.get_button(0) and debounce('home', 0.3):
            self.printer.home_xy()
            self.positions['x'] = self.positions['y'] = 0.0

        # 1: toggle axes group XY <-> UV
        if self.joystick.get_button(1) and debounce('toggle_axes', 0.2):
            self.controller_axes_group = 'uv' if self.controller_axes_group == 'xy' else 'xy'
            # Update label
            if getattr(self, 'mapping_label', None):
                self.mapping_label.config(text=f"Axes: {self.controller_axes_group.upper()}")
            # Reset velocities when changing groups
            self.reset_velocities()

    # 2: save position
        if self.joystick.get_button(2) and debounce('save', 0.1):
            self.positions_list.append((self.positions['x'], self.positions['y'], self.positions['u'], self.positions['v']))
            self._add_row()

        # 4: goto selected position
        if self.joystick.get_button(4) and debounce('goto', 0.1):
            if self.selected_row_index is not None and self.selected_row_index < len(self.positions_list):
                self.goto_saved_position()

    # 4: goto selected position (unchanged)
    # already handled above in button 4 block

        # 8: spiral XY
        if self.joystick.get_button(8) and debounce('spiral_xy', 0.5):
            self.spiral_search(self.positions['x'], self.positions['y'], 8)

        # 9: spiral UV
        if self.joystick.get_button(9) and debounce('spiral_uv', 0.5):
            self.spiral_search(self.positions['u'], self.positions['v'], 9)

        # 5: interrupt search
        if self.joystick.get_button(5) and debounce('interrupt', 0.5):
            self.search_interrupt()

    # Axis 3 handles speed smoothly; no trigger-based speed changes

    # -------------- Input Mode switching ------------------
    def _on_input_mode_change(self, _event=None):
        choice = self.input_var.get().lower()
        if choice.startswith('keyboard'):
            self._switch_to_keyboard()
        else:
            self._switch_to_controller()

    def _switch_to_keyboard(self):
        self.input_mode = 'keyboard'
        # Stop joystick
        self._shutdown_joystick()
        # Start keyboard listener
        self._start_keyboard_listener()
        self.controller_label.config(text="Controller: Keyboard (pynput)")
        self.reset_velocities()

    def _switch_to_controller(self):
        self.input_mode = 'controller'
        # Stop keyboard listener
        try:
            if self._listener:
                self._listener.stop()
        except Exception:
            pass
        # Init joystick
        ok = self._init_joystick()
        if not ok:
            messagebox.showerror("Controller", "No joystick detected; staying in Keyboard mode")
            self.input_var.set('Keyboard')
            self.input_mode = 'keyboard'
            self._start_keyboard_listener()
        self.reset_velocities()
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
        print('Moving to position: ', pos)
        # Absolute like move via setting kinematics then nothing moves physically; instead we issue relative moves required
        # Simplest: set kinematic so display matches saved
        self.printer.goto_position(pos[0], pos[1], pos[2], pos[3])
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
        try:
            if self._listener:
                self._listener.stop()
        except Exception:
            pass
        self.root.destroy()
