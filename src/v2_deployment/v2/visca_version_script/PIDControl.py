#PID control library for PTZ Camera with Autonomous Zoom - VISCA Version
#Written by: Abdullah Alwakeel
#Updated for VISCA Camera Control: July 2025

from PTZControl import vel_x, vel_y, ptz_controller
import time  # Add this line at the top with other imports
# PID gains - adjust these based on your camera's responsiveness
PX = 1.0    # Pan proportional gain
IX = 0    # Pan integral gain

PY = -1.0   # Tilt proportional gain (negative because camera coordinates may be inverted)
IY = 0   # Tilt integral gain

# Zoom PID gains (adjusted for VISCA discrete zoom control)
PZ = 3.0    # Zoom proportional gain (higher since VISCA zoom is more discrete)
IZ = 0    # Zoom integral gain

i_x_acc = 0.0 # Accumulated integral error for pan
i_y_acc = 0.0 # Accumulated integral error for tilt
i_z_acc = 0.0 # Accumulated integral error for zoom

time_since_last_detection = 0 # Frames without detection

# Deadband to prevent jittery movements when target is close to center
DEADBAND_X = 0.03  # 2% deadband for pan
DEADBAND_Y = 0.03  # 2% deadband for tilt  
DEADBAND_Z = 0.03  # 3% deadband for zoom (larger since VISCA zoom is discrete)

# Zoom control settings
TARGET_VEHICLE_SIZE = 0.2  # Target: vehicle should occupy 20% of screen (1/5)
MIN_VEHICLE_SIZE = 0.05    # Minimum size to start zooming in
MAX_VEHICLE_SIZE = 0.4     # Maximum size to start zooming out
ZOOM_ENABLED = True        # Enable/disable autonomous zoom

# VISCA zoom timing control
last_zoom_command_time = 0.0
ZOOM_COMMAND_INTERVAL = 0.3  # Minimum time between zoom commands (seconds)

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
    # Stop zoom movement
    ptz_controller.update_continuous_movement(ptz_controller.pan_state, ptz_controller.tilt_state, 0)

def PID_with_zoom(x_norm, y_norm, bbox_coords, frame_dims, delta_time, detection):
    """
    Enhanced PID controller with autonomous zoom for VISCA PTZ camera tracking
    
    Args:
        x_norm: Normalized x position (0.0 to 1.0, where 0.5 is center)
        y_norm: Normalized y position (0.0 to 1.0, where 0.5 is center) 
        bbox_coords: Tuple (x1, y1, x2, y2) of bounding box coordinates
        frame_dims: Tuple (width, height) of frame dimensions
        delta_time: Time since last update (seconds)
        detection: Boolean indicating if target is detected
    """
    global i_y_acc, i_x_acc, i_z_acc, time_since_last_detection, last_zoom_command_time
    
    current_time = time.time()
    
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
        pan_output = max(-10.0, min(10.0, pan_output))
        tilt_output = max(-10.0, min(10.0, tilt_output))
        zoom_output = max(-5.0, min(5.0, zoom_output))
        
        # Send velocity commands to PTZ controller for pan/tilt
        vel_x(pan_output)
        vel_y(tilt_output)
        
        # Apply zoom control using VISCA discrete zoom commands
        if ZOOM_ENABLED and abs(z_error) > DEADBAND_Z:
            # Rate limit zoom commands to prevent overwhelming the camera
            if current_time - last_zoom_command_time >= ZOOM_COMMAND_INTERVAL:
                # Determine zoom direction based on error magnitude
                if zoom_output > 1.0:
                    # Need to zoom in significantly
                    ptz_controller.update_continuous_movement(
                        ptz_controller.pan_state, 
                        ptz_controller.tilt_state, 
                        1  # Zoom tele
                    )
                    last_zoom_command_time = current_time
                elif zoom_output < -1.0:
                    # Need to zoom out significantly  
                    ptz_controller.update_continuous_movement(
                        ptz_controller.pan_state,
                        ptz_controller.tilt_state,
                        -1  # Zoom wide
                    )
                    last_zoom_command_time = current_time
                else:
                    # Error is small, stop zoom
                    if ptz_controller.zoom_state != 0:
                        ptz_controller.update_continuous_movement(
                            ptz_controller.pan_state,
                            ptz_controller.tilt_state,
                            0  # Zoom stop
                        )
        else:
            # Stop zoom if not needed
            if ptz_controller.zoom_state != 0:
                ptz_controller.update_continuous_movement(
                    ptz_controller.pan_state,
                    ptz_controller.tilt_state,
                    0  # Zoom stop
                )
        
        # Debug output
        if abs(x_error) > DEADBAND_X or abs(y_error) > DEADBAND_Y or abs(z_error) > DEADBAND_Z:
            print(f"PID: x_err={x_error:.3f}, y_err={y_error:.3f}, z_err={z_error:.3f}")
            print(f"     pan_out={pan_output:.3f}, tilt_out={tilt_output:.3f}, zoom_out={zoom_output:.3f}")
            print(f"     zoom_state={ptz_controller.zoom_state}")
            print(f"VEHICLE: position=({x_norm:.3f}, {y_norm:.3f})")
            print(f"ERROR: raw=({x_norm-0.5:.3f}, {y_norm-0.5:.3f})")
            print(f"ERROR: after_deadband=({x_error:.3f}, {y_error:.3f})")
            print(f"OUTPUT: pid=({pan_output:.3f}, {tilt_output:.3f})")
            print(f"THRESHOLDS: will_move=({abs(pan_output)>0.1}, {abs(tilt_output)>0.1})")

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
    
    # Stop zoom if disabling
    if not enabled and ptz_controller.zoom_state != 0:
        ptz_controller.update_continuous_movement(
            ptz_controller.pan_state,
            ptz_controller.tilt_state,
            0  # Stop zoom
        )

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

def set_zoom_timing(command_interval=None):
    """
    Update zoom command timing
    
    Args:
        command_interval: Minimum time between zoom commands (seconds)
    """
    global ZOOM_COMMAND_INTERVAL
    
    if command_interval is not None:
        ZOOM_COMMAND_INTERVAL = max(0.1, min(2.0, command_interval))
        print(f"Zoom command interval set to {ZOOM_COMMAND_INTERVAL:.1f} seconds")

if __name__ == "__main__":
    # Test the enhanced PID controller with VISCA
    print("Enhanced PID Controller Test with VISCA Zoom")
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
            time.sleep(0.4)  # Wait for zoom command interval
    
    print("\nPID VISCA zoom test complete")