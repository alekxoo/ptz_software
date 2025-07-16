#!/usr/bin/env python3
"""
Ultra-Smooth VISCA Control - Optimized for continuous movement
"""

import socket
import tkinter as tk
import threading
import time

class VISCAController:
    def __init__(self, camera_ip="192.168.100.88"):
        self.camera_ip = camera_ip
        self.socket = None
        self.connected = False
        
        # Track actual movement state (not key events)
        self.pan_state = 0    # -1=left, 0=stop, 1=right
        self.tilt_state = 0   # -1=down, 0=stop, 1=up
        
        # Add movement lock to prevent command conflicts
        self.movement_lock = threading.Lock()
        
    def connect(self):
        try:
            self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.socket.settimeout(2.0)
            self.socket.connect((self.camera_ip, 5678))
            self.connected = True
            print(f"✓ Connected to {self.camera_ip}")
            return True
        except Exception as e:
            print(f"✗ Connection failed: {e}")
            return False
    
    def send_visca(self, cmd, name):
        if self.connected:
            try:
                print(f"VISCA: {name}")
                self.socket.send(bytes(cmd))
                return True
            except Exception as e:
                print(f"Send failed: {e}")
                self.connected = False
                return False
        return False
    
    def update_movement(self, new_pan, new_tilt):
        """Only send command if movement state actually changes"""
        with self.movement_lock:
            if new_pan == self.pan_state and new_tilt == self.tilt_state:
                return  # No change, don't send anything
            
            # State changed - update and send command
            self.pan_state = new_pan
            self.tilt_state = new_tilt
            
            # Convert to VISCA direction codes
            if new_pan == -1:
                pan_dir = 0x01  # left
            elif new_pan == 1:
                pan_dir = 0x02  # right
            else:
                pan_dir = 0x03  # stop
                
            if new_tilt == 1:
                tilt_dir = 0x01  # up
            elif new_tilt == -1:
                tilt_dir = 0x02  # down
            else:
                tilt_dir = 0x03  # stop
            
            # Send combined PTZ command with configurable speed
            cmd = [0x81, 0x01, 0x06, 0x01, self.pan_tilt_speed, self.pan_tilt_speed, pan_dir, tilt_dir, 0xFF]
            
            # Create readable description
            pan_desc = {-1: "LEFT", 0: "STOP", 1: "RIGHT"}[new_pan]
            tilt_desc = {-1: "DOWN", 0: "STOP", 1: "UP"}[new_tilt]
            
            self.send_visca(cmd, f"Pan {pan_desc} + Tilt {tilt_desc}")
    
    def stop_all(self):
        self.update_movement(0, 0)
    
    def home(self):
        self.stop_all()
        cmd = [0x81, 0x01, 0x06, 0x04, 0xFF]
        self.send_visca(cmd, "HOME")
    
    def zoom_stop(self):
        cmd = [0x81, 0x01, 0x04, 0x07, 0x00, 0xFF]
        self.send_visca(cmd, "ZOOM STOP")
    
    def zoom_tele(self, variable_speed=False):
        if variable_speed:
            cmd = [0x81, 0x01, 0x04, 0x07, 0x24, 0xFF]  # Variable speed
        else:
            cmd = [0x81, 0x01, 0x04, 0x07, 0x02, 0xFF]  # Standard speed
        self.send_visca(cmd, "ZOOM TELE")
    
    def zoom_wide(self, variable_speed=False):
        if variable_speed:
            cmd = [0x81, 0x01, 0x04, 0x07, 0x34, 0xFF]  # Variable speed
        else:
            cmd = [0x81, 0x01, 0x04, 0x07, 0x03, 0xFF]  # Standard speed
        self.send_visca(cmd, "ZOOM WIDE")
    
    def disconnect(self):
        if self.socket:
            self.stop_all()
            self.socket.close()
            self.connected = False


