import json
import websockets
import asyncio
import time

class AsyncWebSocketClient:
    """Async WebSocket client with proper request-response handling"""
    
    def __init__(self, url):
        self.url = url
        self.websocket = None
        self.connected = False
        self.message_id = 1
        self.pending_requests = {}  # Track pending requests by ID
        self.message_handlers = []  # Callbacks for notifications
        self.reconnect_attempts = 0
        self.max_reconnect_attempts = 5
        self.reconnect_delay = 1.0
        self.last_successful_command = time.time()
        
    async def connect(self):
        """Connect to the WebSocket server"""
        try:
            self.websocket = await websockets.connect(
                self.url,
                ping_interval=30,
                ping_timeout=10,
                close_timeout=5
            )
            self.connected = True
            self.reconnect_attempts = 0
            self.reconnect_delay = 1.0
            self.last_successful_command = time.time()
            print("WebSocket connected successfully")
            
            # Start message handler
            asyncio.create_task(self._message_handler())
            return True
            
        except Exception as e:
            print(f"WebSocket connection failed: {e}")
            self.connected = False
            return False
    
    async def disconnect(self):
        """Disconnect from the WebSocket server"""
        self.connected = False
        if self.websocket:
            await self.websocket.close()
            self.websocket = None
        # Cancel any pending requests
        for future in self.pending_requests.values():
            if not future.done():
                future.cancel()
        self.pending_requests.clear()
    
    async def _message_handler(self):
        """Handle incoming WebSocket messages"""
        try:
            async for message in self.websocket:
                try:
                    data = json.loads(message)
                    
                    # Handle responses to our requests
                    if 'id' in data and data['id'] in self.pending_requests:
                        future = self.pending_requests.pop(data['id'])
                        if not future.cancelled():
                            future.set_result(data)
                    
                    # Handle notifications
                    elif 'method' in data:
                        for handler in self.message_handlers:
                            try:
                                handler(data)
                            except Exception as e:
                                print(f"Error in message handler: {e}")
                    
                    self.last_successful_command = time.time()
                    
                except json.JSONDecodeError as e:
                    print(f"Failed to decode message: {e}")
                except Exception as e:
                    print(f"Error handling message: {e}")
                    
        except websockets.exceptions.ConnectionClosed:
            print("WebSocket connection closed")
            self.connected = False
        except Exception as e:
            print(f"Error in message handler: {e}")
            self.connected = False
    
    async def send_request(self, method, params=None, timeout=5.0):
        """Send a request and wait for response"""
        if not self.connected or not self.websocket:
            raise Exception("Not connected to WebSocket")
        
        request_id = self.message_id
        self.message_id += 1
        
        message = {
            "id": request_id,
            "jsonrpc": "2.0",
            "method": method,
            "params": params or {}
        }
        
        # Create future for response
        future = asyncio.Future()
        self.pending_requests[request_id] = future
        
        try:
            # Send the request
            await self.websocket.send(json.dumps(message))
            
            # Wait for response with timeout
            response = await asyncio.wait_for(future, timeout=timeout)
            return response
            
        except asyncio.TimeoutError:
            # Clean up pending request on timeout
            self.pending_requests.pop(request_id, None)
            if not future.cancelled():
                future.cancel()
            raise Exception(f"Request {request_id} timed out after {timeout}s")
        except Exception as e:
            # Clean up pending request on error
            self.pending_requests.pop(request_id, None)
            if not future.cancelled():
                future.cancel()
            raise e
    
    async def send_gcode(self, gcode):
        """Send G-code without waiting for response"""
        try:
            response = await self.send_request(
                "printer.gcode.script",
                {"script": gcode},
                timeout=2.0
            )
            # DEBUG
            if response.get('result') != 'ok':
                if response.get('error').get('code') == 400:
                    # The silly thing needs to he homed. But it doesn't, we just G92 it to make it happy
                    return 400
            else:
                return True
        except Exception as e:
            print(f"Error sending gcode: {e}")
            return False
    
    async def send_gcode_and_wait(self, gcode, timeout=5.0):
        """Send G-code and wait for response"""
        try:
            response = await self.send_request(
                "printer.gcode.script",
                {"script": gcode},
                timeout=timeout
            )
            return response
        except Exception as e:
            print(f"Error sending gcode with wait: {e}")
            return None
    
    async def get_printer_objects(self, objects=None):
        """Get printer object status"""
        try:
            response = await self.send_request(
                "printer.objects.query",
                {"objects": objects or {}},
                timeout=3.0
            )
            return response.get('result', {})
        except Exception as e:
            print(f"Error getting printer objects: {e}")
            return {}
    
    def add_message_handler(self, handler):
        """Add a handler for incoming notifications"""
        self.message_handlers.append(handler)
    
    def remove_message_handler(self, handler):
        """Remove a message handler"""
        if handler in self.message_handlers:
            self.message_handlers.remove(handler)