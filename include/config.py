import math


class JogConfig:
    """Simplified jogging configuration (single velocity & movement scaling)."""

    def __init__(self):
        # Base speeds (mm/min)
        self.base_speed = 600
        self.max_speed = 40000

        # Joystick feel
        self.deadzone = 0.12
        self.acceleration_curve = 2.0  # exponential shaping

        # Smoothing / thresholds
        self.velocity_smoothing = 0.10  # seconds time constant for low‑pass
        self.min_move_threshold = 0.001  # mm – below this we ignore
        self.velocity_stop_threshold = 5.0  # mm/min – treat as zero

        # Global scaling (one slider now)
        self.movement_scale = 0.5
        self.velocity_scale = 0.5

        # Fine mode multiplier (neutral so fine mode only affects max_speed via GUI)
        self.fine_velocity_factor = 1.0
        self.fine_scale = 1.0

        # Jog interval bounds (dynamic scheduling)
        self.min_jog_interval = 0.02
        self.max_jog_interval = 0.20

    def get_velocity_curve(self, stick_input: float, fine_mode: bool = False) -> float:
        """Convert joystick axis (-1..1) into target velocity (mm/min)."""
        if abs(stick_input) < self.deadzone:
            return 0.0

        # Remove deadzone, normalise 0..1
        normalized = (abs(stick_input) - self.deadzone) / (1.0 - self.deadzone)
        normalized = max(0.0, min(1.0, normalized))

        # Curve
        curved = normalized ** self.acceleration_curve

        if fine_mode:
            max_vel = (self.base_speed + (self.max_speed - self.base_speed) * curved) * self.fine_velocity_factor
        else:
            max_vel = self.base_speed + (self.max_speed - self.base_speed) * curved

        velocity = curved * max_vel
        velocity *= self.velocity_scale
        return velocity if stick_input >= 0 else -velocity

    def get_dynamic_interval(self, velocity: float) -> float:
        if abs(velocity) < 0.1:
            return self.max_jog_interval
        norm = min(1.0, abs(velocity) / self.max_speed)
        return self.max_jog_interval - (self.max_jog_interval - self.min_jog_interval) * norm