class SmoothKeyboardControl:
    def __init__(self, camera_ip="192.168.100.88", pan_tilt_speed=0x18):
        self.visca = VISCAController(camera_ip)
        self.visca.pan_tilt_speed = pan_tilt_speed  # Allow customization
        
        if not self.visca.connect():
            print("Connection failed!")
            return
        
        # Track which keys are ACTUALLY down with debouncing
        self.keys_currently_down = set()
        self.key_state_stable = True
        self.last_key_change_time = 0
        
        # Track zoom state
        self.zoom_state = 0  # -1=wide, 0=stop, 1=tele
        
        # Movement speed options (you can experiment with these)
        self.pan_tilt_speed = pan_tilt_speed  # Use the passed parameter
        
        # Reduce polling interval for smoother response
        self.poll_interval = 20  # 20ms = 50Hz, much smoother
        
        # Debounce settings
        self.debounce_time = 0.05  # 50ms debounce
        
        # Create window
        self.root = tk.Tk()
        self.root.title("Ultra-Smooth VISCA Control")
        self.root.geometry("400x300")
        
        info = tk.Label(self.root, text="""
Ultra-Smooth VISCA Camera Control

Hold Arrow Keys: Pan/Tilt
Q/E: Zoom Wide/Tele
Space: Stop All
Home: Reset
ESC: Quit

Optimized for smooth continuous movement!
""", font=("Arial", 12), justify=tk.LEFT)
        info.pack(expand=True)
        
        self.status = tk.Label(self.root, text="Ready", font=("Arial", 12, "bold"))
        self.status.pack(pady=10)
        
        # Bind key events with better handling
        self.root.bind('<KeyPress>', self.on_key_press)
        self.root.bind('<KeyRelease>', self.on_key_release)
        self.root.bind('<FocusIn>', self.on_focus_in)
        self.root.bind('<FocusOut>', self.on_focus_out)
        self.root.focus_set()
        self.root.protocol("WM_DELETE_WINDOW", self.cleanup)
        
        # Start key state monitoring with higher frequency
        self.check_key_state()
        
        print("Ultra-Smooth VISCA Control Ready!")
        print("Optimized for continuous smooth movement.")
    
    def on_key_press(self, event):
        key = event.keysym
        current_time = time.time()
        
        # Handle special keys immediately
        if key == 'space':
            self.visca.stop_all()
            self.visca.zoom_stop()
            self.keys_currently_down.clear()
            self.status.config(text="STOPPED")
            return
        elif key == 'Home':
            self.visca.home()
            self.visca.zoom_stop()
            self.keys_currently_down.clear()
            self.status.config(text="HOMING")
            return
        elif key == 'Escape':
            self.cleanup()
            return
        
        # For movement and zoom keys, add to set and mark state as potentially unstable
        if key in ['Left', 'Right', 'Up', 'Down', 'q', 'e', 'Q', 'E']:
            if key not in self.keys_currently_down:
                self.keys_currently_down.add(key)
                self.last_key_change_time = current_time
                self.key_state_stable = False
    
    def on_key_release(self, event):
        key = event.keysym
        current_time = time.time()
        
        # Remove key from currently pressed set
        if key in self.keys_currently_down:
            self.keys_currently_down.discard(key)
            self.last_key_change_time = current_time
            self.key_state_stable = False
    
    def on_focus_in(self, event):
        """When window gains focus, clear key state to prevent stuck keys"""
        pass
    
    def on_focus_out(self, event):
        """When window loses focus, stop all movement"""
        self.keys_currently_down.clear()
        self.visca.stop_all()
        self.status.config(text="Focus Lost - Stopped")
    
    def check_key_state(self):
        """Check if the key state has actually changed and update movement"""
        current_time = time.time()
        
        # Check if key state has been stable for debounce period
        if not self.key_state_stable:
            if current_time - self.last_key_change_time >= self.debounce_time:
                self.key_state_stable = True
                self.update_camera_movement()
        else:
            # Even if stable, still update periodically to catch any missed events
            self.update_camera_movement()
        
        # Schedule next check with higher frequency
        self.root.after(self.poll_interval, self.check_key_state)
    
    def update_camera_movement(self):
        """Calculate desired movement based on currently pressed keys"""
        # Calculate pan state
        pan_state = 0
        if 'Left' in self.keys_currently_down:
            pan_state = -1
        elif 'Right' in self.keys_currently_down:
            pan_state = 1
        
        # Calculate tilt state
        tilt_state = 0
        if 'Up' in self.keys_currently_down:
            tilt_state = 1
        elif 'Down' in self.keys_currently_down:
            tilt_state = -1
        
        # Calculate zoom state
        zoom_state = 0
        if 'q' in self.keys_currently_down or 'Q' in self.keys_currently_down:
            zoom_state = -1  # Wide
        elif 'e' in self.keys_currently_down or 'E' in self.keys_currently_down:
            zoom_state = 1   # Tele
        
        # Update camera movement (only sends command if state changed)
        self.visca.update_movement(pan_state, tilt_state)
        
        # Update zoom (only if state changed)
        if zoom_state != self.zoom_state:
            self.zoom_state = zoom_state
            if zoom_state == -1:
                self.visca.zoom_wide(variable_speed=True)
            elif zoom_state == 1:
                self.visca.zoom_tele(variable_speed=True)
            else:
                self.visca.zoom_stop()
        
        # Update status
        movements = []
        if pan_state == -1:
            movements.append("Pan Left")
        elif pan_state == 1:
            movements.append("Pan Right")
        if tilt_state == 1:
            movements.append("Tilt Up")
        elif tilt_state == -1:
            movements.append("Tilt Down")
        if zoom_state == -1:
            movements.append("Zoom Wide")
        elif zoom_state == 1:
            movements.append("Zoom Tele")
        
        if movements:
            self.status.config(text=" + ".join(movements))
        else:
            self.status.config(text="Ready")
    
    def cleanup(self):
        print("Shutting down...")
        self.visca.stop_all()
        self.visca.zoom_stop()
        self.visca.disconnect()
        self.root.destroy()
    
    def run(self):
        try:
            self.root.mainloop()
        except KeyboardInterrupt:
            self.cleanup()


def main():
    print("Ultra-Smooth VISCA Keyboard Control")
    print("=" * 40)
    print("Optimized for smooth continuous movement")
    print("Higher polling rate and better debouncing!")
    print("")
    print("Speed options:")
    print("  0x08 = Slow (less acceleration)")
    print("  0x10 = Medium (original speed)")
    print("  0x18 = Fast (maximum speed)")
    print("")
    
    # You can change the speed here - try 0x10 or 0x08 for less acceleration
    controller = SmoothKeyboardControl("192.168.100.88", pan_tilt_speed=0x10)
    controller.run()

if __name__ == "__main__":
    main()