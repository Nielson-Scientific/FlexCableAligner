import pygame
import time
import threading
import json
from websocket import create_connection, WebSocketApp
import tkinter as tk
from tkinter import ttk, messagebox
import math
from collections import deque
import numpy as np

class SmoothJoggingConfig:
    """Auto-tuning configuration for smooth jogging"""
    
    def __init__(self):
        # Base parameters (will be auto-tuned)
        self.min_jog_interval = 0.02  # Minimum time between commands (50 Hz max)
        self.max_jog_interval = 0.2   # Maximum time between commands
        self.base_speed = 600         # mm/min base speed
        self.max_speed = 2000         # mm/min maximum speed
        self.acceleration_curve = 2.0 # Exponential curve for acceleration
        self.deadzone = 0.12          # Stick sensitivity threshold
        
        # Movement smoothing
        self.velocity_smoothing = 0.1  # Low-pass filter coefficient (faster response)
        self.min_move_threshold = 0.001  # Minimum movement to send (mm)
        self.velocity_stop_threshold = 5.0  # Stop sending commands below this velocity (mm/min)
        
        # Movement scaling (to compensate for device calibration issues)
        self.movement_scale_xy = 0.5  # Scale factor for XY movements
        self.movement_scale_uv = 0.5  # Scale factor for UV movements
        self.velocity_scale = 0.5     # Overall velocity scaling
        
        # Auto-calibration parameters
        self.calibration_samples = 50
        self.network_latency = 0.02  # Will be measured
        self.printer_response_time = 0.05  # Will be measured
        
    def auto_calibrate_network(self, websocket):
        """Measure network latency and printer response time"""
        print("Calibrating network performance...")
        latencies = []
        
        for i in range(10):
            start_time = time.time()
            
            # Send a simple command that should respond quickly
            message = {
                "id": 12345 + i,
                "jsonrpc": "2.0", 
                "method": "printer.gcode.script",
                "params": {"script": "M114"}  # Get position (quick response)
            }
            
            try:
                with websocket.parent.ws_lock if hasattr(websocket, 'parent') else threading.Lock():
                    websocket.send(json.dumps(message))
                    # For WebSocketApp, we'll estimate latency differently
                    # since we can't easily wait for specific responses
                    time.sleep(0.05)  # Brief wait
                    end_time = time.time()
                
                latency = end_time - start_time
                latencies.append(latency)
                time.sleep(0.1)  # Brief pause between tests
                
            except Exception as e:
                print(f"Calibration error: {e}")
                break
        
        if latencies:
            self.network_latency = np.mean(latencies)
            print(f"Estimated network latency: {self.network_latency:.3f}s")
            
            # Adjust intervals based on measured latency
            self.min_jog_interval = max(0.02, self.network_latency * 2)
            print(f"Adjusted min jog interval: {self.min_jog_interval:.3f}s")
        
    def get_velocity_curve(self, stick_input, fine_mode=False):
        """
        Convert stick input (-1 to 1) to velocity with smooth acceleration curve
        """
        if abs(stick_input) < self.deadzone:
            return 0.0
            
        # Normalize input removing deadzone
        normalized = (abs(stick_input) - self.deadzone) / (1.0 - self.deadzone)
        normalized = min(1.0, max(0.0, normalized))
        
        # Apply acceleration curve
        curved_input = normalized ** self.acceleration_curve
        
        # Calculate velocity
        if fine_mode:
            max_vel = self.base_speed * 0.2  # 20% for fine mode
        else:
            max_vel = self.base_speed + (self.max_speed - self.base_speed) * curved_input
            
        velocity = curved_input * max_vel
        
        # Apply velocity scaling
        velocity *= self.velocity_scale
        
        # Apply sign
        return velocity if stick_input >= 0 else -velocity
    
    def get_dynamic_interval(self, velocity):
        """Calculate optimal interval based on velocity"""
        if abs(velocity) < 0.1:
            return self.max_jog_interval
            
        # Higher velocity = more frequent updates for smoothness
        normalized_vel = min(1.0, abs(velocity) / self.max_speed)
        interval = self.max_jog_interval - (self.max_jog_interval - self.min_jog_interval) * normalized_vel
        
        return interval

