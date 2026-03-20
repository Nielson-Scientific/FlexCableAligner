import asyncio
import logging

class CarriageController:
    def __init__(self, client):
        """
        :param client: An instance of AsyncWebSocketClient
        """
        self.client = client
        # Default positions: C1 at 0,0 (traditional), C2 at 792.79,0 (Park/Home)
        self.positions = {'x1': 0.0, 'y1': 0.0, 'x2': 792.79, 'y2': -27.15}
        
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
                self.positions['x2'] = 1000.0
                self.positions['y2'] = 0.0
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
        """
        # Ensure Absolute Mode is active before sending coordinates
        await self.client.send_gcode("G90")

        # Move Carriage 1 (x1, y1)
        # Activate Carriage 1 - MUST WAIT for this to complete
        await self.client.send_gcode_and_wait("SET_DUAL_CARRIAGE CARRIAGE=x")
        await self.client.send_gcode_and_wait("SET_DUAL_CARRIAGE CARRIAGE=y") 
        
        # Move C1
        await self.client.send_gcode(f"G1 X{x1} Y{y1} F{speed}")
        
        # Move Carriage 2 (x2, y2)
        # Activate Carriage 2 - MUST WAIT for this to complete
        await self.client.send_gcode_and_wait("SET_DUAL_CARRIAGE CARRIAGE=x2")
        await self.client.send_gcode_and_wait("SET_DUAL_CARRIAGE CARRIAGE=y2")
        
        # Move C2
        await self.client.send_gcode(f"G1 X{x2} Y{y2} F{speed}")
        
        # Update internal state
        self.positions['x1'] = x1
        self.positions['y1'] = y1
        self.positions['x2'] = x2
        self.positions['y2'] = y2

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
        # Ensure Absolute Mode is active before sending coordinates
        await self.client.send_gcode("G90")

        if carriage_idx == 1:
            # Activate Carriage 1
            await self.client.send_gcode_and_wait("SET_DUAL_CARRIAGE CARRIAGE=x")
            await self.client.send_gcode_and_wait("SET_DUAL_CARRIAGE CARRIAGE=y")
            
            # Move
            await self.client.send_gcode(f"G1 X{x} Y{y} F{speed}")
            
            # Update State
            self.positions['x1'] = x
            self.positions['y1'] = y
            
        elif carriage_idx == 2:
            # Activate Carriage 2
            await self.client.send_gcode_and_wait("SET_DUAL_CARRIAGE CARRIAGE=x2")
            await self.client.send_gcode_and_wait("SET_DUAL_CARRIAGE CARRIAGE=y2")
            
            # Move
            await self.client.send_gcode(f"G1 X{x} Y{y} F{speed}")
            
            # Update State
            self.positions['x2'] = x
            self.positions['y2'] = y
        else:
            logging.error(f"Invalid carriage index: {carriage_idx}")

    async def move_carriage(self, carriage_idx, x, y, speed=1000):
        """
        Moves a single carriage to absolute coordinates.
        """
        cx_name = 'x' if carriage_idx == 1 else 'x2'
        cy_name = 'y' if carriage_idx == 1 else 'y2'
        
        await self.client.send_gcode("G90")
        
        await self.client.send_gcode_and_wait(f"SET_DUAL_CARRIAGE CARRIAGE={cx_name}")
        await self.client.send_gcode_and_wait(f"SET_DUAL_CARRIAGE CARRIAGE={cy_name}")
        
        await self.client.send_gcode(f"G1 X{x} Y{y} F{speed}")
        
        self.positions[f'x{carriage_idx}'] = x
        self.positions[f'y{carriage_idx}'] = y


    async def _send_batch(self, commands):
        # Deprecated / Unused now in favor of explicit sequencing
        for cmd in commands:
            await self.client.send_gcode(cmd)
