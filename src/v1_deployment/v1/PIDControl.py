#PID control library for PTZ Camera
#Written by: Abdullah Alwakeel
#Updated for PTZ Camera: July 2025

from PTZControl import vel_x, vel_y

# PID gains - adjust these based on your camera's responsiveness
PX = 8.0    # Pan proportional gain
IX = 0.2    # Pan integral gain

PY = -8.0   # Tilt proportional gain (negative because camera coordinates may be inverted)
IY = 0.1    # Tilt integral gain

i_x_acc = 0.0 # Accumulated integral error for pan
i_y_acc = 0.0 # Accumulated integral error for tilt

time_since_last_detection = 0 # Frames without detection

# Deadband to prevent jittery movements when target is close to center
DEADBAND_X = 0.02  # 2% deadband for pan
DEADBAND_Y = 0.02  # 2% deadband for tilt

def PID_reset():
    """Reset PID controller state"""
    print("PID resetting...")
    global i_x_acc, i_y_acc
    i_x_acc = 0.0
    i_y_acc = 0.0
    vel_x(0.0)  # Stop pan movement
    vel_y(0.0)  # Stop tilt movement

def PID(x_norm, y_norm, delta_time, detection):
    """
    PID controller for PTZ camera tracking
    
    Args:
        x_norm: Normalized x position (0.0 to 1.0, where 0.5 is center)
        y_norm: Normalized y position (0.0 to 1.0, where 0.5 is center) 
        delta_time: Time since last update (seconds)
        detection: Boolean indicating if target is detected
    """
    global i_y_acc, i_x_acc, time_since_last_detection
    
    if not detection:
        time_since_last_detection += 1
        # Reset PID after losing target for too long (2 seconds at 30fps)
        if time_since_last_detection > 60 and (abs(i_x_acc) > 0 or abs(i_y_acc) > 0):
            PID_reset()
            time_since_last_detection = 0
    else:
        time_since_last_detection = 0
        
        # Calculate error from center (0.5, 0.5)
        x_error = x_norm - 0.5
        y_error = y_norm - 0.5
        
        # Apply deadband to prevent jittery movements
        if abs(x_error) < DEADBAND_X:
            x_error = 0.0
        if abs(y_error) < DEADBAND_Y:
            y_error = 0.0
        
        # Only accumulate integral if we have a significant error
        # This prevents windup when target is close to center
        if abs(x_error) > DEADBAND_X and delta_time > 0:
            i_x_acc += (delta_time * x_error)
            # Clamp integral accumulator to prevent windup
            i_x_acc = max(-1.0, min(1.0, i_x_acc))
        
        if abs(y_error) > DEADBAND_Y and delta_time > 0:
            i_y_acc += (delta_time * y_error)
            # Clamp integral accumulator to prevent windup  
            i_y_acc = max(-1.0, min(1.0, i_y_acc))
        
        # Calculate PID output
        pan_output = PX * x_error + IX * i_x_acc
        tilt_output = PY * y_error + IY * i_y_acc
        
        # Clamp outputs to reasonable ranges
        pan_output = max(-5.0, min(5.0, pan_output))
        tilt_output = max(-5.0, min(5.0, tilt_output))
        
        # Send velocity commands to PTZ controller
        vel_x(pan_output)
        vel_y(tilt_output)
        
        # Debug output
        if abs(x_error) > DEADBAND_X or abs(y_error) > DEADBAND_Y:
            print(f"PID: x_err={x_error:.3f}, y_err={y_error:.3f}, "
                  f"pan_out={pan_output:.3f}, tilt_out={tilt_output:.3f}")

def set_pid_gains(px=None, ix=None, py=None, iy=None):
    """
    Update PID gains dynamically
    
    Args:
        px: Pan proportional gain
        ix: Pan integral gain  
        py: Tilt proportional gain
        iy: Tilt integral gain
    """
    global PX, IX, PY, IY
    
    if px is not None:
        PX = px
    if ix is not None:
        IX = ix
    if py is not None:
        PY = py
    if iy is not None:
        IY = iy
    
    print(f"PID gains updated: PX={PX}, IX={IX}, PY={PY}, IY={IY}")

def set_deadband(x_deadband=None, y_deadband=None):
    """
    Update deadband values
    
    Args:
        x_deadband: Pan deadband (normalized, 0.0 to 1.0)
        y_deadband: Tilt deadband (normalized, 0.0 to 1.0)
    """
    global DEADBAND_X, DEADBAND_Y
    
    if x_deadband is not None:
        DEADBAND_X = x_deadband
    if y_deadband is not None:
        DEADBAND_Y = y_deadband
    
    print(f"Deadband updated: X={DEADBAND_X}, Y={DEADBAND_Y}")

if __name__ == "__main__":
    # Test the PID controller
    print("PID Controller Test")
    print("Simulating tracking a target moving around the frame")
    
    import time
    import math
    
    # Simulate a target moving in a circle
    for i in range(100):
        t = i * 0.1
        x = 0.5 + 0.2 * math.cos(t)  # X position oscillating around center
        y = 0.5 + 0.2 * math.sin(t)  # Y position oscillating around center
        
        PID(x, y, 0.033, True)  # 30 FPS simulation
        time.sleep(0.033)
    
    # Test loss of target
    print("Simulating target loss...")
    for i in range(70):
        PID(0.0, 0.0, 0.033, False)
        time.sleep(0.033)
    
    print("PID test complete")