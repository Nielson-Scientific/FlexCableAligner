import asyncio
import sys
import os
import tkinter as tk
import logging

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Add include and src to path if needed for clean imports
sys.path.append(os.path.join(os.path.dirname(__file__), 'include'))
sys.path.append(os.path.join(os.path.dirname(__file__), 'src'))

try:
    from include.AsyncWebClient import AsyncWebSocketClient
    from src.CarriageController import CarriageController
    from src.CSVHandler import CSVHandler
    from src.App import App, run_tk
except ImportError as e:
    logging.error(f"Failed to import modules: {e}")
    sys.exit(1)

async def main():
    # WebSocket URL from existing config
    url = "ws://172.16.55.2:7125/websocket?token=4deca56b67664a47bb4d59e4ee628d10"
    
    logging.info(f"Starting FlexCableAligner with connection to {url}")

    # Initialize components
    client = AsyncWebSocketClient(url)
    controller = CarriageController(client)
    csv_handler = CSVHandler()
    
    # Get the current loop
    loop = asyncio.get_running_loop()
    
    # Initialize UI
    root = App(loop, csv_handler, controller, client)
    
    # Run the application loop
    try:
        await run_tk(root)
    except KeyboardInterrupt:
        pass
    except tk.TclError:
        pass # Window closed
    finally:
        pass
        # Graceful shutdown if needed
        # if client.connected:
        #     await client.disconnect()

if __name__ == "__main__":
    if sys.platform == 'win32':
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
        
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
