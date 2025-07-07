#PID control library for PTZ Camera with Autonomous Zoom
#Written by: Abdullah Alwakeel
#Updated for PTZ Camera with Zoom Control: July 2025

from PTZControl import vel_x, vel_y, ptz_controller

# PID gains - adjust these based on your camera's responsiveness
PX = 15.0    # Pan proportional gain
IX = 0.2    # Pan integral gain

PY = -15.0   # Tilt proportional gain (negative because camera coordinates may be inverted)
IY = 0.1    # Tilt integral gain

# Zoom PID gains
PZ = 2.0    # Zoom proportional gain
IZ = 0.05   # Zoom integral gain

i_x_acc = 0.0 # Accumulated integral error for pan
i_y_acc = 0.0 # Accumulated integral error for tilt
i_z_acc = 0.0 # Accumulated integral error for zoom

time_since_last_detection = 0 # Frames without detection

# Deadband to prevent jittery movements when target is close to center
DEADBAND_X = 0.02  # 2% deadband for pan
DEADBAND_Y = 0.02  # 2% deadband for tilt
DEADBAND_Z = 0.01  # 1% deadband for zoom

# Zoom control settings
TARGET_VEHICLE_SIZE = 0.2  # Target: vehicle should occupy 20% of screen (1/5)
MIN_VEHICLE_SIZE = 0.05    # Minimum size to start zooming in
MAX_VEHICLE_SIZE = 0.4     # Maximum size to start zooming out
ZOOM_ENABLED = True        # Enable/disable autonomous zoom

def calculate_bbox_size_ratio(x1, y1, x2, y2, frame_width, frame_height):
    """
    Calculate what fraction of the screen the bounding box occupies
    
    Args:
        x1, y1, x2, y2: Bounding box coordinates
        frame_width, frame_height: Frame dimensions
    
    Returns:
        float: Ratio of bbox area to frame area (0.0 to 1.0)
    """
    bbox_width = x2 - x1
    bbox_height = y2 - y1
    bbox_area = bbox_width * bbox_height
    frame_area = frame_width * frame_height
    
    size_ratio = bbox_area / frame_area
    return size_ratio

def calculate_zoom_error(current_size_ratio, target_size_ratio):
    """
    Calculate zoom error based on current and target vehicle size
    
    Args:
        current_size_ratio: Current vehicle size as fraction of screen
        target_size_ratio: Target vehicle size as fraction of screen
    
    Returns:
        float: Zoom error (positive = need to zoom in, negative = zoom out)
    """
    # If vehicle is smaller than target, we need to zoom in (positive error)
    # If vehicle is larger than target, we need to zoom out (negative error)
    zoom_error = (target_size_ratio - current_size_ratio) / target_size_ratio
    return zoom_error

def PID_reset():
    """Reset PID controller state"""
    print("PID resetting...")
    global i_x_acc, i_y_acc, i_z_acc
    i_x_acc = 0.0
    i_y_acc = 0.0
    i_z_acc = 0.0
    vel_x(0.0)  # Stop pan movement
    vel_y(0.0)  # Stop tilt movement

def PID_with_zoom(x_norm, y_norm, bbox_coords, frame_dims, delta_time, detection):
    """
    Enhanced PID controller with autonomous zoom for PTZ camera tracking
    
    Args:
        x_norm: Normalized x position (0.0 to 1.0, where 0.5 is center)
        y_norm: Normalized y position (0.0 to 1.0, where 0.5 is center) 
        bbox_coords: Tuple (x1, y1, x2, y2) of bounding box coordinates
        frame_dims: Tuple (width, height) of frame dimensions
        delta_time: Time since last update (seconds)
        detection: Boolean indicating if target is detected
    """
    global i_y_acc, i_x_acc, i_z_acc, time_since_last_detection
    
    if not detection:
        time_since_last_detection += 1
        # Reset PID after losing target for too long (2 seconds at 30fps)
        if time_since_last_detection > 60 and (abs(i_x_acc) > 0 or abs(i_y_acc) > 0 or abs(i_z_acc) > 0):
            PID_reset()
            time_since_last_detection = 0
    else:
        time_since_last_detection = 0
        
        # Calculate pan/tilt errors from center (0.5, 0.5)
        x_error = x_norm - 0.5
        y_error = y_norm - 0.5
        
        # Calculate zoom error if zoom is enabled and we have bbox info
        z_error = 0.0
        if ZOOM_ENABLED and bbox_coords and frame_dims:
            x1, y1, x2, y2 = bbox_coords
            frame_width, frame_height = frame_dims
            
            current_size_ratio = calculate_bbox_size_ratio(x1, y1, x2, y2, frame_width, frame_height)
            z_error = calculate_zoom_error(current_size_ratio, TARGET_VEHICLE_SIZE)
            
            print(f"Vehicle size: {current_size_ratio:.3f} (target: {TARGET_VEHICLE_SIZE:.3f}), zoom_error: {z_error:.3f}")
        
        # Apply deadband to prevent jittery movements
        if abs(x_error) < DEADBAND_X:
            x_error = 0.0
        if abs(y_error) < DEADBAND_Y:
            y_error = 0.0
        if abs(z_error) < DEADBAND_Z:
            z_error = 0.0
        
        # Only accumulate integral if we have a significant error
        # This prevents windup when target is close to desired position/size
        if abs(x_error) > DEADBAND_X and delta_time > 0:
            i_x_acc += (delta_time * x_error)
            # Clamp integral accumulator to prevent windup
            i_x_acc = max(-1.0, min(1.0, i_x_acc))
        
        if abs(y_error) > DEADBAND_Y and delta_time > 0:
            i_y_acc += (delta_time * y_error)
            # Clamp integral accumulator to prevent windup  
            i_y_acc = max(-1.0, min(1.0, i_y_acc))
            
        if abs(z_error) > DEADBAND_Z and delta_time > 0 and ZOOM_ENABLED:
            i_z_acc += (delta_time * z_error)
            # Clamp zoom integral accumulator
            i_z_acc = max(-0.5, min(0.5, i_z_acc))
        
        # Calculate PID output
        pan_output = PX * x_error + IX * i_x_acc
        tilt_output = PY * y_error + IY * i_y_acc
        zoom_output = PZ * z_error + IZ * i_z_acc
        
        # Clamp outputs to reasonable ranges
        pan_output = max(-5.0, min(5.0, pan_output))
        tilt_output = max(-5.0, min(5.0, tilt_output))
        zoom_output = max(-2.0, min(2.0, zoom_output))
        
        # Send velocity commands to PTZ controller
        vel_x(pan_output)
        vel_y(tilt_output)
        
        # Apply zoom control using absolute positioning
        if ZOOM_ENABLED and abs(z_error) > DEADBAND_Z:
            current_zoom = ptz_controller.current_zoom
            # Convert zoom velocity to position change
            zoom_change = int(zoom_output * 10)  # Adjust multiplier as needed
            new_zoom = current_zoom + zoom_change
            ptz_controller.set_zoom_absolute(new_zoom)
        
        # Debug output
        if abs(x_error) > DEADBAND_X or abs(y_error) > DEADBAND_Y or abs(z_error) > DEADBAND_Z:
            print(f"PID: x_err={x_error:.3f}, y_err={y_error:.3f}, z_err={z_error:.3f}")
            print(f"     pan_out={pan_output:.3f}, tilt_out={tilt_output:.3f}, zoom_out={zoom_output:.3f}")