class SmoothJoystickController:
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
        self.ws = None
        self.ws_app = None
        self.joystick = None
        self.jog_thread = None
        self.running = False
        self.connected = False
        self.reconnect_attempts = 0
        self.max_reconnect_attempts = 5  # Reduced since reconnection will be faster
        self.last_disconnect_time = 0
        self.last_successful_command = time.time()
        self.connection_timeout = 3.0  # Consider disconnected after 3s of failed commands (was 5s)
        self.reconnect_backoff = 0.0  # Start with 0 second backoff
        self.websocket_url = "ws://products.local:7125/websocket"
        self.ws_lock = threading.Lock()  # Thread safety for WebSocket operations

        # Initialize pygame
        pygame.init()
        pygame.joystick.init()
        
        # Create GUI
        self.setup_gui()
        
    def on_websocket_message(self, ws, message):
        """Handle incoming WebSocket messages"""
        try:
            data = json.loads(message)
            # Could process printer responses here if needed
            # For now, just update last successful command time
            self.last_successful_command = time.time()
        except Exception as e:
            print(f"Error processing WebSocket message: {e}")
    
    def on_websocket_error(self, ws, error):
        """Handle WebSocket errors"""
        print(f"WebSocket error: {error}")
        self.connected = False
        self.last_disconnect_time = time.time()
    
    def on_websocket_close(self, ws, close_status_code, close_msg):
        """Handle WebSocket close - automatically attempt reconnection"""
        print(f"WebSocket closed: {close_status_code} - {close_msg}")
        self.connected = False
        self.last_disconnect_time = time.time()
        
        # Update GUI status on main thread
        self.root.after(0, lambda: self.status_label.config(text="Status: Disconnected", foreground="red"))
        
        # Attempt immediate reconnection if we were previously connected and running
        if self.running and self.reconnect_attempts < self.max_reconnect_attempts:
            print("WebSocket closed, attempting automatic reconnection...")
            # Small delay to avoid immediate reconnection spam
            threading.Timer(0.5, self.attempt_websocket_reconnection).start()
    
    def on_websocket_open(self, ws):
        """Handle WebSocket open"""
        print("WebSocket connection opened")
        self.connected = True
        self.reconnect_attempts = 0
        self.reconnect_backoff = 0.0
        self.last_successful_command = time.time()
        self.ws = ws  # Store reference for sending messages
        
        # Update GUI status on main thread
        self.root.after(0, lambda: self.status_label.config(text="Status: Connected", foreground="green"))
        
        # Initialize printer settings
        try:
            self.initialize_printer()
        except Exception as e:
            print(f"Error initializing printer after connection: {e}")
    
    def attempt_websocket_reconnection(self):
        """Attempt to reconnect using WebSocketApp"""
        if not self.running or self.connected:
            return
            
        if self.reconnect_attempts >= self.max_reconnect_attempts:
            print(f"Max reconnection attempts ({self.max_reconnect_attempts}) reached")
            self.reconnect_attempts = 0
            self.reconnect_backoff = 5.0
            return
            
        # Exponential backoff
        wait_time = min(self.reconnect_backoff, 3.0)  # Cap at 3 seconds since WebSocketApp is faster
        if time.time() - self.last_disconnect_time < wait_time:
            threading.Timer(wait_time, self.attempt_websocket_reconnection).start()
            return
            
        self.reconnect_attempts += 1
        print(f"Attempting WebSocketApp reconnection {self.reconnect_attempts}/{self.max_reconnect_attempts}")
        
        try:
            # Close existing connection if any
            if self.ws_app:
                self.ws_app.close()
                
            # Create new WebSocketApp
            self.ws_app = WebSocketApp(
                self.websocket_url,
                on_message=self.on_websocket_message,
                on_error=self.on_websocket_error,
                on_close=self.on_websocket_close,
                on_open=self.on_websocket_open
            )
            
            # Start WebSocket in a separate thread
            threading.Thread(
                target=self.ws_app.run_forever,
                kwargs={'ping_interval': 30, 'ping_timeout': 10},
                daemon=True
            ).start()
            
            self.reconnect_backoff = min(self.reconnect_backoff * 1.5 + 0.5, 3.0)
            
        except Exception as e:
            print(f"WebSocketApp reconnection failed: {e}")
            self.last_disconnect_time = time.time()
            # Schedule next attempt
            threading.Timer(self.reconnect_backoff, self.attempt_websocket_reconnection).start()
        
    def setup_gui(self):
        self.root = tk.Tk()
        self.root.title("Smooth Joystick Controller")
        self.root.geometry("900x700")  # Made wider to accommodate 3 columns
        
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
        self.estop_btn.config(style='Emergency.TButton')  # We'll style this red
        
        self.status_label = ttk.Label(connection_frame, text="Status: Disconnected", foreground="red")
        self.status_label.grid(row=1, column=0, columnspan=5, pady=5)
        
        # Controller info section
        controller_frame = ttk.LabelFrame(main_frame, text="Controller Info", padding="10")
        controller_frame.grid(row=1, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=5)
        
        self.controller_label = ttk.Label(controller_frame, text="Controller: Not detected")
        self.controller_label.grid(row=0, column=0, sticky=tk.W)

        # Saved Positions section (moved to right side)
        saved_positions_frame = ttk.LabelFrame(main_frame, text="Saved Positions", padding="10")
        saved_positions_frame.grid(row=1, column=2, sticky=(tk.W, tk.E, tk.N), pady=5, padx=(10, 0))
        self.saved_positions_text = tk.Text(saved_positions_frame, height=3, width=30)
        self.saved_positions_text.grid(row=0, column=0, sticky=(tk.W, tk.E))
        
        # Performance section
        perf_frame = ttk.LabelFrame(main_frame, text="Performance Metrics", padding="10")
        perf_frame.grid(row=2, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=5)
        
        self.perf_text = tk.Text(perf_frame, height=4, width=50)
        self.perf_text.grid(row=0, column=0, sticky=(tk.W, tk.E))

        # Velocity section (moved to right column)
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
        main_frame.columnconfigure(0, weight=2)  # Main content column gets more space
        main_frame.columnconfigure(1, weight=1)  # Secondary content column
        main_frame.columnconfigure(2, weight=1)  # Right side panels column
        
        # Bind keyboard shortcuts
        self.root.bind('<Escape>', lambda e: self.emergency_stop())
        self.root.bind('<space>', lambda e: self.reset_velocities())
        self.root.focus_set()  # Enable keyboard focus
        
        self.update_displays()
        
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

    def auto_calibrate(self):
        """Run auto-calibration routine"""
        if not self.connected:
            messagebox.showerror("Error", "Must be connected to calibrate")
            return
            
        self.calibrate_btn.config(state=tk.DISABLED, text="Calibrating...")
        
        # Run calibration in separate thread to avoid blocking GUI
        def calibrate_thread():
            try:
                self.config.auto_calibrate_network(self.ws)
                self.root.after(0, lambda: self.calibrate_btn.config(state=tk.NORMAL, text="Auto-Calibrate"))
                self.root.after(0, lambda: messagebox.showinfo("Calibration", "Auto-calibration complete!"))
            except Exception as e:
                self.root.after(0, lambda: messagebox.showerror("Calibration Error", str(e)))
                self.root.after(0, lambda: self.calibrate_btn.config(state=tk.NORMAL, text="Auto-Calibrate"))
                
        threading.Thread(target=calibrate_thread, daemon=True).start()

    def manual_reconnect(self):
        """Manually trigger reconnection"""
        self.reconnect_attempts = 0  # Reset attempts
        self.reconnect_backoff = 0.0  # Allow immediate reconnection for manual attempts
        self.last_disconnect_time = 0  # Allow immediate reconnection
        
        # Close existing connection
        if self.ws_app:
            try:
                self.ws_app.close()
            except:
                pass
                
        # Ensure jogging thread is running
        if not self.jog_thread or not self.jog_thread.is_alive():
            print("Starting jogging thread for manual reconnection...")
            self.running = True
            self.jog_thread = threading.Thread(target=self.smooth_jog_loop)
            self.jog_thread.daemon = True
            self.jog_thread.start()
        
        # Start immediate reconnection attempt
        self.attempt_websocket_reconnection()
        
        # Give it a moment to connect
        def check_connection():
            if self.connected:
                messagebox.showinfo("Reconnection", "Successfully reconnected to printer!")
            else:
                messagebox.showwarning("Reconnection", "Reconnection attempt started. Check status for updates.")
                
        # Check after 2 seconds
        threading.Timer(2.0, check_connection).start()

    def connect(self):
        """Connect to both controller and WebSocket"""
        # Check controller first
        controller_ok, controller_msg = self.check_controller()
        self.controller_label.config(text=controller_msg)
        
        if not controller_ok:
            messagebox.showerror("Controller Error", controller_msg)
            return
        
        # Try to connect to WebSocket using WebSocketApp
        try:
            self.status_label.config(text="Status: Connecting...", foreground="orange")
            
            # Create WebSocketApp with event handlers
            self.ws_app = WebSocketApp(
                self.websocket_url,
                on_message=self.on_websocket_message,
                on_error=self.on_websocket_error,
                on_close=self.on_websocket_close,
                on_open=self.on_websocket_open
            )
            
            # Start WebSocket connection in separate thread
            def run_websocket():
                self.ws_app.run_forever(
                    ping_interval=30,
                    ping_timeout=10
                )
            
            ws_thread = threading.Thread(target=run_websocket, daemon=True)
            ws_thread.start()
            
            # Update GUI state
            self.connect_btn.config(state=tk.DISABLED)
            self.disconnect_btn.config(state=tk.NORMAL)
            self.calibrate_btn.config(state=tk.NORMAL)
            self.reconnect_btn.config(state=tk.NORMAL)

            # Start jogging thread
            self.running = True
            self.jog_thread = threading.Thread(target=self.smooth_jog_loop)
            self.jog_thread.daemon = True
            self.jog_thread.start()
            
            messagebox.showinfo("Success", "Connecting to printer...\nConnection status will update automatically.\nRun auto-calibration once connected for optimal performance.")
            
        except Exception as e:
            self.status_label.config(text="Status: Connection Failed", foreground="red")
            messagebox.showerror("Connection Error", f"Failed to start connection to printer: {str(e)}")
    
    def initialize_printer(self):
        """Initialize printer with proper settings"""
        # Set relative positioning and get current positions
        gcode = "G91"  # Set relative positioning
        self.send_gcode(gcode)

        # Get initial positions for both carriages
        self.update_printer_positions()
    
    def update_printer_positions(self):
        """Update positions from printer"""
        try:
            # Get carriage 1 position
            gcode = """
            SET_DUAL_CARRIAGE CARRIAGE=x
            SET_DUAL_CARRIAGE CARRIAGE=y
            M114"""
            self.send_gcode(gcode)
            response = self.receive_response()  # OK
            response = self.receive_response()  # Position
            if response and 'params' in response:
                response_parts = response['params'][0].split()
                self.positions['x'] = float(response_parts[0].split(':')[1])
                self.positions['y'] = float(response_parts[1].split(':')[1])

            # Get carriage 2 position
            gcode = """
            SET_DUAL_CARRIAGE CARRIAGE=x2
            SET_DUAL_CARRIAGE CARRIAGE=y2
            M114"""
            self.send_gcode(gcode)
            response = self.receive_response()  # OK
            response = self.receive_response()  # Position
            if response and 'params' in response:
                response_parts = response['params'][0].split()
                self.positions['u'] = float(response_parts[0].split(':')[1])
                self.positions['v'] = float(response_parts[1].split(':')[1])
        except Exception as e:
            print(f"Error updating positions: {e}")
    
    def disconnect(self):
        """Disconnect from WebSocket and stop jogging"""
        self.running = False
        self.connected = False
        self.last_disconnect_time = time.time()
        
        # Immediately stop all movement
        self.reset_velocities()
        
        # Close WebSocketApp
        if self.ws_app:
            try:
                self.ws_app.close()
            except Exception as e:
                print(f"Error closing WebSocketApp: {e}")
            self.ws_app = None
            
        # Clear WebSocket reference
        self.ws = None
        
        self.status_label.config(text="Status: Disconnected", foreground="red")
        self.connect_btn.config(state=tk.NORMAL)
        self.disconnect_btn.config(state=tk.DISABLED)
        self.calibrate_btn.config(state=tk.DISABLED)
        self.reconnect_btn.config(state=tk.DISABLED)

    def reset_velocities(self):
        """Reset all velocities to zero"""
        self.target_velocities = {'x': 0.0, 'y': 0.0, 'u': 0.0, 'v': 0.0}
        self.current_velocities = {'x': 0.0, 'y': 0.0, 'u': 0.0, 'v': 0.0}

    def emergency_stop(self):
        """Emergency stop - immediately halt all movement"""
        print("EMERGENCY STOP ACTIVATED")
        self.reset_velocities()
        
        if self.connected and self.ws:
            try:
                # Send M112 emergency stop command
                emergency_gcode = "M112"
                self.send_gcode(emergency_gcode)
                print("Emergency stop command sent to printer")
            except Exception as e:
                print(f"Error sending emergency stop: {e}")
        
        messagebox.showwarning("Emergency Stop", "Emergency stop activated!\nAll movement halted.")

    def send_gcode(self, gcode):
        """Send G-code to printer with thread safety"""
        if not self.connected or not self.ws:
            return False
        
        try:
            with self.ws_lock:
                message = {
                    "id": int(time.time() * 1000) % 100000,
                    "jsonrpc": "2.0",
                    "method": "printer.gcode.script",
                    "params": {"script": gcode}
                }
                self.ws.send(json.dumps(message))
                self.last_successful_command = time.time()
                return True
        except Exception as e:
            print(f"Error sending gcode: {e}")
            self.connected = False
            self.last_disconnect_time = time.time()
            return False

    def receive_response(self):
        """Get response from printer"""
        if not self.ws or not self.connected:
            return None
        
        try:
            response = self.ws.recv()
            data = json.loads(response)
            return data
        except Exception as e:
            print(f"Error receiving response: {e}")
            return None

    def smooth_jog_loop(self):
        """Main smooth jogging loop with velocity-based control"""
        last_update_time = time.time()
        print("Jogging thread started")
        
        while self.running:
            try:
                # Skip if not connected but keep thread alive for reconnection
                if not self.connected:
                    time.sleep(0.1)
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
                self.execute_smooth_movement(dt)

                # Determine next update interval based on current velocity
                max_velocity = max(abs(v) for v in self.current_velocities.values())
                next_interval = self.config.get_dynamic_interval(max_velocity)
                
                last_update_time = current_time
                time.sleep(next_interval)
                
            except Exception as e:
                print(f"Error in smooth jog loop: {e}")
                # Don't break on errors, just continue
                time.sleep(0.1)
        
        print("Jogging thread stopped")

    def smooth_velocity_transition(self, current_vel, target_vel, dt):
        """Apply low-pass filter for smooth velocity transitions with faster stopping"""
        # If target is zero (stick released), stop more aggressively
        if abs(target_vel) < 0.1:
            # Much faster decay when stopping - even more aggressive
            alpha = 1.0 - math.exp(-dt / (self.config.velocity_smoothing * 0.1))  # 10x faster stop
            # Also add a minimum decay rate to ensure stopping
            decay_rate = max(alpha, 0.3)  # At least 30% decay per update
            new_vel = current_vel * (1.0 - decay_rate)
        else:
            # Normal smoothing when moving
            alpha = 1.0 - math.exp(-dt / self.config.velocity_smoothing)
            new_vel = current_vel + alpha * (target_vel - current_vel)
        
        # Force stop if velocity is very small
        if abs(new_vel) < self.config.velocity_stop_threshold:
            new_vel = 0.0
            
        return new_vel

    def execute_smooth_movement(self, dt):
        """Execute movement commands based on current velocities"""
        if not self.connected:
            return
            
        # Calculate movements for XY carriage
        if abs(self.current_velocities['x']) > self.config.velocity_stop_threshold or abs(self.current_velocities['y']) > self.config.velocity_stop_threshold:
            dx = (self.current_velocities['x'] / 60.0) * dt  # Convert mm/min to mm/s
            dy = (self.current_velocities['y'] / 60.0) * dt
            
            # Apply XY movement scaling
            dx *= self.config.movement_scale_xy
            dy *= self.config.movement_scale_xy
            
            if abs(dx) > self.config.min_move_threshold or abs(dy) > self.config.min_move_threshold:
                self.positions['x'] += dx
                self.positions['y'] += dy
                
                # Calculate dynamic feedrate
                velocity_magnitude = math.sqrt(dx*dx + dy*dy) / dt * 60  # mm/min
                feedrate = max(100, min(self.config.max_speed, velocity_magnitude))
                
                gcode = f"""SET_DUAL_CARRIAGE CARRIAGE=x
SET_DUAL_CARRIAGE CARRIAGE=y
G1 X{dx:.4f} Y{dy:.4f} F{feedrate:.0f}"""
                
                if self.send_gcode(gcode):
                    self.record_movement_performance(dx, dy, feedrate)

        # Calculate movements for UV carriage  
        elif abs(self.current_velocities['u']) > self.config.velocity_stop_threshold or abs(self.current_velocities['v']) > self.config.velocity_stop_threshold:
            du = (self.current_velocities['u'] / 60.0) * dt
            dv = (self.current_velocities['v'] / 60.0) * dt
            
            # Apply UV movement scaling
            du *= self.config.movement_scale_uv
            dv *= self.config.movement_scale_uv
            
            if abs(du) > self.config.min_move_threshold or abs(dv) > self.config.min_move_threshold:
                self.positions['u'] += du
                self.positions['v'] += dv
                
                velocity_magnitude = math.sqrt(du*du + dv*dv) / dt * 60
                feedrate = max(100, min(self.config.max_speed, velocity_magnitude))
                
                gcode = f"""SET_DUAL_CARRIAGE CARRIAGE=x2
SET_DUAL_CARRIAGE CARRIAGE=y2
G1 X{du:.4f} Y{dv:.4f} F{feedrate:.0f}"""
                
                if self.send_gcode(gcode):
                    self.record_movement_performance(du, dv, feedrate)

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
                    # Switch to 1.0x speed for fine mode
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
                    # Switch back to 0.5x speed for normal mode
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
                    self.goto_saved_position()
                self.last_goto = current_time

    def goto_saved_position(self):
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
            self.send_gcode(gcode)
            self.positions['x'] = pos[0]
            self.positions['y'] = pos[1]
            self.positions['u'] = pos[2]
            self.positions['v'] = pos[3]
        except Exception as e:
            print(f"Error going to saved position: {e}")

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
        if not self.connected and self.reconnect_attempts > 0:
            self.status_label.config(
                text=f"Status: Reconnecting... ({self.reconnect_attempts}/{self.max_reconnect_attempts})", 
                foreground="orange"
            )
        
        # Schedule next update
        self.root.after(100, self.update_displays)

    def update_performance_display(self):
        """Update performance metrics display"""
        if not self.movement_history:
            # Show connection info when no movement data
            self.perf_text.delete(1.0, tk.END)
            self.perf_text.insert(tk.END, f"Network Latency: {self.config.network_latency:.3f}s\n")
            self.perf_text.insert(tk.END, f"Reconnect Attempts: {self.reconnect_attempts}/{self.max_reconnect_attempts}\n")
            time_since_disconnect = time.time() - self.last_disconnect_time if self.last_disconnect_time > 0 else 0
            self.perf_text.insert(tk.END, f"Time Since Disconnect: {time_since_disconnect:.1f}s\n")
            time_since_command = time.time() - self.last_successful_command
            self.perf_text.insert(tk.END, f"Last Command: {time_since_command:.1f}s ago")
            return
            
        recent_movements = list(self.movement_history)[-10:]  # Last 10 movements
        
        if len(recent_movements) > 1:
            avg_distance = np.mean([m['distance'] for m in recent_movements])
            avg_feedrate = np.mean([m['feedrate'] for m in recent_movements])
            
            # Calculate movement frequency
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
        self.root.destroy()

def main():
    app = SmoothJoystickController()
    app.run()

if __name__ == "__main__":
    main()
