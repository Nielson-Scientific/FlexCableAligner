import asyncio
import logging
import json
import os

class CarriageController:
    def __init__(self, client):
        """
        :param client: An instance of AsyncWebSocketClient
        """
        self.client = client
        
        # Load bounds from config
        self.bounds = {}
        config_path = os.path.join(os.path.dirname(__file__), '..', 'config', 'carriage_bounds.json')
        try:
            with open(config_path, 'r') as f:
                self.bounds = json.load(f)
            logging.info(f"Loaded carriage bounds from {config_path}")
        except Exception as e:
            logging.error(f"Failed to load carriage bounds: {e}")
            # Fallback to defaults
            self.bounds = {
                'x1': {'home': 0.0, 'min': 0.0, 'max': 800.0},
                'y1': {'home': 0.0, 'min': -50.0, 'max': 300.0},
                'x2': {'home': 711.31, 'min': 0.0, 'max': 800.0},
                'y2': {'home': -26.8, 'min': -50.0, 'max': 300.0}
            }

        # Initialize positions based on home bounds
        self.positions = {
            'x1': self.bounds['x1']['home'],
            'y1': self.bounds['y1']['home'],
            'x2': self.bounds['x2']['home'],
            'y2': self.bounds['y2']['home']
        }

    def _clamp_position(self, axis, value):
        min_val = self.bounds[axis]['min']
        max_val = self.bounds[axis]['max']
        clamped = max(min_val, min(max_val, value))
        if clamped != value:
            logging.warning(f"Clamping {axis} command from {value} to bounds [{min_val}, {max_val}] -> {clamped}")
        return clamped
        
    async def initialize(self):
        """
        Prepare printer:
        1. Query homing status.
        2. Home if needed.
        3. Set absolute mode (G90).
        """
        logging.info("Initializing printer controller...")
        
        # Check homing
        try:
            status = await self.client.get_toolhead_status()
            homed_axes = status.get('homed_axes', '')
            need_home = False
            for axis in ['x', 'y']:
                if axis not in homed_axes:
                    need_home = True
                    break
            
            if need_home:
                logging.info(f"Axes not fully homed ({homed_axes}). Homing X and Y now...")
                # Using G28 X Y only (leaving Z alone as requested Z is not used)
                await self.client.send_gcode_and_wait("G28 X Y")
                
                # Update positions to home coordinates
                self.positions['x1'] = self.bounds['x1']['home']
                self.positions['y1'] = self.bounds['y1']['home']
                self.positions['x2'] = self.bounds['x2']['home']
                self.positions['y2'] = self.bounds['y2']['home']
            else:
                logging.info(f"Axes already homed: {homed_axes}")

        except Exception as e:
            logging.error(f"Failed to check/home axes: {e}")
            # Depending on severity, we might want to raise, but let's try to proceed 
            # or at least set G90.

        # Force Absolute Mode
        logging.info("Setting Absolute Mode (G90)")
        await self.client.send_gcode_and_wait("G90")

    async def move_to_coordinates(self, x1, y1, x2, y2, speed=1000):
        """
        Moves both carriages to the specified absolute coordinates.
        Strategies: 
        1. Set dual carriage to T0 (x/y), move X/Y.
        2. Set dual carriage to T1 (x2/y2), move X/Y (mapped to X2/Y2).
        
        Klipper Dual Carriage usually mapping:
        SET_DUAL_CARRIAGE CARRIAGE=x  -> COMPENSATED_ABS_MV X.. moves X1
        SET_DUAL_CARRIAGE CARRIAGE=x2 -> COMPENSATED_ABS_MV X.. moves X2
        """
        # Clamp positions before sending
        cx1 = self._clamp_position('x1', x1)
        cy1 = self._clamp_position('y1', y1)
        cx2 = self._clamp_position('x2', x2)
        cy2 = self._clamp_position('y2', y2)

        # Ensure Absolute Mode is active before sending coordinates
        await self.client.send_gcode("G90")

        # Move Carriage 1 (cx1, cy1)
        # Activate Carriage 1 - MUST WAIT for this to complete
        await self.client.send_gcode_and_wait("SET_DUAL_CARRIAGE CARRIAGE=x")
        await self.client.send_gcode_and_wait("SET_DUAL_CARRIAGE CARRIAGE=y") 
        
        # Move C1
        await self.client.send_gcode(f"COMPENSATED_ABS_MV X={cx1} Y={cy1} F={speed}")
        
        # Move Carriage 2 (cx2, cy2)
        # Activate Carriage 2 - MUST WAIT for this to complete
        await self.client.send_gcode_and_wait("SET_DUAL_CARRIAGE CARRIAGE=x2")
        await self.client.send_gcode_and_wait("SET_DUAL_CARRIAGE CARRIAGE=y2")
        
        # Move C2
        await self.client.send_gcode(f"COMPENSATED_ABS_MV X={cx2} Y={cy2} F={speed}")
        
        # Update internal state with clamped values
        self.positions['x1'] = cx1
        self.positions['y1'] = cy1
        self.positions['x2'] = cx2
        self.positions['y2'] = cy2

    async def jog_axis(self, carriage_idx, axis, distance, speed=1000):
        """
        Jogs a specific axis relative to current position.
        :param carriage_idx: 1 or 2
        :param axis: 'X' or 'Y'
        :param distance: float (+ or -)
        """
        # Determine carriage name
        cx_name = 'x' if carriage_idx == 1 else 'x2'
        cy_name = 'y' if carriage_idx == 1 else 'y2'
        
        current_x = self.positions[f'x{carriage_idx}']
        current_y = self.positions[f'y{carriage_idx}']
        
        target_x = current_x
        target_y = current_y
        
        if axis.upper() == 'X':
            target_x += distance
        elif axis.upper() == 'Y':
            target_y += distance
            
        await self.move_carriage(carriage_idx, target_x, target_y, speed)

    async def move_carriage(self, carriage_idx, x, y, speed=1000):
        """
        Moves a single carriage to absolute coordinates.
        Updates internal position state.
        :param carriage_idx: 1 or 2
        :param x: Target X
        :param y: Target Y
        :param speed: Feed rate
        """
        if carriage_idx not in (1, 2):
            logging.error(f"Invalid carriage index: {carriage_idx}")
            return

        cx_key = f'x{carriage_idx}'
        cy_key = f'y{carriage_idx}'

        # Clamp positions before sending
        clamped_x = self._clamp_position(cx_key, x)
        clamped_y = self._clamp_position(cy_key, y)

        cx_name = 'x' if carriage_idx == 1 else 'x2'
        cy_name = 'y' if carriage_idx == 1 else 'y2'

        # Ensure Absolute Mode is active before sending coordinates
        await self.client.send_gcode("G90")

        # Activate Carriage
        await self.client.send_gcode_and_wait(f"SET_DUAL_CARRIAGE CARRIAGE={cx_name}")
        await self.client.send_gcode_and_wait(f"SET_DUAL_CARRIAGE CARRIAGE={cy_name}")
        
        # Move
        await self.client.send_gcode(f"COMPENSATED_ABS_MV X={clamped_x} Y={clamped_y} F={speed}")
        
        # Update State
        self.positions[cx_key] = clamped_x
        self.positions[cy_key] = clamped_y


    async def _send_batch(self, commands):
        # Deprecated / Unused now in favor of explicit sequencing
        for cmd in commands:
            await self.client.send_gcode(cmd)
