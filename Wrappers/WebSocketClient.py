import websocket
import threading
import queue
import time
import json

class WebSocketClient:
    def __init__(self, url):
        self.url = url
        self.ws = None
        self.wst = None
        self._io_lock = threading.Lock()
        # Queue to pass messages from the WS thread to the main thread
        self.message_queue = queue.Queue()
        # Event to pause the main thread until the connection is fully open
        self.connected_event = threading.Event()

    def connect(self):
        self.ws = websocket.WebSocketApp(
            self.url,
            on_open=self.on_open,
            on_message=self.on_message,
            on_error=self.on_error,
            on_close=self.on_close
        )

        # Run the WebSocket connection in a separate background thread
        self.wst = threading.Thread(
            target=self.ws.run_forever, 
            kwargs={"ping_interval": 10, "ping_timeout": 5}
        )
        # Daemon threads exit automatically when the main program exits
        self.wst.daemon = True 
        self.wst.start()

        # Block the main thread until on_open triggers
        self.connected_event.wait()

    def on_open(self, ws):
        # Signal the main thread that we are ready to send messages
        self.connected_event.set()

    def on_message(self, ws, message):
        # Put incoming messages into the queue for the main thread to read
        self.message_queue.put(message)

    def on_error(self, ws, error):
        print(f"Error: {error}")

    def on_close(self, ws, close_status_code, close_msg):
        self.connected_event.clear()

    def send(self, message):
        with self._io_lock:
            if self.ws and self.connected_event.is_set():
                self.ws.send(message)
            else:
                print("Cannot send message. WebSocket is not connected.")

    def send_and_wait_for(self, message, target_id, timeout=10):
        """Sends a message and collects responses until target_reply is found."""

        with self._io_lock:
            # Clear the queue of any old messages before sending
            while not self.message_queue.empty():
                self.message_queue.get()

            self.ws.send(message)

            collected_responses = []

            while True:
                try:
                    # Block here until a message arrives or it times out
                    reply = self.message_queue.get(timeout=timeout)
                    collected_responses.append(reply)

                    reply = json.loads(reply)
                    if reply.get("id") == target_id:
                        return reply  # Return the target reply immediately when found

                except queue.Empty:
                    print(f"Timeout: Did not receive '{target_id}' within {timeout} seconds.")
                    break
            return None

    def close(self):
        if self.ws:
            self.ws.close()

# --- Example Usage ---
if __name__ == "__main__":
    # Using an echo server for testing
    client = WebSocketClient("ws://10.34.243.54:7125/websocket")
    client.connect()

    # The connection is now maintained in the background. 
    # We can send messages whenever we want from the main thread.
    
    # 1. Send a message and wait for it to echo back
    print("\n--- Test 1 ---")
    subscribe_req = {
            "jsonrpc": "2.0",
            "method": "printer.objects.subscribe",
            "params": {
                "objects": {
                    "toolhead": ["position"]
                }
            },
            "id": 1
        }
    response = client.send_and_wait_for(json.dumps(subscribe_req), target_id=1, timeout=5)
    print(f"Final response: {response}")
    
    # Do some other work in the main thread while the WS stays alive
    print("\nDoing some other work...")
    time.sleep(10) 

    # 2. Send another message
    print("\n--- Test 2 ---")
    responses = client.send_and_wait_for(json.dumps(subscribe_req), target_id=1, timeout=5)
    print(f"Final response: {responses}")
    
    # Clean up
    client.close()