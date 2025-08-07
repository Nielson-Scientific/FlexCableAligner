import pygame
import time
import asyncio
import tkinter as tk
from tkinter import ttk, messagebox
import math
from collections import deque
import numpy as np
import threading
from include.AsyncWebClient import AsyncWebSocketClient
from include.SmoothJoggingConfig import SmoothJoggingConfig

class AsyncSmoothJoystickController:
    def __init__(self):
        self.config = SmoothJoggingConfig()
        self.fine_mode = False
        self.positions = {'x': 0.0, 'y': 0.0, 'u': 0.0, 'v': 0.0, 'saved': []}
        
        # Velocity tracking for smoothing
        self.target_velocities = {'x': 0.0, 'y': 0.0, 'u': 0.0, 'v': 0.0}
        self.current_velocities = {'x': 0.0, 'y': 0.0, 'u': 0.0, 'v': 0.0}
        self.last_movement_time = time.time()
        
        # Performance tracking
        self.movement_history = deque(maxlen=100)
        self.command_queue = deque()
        
        # Connection management
        self.websocket_client = AsyncWebSocketClient("ws://products.local:7125/websocket")
        self.joystick = None
        self.running = False
        self.connected = False
        self.last_disconnect_time = 0
        self.connection_timeout = 3.0
        
        # Carriage tracking for position updates
        self.current_carriage = None  # Track which carriage is currently active
        self.pending_position_request = None  # Track which carriage we're expecting position for
        
        # Async event loop management
        self.loop = None
        self.loop_thread = None

        # Initialize pygame
        pygame.init()
        pygame.joystick.init()
        
        # Create GUI
        self.setup_gui()
        
        # Setup message handlers
        self.websocket_client.add_message_handler(self.handle_printer_message)
        
    def handle_printer_message(self, message):
        """Handle incoming printer messages/notifications"""
        try:
            # Handle position updates from M114 responses
            if message.get('method') == 'notify_gcode_response':
                response_text = message.get('params', [''])[0]
                if 'X:' in response_text and 'Y:' in response_text:
                    self.parse_position_response(response_text)
        except Exception as e:
            print(f"Error handling printer message: {e}")
    
    def parse_position_response(self, response_text):
        """Parse position from M114 response based on currently active carriage"""
        try:
            # Example: "X:100.000 Y:200.000 Z:0.000 E:0.000"
            parts = response_text.split()
            x_pos = None
            y_pos = None
            
            for part in parts:
                if ':' in part:
                    axis, value = part.split(':', 1)
                    if axis == 'X':
                        x_pos = float(value)
                    elif axis == 'Y':
                        y_pos = float(value)
            
            # Map positions based on which carriage we were expecting a response from
            if self.pending_position_request == 'xy' and x_pos is not None and y_pos is not None:
                self.positions['x'] = x_pos
                self.positions['y'] = y_pos
                # print(f"Updated XY carriage position: X={x_pos:.3f}, Y={y_pos:.3f}")
            elif self.pending_position_request == 'uv' and x_pos is not None and y_pos is not None:
                # For the UV carriage (x2/y2), the M114 response still shows as X/Y
                # but we map them to our U/V coordinates
                self.positions['u'] = x_pos
                self.positions['v'] = y_pos
                # print(f"Updated UV carriage position: U={x_pos:.3f}, V={y_pos:.3f}")
            
            # Clear the pending request
            self.pending_position_request = None
                        
        except Exception as e:
            print(f"Error parsing position response: {e}")
    
    def setup_gui(self):
        self.root = tk.Tk()
        self.root.title("Async Smooth Joystick Controller")
        self.root.geometry("900x700")
        
        # Main frame
        main_frame = ttk.Frame(self.root, padding="10")
        main_frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        
        # Connection section
        connection_frame = ttk.LabelFrame(main_frame, text="Connection", padding="10")
        connection_frame.grid(row=0, column=0, columnspan=3, sticky=(tk.W, tk.E), pady=5)
        
        self.connect_btn = ttk.Button(connection_frame, text="Connect", command=self.connect)
        self.connect_btn.grid(row=0, column=0, padx=5)
        
        self.disconnect_btn = ttk.Button(connection_frame, text="Disconnect", command=self.disconnect, state=tk.DISABLED)
        self.disconnect_btn.grid(row=0, column=1, padx=5)
        
        self.calibrate_btn = ttk.Button(connection_frame, text="Auto-Calibrate", command=self.auto_calibrate, state=tk.DISABLED)
        self.calibrate_btn.grid(row=0, column=2, padx=5)
        
        self.reconnect_btn = ttk.Button(connection_frame, text="Reconnect", command=self.manual_reconnect, state=tk.DISABLED)
        self.reconnect_btn.grid(row=0, column=3, padx=5)
        
        self.estop_btn = ttk.Button(connection_frame, text="EMERGENCY STOP", command=self.emergency_stop)
        self.estop_btn.grid(row=0, column=4, padx=5)
        
        self.status_label = ttk.Label(connection_frame, text="Status: Disconnected", foreground="red")
        self.status_label.grid(row=1, column=0, columnspan=5, pady=5)
        
        # Controller info section
        controller_frame = ttk.LabelFrame(main_frame, text="Controller Info", padding="10")
        controller_frame.grid(row=1, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=5)
        
        self.controller_label = ttk.Label(controller_frame, text="Controller: Not detected")
        self.controller_label.grid(row=0, column=0, sticky=tk.W)

        # Saved Positions section
        saved_positions_frame = ttk.LabelFrame(main_frame, text="Saved Positions", padding="10")
        saved_positions_frame.grid(row=1, column=2, sticky=(tk.W, tk.E, tk.N), pady=5, padx=(10, 0))
        self.saved_positions_text = tk.Text(saved_positions_frame, height=3, width=30)
        self.saved_positions_text.grid(row=0, column=0, sticky=(tk.W, tk.E))
        
        # Performance section
        perf_frame = ttk.LabelFrame(main_frame, text="Performance Metrics", padding="10")
        perf_frame.grid(row=2, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=5)
        
        self.perf_text = tk.Text(perf_frame, height=4, width=50)
        self.perf_text.grid(row=0, column=0, sticky=(tk.W, tk.E))

        # Velocity section
        velocity_frame = ttk.LabelFrame(main_frame, text="Current Velocities", padding="10")
        velocity_frame.grid(row=2, column=2, sticky=(tk.W, tk.E, tk.N), pady=5, padx=(10, 0))
        
        self.velocity_text = tk.Text(velocity_frame, height=4, width=30)
        self.velocity_text.grid(row=0, column=0, sticky=(tk.W, tk.E))
        
        # Mode section
        mode_frame = ttk.LabelFrame(main_frame, text="Mode & Settings", padding="10")
        mode_frame.grid(row=3, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=5)
        
        self.mode_label = ttk.Label(mode_frame, text="Fine Mode: OFF")
        self.mode_label.grid(row=0, column=0, sticky=tk.W)
        
        # Speed adjustment
        ttk.Label(mode_frame, text="Max Speed:").grid(row=1, column=0, sticky=tk.W)
        self.speed_var = tk.DoubleVar(value=self.config.max_speed)
        self.speed_scale = ttk.Scale(mode_frame, from_=500, to=3000, variable=self.speed_var, 
                                   command=self.update_speed_config)
        self.speed_scale.grid(row=1, column=1, sticky=(tk.W, tk.E))
        self.speed_label = ttk.Label(mode_frame, text=f"{self.config.max_speed:.0f} mm/min")
        self.speed_label.grid(row=1, column=2)
        
        # Movement scaling controls
        ttk.Label(mode_frame, text="XY Scale:").grid(row=2, column=0, sticky=tk.W)
        self.xy_scale_var = tk.DoubleVar(value=self.config.movement_scale_xy)
        self.xy_scale_scale = ttk.Scale(mode_frame, from_=0.1, to=2.0, variable=self.xy_scale_var,
                                      command=self.update_xy_scale)
        self.xy_scale_scale.grid(row=2, column=1, sticky=(tk.W, tk.E))
        self.xy_scale_label = ttk.Label(mode_frame, text=f"{self.config.movement_scale_xy:.2f}x")
        self.xy_scale_label.grid(row=2, column=2)
        
        ttk.Label(mode_frame, text="UV Scale:").grid(row=3, column=0, sticky=tk.W)
        self.uv_scale_var = tk.DoubleVar(value=self.config.movement_scale_uv)
        self.uv_scale_scale = ttk.Scale(mode_frame, from_=0.1, to=2.0, variable=self.uv_scale_var,
                                      command=self.update_uv_scale)
        self.uv_scale_scale.grid(row=3, column=1, sticky=(tk.W, tk.E))
        self.uv_scale_label = ttk.Label(mode_frame, text=f"{self.config.movement_scale_uv:.2f}x")
        self.uv_scale_label.grid(row=3, column=2)
        
        ttk.Label(mode_frame, text="Overall Scale:").grid(row=4, column=0, sticky=tk.W)
        self.overall_scale_var = tk.DoubleVar(value=self.config.velocity_scale)
        self.overall_scale_scale = ttk.Scale(mode_frame, from_=0.1, to=2.0, variable=self.overall_scale_var,
                                           command=self.update_overall_scale)
        self.overall_scale_scale.grid(row=4, column=1, sticky=(tk.W, tk.E))
        self.overall_scale_label = ttk.Label(mode_frame, text=f"{self.config.velocity_scale:.2f}x")
        self.overall_scale_label.grid(row=4, column=2)
        
        # Preset scaling buttons
        preset_frame = ttk.Frame(mode_frame)
        preset_frame.grid(row=5, column=0, columnspan=3, pady=5)
        
        ttk.Button(preset_frame, text="50%", command=lambda: self.set_preset_scale(0.5)).pack(side=tk.LEFT, padx=2)
        ttk.Button(preset_frame, text="75%", command=lambda: self.set_preset_scale(0.75)).pack(side=tk.LEFT, padx=2)
        ttk.Button(preset_frame, text="100%", command=lambda: self.set_preset_scale(1.0)).pack(side=tk.LEFT, padx=2)
        ttk.Button(preset_frame, text="125%", command=lambda: self.set_preset_scale(1.25)).pack(side=tk.LEFT, padx=2)
        ttk.Button(preset_frame, text="150%", command=lambda: self.set_preset_scale(1.5)).pack(side=tk.LEFT, padx=2)
        
        # Position section
        position_frame = ttk.LabelFrame(main_frame, text="Positions", padding="10")
        position_frame.grid(row=4, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=5)
        
        self.position_text = tk.Text(position_frame, height=4, width=50)
        self.position_text.grid(row=0, column=0, sticky=(tk.W, tk.E))
        
        # Configure grid weights
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)
        main_frame.columnconfigure(0, weight=2)
        main_frame.columnconfigure(1, weight=1)
        main_frame.columnconfigure(2, weight=1)
        
        # Bind keyboard shortcuts
        self.root.bind('<Escape>', lambda e: self.emergency_stop())
        self.root.bind('<space>', lambda e: self.reset_velocities())
        self.root.focus_set()
        
        self.update_displays()
    
    def run_async_function(self, coro):
        """Run an async function from the GUI thread"""
        if self.loop and not self.loop.is_closed():
            future = asyncio.run_coroutine_threadsafe(coro, self.loop)
            return future
        return None
    
    def start_event_loop(self):
        """Start the asyncio event loop in a separate thread"""
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)
        
        try:
            self.loop.run_forever()
        except Exception as e:
            print(f"Event loop error: {e}")
        finally:
            self.loop.close()
    
    def check_controller(self):
        """Check if a controller is connected"""
        try:
            if pygame.joystick.get_count() == 0:
                return False, "No controller detected"
            
            self.joystick = pygame.joystick.Joystick(0)
            self.joystick.init()
            controller_name = self.joystick.get_name()
            return True, f"Controller: {controller_name}"
        except Exception as e:
            return False, f"Controller error: {str(e)}"

    def connect(self):
        """Connect to both controller and WebSocket"""
        # Check controller first
        controller_ok, controller_msg = self.check_controller()
        self.controller_label.config(text=controller_msg)
        
        if not controller_ok:
            messagebox.showerror("Controller Error", controller_msg)
            return
        
        # Start event loop if not running
        if not self.loop_thread or not self.loop_thread.is_alive():
            self.loop_thread = threading.Thread(target=self.start_event_loop, daemon=True)
            self.loop_thread.start()
            time.sleep(0.1)  # Give loop time to start
        
        # Connect to WebSocket
        def connect_async():
            async def _connect():
                try:
                    self.status_label.config(text="Status: Connecting...", foreground="orange")
                    
                    success = await self.websocket_client.connect()
                    if success:
                        self.connected = True
                        self.root.after(0, lambda: self.status_label.config(text="Status: Connected", foreground="green"))
                        self.root.after(0, lambda: self.connect_btn.config(state=tk.DISABLED))
                        self.root.after(0, lambda: self.disconnect_btn.config(state=tk.NORMAL))
                        self.root.after(0, lambda: self.calibrate_btn.config(state=tk.NORMAL))
                        self.root.after(0, lambda: self.reconnect_btn.config(state=tk.NORMAL))
                        
                        # Initialize printer settings
                        await self.initialize_printer()
                        
                        # Start jogging loop and position update task
                        self.running = True
                        asyncio.create_task(self.smooth_jog_loop())
                        asyncio.create_task(self.periodic_position_update())
                        
                        self.root.after(0, lambda: messagebox.showinfo("Success", 
                            "Connected to printer!\nRun auto-calibration for optimal performance."))
                    else:
                        self.root.after(0, lambda: self.status_label.config(text="Status: Connection Failed", foreground="red"))
                        self.root.after(0, lambda: messagebox.showerror("Connection Error", 
                            "Failed to connect to printer WebSocket"))
                        
                except Exception as e:
                    self.root.after(0, lambda: self.status_label.config(text="Status: Connection Failed", foreground="red"))
                    self.root.after(0, lambda: messagebox.showerror("Connection Error", 
                        f"Failed to connect to printer: {str(e)}"))
            
            return _connect()
        
        self.run_async_function(connect_async())

    async def initialize_printer(self):
        """Initialize printer with proper settings"""
        try:
            # Set relative positioning
            await self.websocket_client.send_gcode("G91")
            
            # Get initial positions for both carriages
            await self.update_printer_positions()
            
        except Exception as e:
            print(f"Error initializing printer: {e}")
    
    async def periodic_position_update(self):
        """Periodically update actual positions from printer (every 5 seconds during idle)"""
        last_update = time.time()
        
        while self.running and self.connected:
            try:
                current_time = time.time()
                
                # Only update positions if we haven't moved recently (idle for 2+ seconds)
                # and it's been 5+ seconds since last update
                max_velocity = max(abs(v) for v in self.current_velocities.values())
                time_since_movement = current_time - self.last_movement_time
                time_since_update = current_time - last_update
                
                if (max_velocity < self.config.velocity_stop_threshold and 
                    time_since_movement > 2.0 and 
                    time_since_update > 5.0):
                    
                    print("Updating positions from printer...")
                    await self.update_printer_positions()
                    last_update = current_time
                
                await asyncio.sleep(1.0)  # Check every second
                
            except Exception as e:
                print(f"Error in periodic position update: {e}")
                await asyncio.sleep(5.0)  # Wait longer on error
    
    async def update_printer_positions(self):
        """Update positions from printer using proper sequential carriage selection"""
        try:
            # Get XY carriage position (carriage 1)
            self.pending_position_request = 'xy'
            response1 = await self.websocket_client.send_gcode_and_wait(
                "SET_DUAL_CARRIAGE CARRIAGE=x\nSET_DUAL_CARRIAGE CARRIAGE=y\nM114", 
                timeout=3.0
            )
            print(f"XY carriage response: {response1}")
            
            # Small delay to ensure carriage switching is complete
            await asyncio.sleep(0.1)
            
            # Get UV carriage position (carriage 2 - x2/y2)
            self.pending_position_request = 'uv' 
            response2 = await self.websocket_client.send_gcode_and_wait(
                "SET_DUAL_CARRIAGE CARRIAGE=x2\nSET_DUAL_CARRIAGE CARRIAGE=y2\nM114", 
                timeout=3.0
            )
            print(f"UV carriage response: {response2}")
                
        except Exception as e:
            print(f"Error updating positions: {e}")
            self.pending_position_request = None

    def disconnect(self):
        """Disconnect from WebSocket and stop jogging"""
        self.running = False
        self.connected = False
        self.last_disconnect_time = time.time()
        
        # Immediately stop all movement
        self.reset_velocities()
        
        # Disconnect WebSocket
        if self.loop and not self.loop.is_closed():
            asyncio.run_coroutine_threadsafe(self.websocket_client.disconnect(), self.loop)
        
        self.status_label.config(text="Status: Disconnected", foreground="red")
        self.connect_btn.config(state=tk.NORMAL)
        self.disconnect_btn.config(state=tk.DISABLED)
        self.calibrate_btn.config(state=tk.DISABLED)
        self.reconnect_btn.config(state=tk.DISABLED)

    def auto_calibrate(self):
        """Run auto-calibration routine"""
        if not self.connected:
            messagebox.showerror("Error", "Must be connected to calibrate")
            return
            
        self.calibrate_btn.config(state=tk.DISABLED, text="Calibrating...")
        
        def calibrate_callback():
            async def _calibrate():
                try:
                    await self.config.auto_calibrate_network(self.websocket_client)
                    self.root.after(0, lambda: self.calibrate_btn.config(state=tk.NORMAL, text="Auto-Calibrate"))
                    self.root.after(0, lambda: messagebox.showinfo("Calibration", "Auto-calibration complete!"))
                except Exception as e:
                    self.root.after(0, lambda: messagebox.showerror("Calibration Error", str(e)))
                    self.root.after(0, lambda: self.calibrate_btn.config(state=tk.NORMAL, text="Auto-Calibrate"))
            
            return _calibrate()
        
        self.run_async_function(calibrate_callback())

    def manual_reconnect(self):
        """Manually trigger reconnection"""
        def reconnect_callback():
            async def _reconnect():
                try:
                    # Disconnect first
                    await self.websocket_client.disconnect()
                    await asyncio.sleep(0.5)
                    
                    # Reconnect
                    success = await self.websocket_client.connect()
                    if success:
                        self.connected = True
                        self.root.after(0, lambda: self.status_label.config(text="Status: Connected", foreground="green"))
                        await self.initialize_printer()
                        
                        if not self.running:
                            self.running = True
                            asyncio.create_task(self.smooth_jog_loop())
                        
                        self.root.after(0, lambda: messagebox.showinfo("Reconnection", "Successfully reconnected to printer!"))
                    else:
                        self.root.after(0, lambda: messagebox.showerror("Reconnection", "Failed to reconnect to printer"))
                        
                except Exception as e:
                    self.root.after(0, lambda: messagebox.showerror("Reconnection Error", str(e)))
            
            return _reconnect()
        
        self.run_async_function(reconnect_callback())

    def reset_velocities(self):
        """Reset all velocities to zero"""
        self.target_velocities = {'x': 0.0, 'y': 0.0, 'u': 0.0, 'v': 0.0}
        self.current_velocities = {'x': 0.0, 'y': 0.0, 'u': 0.0, 'v': 0.0}

    def emergency_stop(self):
        """Emergency stop - immediately halt all movement"""
        print("EMERGENCY STOP ACTIVATED")
        self.reset_velocities()
        
        if self.connected:
            def estop_callback():
                async def _estop():
                    try:
                        await self.websocket_client.send_gcode("M112")
                        print("Emergency stop command sent to printer")
                    except Exception as e:
                        print(f"Error sending emergency stop: {e}")
                return _estop()
            
            self.run_async_function(estop_callback())
        
        messagebox.showwarning("Emergency Stop", "Emergency stop activated!\nAll movement halted.")

    async def smooth_jog_loop(self):
        """Main smooth jogging loop with async velocity-based control"""
        last_update_time = time.time()
        print("Async jogging loop started")
        
        while self.running:
            try:
                # Skip if not connected but keep loop alive for reconnection
                if not self.connected:
                    await asyncio.sleep(0.1)
                    continue
                    
                current_time = time.time()
                dt = current_time - last_update_time
                
                pygame.event.pump()

                # Read joystick inputs
                x_axis = self.joystick.get_axis(0)
                y_axis = -self.joystick.get_axis(1)
                u_axis = self.joystick.get_axis(2)
                v_axis = -self.joystick.get_axis(3)

                # Handle button inputs
                self.handle_button_inputs()

                # Convert stick inputs to target velocities
                self.target_velocities['x'] = self.config.get_velocity_curve(x_axis, self.fine_mode)
                self.target_velocities['y'] = self.config.get_velocity_curve(y_axis, self.fine_mode)
                self.target_velocities['u'] = self.config.get_velocity_curve(u_axis, self.fine_mode)
                self.target_velocities['v'] = self.config.get_velocity_curve(v_axis, self.fine_mode)

                # Smooth velocity transitions
                for axis in ['x', 'y', 'u', 'v']:
                    self.current_velocities[axis] = self.smooth_velocity_transition(
                        self.current_velocities[axis], 
                        self.target_velocities[axis], 
                        dt
                    )

                # Calculate movements and send commands
                await self.execute_smooth_movement(dt)

                # Determine next update interval based on current velocity
                max_velocity = max(abs(v) for v in self.current_velocities.values())
                next_interval = self.config.get_dynamic_interval(max_velocity)
                
                last_update_time = current_time
                await asyncio.sleep(next_interval)
                
            except Exception as e:
                print(f"Error in smooth jog loop: {e}")
                await asyncio.sleep(0.1)
        
        print("Async jogging loop stopped")

    def smooth_velocity_transition(self, current_vel, target_vel, dt):
        """Apply low-pass filter for smooth velocity transitions with faster stopping"""
        # If target is zero (stick released), stop more aggressively
        if abs(target_vel) < 0.1:
            alpha = 1.0 - math.exp(-dt / (self.config.velocity_smoothing * 0.1))
            decay_rate = max(alpha, 0.3)
            new_vel = current_vel * (1.0 - decay_rate)
        else:
            alpha = 1.0 - math.exp(-dt / self.config.velocity_smoothing)
            new_vel = current_vel + alpha * (target_vel - current_vel)
        
        # Force stop if velocity is very small
        if abs(new_vel) < self.config.velocity_stop_threshold:
            new_vel = 0.0
            
        return new_vel

    async def execute_smooth_movement(self, dt):
        """Execute movement commands based on current velocities"""
        if not self.connected:
            return
            
        # Calculate movements for XY carriage
        xy_moving = abs(self.current_velocities['x']) > self.config.velocity_stop_threshold or abs(self.current_velocities['y']) > self.config.velocity_stop_threshold
        if xy_moving:
            dx = (self.current_velocities['x'] / 60.0) * dt
            dy = (self.current_velocities['y'] / 60.0) * dt
            
            # Apply XY movement scaling
            dx *= self.config.movement_scale_xy
            dy *= self.config.movement_scale_xy
            
            if abs(dx) > self.config.min_move_threshold or abs(dy) > self.config.min_move_threshold:
                self.positions['x'] += dx
                self.positions['y'] += dy
                self.last_movement_time = time.time()  # Track movement time for position updates
                
                # Calculate dynamic feedrate
                velocity_magnitude = math.sqrt(dx*dx + dy*dy) / dt * 60
                feedrate = max(100, min(self.config.max_speed, velocity_magnitude))
                
                gcode = f"""SET_DUAL_CARRIAGE CARRIAGE=x
SET_DUAL_CARRIAGE CARRIAGE=y
G1 X{dx:.4f} Y{dy:.4f} F{feedrate:.0f}"""
                
                success = await self.websocket_client.send_gcode(gcode)
                await self.handle_success_message(success, dx, dy, feedrate)

        # Calculate movements for UV carriage (can happen simultaneously with XY)
        uv_moving = abs(self.current_velocities['u']) > self.config.velocity_stop_threshold or abs(self.current_velocities['v']) > self.config.velocity_stop_threshold
        if uv_moving:
            du = (self.current_velocities['u'] / 60.0) * dt
            dv = (self.current_velocities['v'] / 60.0) * dt
            
            # Apply UV movement scaling
            du *= self.config.movement_scale_uv
            dv *= self.config.movement_scale_uv
            
            if abs(du) > self.config.min_move_threshold or abs(dv) > self.config.min_move_threshold:
                self.positions['u'] += du
                self.positions['v'] += dv
                self.last_movement_time = time.time()  # Track movement time for position updates
                
                velocity_magnitude = math.sqrt(du*du + dv*dv) / dt * 60
                feedrate = max(100, min(self.config.max_speed, velocity_magnitude))
                
                gcode = f"""SET_DUAL_CARRIAGE CARRIAGE=x2
SET_DUAL_CARRIAGE CARRIAGE=y2
G1 X{du:.4f} Y{dv:.4f} F{feedrate:.0f}"""
                
                success = await self.websocket_client.send_gcode(gcode)
                await self.handle_success_message(success, du, dv, feedrate)

    async def handle_success_message(self, success, dx, dy, feedrate):
        if success == 400:
            # If we get a 400, it means the printer needs to be homed
            gcode = f"""SET_DUAL_CARRIAGE CARRIAGE=x
SET_DUAL_CARRIAGE CARRIAGE=y
SET_KINEMATIC_POSITION X={self.positions['x']:.4f} Y={self.positions['y']:.4f}
SET_DUAL_CARRIAGE CARRIAGE=x2
SET_DUAL_CARRIAGE CARRIAGE=y2
SET_KINEMATIC_POSITION X={self.positions['u']:.4f} Y={self.positions['v']:.4f}"""
            success = await self.websocket_client.send_gcode(gcode)
            if success is not True:
                messagebox.showerror('Homing Error', 'Printer needs to be homed before jogging.')
                return
        if success:
            self.record_movement_performance(dx, dy, feedrate)
        else:
            messagebox.showerror('Unknown error', 'Could not send command. Are you going out of bounds?')

    def record_movement_performance(self, dx, dy, feedrate):
        """Record movement for performance analysis"""
        movement_data = {
            'time': time.time(),
            'distance': math.sqrt(dx*dx + dy*dy),
            'feedrate': feedrate
        }
        self.movement_history.append(movement_data)

    def handle_button_inputs(self):
        """Handle joystick button inputs with debouncing"""
        current_time = time.time()
        
        # Fine mode toggle
        if self.joystick.get_button(0):
            if not hasattr(self, 'last_fine_toggle') or current_time - self.last_fine_toggle > 0.5:
                self.fine_mode = not self.fine_mode
                mode_text = "Fine Mode: ON" if self.fine_mode else "Fine Mode: OFF"
                
                # Automatically adjust speed scaling based on fine mode
                if self.fine_mode:
                    self.config.velocity_scale = 1.0
                    self.config.movement_scale_xy = 1.0
                    self.config.movement_scale_uv = 1.0
                    self.overall_scale_var.set(1.0)
                    self.xy_scale_var.set(1.0)
                    self.uv_scale_var.set(1.0)
                    self.root.after(0, lambda: self.overall_scale_label.config(text="1.00x"))
                    self.root.after(0, lambda: self.xy_scale_label.config(text="1.00x"))
                    self.root.after(0, lambda: self.uv_scale_label.config(text="1.00x"))
                else:
                    self.config.velocity_scale = 0.5
                    self.config.movement_scale_xy = 0.5
                    self.config.movement_scale_uv = 0.5
                    self.overall_scale_var.set(0.5)
                    self.xy_scale_var.set(0.5)
                    self.uv_scale_var.set(0.5)
                    self.root.after(0, lambda: self.overall_scale_label.config(text="0.50x"))
                    self.root.after(0, lambda: self.xy_scale_label.config(text="0.50x"))
                    self.root.after(0, lambda: self.uv_scale_label.config(text="0.50x"))
                
                self.root.after(0, lambda: self.mode_label.config(text=mode_text))
                self.last_fine_toggle = current_time

        # Save position
        if self.joystick.get_button(1):
            if not hasattr(self, 'last_save') or current_time - self.last_save > 0.5:
                self.positions['saved'] = (self.positions['x'], self.positions['y'], 
                                         self.positions['u'], self.positions['v'])
                self.last_save = current_time

        # Go to saved position
        if self.joystick.get_button(3):
            if not hasattr(self, 'last_goto') or current_time - self.last_goto > 0.5:
                if self.positions['saved']:
                    def goto_callback():
                        return self.goto_saved_position()
                    self.run_async_function(goto_callback())
                self.last_goto = current_time

        # Home XY axes (button 2)
        if self.joystick.get_button(2):
            if not hasattr(self, 'last_home_xy') or current_time - self.last_home_xy > 0.5:
                def home_xy_callback():
                    return self.home_xy_axes()
                self.run_async_function(home_xy_callback())
                self.last_home_xy = current_time

    async def home_xy_axes(self):
        gcode = """G28 X Y\n"""
        try:
            success = await self.websocket_client.send_gcode(gcode)
            if success:
                print("Successfully homed XY axes")
        except Exception as e:
            print(f"Error homing XY axes: {e}")

    async def goto_saved_position(self):
        """Move to saved position smoothly"""
        pos = self.positions['saved']
        gcode = f"""G90
SET_DUAL_CARRIAGE CARRIAGE=x
SET_DUAL_CARRIAGE CARRIAGE=y
G0 X{pos[0]:.3f} Y{pos[1]:.3f} F{self.config.base_speed}
SET_DUAL_CARRIAGE CARRIAGE=x2
SET_DUAL_CARRIAGE CARRIAGE=y2
G0 X{pos[2]:.3f} Y{pos[3]:.3f} F{self.config.base_speed}
G91"""
        
        try:
            success = await self.websocket_client.send_gcode(gcode)
            if success:
                self.positions['x'] = pos[0]
                self.positions['y'] = pos[1]
                self.positions['u'] = pos[2]
                self.positions['v'] = pos[3]
        except Exception as e:
            print(f"Error going to saved position: {e}")

    # GUI update methods (same as original)
    def update_speed_config(self, value):
        """Update max speed configuration"""
        self.config.max_speed = float(value)
        self.speed_label.config(text=f"{self.config.max_speed:.0f} mm/min")
    
    def update_xy_scale(self, value):
        """Update XY movement scale"""
        self.config.movement_scale_xy = float(value)
        self.xy_scale_label.config(text=f"{self.config.movement_scale_xy:.2f}x")
    
    def update_uv_scale(self, value):
        """Update UV movement scale"""
        self.config.movement_scale_uv = float(value)
        self.uv_scale_label.config(text=f"{self.config.movement_scale_uv:.2f}x")
    
    def update_overall_scale(self, value):
        """Update overall velocity scale"""
        self.config.velocity_scale = float(value)
        self.overall_scale_label.config(text=f"{self.config.velocity_scale:.2f}x")
    
    def set_preset_scale(self, scale_value):
        """Set all scales to a preset value"""
        self.config.velocity_scale = scale_value
        self.config.movement_scale_xy = scale_value
        self.config.movement_scale_uv = scale_value
        
        # Update sliders
        self.overall_scale_var.set(scale_value)
        self.xy_scale_var.set(scale_value)
        self.uv_scale_var.set(scale_value)
        
        # Update labels
        self.overall_scale_label.config(text=f"{scale_value:.2f}x")
        self.xy_scale_label.config(text=f"{scale_value:.2f}x")
        self.uv_scale_label.config(text=f"{scale_value:.2f}x")

    def update_displays(self):
        """Update all GUI displays"""
        if not hasattr(self, 'position_text'):
            self.root.after(100, self.update_displays)
            return
            
        # Update positions
        self.position_text.delete(1.0, tk.END)
        self.position_text.insert(tk.END, f"X: {self.positions['x']:.3f} mm\n")
        self.position_text.insert(tk.END, f"Y: {self.positions['y']:.3f} mm\n")
        self.position_text.insert(tk.END, f"U: {self.positions['u']:.3f} mm\n")
        self.position_text.insert(tk.END, f"V: {self.positions['v']:.3f} mm")
        
        # Update velocities
        self.velocity_text.delete(1.0, tk.END)
        self.velocity_text.insert(tk.END, f"X: {self.current_velocities['x']:.1f} mm/min\n")
        self.velocity_text.insert(tk.END, f"Y: {self.current_velocities['y']:.1f} mm/min\n")
        self.velocity_text.insert(tk.END, f"U: {self.current_velocities['u']:.1f} mm/min\n")
        self.velocity_text.insert(tk.END, f"V: {self.current_velocities['v']:.1f} mm/min")
        
        # Update saved positions
        if self.positions['saved']:
            self.saved_positions_text.delete(1.0, tk.END)
            saved = self.positions['saved']
            self.saved_positions_text.insert(tk.END, 
                f"Saved: X={saved[0]:.3f}, Y={saved[1]:.3f}, U={saved[2]:.3f}, V={saved[3]:.3f}")
        
        # Update performance metrics
        self.update_performance_display()
        
        # Update connection status
        if not self.connected and hasattr(self.websocket_client, 'reconnect_attempts'):
            if self.websocket_client.reconnect_attempts > 0:
                self.status_label.config(
                    text=f"Status: Reconnecting... ({self.websocket_client.reconnect_attempts}/{self.websocket_client.max_reconnect_attempts})", 
                    foreground="orange"
                )
        
        # Schedule next update
        self.root.after(100, self.update_displays)

    def update_performance_display(self):
        """Update performance metrics display"""
        if not self.movement_history:
            self.perf_text.delete(1.0, tk.END)
            self.perf_text.insert(tk.END, f"Network Latency: {self.config.network_latency:.3f}s\n")
            self.perf_text.insert(tk.END, f"Reconnect Attempts: {getattr(self.websocket_client, 'reconnect_attempts', 0)}\n")
            time_since_disconnect = time.time() - self.last_disconnect_time if self.last_disconnect_time > 0 else 0
            self.perf_text.insert(tk.END, f"Time Since Disconnect: {time_since_disconnect:.1f}s\n")
            time_since_command = time.time() - getattr(self.websocket_client, 'last_successful_command', time.time())
            self.perf_text.insert(tk.END, f"Last Command: {time_since_command:.1f}s ago")
            return
            
        recent_movements = list(self.movement_history)[-10:]
        
        if len(recent_movements) > 1:
            avg_distance = np.mean([m['distance'] for m in recent_movements])
            avg_feedrate = np.mean([m['feedrate'] for m in recent_movements])
            
            time_span = recent_movements[-1]['time'] - recent_movements[0]['time']
            frequency = len(recent_movements) / max(time_span, 0.001)
            
            self.perf_text.delete(1.0, tk.END)
            self.perf_text.insert(tk.END, f"Network Latency: {self.config.network_latency:.3f}s\n")
            self.perf_text.insert(tk.END, f"Update Frequency: {frequency:.1f} Hz\n")
            self.perf_text.insert(tk.END, f"Avg Distance/Move: {avg_distance:.4f} mm\n")
            self.perf_text.insert(tk.END, f"Avg Feedrate: {avg_feedrate:.0f} mm/min")

    def run(self):
        """Start the GUI application"""
        try:
            self.root.protocol("WM_DELETE_WINDOW", self.on_closing)
            self.root.mainloop()
        except KeyboardInterrupt:
            print("Exiting...")
            self.disconnect()

    def on_closing(self):
        """Handle application closing"""
        self.disconnect()
        
        # Stop event loop
        if self.loop and not self.loop.is_closed():
            self.loop.call_soon_threadsafe(self.loop.stop)
        
        self.root.destroy()