# Backward compatibility wrapper
def PID(x_norm, y_norm, delta_time, detection):
    """Original PID function for backward compatibility"""
    PID_with_zoom(x_norm, y_norm, None, None, delta_time, detection)

def set_target_vehicle_size(size_ratio):
    """
    Set the target size for the vehicle on screen
    
    Args:
        size_ratio: Fraction of screen the vehicle should occupy (0.0 to 1.0)
                   e.g., 0.2 = 1/5 of screen, 0.25 = 1/4 of screen
    """
    global TARGET_VEHICLE_SIZE
    TARGET_VEHICLE_SIZE = max(0.05, min(0.5, size_ratio))
    print(f"Target vehicle size set to {TARGET_VEHICLE_SIZE:.3f} ({TARGET_VEHICLE_SIZE*100:.1f}% of screen)")

def set_zoom_enabled(enabled):
    """Enable or disable autonomous zoom control"""
    global ZOOM_ENABLED
    ZOOM_ENABLED = enabled
    print(f"Autonomous zoom {'enabled' if enabled else 'disabled'}")

def set_pid_gains(px=None, ix=None, py=None, iy=None, pz=None, iz=None):
    """
    Update PID gains dynamically
    
    Args:
        px: Pan proportional gain
        ix: Pan integral gain  
        py: Tilt proportional gain
        iy: Tilt integral gain
        pz: Zoom proportional gain
        iz: Zoom integral gain
    """
    global PX, IX, PY, IY, PZ, IZ
    
    if px is not None:
        PX = px
    if ix is not None:
        IX = ix
    if py is not None:
        PY = py
    if iy is not None:
        IY = iy
    if pz is not None:
        PZ = pz
    if iz is not None:
        IZ = iz
    
    print(f"PID gains updated: PX={PX}, IX={IX}, PY={PY}, IY={IY}, PZ={PZ}, IZ={IZ}")

def set_deadband(x_deadband=None, y_deadband=None, z_deadband=None):
    """
    Update deadband values
    
    Args:
        x_deadband: Pan deadband (normalized, 0.0 to 1.0)
        y_deadband: Tilt deadband (normalized, 0.0 to 1.0)
        z_deadband: Zoom deadband (normalized, 0.0 to 1.0)
    """
    global DEADBAND_X, DEADBAND_Y, DEADBAND_Z
    
    if x_deadband is not None:
        DEADBAND_X = x_deadband
    if y_deadband is not None:
        DEADBAND_Y = y_deadband
    if z_deadband is not None:
        DEADBAND_Z = z_deadband
    
    print(f"Deadband updated: X={DEADBAND_X}, Y={DEADBAND_Y}, Z={DEADBAND_Z}")

if __name__ == "__main__":
    # Test the enhanced PID controller
    print("Enhanced PID Controller Test with Zoom")
    print("Testing different vehicle sizes and zoom responses")
    
    import time
    import math
    
    # Test different vehicle sizes
    test_cases = [
        (0.1, "Small vehicle - should zoom in"),
        (0.2, "Target size vehicle - should maintain zoom"),
        (0.35, "Large vehicle - should zoom out")
    ]
    
    for size_ratio, description in test_cases:
        print(f"\nTesting: {description}")
        
        # Simulate bounding box for different vehicle sizes
        frame_width, frame_height = 854, 480
        bbox_width = int(math.sqrt(size_ratio) * frame_width)
        bbox_height = int(math.sqrt(size_ratio) * frame_height)
        
        # Center the bbox
        x1 = (frame_width - bbox_width) // 2
        y1 = (frame_height - bbox_height) // 2
        x2 = x1 + bbox_width
        y2 = y1 + bbox_height
        
        bbox_coords = (x1, y1, x2, y2)
        frame_dims = (frame_width, frame_height)
        
        # Test for a few iterations
        for i in range(5):
            PID_with_zoom(0.5, 0.5, bbox_coords, frame_dims, 0.033, True)
            time.sleep(0.1)
    
    print("\nPID zoom test complete")