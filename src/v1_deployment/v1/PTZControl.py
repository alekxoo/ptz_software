#!/usr/bin/env python3
"""
PTZ Camera Control Library
Replaces StepperControl.py and ServoControl.py for v4l2-ctl based PTZ camera
Written by: Assistant
Date: July 2025
"""

import subprocess
import threading
import time

class PTZController:
    def __init__(self):
        # Position limits based on camera specs
        self.PAN_MIN = -612000
        self.PAN_MAX = 612000
        self.TILT_MIN = -108000
        self.TILT_MAX = 324000
        self.ZOOM_MIN = 0
        self.ZOOM_MAX = 6368
        
        # Current positions (software tracking)
        self.current_pan = 0
        self.current_tilt = 0
        self.current_zoom = 0
        
        # Default/home positions
        self.home_pan = -612000
        self.home_tilt = -108000
        self.home_zoom = 0
        
        # Movement increments for manual control
        self.pan_increment = 5000
        self.tilt_increment = 5000
        self.zoom_increment = 100
        
        # Lock for thread safety
        self.lock = threading.Lock()
        
        # Initialize camera to home position
        self.initialize_camera()
    
    def clamp_value(self, value, min_val, max_val):
        """Clamp value within specified range"""
        return max(min_val, min(max_val, int(value)))
    
    def send_v4l2_command(self, control, value):
        """Send v4l2-ctl command to camera"""
        try:
            args = ["v4l2-ctl", f"--set-ctrl={control}={value}"]
            result = subprocess.run(args, capture_output=True, text=True, timeout=5)
            if result.returncode != 0:
                print(f"v4l2-ctl error: {result.stderr}")
                return False
            return True
        except subprocess.TimeoutExpired:
            print(f"v4l2-ctl timeout for {control}={value}")
            return False
        except Exception as e:
            print(f"v4l2-ctl exception: {e}")
            return False
    
    def initialize_camera(self):
        """Initialize camera to home position on startup"""
        print("Initializing PTZ camera to home position...")
        
        # Reset to home positions
        self.set_pan_absolute(self.home_pan)
        self.set_tilt_absolute(self.home_tilt)
        self.set_zoom_absolute(self.home_zoom)
        
        # Wait for movements to complete (zoom takes longest)
        print("Waiting for camera to reach home position...")
        time.sleep(3.0)  # Adjust based on your camera's speed
        print("Camera initialization complete.")
    
    def set_pan_absolute(self, value):
        """Set absolute pan position"""
        with self.lock:
            clamped_value = self.clamp_value(value, self.PAN_MIN, self.PAN_MAX)
            if self.send_v4l2_command("pan_absolute", clamped_value):
                self.current_pan = clamped_value
                return True
            return False
    
    def set_tilt_absolute(self, value):
        """Set absolute tilt position"""
        with self.lock:
            clamped_value = self.clamp_value(value, self.TILT_MIN, self.TILT_MAX)
            if self.send_v4l2_command("tilt_absolute", clamped_value):
                self.current_tilt = clamped_value
                return True
            return False
    
    def set_zoom_absolute(self, value):
        """Set absolute zoom position"""
        with self.lock:
            clamped_value = self.clamp_value(value, self.ZOOM_MIN, self.ZOOM_MAX)
            if self.send_v4l2_command("zoom_absolute", clamped_value):
                self.current_zoom = clamped_value
                return True
            return False
    
    def vel_x(self, velocity):
        """Pan velocity control (replaces StepperControl.vel_x)"""
        def move_pan():
            # Convert velocity to position change
            # Adjust multiplier based on your desired responsiveness
            position_change = velocity * 1000  # Adjust this multiplier as needed
            new_pan = self.current_pan + position_change
            self.set_pan_absolute(new_pan)
        
        thread = threading.Thread(target=move_pan)
        thread.daemon = True
        thread.start()
    
    def vel_y(self, velocity):
        """Tilt velocity control (replaces ServoControl.vel_y)"""
        def move_tilt():
            # Convert velocity to position change
            # Adjust multiplier based on your desired responsiveness
            position_change = velocity * 1000  # Adjust this multiplier as needed
            new_tilt = self.current_tilt + position_change
            self.set_tilt_absolute(new_tilt)
        
        thread = threading.Thread(target=move_tilt)
        thread.daemon = True
        thread.start()
    
    def manual_pan_left(self):
        """Manual pan left"""
        new_pan = self.current_pan - self.pan_increment
        self.set_pan_absolute(new_pan)
    
    def manual_pan_right(self):
        """Manual pan right"""
        new_pan = self.current_pan + self.pan_increment
        self.set_pan_absolute(new_pan)
    
    def manual_tilt_up(self):
        """Manual tilt up"""
        new_tilt = self.current_tilt + self.tilt_increment
        self.set_tilt_absolute(new_tilt)
    
    def manual_tilt_down(self):
        """Manual tilt down"""
        new_tilt = self.current_tilt - self.tilt_increment
        self.set_tilt_absolute(new_tilt)
    
    def manual_zoom_in(self):
        """Manual zoom in"""
        new_zoom = self.current_zoom + self.zoom_increment
        self.set_zoom_absolute(new_zoom)
    
    def manual_zoom_out(self):
        """Manual zoom out"""
        new_zoom = self.current_zoom - self.zoom_increment
        self.set_zoom_absolute(new_zoom)
    
    def go_home(self):
        """Return camera to home position"""
        print("Returning camera to home position...")
        self.set_pan_absolute(self.home_pan)
        self.set_tilt_absolute(self.home_tilt)
        self.set_zoom_absolute(self.home_zoom)
    
    def get_position(self):
        """Get current position as tuple (pan, tilt, zoom)"""
        with self.lock:
            return (self.current_pan, self.current_tilt, self.current_zoom)
    
    def set_increments(self, pan_inc=None, tilt_inc=None, zoom_inc=None):
        """Set movement increments for manual control"""
        if pan_inc is not None:
            self.pan_increment = pan_inc
        if tilt_inc is not None:
            self.tilt_increment = tilt_inc
        if zoom_inc is not None:
            self.zoom_increment = zoom_inc

# Global PTZ controller instance
ptz_controller = PTZController()

# Legacy function wrappers for compatibility with existing PID code
def vel_x(velocity):
    """Legacy wrapper for pan velocity control"""
    ptz_controller.vel_x(velocity)

def vel_y(velocity):
    """Legacy wrapper for tilt velocity control"""
    ptz_controller.vel_y(velocity)

if __name__ == "__main__":
    # Test the PTZ controller
    print("PTZ Controller Test")
    print("Commands: home, left, right, up, down, zin, zout, pos, quit")
    
    while True:
        try:
            cmd = input("Enter command: ").strip().lower()
            
            if cmd == "quit":
                break
            elif cmd == "home":
                ptz_controller.go_home()
            elif cmd == "left":
                ptz_controller.manual_pan_left()
            elif cmd == "right":
                ptz_controller.manual_pan_right()
            elif cmd == "up":
                ptz_controller.manual_tilt_up()
            elif cmd == "down":
                ptz_controller.manual_tilt_down()
            elif cmd == "zin":
                ptz_controller.manual_zoom_in()
            elif cmd == "zout":
                ptz_controller.manual_zoom_out()
            elif cmd == "pos":
                pan, tilt, zoom = ptz_controller.get_position()
                print(f"Position - Pan: {pan}, Tilt: {tilt}, Zoom: {zoom}")
            else:
                print("Unknown command")
                
        except KeyboardInterrupt:
            break
        except Exception as e:
            print(f"Error: {e}")
    
    print("PTZ Controller test finished.")