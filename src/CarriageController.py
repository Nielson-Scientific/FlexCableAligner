import asyncio
import logging

from src.PositionValidator import PositionValidator


class CarriageController:
    def __init__(self, client):
        """
        :param client: An instance of AsyncWebSocketClient
        """
        self.client = client
        # Default positions: C1 at 0,0 (traditional), C2 at 792.79,0 (Park/Home)
        self.positions = {'x1': 0.0, 'y1': 0.0, 'x2': 792.79, 'y2': -27.15}
        # Initialize position validator for bounds checking
        self.validator = PositionValidator()
        
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
                
                # Update positions just in case
                self.positions['x1'] = 0.0
                self.positions['y1'] = 0.0
                self.positions['x2'] = 792.79
                self.positions['y2'] = -27.15
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
        SET_DUAL_CARRIAGE CARRIAGE=x  -> G1 X.. moves X1
        SET_DUAL_CARRIAGE CARRIAGE=x2 -> G1 X.. moves X2
        
        Bounds checking is performed before movement; positions are clipped to
        valid limits if they exceed the machine bounds.
        """
        # Validate and clip coordinates against machine bounds
        validated = self.validator.validate_position(x1, y1, x2, y2)
        
        # Extract validated (possibly clipped) coordinates
        x1_clipped, clipped_x1 = validated['x1']
        y1_clipped, clipped_y1 = validated['y1']
        x2_clipped, clipped_x2 = validated['x2']
        y2_clipped, clipped_y2 = validated['y2']
        
        # Log if any clipping occurred
        if any([clipped_x1, clipped_y1, clipped_x2, clipped_y2]):
            logging.warning(
                f"Move coordinates were clipped. Original: C1({x1}, {y1}) C2({x2}, {y2}) -> "
                f"Validated: C1({x1_clipped}, {y1_clipped}) C2({x2_clipped}, {y2_clipped})"
            )
        
        # Ensure Absolute Mode is active before sending coordinates
        await self.client.send_gcode("G90")

        # Move Carriage 1 (x1, y1)
        # Activate Carriage 1 - MUST WAIT for this to complete
        await self.client.send_gcode_and_wait("SET_DUAL_CARRIAGE CARRIAGE=x")
        await self.client.send_gcode_and_wait("SET_DUAL_CARRIAGE CARRIAGE=y") 
        
        # Move C1 with validated coordinates
        await self.client.send_gcode(f"G1 X{x1_clipped} Y{y1_clipped} F{speed}")
        
        # Move Carriage 2 (x2, y2)
        # Activate Carriage 2 - MUST WAIT for this to complete
        await self.client.send_gcode_and_wait("SET_DUAL_CARRIAGE CARRIAGE=x2")
        await self.client.send_gcode_and_wait("SET_DUAL_CARRIAGE CARRIAGE=y2")
        
        # Move C2 with validated coordinates
        await self.client.send_gcode(f"G1 X{x2_clipped} Y{y2_clipped} F{speed}")
        
        # Update internal state with validated (clipped) positions
        self.positions['x1'] = x1_clipped
        self.positions['y1'] = y1_clipped
        self.positions['x2'] = x2_clipped
        self.positions['y2'] = y2_clipped

    async def jog_axis(self, carriage_idx, axis, distance, speed=1000):
        """
        Jogs a specific axis relative to current position.
        :param carriage_idx: 1 or 2
        :param axis: 'X' or 'Y'
        :param distance: float (+ or -)
        
        The target position is validated against machine bounds and clipped if necessary.
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
        
        # Validate and clip the target position against machine bounds
        validated_x, clipped_x = self.validator.validate_and_clip(cx_name, target_x)
        validated_y, clipped_y = self.validator.validate_and_clip(cy_name, target_y)
        
        if clipped_x or clipped_y:
            logging.warning(
                f"Jog target for carriage {carriage_idx} from ({target_x}, {target_y}) "
                f"clipped to ({validated_x}, {validated_y}) due to bounds."
            )
            
        await self.move_carriage(carriage_idx, validated_x, validated_y, speed)

    async def move_carriage(self, carriage_idx, x, y, speed=1000):
        """
        Moves a single carriage to absolute coordinates.
        Updates internal position state.
        :param carriage_idx: 1 or 2
        :param x: Target X
        :param y: Target Y
        :param speed: Feed rate
        
        The target position is validated against machine bounds and clipped if necessary.
        """
        # Determine axis names for validation
        cx_name = 'x' if carriage_idx == 1 else 'x2'
        cy_name = 'y' if carriage_idx == 1 else 'y2'
        
        # Validate and clip the target position against machine bounds
        validated_x, clipped_x = self.validator.validate_and_clip(cx_name, x)
        validated_y, clipped_y = self.validator.validate_and_clip(cy_name, y)
        
        if clipped_x or clipped_y:
            logging.warning(
                f"Carriage {carriage_idx} move from ({x}, {y}) clipped to "
                f"({validated_x}, {validated_y}) due to bounds."
            )
        
        # Ensure Absolute Mode is active before sending coordinates
        await self.client.send_gcode("G90")

        if carriage_idx == 1:
            # Activate Carriage 1
            await self.client.send_gcode_and_wait("SET_DUAL_CARRIAGE CARRIAGE=x")
            await self.client.send_gcode_and_wait("SET_DUAL_CARRIAGE CARRIAGE=y")
            
            # Move with validated coordinates
            await self.client.send_gcode(f"G1 X{validated_x} Y{validated_y} F{speed}")
            
            # Update State
            self.positions['x1'] = validated_x
            self.positions['y1'] = validated_y
            
        elif carriage_idx == 2:
            # Activate Carriage 2
            await self.client.send_gcode_and_wait("SET_DUAL_CARRIAGE CARRIAGE=x2")
            await self.client.send_gcode_and_wait("SET_DUAL_CARRIAGE CARRIAGE=y2")
            
            # Move with validated coordinates
            await self.client.send_gcode(f"G1 X{validated_x} Y{validated_y} F{speed}")
            
            # Update State
            self.positions['x2'] = validated_x
            self.positions['y2'] = validated_y
        else:
            logging.error(f"Invalid carriage index: {carriage_idx}")


    async def _send_batch(self, commands):
        # Deprecated / Unused now in favor of explicit sequencing
        for cmd in commands:
            await self.client.send_gcode(cmd)
