import logging
import json
from pathlib import Path


class PositionValidator:
    """
    Validates and clips carriage positions against machine bounds stored in a JSON file.
    
    This class provides independent bounds checking for the FlexCableAligner software,
    ensuring that all move commands stay within safe limits defined by the printer's
    physical constraints (as configured in Klipper's printer.cfg).
    """
    
    def __init__(self, bounds_file_path="machine_bounds.json"):
        """
        Initialize the PositionValidator with bounds from a JSON file.
        
        Args:
            bounds_file_path: Path to the JSON file containing machine bounds.
                             Defaults to 'machine_bounds.json' in the current directory.
        """
        self.bounds_file = Path(bounds_file_path)
        self.bounds = self._load_bounds()
    
    def _load_bounds(self):
        """
        Load machine bounds from JSON file.
        
        Returns:
            Dict containing bounds for each axis (x1, y1, x2, y2).
            If file not found or invalid, returns default bounds matching printer.cfg.
        """
        try:
            with open(self.bounds_file, 'r') as f:
                return json.load(f)
        except FileNotFoundError:
            logging.warning(f"Bounds file {self.bounds_file} not found. Using defaults.")
            return self._get_default_bounds()
        except json.JSONDecodeError as e:
            logging.error(f"Invalid JSON in bounds file: {e}")
            return self._get_default_bounds()
    
    def _get_default_bounds(self):
        """
        Return default bounds matching printer.cfg configuration.
        
        Returns:
            Default bounds dict for x1, y1, x2, y2 axes.
        """
        return {
            "x1": {"home": 0.0, "min": 0.0, "max": 200.0},
            "y1": {"home": 0.0, "min": 0.0, "max": 100.0},
            "x2": {"home": 0.0, "min": 0.0, "max": 200.0},
            "y2": {"home": 0.0, "min": 0.0, "max": 100.0}
        }
    
    def validate_and_clip(self, axis: str, target_value: float) -> tuple:
        """
        Validate a target position against bounds and clip if necessary.
        
        Args:
            axis: One of 'x1', 'y1', 'x2', 'y2'
            target_value: The requested target position
            
        Returns:
            Tuple of (clipped_value, was_clipped) where was_clipped is True
            if the value was modified to fit within bounds.
        """
        if axis not in self.bounds:
            logging.error(f"Unknown axis: {axis}")
            return target_value, False
        
        bounds = self.bounds[axis]
        min_val = bounds["min"]
        max_val = bounds["max"]
        
        if target_value < min_val:
            clipped = min_val
            logging.warning(f"{axis} position {target_value:.2f} below minimum {min_val}. Clipping to {clipped}.")
            return clipped, True
        elif target_value > max_val:
            clipped = max_val
            logging.warning(f"{axis} position {target_value:.2f} above maximum {max_val}. Clipping to {clipped}.")
            return clipped, True
        
        return target_value, False
    
    def validate_position(self, x1: float, y1: float, x2: float, y2: float) -> dict:
        """
        Validate all four coordinates and return clipping results.
        
        Args:
            x1, y1: Target coordinates for carriage 1
            x2, y2: Target coordinates for carriage 2
            
        Returns:
            Dict with keys 'x1', 'y1', 'x2', 'y2' containing (clipped_value, was_clipped) tuples.
        """
        return {
            'x1': self.validate_and_clip('x1', x1),
            'y1': self.validate_and_clip('y1', y1),
            'x2': self.validate_and_clip('x2', x2),
            'y2': self.validate_and_clip('y2', y2)
        }
    
    def update_home(self, axis: str, home_position: float):
        """
        Update the home position for an axis after homing.
        
        Args:
            axis: One of 'x1', 'y1', 'x2', 'y2'
            home_position: The new home position value
        """
        if axis in self.bounds:
            self.bounds[axis]["home"] = home_position
    
    def save_bounds(self):
        """
        Save current bounds (including updated home positions) to file.
        
        Returns:
            True if successful, False otherwise.
        """
        try:
            with open(self.bounds_file, 'w') as f:
                json.dump(self.bounds, f, indent=4)
            logging.info(f"Saved bounds to {self.bounds_file}")
            return True
        except Exception as e:
            logging.error(f"Failed to save bounds: {e}")
            return False
