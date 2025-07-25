import asyncio
import time
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
        
    async def auto_calibrate_network(self, websocket_client):
        """Measure network latency and printer response time"""
        print("Calibrating network performance...")
        latencies = []
        
        for i in range(10):
            start_time = time.time()
            
            # Send a simple command that should respond quickly
            try:
                response = await websocket_client.send_gcode_and_wait("M114", timeout=2.0)
                end_time = time.time()
                
                if response:
                    latency = end_time - start_time
                    latencies.append(latency)
                    print(f"Calibration {i+1}: {latency:.3f}s")
                
                await asyncio.sleep(0.1)  # Brief pause between tests
                
            except Exception as e:
                print(f"Calibration error: {e}")
                break
        
        if latencies:
            self.network_latency = np.mean(latencies)
            print(f"Measured network latency: {self.network_latency:.3f}s")
            
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