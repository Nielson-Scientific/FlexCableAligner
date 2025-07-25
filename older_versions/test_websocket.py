import pygame
import time
import threading
import json
from websocket import create_connection
import tkinter as tk
from tkinter import ttk, messagebox

# CONFIG
PRINTER_WS_URL = "ws://products.local:7125/websocket"  # Replace with your Pi's IP
JOG_INTERVAL = 0.05  # seconds between jog commands
MAX_JOG_DISTANCE = 0.5  # mm per jog
MAX_JOG_DISTANCE_FINE = 0.1  # mm for fine movements
FEEDRATE = 700  # mm/min
FEEDRATE_FINE = 100  # mm/min for fine movements
DEADZONE = 0.15  # stick sensitivity threshold

class JoystickController:
    def __init__(self):
        self.fine_mode = False
        self.positions = {'x': 0.0, 'y': 0.0, 'u': 0.0, 'v': 0.0, 'saved': []}
        self.ws = None
        self.joystick = None
        self.jog_thread = None
        self.running = False
        self.connected = False
        
        # Initialize pygame
        pygame.init()
        pygame.joystick.init()
        
        # Create GUI
        self.setup_gui()
        
    def setup_gui(self):
        self.root = tk.Tk()
        self.root.title("Joystick Controller")
        self.root.geometry("400x500")
        
        # Main frame
        main_frame = ttk.Frame(self.root, padding="10")
        main_frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        
        # Connection section
        connection_frame = ttk.LabelFrame(main_frame, text="Connection", padding="10")
        connection_frame.grid(row=0, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=5)
        
        self.connect_btn = ttk.Button(connection_frame, text="Connect", command=self.connect)
        self.connect_btn.grid(row=0, column=0, padx=5)
        
        self.disconnect_btn = ttk.Button(connection_frame, text="Disconnect", command=self.disconnect, state=tk.DISABLED)
        self.disconnect_btn.grid(row=0, column=1, padx=5)
        
        self.status_label = ttk.Label(connection_frame, text="Status: Disconnected", foreground="red")
        self.status_label.grid(row=1, column=0, columnspan=2, pady=5)
        
        # Controller info section
        controller_frame = ttk.LabelFrame(main_frame, text="Controller Info", padding="10")
        controller_frame.grid(row=1, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=5)
        
        self.controller_label = ttk.Label(controller_frame, text="Controller: Not detected")
        self.controller_label.grid(row=0, column=0, sticky=tk.W)
        
        # Mode section
        mode_frame = ttk.LabelFrame(main_frame, text="Mode", padding="10")
        mode_frame.grid(row=2, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=5)
        
        self.mode_label = ttk.Label(mode_frame, text="Fine Mode: OFF")
        self.mode_label.grid(row=0, column=0, sticky=tk.W)
        
        # Position section
        position_frame = ttk.LabelFrame(main_frame, text="Positions", padding="10")
        position_frame.grid(row=3, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=5)
        
        self.position_text = tk.Text(position_frame, height=4, width=40)
        self.position_text.grid(row=0, column=0, sticky=(tk.W, tk.E))

        # Saved Positions section
        saved_positions_frame = ttk.LabelFrame(main_frame, text="Saved Positions", padding="10")
        saved_positions_frame.grid(row=4, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=5)
        self.saved_positions_text = tk.Text(saved_positions_frame, height=4, width=40)
        self.saved_positions_text.grid(row=0, column=0, sticky=(tk.W, tk.E))
        
        # Configure grid weights
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)
        main_frame.columnconfigure(0, weight=1)
        
        self.update_position_display()
        
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

    def connect(self):
        """Connect to both controller and WebSocket"""
        # Check controller first
        controller_ok, controller_msg = self.check_controller()
        self.controller_label.config(text=controller_msg)
        
        if not controller_ok:
            messagebox.showerror("Controller Error", controller_msg)
            return
        
        # Try to connect to WebSocket
        try:
            self.ws = create_connection(PRINTER_WS_URL)
            self.connected = True
            self.status_label.config(text="Status: Connected", foreground="green")
            self.connect_btn.config(state=tk.DISABLED)
            self.disconnect_btn.config(state=tk.NORMAL)

            # Ensure gcode is relative
            gcode = "G91\n"  # Set relative positioning
            self.send_gcode(gcode)

            # Set initial position on carriage 1
            gcode = """
            SET_DUAL_CARRIAGE CARRIAGE=x\n
            SET_DUAL_CARRIAGE CARRIAGE=y\n
            M114\n"""  # Request current position
            self.send_gcode(gcode)
            response = self.receive_response() # The OK acknowledgement
            response = self.receive_response() # The actual position response
            response = response['params'][0].split()
            self.positions['x'] = float(response[0].split(':')[1])
            self.positions['y'] = float(response[1].split(':')[1])

            # Do the same thing for carriage 2
            gcode = """
            SET_DUAL_CARRIAGE CARRIAGE=x2\n
            SET_DUAL_CARRIAGE CARRIAGE=y2\n
            M114\n"""  # Request current position
            self.send_gcode(gcode)
            response = self.receive_response() # The OK acknowledgement
            response = self.receive_response() # The actual position response
            response = response['params'][0].split()
            self.positions['u'] = float(response[0].split(':')[1])
            self.positions['v'] = float(response[1].split(':')[1])

            # Start jogging thread
            self.running = True
            self.jog_thread = threading.Thread(target=self.jog_loop)
            self.jog_thread.daemon = True
            self.jog_thread.start()
            
            messagebox.showinfo("Success", "Connected successfully!")
            
        except Exception as e:
            messagebox.showerror("Connection Error", f"Failed to connect to printer: {str(e)}")
    
    def disconnect(self):
        """Disconnect from WebSocket and stop jogging"""
        self.running = False
        self.connected = False
        
        if self.ws:
            try:
                self.ws.close()
            except Exception as e:
                print(f"Error closing WebSocket: {e}")
            self.ws = None
        
        self.status_label.config(text="Status: Disconnected", foreground="red")
        self.connect_btn.config(state=tk.NORMAL)
        self.disconnect_btn.config(state=tk.DISABLED)
    
    def reconnect_websocket(self):
        """Reconnect to WebSocket"""
        try:
            if self.ws:
                self.ws.close()
        except Exception as e:
            print(f"Error closing WebSocket: {e}")
        
        try:
            self.ws = create_connection(PRINTER_WS_URL)
            print("Reconnected to printer WebSocket")
        except Exception as e:
            print(f"Failed to reconnect: {e}")
            self.disconnect()

    def send_gcode(self, gcode):
        """Send G-code to printer"""
        if not self.ws or not self.connected:
            return
        
        message = {
            "id": 45770,
            "jsonrpc": "2.0",
            "method": "printer.gcode.script",
            "params": {
                "script": gcode
            }
        }
        self.ws.send(json.dumps(message))

    def receive_response(self):
        """Get the position response from the printer"""
        if not self.ws or not self.connected:
            return
        
        try:
            response = self.ws.recv()
            data = json.loads(response)
            return(data)
        except Exception as e:
            print(f"Error receiving response: {e}")

    def update_position_display(self):
        """Update the position display in the GUI"""
        if hasattr(self, 'position_text'):
            self.position_text.delete(1.0, tk.END)
            self.position_text.insert(tk.END, f"X: {self.positions['x']:.3f} mm\n")
            self.position_text.insert(tk.END, f"Y: {self.positions['y']:.3f} mm\n")
            self.position_text.insert(tk.END, f"U: {self.positions['u']:.3f} mm\n")
            self.position_text.insert(tk.END, f"V: {self.positions['v']:.3f} mm")
        
        if self.positions['saved']:
            self.saved_positions_text.delete(1.0, tk.END)
            self.saved_positions_text.insert(tk.END, f"Saved: X={self.positions['saved'][0]:.3f}, Y={self.positions['saved'][1]:.3f}, U={self.positions['saved'][2]:.3f}, V={self.positions['saved'][3]:.3f}\n")
        
        # Schedule next update
        self.root.after(100, self.update_position_display)

    def jog_loop(self):
        """Main jogging loop"""
        while self.running and self.connected:
            try:
                pygame.event.pump()

                x_axis = self.joystick.get_axis(0)  # left stick X
                y_axis = -self.joystick.get_axis(1)  # left stick Y (invert for typical Y+ forward)
                u_axis = self.joystick.get_axis(2)  # right stick X (optional)
                v_axis = -self.joystick.get_axis(3)  # right stick Y (optional)

                # Check for fine mode toggle
                if self.joystick.get_button(0):  # Corresponds to a button on the joystick
                    print("Fine mode toggled")
                    self.fine_mode = not self.fine_mode
                    mode_text = "Fine Mode: ON" if self.fine_mode else "Fine Mode: OFF"
                    self.root.after(0, lambda: self.mode_label.config(text=mode_text))
                    time.sleep(0.5)  # Debounce delay

                if self.joystick.get_button(1):
                    self.positions['saved'] = ((self.positions['x'], self.positions['y'], self.positions['u'], self.positions['v']))
                    time.sleep(0.5)  # Debounce delay

                # if self.joystick.get_button(2):
                #     self.positions['x'] = 0.0
                #     self.positions['y'] = 0.0
                #     self.positions['u'] = 0.0
                #     self.positions['v'] = 0.0
                #     time.sleep(0.5)

                if self.joystick.get_button(3):
                    pos = self.positions['saved']
                    gcode = f"""
                    G90\n
                    SET_DUAL_CARRIAGE CARRIAGE=x\n
                    SET_DUAL_CARRIAGE CARRIAGE=y\n
                    G0 X{pos[0]:.3f} Y{pos[1]:.3f}\n
                    SET_DUAL_CARRIAGE CARRIAGE=x2\n
                    SET_DUAL_CARRIAGE CARRIAGE=y2\n
                    G0 X{pos[2]:.3f} Y{pos[3]:.3f}\n
                    G91\n"""
                    self.send_gcode(gcode)
                    self.positions['x'] = pos[0]
                    self.positions['y'] = pos[1]
                    self.positions['u'] = pos[2]
                    self.positions['v'] = pos[3]
                    time.sleep(0.5)

                # Apply deadzone
                jog_distance = MAX_JOG_DISTANCE_FINE if self.fine_mode else MAX_JOG_DISTANCE
                feedrate = FEEDRATE_FINE if self.fine_mode else FEEDRATE
                x = x_axis if abs(x_axis) > DEADZONE else 0.0
                y = y_axis if abs(y_axis) > DEADZONE else 0.0
                u = u_axis if abs(u_axis) > DEADZONE else 0.0
                v = v_axis if abs(v_axis) > DEADZONE else 0.0

                if x != 0.0 or y != 0.0:
                    dx = round(x * jog_distance, 3)
                    dy = round(y * jog_distance, 3)
                    self.positions['x'] += dx
                    self.positions['y'] += dy

                    gcode = "SET_DUAL_CARRIAGE CARRIAGE=x\nSET_DUAL_CARRIAGE CARRIAGE=y\n"
                    gcode += f"G1 X{dx} Y{dy} F{feedrate}\n"
                    try:
                        self.send_gcode(gcode)
                    except Exception as e:
                        print(f"Error sending gcode: {e}")
                        self.reconnect_websocket()

                elif u != 0.0 or v != 0.0:
                    du = round(u * MAX_JOG_DISTANCE, 3)
                    dv = round(v * MAX_JOG_DISTANCE, 3)
                    self.positions['u'] += du
                    self.positions['v'] += dv

                    gcode = "SET_DUAL_CARRIAGE CARRIAGE=x2\nSET_DUAL_CARRIAGE CARRIAGE=y2\n"
                    gcode += f"G1 X{du} Y{dv} F{feedrate}\n"
                    try:
                        self.send_gcode(gcode)
                    except Exception as e:
                        print(f"Error sending gcode: {e}")
                        self.reconnect_websocket()
                        
                time.sleep(JOG_INTERVAL)
                
            except Exception as e:
                print(f"Error in jog loop: {e}")
                break

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
    app = JoystickController()
    app.run()

if __name__ == "__main__":
    main()
