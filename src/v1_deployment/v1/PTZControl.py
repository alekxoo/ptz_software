#!/usr/bin/env python3
"""
PTZ Camera Control Library - VISCA Version
Replaces v4l2-ctl with smooth VISCA TCP commands
Written by: Assistant
Date: July 2025
"""

import socket
import threading
import time

class PTZController:
    def __init__(self, camera_ip="192.168.100.88", camera_port=5678):
        self.camera_ip = camera_ip
        self.camera_port = camera_port
        self.socket = None
        self.connected = False
        
        # Movement state tracking
        self.pan_state = 0    # -1=left, 0=stop, 1=right
        self.tilt_state = 0   # -1=down, 0=stop, 1=up
        self.zoom_state = 0   # -1=wide, 0=stop, 1=tele
        
        # Position limits (VISCA uses different ranges than v4l2-ctl)
        # These are approximate - adjust based on your camera specs
        self.PAN_MIN = -1728   # VISCA pan range (adjust for your camera)
        self.PAN_MAX = 1728
        self.TILT_MIN = -432   # VISCA tilt range (adjust for your camera)
        self.TILT_MAX = 1296
        self.ZOOM_MIN = 0      # VISCA zoom range
        self.ZOOM_MAX = 4000   # Adjust based on your camera
        
        # Current positions (estimated - VISCA doesn't easily provide feedback)
        self.current_pan = 0
        self.current_tilt = 0
        self.current_zoom = 0
        
        # Default/home positions
        self.home_pan = 0
        self.home_tilt = 0
        self.home_zoom = 0
        
        # Movement speeds for different controls
        # self.continuous_speed = 0x05  # Very slow  
        self.continuous_speed = 0x08  # Slow
        # self.continuous_speed = 0x10  # Medium (what your manual_speed uses)
        # self.continuous_speed = 0x18  # Max speed for continuous movement
        self.manual_speed = 0x15      # Slightly slower for manual steps
        
        # Movement increments for manual control (in VISCA units)
        self.pan_increment = 200    # Adjust these based on desired step size
        self.tilt_increment = 100
        self.zoom_increment = 100
        
        # Lock for thread safety
        self.lock = threading.Lock()
        
        self.last_cmd_time = 0.0
        
        # Initialize camera connection
        self.initialize_camera()
    
    def connect(self):
        """Establish VISCA TCP connection"""
        try:
            self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.socket.settimeout(2.0)
            self.socket.connect((self.camera_ip, self.camera_port))
            self.connected = True
            print(f"✓ Connected to VISCA camera at {self.camera_ip}:{self.camera_port}")
            return True
        except Exception as e:
            print(f"✗ VISCA connection failed: {e}")
            return False
    
    def send_visca_command(self, cmd, description=""):
        """Send VISCA command and measure timing"""
        if not self.connected:
            return False
        
        try:
            cmd_start = time.time()
            self.socket.send(bytes(cmd))
            self.last_cmd_time = (time.time() - cmd_start) * 1000
            
            if description:
                print(f"VISCA: {description}")
            return True
        except Exception as e:
            print(f"VISCA send failed: {e}")
            self.connected = False
            return False
        
    def update_position_from_camera(self):
        """Periodically update position from camera (call this regularly)"""
        if not self.connected:
            return
        
        # Query pan/tilt position
        pan_tilt_response = self.send_visca_inquiry([0x81, 0x09, 0x06, 0x12, 0xFF], "")
        if pan_tilt_response and len(pan_tilt_response) >= 11:
            try:
                if pan_tilt_response[0] == 0x90 and pan_tilt_response[1] == 0x50:
                    # Extract pan position
                    pan_bytes = pan_tilt_response[2:6]
                    pan = (pan_bytes[0] << 12) | (pan_bytes[1] << 8) | (pan_bytes[2] << 4) | pan_bytes[3]
                    
                    # Extract tilt position
                    tilt_bytes = pan_tilt_response[6:10]
                    tilt = (tilt_bytes[0] << 12) | (tilt_bytes[1] << 8) | (tilt_bytes[2] << 4) | tilt_bytes[3]
                    
                    # Convert from unsigned to signed
                    if pan > 32767:
                        pan -= 65536
                    if tilt > 32767:
                        tilt -= 65536
                    
                    with self.lock:
                        self.current_pan = pan
                        self.current_tilt = tilt
            except Exception as e:
                print(f"Error updating pan/tilt: {e}")
        
        # Query zoom position
        zoom_response = self.send_visca_inquiry([0x81, 0x09, 0x04, 0x47, 0xFF], "")
        if zoom_response and len(zoom_response) >= 7:
            try:
                if zoom_response[0] == 0x90 and zoom_response[1] == 0x50:
                    zoom_bytes = zoom_response[2:6]
                    zoom = (zoom_bytes[0] << 12) | (zoom_bytes[1] << 8) | (zoom_bytes[2] << 4) | zoom_bytes[3]
                    
                    with self.lock:
                        self.current_zoom = zoom
            except Exception as e:
                print(f"Error updating zoom: {e}")
    def send_visca_inquiry(self, cmd, description=""):
        """Send VISCA inquiry command and return response"""
        if not self.connected:
            return None
        
        try:
            cmd_start = time.time()
            self.socket.send(bytes(cmd))
            
            # Read response (VISCA responses are typically 7-11 bytes)
            response = self.socket.recv(16)
            self.last_cmd_time = (time.time() - cmd_start) * 1000
            
            if description:
                print(f"VISCA INQ: {description}")
            return response
        except Exception as e:
            print(f"VISCA inquiry failed: {e}")
            return None
    
    def initialize_camera(self):
        """Initialize camera connection and move to home position"""
        print("Initializing VISCA PTZ camera...")
        
        if not self.connect():
            print("Failed to connect to camera!")
            return False
        
        # Stop any current movement
        self.stop_all_movement()
        
        # Move to home position
        print("Moving to home position...")
        self.go_home()
        
        # Wait for movement to complete
        time.sleep(3.0)
        print("VISCA camera initialization complete.")
        return True
    
    def update_continuous_movement_with_variable_speed(self, new_pan, new_tilt, pan_speed=None, tilt_speed=None):
        """Update continuous movement state with variable speeds"""
        with self.lock:
            state_changed = False
            
            if new_pan != self.pan_state or new_tilt != self.tilt_state:
                self.pan_state = new_pan
                self.tilt_state = new_tilt
                state_changed = True
                
                # Use variable speed for pan if provided, otherwise use continuous_speed
                actual_pan_speed = pan_speed if pan_speed is not None else self.continuous_speed
                actual_tilt_speed = tilt_speed if tilt_speed is not None else self.continuous_speed
                
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
                
                # Send combined PTZ command with variable speeds
                cmd = [0x81, 0x01, 0x06, 0x01, actual_pan_speed, actual_tilt_speed, pan_dir, tilt_dir, 0xFF]
                
                # Create description
                pan_desc = {-1: "LEFT", 0: "STOP", 1: "RIGHT"}[new_pan]
                tilt_desc = {-1: "DOWN", 0: "STOP", 1: "UP"}[new_tilt]
                speed_desc = f"(PanSpeed: 0x{actual_pan_speed:02X}, TiltSpeed: 0x{actual_tilt_speed:02X})"
                
                self.send_visca_command(cmd, f"Pan {pan_desc} + Tilt {tilt_desc} {speed_desc}")
            
            return state_changed
    
    def update_continuous_movement(self, new_pan, new_tilt, new_zoom=None):
        """Update continuous movement state - only sends command if state changes"""
        with self.lock:
            state_changed = False
            
            if new_pan != self.pan_state or new_tilt != self.tilt_state:
                self.pan_state = new_pan
                self.tilt_state = new_tilt
                state_changed = True
                
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
                
                # Send combined PTZ command
                cmd = [0x81, 0x01, 0x06, 0x01, self.continuous_speed, self.continuous_speed, pan_dir, tilt_dir, 0xFF]
                
                # Create description
                pan_desc = {-1: "LEFT", 0: "STOP", 1: "RIGHT"}[new_pan]
                tilt_desc = {-1: "DOWN", 0: "STOP", 1: "UP"}[new_tilt]
                
                self.send_visca_command(cmd, f"Pan {pan_desc} + Tilt {tilt_desc}")
            
            # Handle zoom separately if provided
            if new_zoom is not None and new_zoom != self.zoom_state:
                self.zoom_state = new_zoom
                state_changed = True
                
                if new_zoom == -1:
                    # Zoom wide
                    cmd = [0x81, 0x01, 0x04, 0x07, 0x34, 0xFF]  # Variable speed wide
                    self.send_visca_command(cmd, "ZOOM WIDE")
                elif new_zoom == 1:
                    # Zoom tele
                    cmd = [0x81, 0x01, 0x04, 0x07, 0x24, 0xFF]  # Variable speed tele
                    self.send_visca_command(cmd, "ZOOM TELE")
                else:
                    # Zoom stop
                    cmd = [0x81, 0x01, 0x04, 0x07, 0x00, 0xFF]
                    self.send_visca_command(cmd, "ZOOM STOP")
            
            return state_changed
    
    def stop_all_movement(self):
        """Stop all camera movement"""
        self.update_continuous_movement(0, 0, 0)
    
    def go_home(self):
        """Return camera to home position"""
        self.stop_all_movement()
        time.sleep(0.1)  # Brief pause
        cmd = [0x81, 0x01, 0x06, 0x04, 0xFF]
        self.send_visca_command(cmd, "HOME")
        
        # Reset position tracking
        self.current_pan = self.home_pan
        self.current_tilt = self.home_tilt
        self.current_zoom = self.home_zoom
    
    def manual_pan_left(self):
        """Manual pan left step"""
        self.current_pan = max(self.PAN_MIN, self.current_pan - self.pan_increment)
        cmd = [0x81, 0x01, 0x06, 0x01, self.manual_speed, self.manual_speed, 0x01, 0x03, 0xFF]
        self.send_visca_command(cmd, "Manual Pan Left")
        time.sleep(0.1)  # Brief movement
        self.stop_all_movement()
    
    def manual_pan_right(self):
        """Manual pan right step"""
        self.current_pan = min(self.PAN_MAX, self.current_pan + self.pan_increment)
        cmd = [0x81, 0x01, 0x06, 0x01, self.manual_speed, self.manual_speed, 0x02, 0x03, 0xFF]
        self.send_visca_command(cmd, "Manual Pan Right")
        time.sleep(0.1)  # Brief movement
        self.stop_all_movement()
    
    def manual_tilt_up(self):
        """Manual tilt up step"""
        self.current_tilt = min(self.TILT_MAX, self.current_tilt + self.tilt_increment)
        cmd = [0x81, 0x01, 0x06, 0x01, self.manual_speed, self.manual_speed, 0x03, 0x01, 0xFF]
        self.send_visca_command(cmd, "Manual Tilt Up")
        time.sleep(0.1)  # Brief movement
        self.stop_all_movement()
    
    def manual_tilt_down(self):
        """Manual tilt down step"""
        self.current_tilt = max(self.TILT_MIN, self.current_tilt - self.tilt_increment)
        cmd = [0x81, 0x01, 0x06, 0x01, self.manual_speed, self.manual_speed, 0x03, 0x02, 0xFF]
        self.send_visca_command(cmd, "Manual Tilt Down")
        time.sleep(0.1)  # Brief movement
        self.stop_all_movement()
    
    def manual_zoom_in(self):
        """Manual zoom in step"""
        self.current_zoom = min(self.ZOOM_MAX, self.current_zoom + self.zoom_increment)
        cmd = [0x81, 0x01, 0x04, 0x07, 0x24, 0xFF]  # Variable speed tele
        self.send_visca_command(cmd, "Manual Zoom In")
        time.sleep(0.15)  # Brief zoom
        cmd = [0x81, 0x01, 0x04, 0x07, 0x00, 0xFF]  # Stop zoom
        self.send_visca_command(cmd, "Zoom Stop")
    
    def manual_zoom_out(self):
        """Manual zoom out step"""
        self.current_zoom = max(self.ZOOM_MIN, self.current_zoom - self.zoom_increment)
        cmd = [0x81, 0x01, 0x04, 0x07, 0x34, 0xFF]  # Variable speed wide
        self.send_visca_command(cmd, "Manual Zoom Out")
        time.sleep(0.15)  # Brief zoom
        cmd = [0x81, 0x01, 0x04, 0x07, 0x00, 0xFF]  # Stop zoom
        self.send_visca_command(cmd, "Zoom Stop")
    
    def set_zoom_absolute(self, zoom_value):
        """Set absolute zoom position (for PID control)"""
        with self.lock:
            # Clamp zoom value to valid range
            clamped_zoom = max(self.ZOOM_MIN, min(self.ZOOM_MAX, int(zoom_value)))
            
            # VISCA absolute zoom command is more complex, so we'll use relative movement
            zoom_diff = clamped_zoom - self.current_zoom
            
            if abs(zoom_diff) > 20:  # Only move if significant difference
                if zoom_diff > 0:
                    # Need to zoom in
                    cmd = [0x81, 0x01, 0x04, 0x07, 0x24, 0xFF]  # Tele
                    self.send_visca_command(cmd, f"PID Zoom In (target: {clamped_zoom})")
                else:
                    # Need to zoom out
                    cmd = [0x81, 0x01, 0x04, 0x07, 0x34, 0xFF]  # Wide
                    self.send_visca_command(cmd, f"PID Zoom Out (target: {clamped_zoom})")
                
                # Update position tracking
                self.current_zoom = clamped_zoom
                return True
            else:
                # Stop zoom if we're close enough
                if self.zoom_state != 0:
                    cmd = [0x81, 0x01, 0x04, 0x07, 0x00, 0xFF]
                    self.send_visca_command(cmd, "PID Zoom Stop")
                    self.zoom_state = 0
                return False
    
    # def vel_x(self, velocity):
    #     """Pan velocity control for PID (replaces old vel_x function)"""
    #     # Convert velocity to movement state
    #     if velocity > 0.1:
    #         pan_state = 1   # Right
    #     elif velocity < -0.1:
    #         pan_state = -1  # Left
    #     else:
    #         pan_state = 0   # Stop
        

    def vel_x(self, velocity):
        """Pan velocity control with variable speed"""
        error_magnitude = abs(velocity)
        
        if error_magnitude > 0.01:
            # Map error magnitude to VISCA speed
            # Small errors: slow speed (0x05-0x08)
            # Large errors: faster speed (up to 0x10)
            
            # Linear mapping: 0.01 error -> 0x05 speed, 0.3 error -> 0x10 speed
            speed_range = 0x18 - 0x05 # Range from 0x05 to 0x10
            error_range = 0.3 - 0.01   # Error range we care about
            
            
            # Calculate speed based on error
            speed_factor = min(1.0, (error_magnitude - 0.01) / error_range)
            calculated_speed = 0x05 + int(speed_factor * speed_range)
            
            # Clamp speed to valid range
            visca_speed = max(0x05, min(0x10, calculated_speed))
            
            # Determine direction
            direction = 1 if velocity > 0 else -1
            
            # Send movement command with variable speed
            self.update_continuous_movement_with_variable_speed(
                direction, self.tilt_state, pan_speed=visca_speed
            )
            
            # Debug output
            print(f"Variable Speed Pan: error={error_magnitude:.3f}, speed=0x{visca_speed:02X}")
            
        else:
            # Stop pan movement
            self.update_continuous_movement_with_variable_speed(
                0, self.tilt_state, pan_speed=self.continuous_speed
            )


    
    def vel_y(self, velocity):
        """Tilt velocity control for PID (replaces old vel_y function)"""
        # Convert velocity to movement state  
        if velocity > 0.1:
            tilt_state = 1   # Up
        elif velocity < -0.1:
            tilt_state = -1  # Down
        else:
            tilt_state = 0   # Stop
        
        # Only update if state would change
        if tilt_state != self.tilt_state:
            self.update_continuous_movement(self.pan_state, tilt_state)
    
    def get_position(self):
        """Get current position as tuple (pan, tilt, zoom) - queries camera directly"""
        with self.lock:
            pan, tilt, zoom = self.current_pan, self.current_tilt, self.current_zoom
            
            # Query pan/tilt position from camera
            pan_tilt_response = self.send_visca_inquiry([0x81, 0x09, 0x06, 0x12, 0xFF], "Pan/Tilt Position Inquiry")
            if pan_tilt_response and len(pan_tilt_response) >= 11:
                try:
                    if pan_tilt_response[0] == 0x90 and pan_tilt_response[1] == 0x50:
                        # Extract pan position (4 bytes, big endian)
                        pan_bytes = pan_tilt_response[2:6]
                        pan = (pan_bytes[0] << 12) | (pan_bytes[1] << 8) | (pan_bytes[2] << 4) | pan_bytes[3]
                        
                        # Extract tilt position (4 bytes, big endian) 
                        tilt_bytes = pan_tilt_response[6:10]
                        tilt = (tilt_bytes[0] << 12) | (tilt_bytes[1] << 8) | (tilt_bytes[2] << 4) | tilt_bytes[3]
                        
                        # Convert from unsigned to signed (VISCA uses signed values)
                        if pan > 32767:
                            pan -= 65536
                        if tilt > 32767:
                            tilt -= 65536
                        
                        # Sanity check - reject crazy values
                        if abs(pan) < 10000 and abs(tilt) < 5000:
                            self.current_pan = pan
                            self.current_tilt = tilt
                        
                        print(f"Real pan/tilt: {pan}, {tilt}")
                except Exception as e:
                    print(f"Error parsing pan/tilt response: {e}")
            
            # Query zoom position with bounds checking
            zoom_response = self.send_visca_inquiry([0x81, 0x09, 0x04, 0x47, 0xFF], "Zoom Position Inquiry")
            if zoom_response and len(zoom_response) >= 7:
                try:
                    if zoom_response[0] == 0x90 and zoom_response[1] == 0x50:
                        zoom_bytes = zoom_response[2:6]
                        zoom = (zoom_bytes[0] << 12) | (zoom_bytes[1] << 8) | (zoom_bytes[2] << 4) | zoom_bytes[3]
                        
                        # Sanity check zoom value
                        if zoom < 50000:  # Reject obviously wrong values
                            self.current_zoom = zoom
                            print(f"Real zoom: {zoom}")
                        else:
                            print(f"Rejected invalid zoom: {zoom}")
                except Exception as e:
                    print(f"Error parsing zoom response: {e}")
            
            return (self.current_pan, self.current_tilt, self.current_zoom)    
        
    def set_increments(self, pan_inc=None, tilt_inc=None, zoom_inc=None):
        """Set movement increments for manual control"""
        if pan_inc is not None:
            self.pan_increment = pan_inc
        if tilt_inc is not None:
            self.tilt_increment = tilt_inc
        if zoom_inc is not None:
            self.zoom_increment = zoom_inc
    
    def set_speeds(self, continuous_speed=None, manual_speed=None):
        """Set movement speeds"""
        if continuous_speed is not None:
            self.continuous_speed = max(0x01, min(0x18, continuous_speed))
        if manual_speed is not None:
            self.manual_speed = max(0x01, min(0x18, manual_speed))
    
    def disconnect(self):
        """Disconnect from camera"""
        if self.socket:
            self.stop_all_movement()
            time.sleep(0.1)
            self.socket.close()
            self.connected = False
            print("Disconnected from VISCA camera")

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
    # Test the VISCA PTZ controller
    print("VISCA PTZ Controller Test")
    print("Commands: home, left, right, up, down, zin, zout, pos, speed, quit")
    
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
            elif cmd == "speed":
                speed = input("Enter speed (1-24, current continuous/manual): ")
                try:
                    speed_val = int(speed)
                    ptz_controller.set_speeds(continuous_speed=speed_val, manual_speed=speed_val)
                    print(f"Speed set to {speed_val}")
                except ValueError:
                    print("Invalid speed value")
            elif cmd == "test":
                print("Testing continuous movement...")
                ptz_controller.update_continuous_movement(1, 0)  # Pan right
                time.sleep(2)
                ptz_controller.update_continuous_movement(0, 1)  # Tilt up
                time.sleep(2)
                ptz_controller.update_continuous_movement(0, 0)  # Stop
            else:
                print("Unknown command")
                
        except KeyboardInterrupt:
            break
        except Exception as e:
            print(f"Error: {e}")
    
    ptz_controller.disconnect()
    print("VISCA PTZ Controller test finished.")