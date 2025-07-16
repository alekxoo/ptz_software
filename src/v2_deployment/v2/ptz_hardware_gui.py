import sys
import glob
import torch
import cv2
import numpy as np
from PIL import Image, ImageTk
from torchvision import models, transforms
import torch.nn as nn
import torch.backends.cudnn as cudnn
import torch.nn.functional as F
from ultralytics import YOLO
import warnings
import tkinter as tk
from tkinter import ttk, Label, messagebox
import threading
from threading import Thread
import time
import customtkinter as ctk
import os
import boto3
from dotenv import load_dotenv
import math 

import socket
import warnings
import sys
from datetime import datetime

# Import our new PTZ controller
from PTZControl import ptz_controller, vel_x, vel_y
from PIDControl import PID_with_zoom, set_target_vehicle_size, set_zoom_enabled, PID

sys.path.append("/home/machvision/Documents/senior-design/src/embedded")
warnings.filterwarnings("ignore", category=FutureWarning)
warnings.filterwarnings("ignore", category=UserWarning)
load_dotenv()

warnings.filterwarnings("ignore", category=FutureWarning)


class OverlayVideoRecorder:
    def __init__(self):
        self.is_recording = False
        self.video_writer = None
        self.output_folder = "OverlayVideos"
        os.makedirs(self.output_folder, exist_ok=True)
        
    def start_recording(self, frame_size=(854, 480), fps=30):
        if self.is_recording:
            return False
            
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.output_path = os.path.join(self.output_folder, f"overlay_{timestamp}.mp4")
        
        fourcc = cv2.VideoWriter_fourcc(*'mp4v')
        self.video_writer = cv2.VideoWriter(self.output_path, fourcc, fps, frame_size)
        
        if not self.video_writer.isOpened():
            print("ERROR: Could not open overlay video writer!")
            return False
            
        self.is_recording = True
        print(f"Started overlay recording: {self.output_path}")
        return True
    
    def add_frame(self, frame):
        """Add processed frame with overlays"""
        if not self.is_recording or self.video_writer is None:
            return
            
        # Convert from RGB to BGR if needed
        if len(frame.shape) == 3 and frame.shape[2] == 3:
            # Assume it's RGB, convert to BGR for OpenCV
            frame_bgr = cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)
            self.video_writer.write(frame_bgr)
        else:
            self.video_writer.write(frame)
    
    def stop_recording(self):
        if not self.is_recording:
            return
            
        self.is_recording = False
        
        if self.video_writer:
            self.video_writer.release()
            self.video_writer = None
        
        print(f"Overlay recording saved: {self.output_path}")


def load_yaml(file_path):
    import yaml
    with open(file_path, 'r') as file:
        data = yaml.safe_load(file)
    return data

def parse_class_data(data):
    class_labels = [cls['label'] for cls in data['classes']]
    num_classes = data['num_classes']
    return class_labels, num_classes

    
class VehicleTrackerApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Vehicle Tracker")
        self.current_mode = tk.StringVar(value="ptz")

        #create a thread locker for recording
        self.lock = threading.Lock()

        # Create a Label to display the video feed
        self.video_label = Label(self.root)
        self.video_label.pack()

        # Bind keyboard events for PTZ control
        self.root.bind('<KeyPress>', self.on_key_press)
        self.root.focus_set()  # Ensure window can receive keyboard events

        self.zoom_enabled = tk.BooleanVar(value=True)
        self.target_vehicle_size = tk.DoubleVar(value=0.2)  # Default to 1/5 screen

        self.tracking_mode = tk.StringVar(value="specific")  # "specific" or "any"
        self.tracked_vehicle_id = None  # For tracking specific vehicle in "any" mode

        # PID control variables
        self.pid_px = tk.DoubleVar(value=15.0)   # Pan proportional
        self.pid_ix = tk.DoubleVar(value=0.2)    # Pan integral
        self.pid_py = tk.DoubleVar(value=-15.0)  # Tilt proportional  
        self.pid_iy = tk.DoubleVar(value=0.1)    # Tilt integral
        self.pid_pz = tk.DoubleVar(value=2.0)    # Zoom proportional
        self.pid_iz = tk.DoubleVar(value=0.05)   # Zoom integral

        self.debug_timing = {
            'frame_time': 0.0,
            'yolo_time': 0.0,
            'class_time': 0.0,
            'last_cmd_time': 0.0,
            'vehicle_speed': 0.0,
            'pid_x_error': 0.0,
            'pid_y_error': 0.0,
            'pid_error': 0.0,
            'pan_rate': 0.0
        }
        
        self.last_positions = []  # For vehicle speed tracking
        self.last_pan_positions = []  # For pan rate tracking
        self.frames_since_detection = 0
                
        # Set up device
        cudnn.benchmark = True
        self.device = torch.device("cuda:0" if torch.cuda.is_available() else "cpu")
        
        # Load models
        print("Loading YOLOv9s model...")
        self.yolov9_model = YOLO("./yoloModels/yolov9s.pt").to(self.device)

        # Load configuration and models
        yaml_data = load_yaml("/home/machvision/Documents/ptz_software/src/ml/object_detection/config/config_998f13b1.yaml")
        self.class_labels, num_classes = parse_class_data(yaml_data)

        model_classification_start_time = time.time()
        print("Loading classification model...\n")
        self.classification_model = models.resnet18(weights='IMAGENET1K_V1')
        print(f"Classification model loaded in {time.time() - model_classification_start_time:.2f} seconds\n")
        self.classification_model.fc = nn.Linear(self.classification_model.fc.in_features, num_classes)
        self.classification_model.load_state_dict(torch.load("/home/machvision/Documents/ptz_software/src/ml/object_detection/config/best.pt"))
        print(f"Finished loading classification omdel in {time.time() - model_classification_start_time:.2f} seconds\n")
        self.classification_model.to(self.device)
        self.classification_model.eval()
        print(f"Finished loading all models in {time.time() - model_classification_start_time:.2f} seconds\n")
        
        # Image transformation
        self.transform = transforms.Compose([
            # transforms.Resize((224, 224)),
            transforms.CenterCrop((224, 224)),
            transforms.ToTensor(),
            transforms.Normalize([0.485, 0.456, 0.406], [0.229, 0.224, 0.225])
        ])

        session_timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

        gst = ("v4l2src device=/dev/video0 ! "
            "image/jpeg,width=3840,height=2160,framerate=30/1 ! "
            "jpegparse ! tee name=t "
            
            # Recording branch - heavily buffered, reliable, never drops frames
            "t. ! queue max-size-buffers=120 leaky=upstream ! "
            "avimux ! filesink location=full_quality_{session_timestamp}.avi sync=false async=true "
            
            # Processing branch - same as before, optimized for low latency
            "t. ! queue max-size-buffers=1 leaky=downstream ! "
            "jpegdec ! videoscale ! "
            "video/x-raw,width=854,height=480,format=BGR ! "
            "videoconvert ! "
            "appsink sync=false drop=true max-buffers=1").format(session_timestamp=session_timestamp)

        self.cap = cv2.VideoCapture(gst, cv2.CAP_GSTREAMER)

        if not self.cap.isOpened():
            print("Error: Could not open webcam")
            return
        
        # Tracking variables
        self.tracking_enabled = False
        self.selected_label = tk.StringVar()
        self.track_status = tk.StringVar(value="Not Tracking")
        self.vehicle_position = tk.StringVar(value="N/A")
        
        # Video recording variables - Simple overlay recorder only
        self.overlay_recorder = OverlayVideoRecorder()

        # Schedule the first update of the webcam frame
        self.create_ui()
        self.update_frame()
        self.on_pid_change()

    def calculate_vehicle_speed(self, center_x, center_y, frame_width):
        """Calculate vehicle speed in pixels per second"""
        current_time = time.time()
        self.last_positions.append((center_x, center_y, current_time))
        
        # Keep only last 5 positions (for smoothing)
        if len(self.last_positions) > 5:
            self.last_positions.pop(0)
        
        if len(self.last_positions) >= 2:
            pos1 = self.last_positions[-2]  # Previous position
            pos2 = self.last_positions[-1]  # Current position
            
            dt = pos2[2] - pos1[2]
            if dt > 0:
                dx = (pos2[0] - pos1[0]) * frame_width  # Convert to pixels
                dy = (pos2[1] - pos1[1]) * frame_width  # Assume square pixels
                
                velocity_pixels_per_sec = math.sqrt(dx*dx + dy*dy) / dt
                return velocity_pixels_per_sec
        
        return 0.0

    def calculate_pan_rate(self):
        """Calculate camera pan rate in units per second"""
        current_time = time.time()
        current_pan = ptz_controller.current_pan
        self.last_pan_positions.append((current_pan, current_time))
        
        # Keep only last 3 positions
        if len(self.last_pan_positions) > 3:
            self.last_pan_positions.pop(0)
        
        if len(self.last_pan_positions) >= 2:
            pos1 = self.last_pan_positions[-2]
            pos2 = self.last_pan_positions[-1]
            
            dt = pos2[1] - pos1[1]
            if dt > 0:
                dpan = abs(pos2[0] - pos1[0])
                return dpan / dt
        
        return 0.0

    def add_debug_overlay(self, frame):
        """Add comprehensive debug information to frame matching left side style"""
        debug_lines = [
            f"Frame: {self.debug_timing['frame_time']:.1f}ms ({1000/max(self.debug_timing['frame_time'], 1):.1f}FPS)",
            f"YOLO: {self.debug_timing['yolo_time']:.1f}ms",
            f"Class: {self.debug_timing['class_time']:.1f}ms", 
            f"PTZ Cmd: {self.debug_timing['last_cmd_time']:.1f}ms",
            f"Vehicle Speed: {self.debug_timing['vehicle_speed']:.0f} px/s",
            f"PID X Error: {self.debug_timing['pid_x_error']:.3f}",
            f"PID Y Error: {self.debug_timing['pid_y_error']:.3f}",
            f"PID Error: {self.debug_timing['pid_error']:.3f}",
            f"Pan Rate: {self.debug_timing['pan_rate']:.0f} units/s",
            f"Lost Frames: {self.frames_since_detection}"
        ]
        
        # Background dimensions to match left side
        debug_width = 320
        debug_height = len(debug_lines) * 20 + 10
        start_x = frame.shape[1] - debug_width
        
        # Semi-transparent background matching left side
        overlay = frame.copy()
        cv2.rectangle(overlay, (start_x, 0), (frame.shape[1], debug_height), (0, 0, 0), -1)
        alpha = 0.7
        cv2.addWeighted(overlay, alpha, frame, 1 - alpha, 0, frame)
        
        # Text styling to match left side exactly
        font = cv2.FONT_HERSHEY_SIMPLEX
        font_scale = 0.5  # Same as left side
        color = (255, 255, 255)  # White text like left side
        thickness = 1  # Thinner text like left side
        
        for i, line in enumerate(debug_lines):
            y_pos = 20 + i* 20  # Match left side spacing
            cv2.putText(frame, line, (start_x + 5, y_pos), font, font_scale, color, thickness)

    def on_pid_change(self, *args):
        """Handle PID gain changes"""
        from PIDControl import set_pid_gains
        set_pid_gains(
            px=self.pid_px.get(),
            ix=self.pid_ix.get(), 
            py=self.pid_py.get(),
            iy=self.pid_iy.get(),
            pz=self.pid_pz.get(),
            iz=self.pid_iz.get()
        )

    def reset_pid_defaults(self):
        """Reset PID gains to default values"""
        self.pid_px.set(15.0)
        self.pid_ix.set(0.2)
        self.pid_py.set(-15.0)
        self.pid_iy.set(0.1)
        self.pid_pz.set(2.0)
        self.pid_iz.set(0.05)
        self.on_pid_change()

    def on_key_press(self, event):
        """Handle keyboard input for PTZ control"""
        key = event.keysym
        
        if key == 'Right':
            ptz_controller.manual_pan_right()
            print("Pan Right")
        elif key == 'Left':
            ptz_controller.manual_pan_left()
            print("Pan Left")
        elif key == 'Up':
            ptz_controller.manual_tilt_up()
            print("Tilt Up")
        elif key == 'Down':
            ptz_controller.manual_tilt_down()
            print("Tilt Down")
        elif key == 'Prior':  # Page Up
            ptz_controller.manual_zoom_in()
            print("Zoom In")
        elif key == 'Next':   # Page Down
            ptz_controller.manual_zoom_out()
            print("Zoom Out")
        elif key == 'Escape':
            ptz_controller.go_home()
            print("PTZ Home")

    def create_ui(self):
        # Main container
        main_container = ctk.CTkFrame(self.root)
        main_container.pack(fill="both", expand=True, padx=20, pady=20)

        # Left panel - Video Feed
        left_panel = ctk.CTkFrame(main_container, width=550)
        left_panel.pack(side="left", fill="both", expand=True, padx=(0, 10))
        left_panel.pack_propagate(False)

        self.video_label = ctk.CTkLabel(left_panel, text="")  # Placeholder for video feed
        self.video_label.pack(fill="both", expand=True)

        self.recording_controls = ctk.CTkFrame(left_panel)
        self.recording_controls.pack(fill="x", pady=(0, 10))

        self.record_button = ctk.CTkButton(self.recording_controls, text="Start Recording", command=self.record_and_save)
        self.record_button.pack(side="left", expand=True, padx=5)

        # Right panel - Controls
        self.right_panel = ctk.CTkFrame(main_container, width=600)
        self.right_panel.pack(side="right", fill="both", padx=(10, 0), expand=True)
        self.right_panel.pack_propagate(False)

        # Mode selection buttons
        mode_frame = ctk.CTkFrame(self.right_panel)
        mode_frame.pack(fill="x", pady=(0, 10))

        autonomous_btn = ctk.CTkButton(mode_frame, text="Autonomous", width=160, height=32,
                                       command=lambda: self.switch_mode("autonomous"))
        autonomous_btn.pack(side="left", expand=True, padx=5)

        ptz_btn = ctk.CTkButton(mode_frame, text="PTZ Control", width=160, height=32,
                                command=lambda: self.switch_mode("ptz"))
        ptz_btn.pack(side="left", expand=True, padx=5)

        quit_btn = ctk.CTkButton(mode_frame, text = "Quit", width=160, height=32, command=lambda: self.switch_mode("quit"))
        quit_btn.pack(side="right", expand=True, padx=5)

        # Dynamic content area for additional features
        self.mode_content_frame = ctk.CTkFrame(self.right_panel)
        self.mode_content_frame.pack(fill="both", expand=True, padx=10, pady=10)
        
        # Initialize with autonomous mode
        self.update_controls()

    def switch_mode(self, mode):
        self.current_mode.set(mode)
        self.update_controls()

    def update_controls(self):
        # Clear current controls
        for widget in self.mode_content_frame.winfo_children():
            widget.destroy()
        
        if self.current_mode.get() == "autonomous":
            # Vehicle Tracking Controls
            ctk.CTkLabel(self.mode_content_frame, text="Vehicle Tracking", font=("Arial", 16, "bold")).pack(pady=(0, 10))
            
            # Tracking Mode Selection
            mode_frame = ctk.CTkFrame(self.mode_content_frame)
            mode_frame.pack(fill="x", pady=(0, 10))
            
            ctk.CTkLabel(mode_frame, text="Tracking Mode:", font=("Arial", 12, "bold")).pack(pady=(0, 5))
            
            mode_buttons_frame = ctk.CTkFrame(mode_frame)
            mode_buttons_frame.pack()
            
            self.specific_mode_btn = ctk.CTkButton(mode_buttons_frame, text="Specific Vehicle", width=140, height=30,
                                                command=lambda: self.set_tracking_mode("specific"))
            self.specific_mode_btn.pack(side="left", padx=5)
            
            self.any_mode_btn = ctk.CTkButton(mode_buttons_frame, text="Any Vehicle", width=140, height=30,
                                            command=lambda: self.set_tracking_mode("any"))
            self.any_mode_btn.pack(side="left", padx=5)
            
            # Update button colors based on current mode
            self.update_mode_buttons()
            
            self.track_button = ctk.CTkButton(self.mode_content_frame, text="Start Tracking", command=self.toggle_tracking)
            self.track_button.pack(pady=5)
            
            # Vehicle selection (only show in specific mode)
            self.vehicle_selection_frame = ctk.CTkFrame(self.mode_content_frame)
            if self.tracking_mode.get() == "specific":
                self.vehicle_selection_frame.pack(fill="x", pady=(5, 0))
                ctk.CTkLabel(self.vehicle_selection_frame, text="Select Vehicle Type:").pack(pady=(5, 0))
                self.vehicle_menu = ctk.CTkComboBox(self.vehicle_selection_frame, values=self.class_labels, variable=self.selected_label)
                self.vehicle_menu.pack(pady=5)
            
            # Zoom Control Section
            zoom_frame = ctk.CTkFrame(self.mode_content_frame)
            zoom_frame.pack(fill="x", pady=10)
            
            ctk.CTkLabel(zoom_frame, text="Autonomous Zoom Control", font=("Arial", 14, "bold")).pack(pady=(0, 5))
            
            # Zoom enable/disable checkbox
            zoom_checkbox = ctk.CTkCheckBox(zoom_frame, text="Enable Auto-Zoom", 
                                        variable=self.zoom_enabled, command=self.on_zoom_toggle)
            zoom_checkbox.pack(pady=2)
            
            # Target vehicle size slider
            ctk.CTkLabel(zoom_frame, text="Target Vehicle Size:", font=("Arial", 12)).pack(pady=(10, 0))
            
            size_frame = ctk.CTkFrame(zoom_frame)
            size_frame.pack(fill="x", pady=5)
            
            self.size_slider = ctk.CTkSlider(size_frame, from_=0.05, to=0.4, number_of_steps=35,
                                        variable=self.target_vehicle_size, command=self.on_size_change)
            self.size_slider.pack(fill="x", padx=10, pady=5)
            
            self.size_label = ctk.CTkLabel(size_frame, text="20% of screen (1/5)")
            self.size_label.pack(pady=2)
            
            # Quick preset buttons
            preset_frame = ctk.CTkFrame(zoom_frame)
            preset_frame.pack(fill="x", pady=5)
            
            ctk.CTkLabel(preset_frame, text="Quick Presets:", font=("Arial", 11)).pack()
            
            preset_buttons_frame = ctk.CTkFrame(preset_frame)
            preset_buttons_frame.pack()
            
            ctk.CTkButton(preset_buttons_frame, text="1/8 (12.5%)", width=80, height=25,
                        command=lambda: self.set_preset_size(0.125)).pack(side="left", padx=2)
            ctk.CTkButton(preset_buttons_frame, text="1/6 (16.7%)", width=80, height=25,
                        command=lambda: self.set_preset_size(0.167)).pack(side="left", padx=2)
            ctk.CTkButton(preset_buttons_frame, text="1/5 (20%)", width=80, height=25,
                        command=lambda: self.set_preset_size(0.2)).pack(side="left", padx=2)
            ctk.CTkButton(preset_buttons_frame, text="1/4 (25%)", width=80, height=25,
                        command=lambda: self.set_preset_size(0.25)).pack(side="left", padx=2)
            

            # PID Control Section
            pid_frame = ctk.CTkFrame(self.mode_content_frame)
            pid_frame.pack(fill="x", pady=10)

            ctk.CTkLabel(pid_frame, text="PID Gains", font=("Arial", 14, "bold")).pack(pady=(0, 5))

            # Pan controls
            pan_pid_frame = ctk.CTkFrame(pid_frame)
            pan_pid_frame.pack(fill="x", pady=2)
            ctk.CTkLabel(pan_pid_frame, text="Pan:", font=("Arial", 11, "bold"), width=50).pack(side="left")

            ctk.CTkLabel(pan_pid_frame, text="P:", width=20).pack(side="left", padx=(10,0))
            px_slider = ctk.CTkSlider(pan_pid_frame, from_=0.1, to=30.0, number_of_steps=299,
                                    variable=self.pid_px, command=lambda x: self.on_pid_change(), width=80)
            px_slider.pack(side="left", padx=2)
            px_label = ctk.CTkLabel(pan_pid_frame, text=f"{self.pid_px.get():.1f}", width=30)
            px_label.pack(side="left")
            self.pid_px.trace_add('write', lambda *args: px_label.configure(text=f"{self.pid_px.get():.1f}"))

            ctk.CTkLabel(pan_pid_frame, text="I:", width=20).pack(side="left", padx=(10,0))
            ix_slider = ctk.CTkSlider(pan_pid_frame, from_=0.0, to=2.0, number_of_steps=200,
                                    variable=self.pid_ix, command=lambda x: self.on_pid_change(), width=80)
            ix_slider.pack(side="left", padx=2)
            ix_label = ctk.CTkLabel(pan_pid_frame, text=f"{self.pid_ix.get():.2f}", width=30)
            ix_label.pack(side="left")
            self.pid_ix.trace_add('write', lambda *args: ix_label.configure(text=f"{self.pid_ix.get():.2f}"))

            # Tilt controls
            tilt_pid_frame = ctk.CTkFrame(pid_frame)
            tilt_pid_frame.pack(fill="x", pady=2)
            ctk.CTkLabel(tilt_pid_frame, text="Tilt:", font=("Arial", 11, "bold"), width=50).pack(side="left")

            ctk.CTkLabel(tilt_pid_frame, text="P:", width=20).pack(side="left", padx=(10,0))
            py_slider = ctk.CTkSlider(tilt_pid_frame, from_=-30.0, to=30.0, number_of_steps=600,
                                    variable=self.pid_py, command=lambda x: self.on_pid_change(), width=80)
            py_slider.pack(side="left", padx=2)
            py_label = ctk.CTkLabel(tilt_pid_frame, text=f"{self.pid_py.get():.1f}", width=30)
            py_label.pack(side="left")
            self.pid_py.trace_add('write', lambda *args: py_label.configure(text=f"{self.pid_py.get():.1f}"))

            ctk.CTkLabel(tilt_pid_frame, text="I:", width=20).pack(side="left", padx=(10,0))
            iy_slider = ctk.CTkSlider(tilt_pid_frame, from_=0.0, to=2.0, number_of_steps=200,
                                    variable=self.pid_iy, command=lambda x: self.on_pid_change(), width=80)
            iy_slider.pack(side="left", padx=2)
            iy_label = ctk.CTkLabel(tilt_pid_frame, text=f"{self.pid_iy.get():.2f}", width=30)
            iy_label.pack(side="left")
            self.pid_iy.trace_add('write', lambda *args: iy_label.configure(text=f"{self.pid_iy.get():.2f}"))

            # Zoom controls
            zoom_pid_frame = ctk.CTkFrame(pid_frame)
            zoom_pid_frame.pack(fill="x", pady=2)
            ctk.CTkLabel(zoom_pid_frame, text="Zoom:", font=("Arial", 11, "bold"), width=50).pack(side="left")

            ctk.CTkLabel(zoom_pid_frame, text="P:", width=20).pack(side="left", padx=(10,0))
            pz_slider = ctk.CTkSlider(zoom_pid_frame, from_=0.1, to=10.0, number_of_steps=99,
                                    variable=self.pid_pz, command=lambda x: self.on_pid_change(), width=80)
            pz_slider.pack(side="left", padx=2)
            pz_label = ctk.CTkLabel(zoom_pid_frame, text=f"{self.pid_pz.get():.1f}", width=30)
            pz_label.pack(side="left")
            self.pid_pz.trace_add('write', lambda *args: pz_label.configure(text=f"{self.pid_pz.get():.1f}"))

            ctk.CTkLabel(zoom_pid_frame, text="I:", width=20).pack(side="left", padx=(10,0))
            iz_slider = ctk.CTkSlider(zoom_pid_frame, from_=0.0, to=0.5, number_of_steps=50,
                                    variable=self.pid_iz, command=lambda x: self.on_pid_change(), width=80)
            iz_slider.pack(side="left", padx=2)
            iz_label = ctk.CTkLabel(zoom_pid_frame, text=f"{self.pid_iz.get():.3f}", width=30)
            iz_label.pack(side="left")
            self.pid_iz.trace_add('write', lambda *args: iz_label.configure(text=f"{self.pid_iz.get():.3f}"))

            # Reset button
            reset_pid_btn = ctk.CTkButton(pid_frame, text="Reset to Defaults", 
                                        command=self.reset_pid_defaults, width=120, height=25)
            reset_pid_btn.pack(pady=(5, 0))

            # Status display
            status_frame = ctk.CTkFrame(self.mode_content_frame)
            status_frame.pack(fill="x", pady=10)
            
            ctk.CTkLabel(status_frame, text="Tracking Status:", font=("Arial", 12, "bold")).pack()
            ctk.CTkLabel(status_frame, textvariable=self.track_status, font=("Arial", 12)).pack()
            
            ctk.CTkLabel(status_frame, text="Position:", font=("Arial", 12, "bold")).pack(pady=(10, 0))
            ctk.CTkLabel(status_frame, textvariable=self.vehicle_position, font=("Arial", 12)).pack()

            # Add vehicle size display
            ctk.CTkLabel(status_frame, text="Vehicle Size:", font=("Arial", 12, "bold")).pack(pady=(10, 0))
            if not hasattr(self, 'vehicle_size_var'):
                self.vehicle_size_var = tk.StringVar(value="N/A")
            ctk.CTkLabel(status_frame, textvariable=self.vehicle_size_var, font=("Arial", 12)).pack()
            
            # Add tracked vehicle info (for any mode)
            if not hasattr(self, 'tracked_vehicle_info'):
                self.tracked_vehicle_info = tk.StringVar(value="N/A")
            ctk.CTkLabel(status_frame, text="Tracking:", font=("Arial", 12, "bold")).pack(pady=(10, 0))
            ctk.CTkLabel(status_frame, textvariable=self.tracked_vehicle_info, font=("Arial", 12)).pack()

        elif self.current_mode.get() == "ptz":
            # PTZ Manual Controls
            ctk.CTkLabel(self.mode_content_frame, text="PTZ Manual Control", font=("Arial", 16, "bold")).pack(pady=(0, 10))
            
            # Position display
            position_frame = ctk.CTkFrame(self.mode_content_frame)
            position_frame.pack(fill="x", pady=(0, 10))
            
            self.position_label = ctk.CTkLabel(position_frame, text="Position: Pan=0, Tilt=0, Zoom=0", font=("Arial", 12))
            self.position_label.pack(pady=5)
            
            # Home button
            home_btn = ctk.CTkButton(self.mode_content_frame, text="🏠 Home Position", 
                                command=self.go_home, width=200, height=40)
            home_btn.pack(pady=10)
            
            # Pan controls
            pan_frame = ctk.CTkFrame(self.mode_content_frame)
            pan_frame.pack(fill="x", pady=5)
            ctk.CTkLabel(pan_frame, text="Pan Control", font=("Arial", 14, "bold")).pack()
            
            pan_buttons = ctk.CTkFrame(pan_frame)
            pan_buttons.pack()
            ctk.CTkButton(pan_buttons, text="◀ Left", command=ptz_controller.manual_pan_left, width=100).pack(side="left", padx=5)
            ctk.CTkButton(pan_buttons, text="Right ▶", command=ptz_controller.manual_pan_right, width=100).pack(side="left", padx=5)
            
            # Tilt controls
            tilt_frame = ctk.CTkFrame(self.mode_content_frame)
            tilt_frame.pack(fill="x", pady=5)
            ctk.CTkLabel(tilt_frame, text="Tilt Control", font=("Arial", 14, "bold")).pack()
            
            tilt_buttons = ctk.CTkFrame(tilt_frame)
            tilt_buttons.pack()
            ctk.CTkButton(tilt_buttons, text="▲ Up", command=ptz_controller.manual_tilt_up, width=100).pack(side="top", pady=2)
            ctk.CTkButton(tilt_buttons, text="▼ Down", command=ptz_controller.manual_tilt_down, width=100).pack(side="top", pady=2)
            
            # Zoom controls
            zoom_frame = ctk.CTkFrame(self.mode_content_frame)
            zoom_frame.pack(fill="x", pady=5)
            ctk.CTkLabel(zoom_frame, text="Zoom Control", font=("Arial", 14, "bold")).pack()
            
            zoom_buttons = ctk.CTkFrame(zoom_frame)
            zoom_buttons.pack()
            ctk.CTkButton(zoom_buttons, text="🔍+ In", command=ptz_controller.manual_zoom_in, width=100).pack(side="left", padx=5)
            ctk.CTkButton(zoom_buttons, text="🔍- Out", command=ptz_controller.manual_zoom_out, width=100).pack(side="left", padx=5)
            
            # Keyboard shortcuts info
            shortcuts_frame = ctk.CTkFrame(self.mode_content_frame)
            shortcuts_frame.pack(fill="x", pady=10)
            ctk.CTkLabel(shortcuts_frame, text="Keyboard Shortcuts:", font=("Arial", 12, "bold")).pack()
            ctk.CTkLabel(shortcuts_frame, text="Arrow Keys: Pan/Tilt", font=("Arial", 10)).pack()
            ctk.CTkLabel(shortcuts_frame, text="Page Up/Down: Zoom", font=("Arial", 10)).pack()
            ctk.CTkLabel(shortcuts_frame, text="ESC: Home Position", font=("Arial", 10)).pack()
            
            # Start position update timer for PTZ mode
            self.update_ptz_position()
        
        elif self.current_mode.get() == "quit":
            self.on_closing()

    def on_zoom_toggle(self):
        """Handle zoom enable/disable"""
        zoom_enabled = self.zoom_enabled.get()
        set_zoom_enabled(zoom_enabled)
        print(f"Auto-zoom {'enabled' if zoom_enabled else 'disabled'}")

    def on_size_change(self, value):
        """Handle target size slider change"""
        size_ratio = float(value)
        set_target_vehicle_size(size_ratio)
        percentage = size_ratio * 100
        fraction_text = self.get_fraction_text(size_ratio)
        self.size_label.configure(text=f"{percentage:.1f}% of screen {fraction_text}")

    def set_preset_size(self, size_ratio):
        """Set preset vehicle size"""
        self.target_vehicle_size.set(size_ratio)
        self.on_size_change(size_ratio)

    def get_fraction_text(self, ratio):
        """Convert ratio to approximate fraction text"""
        fractions = {
            0.125: "(1/8)",
            0.167: "(1/6)", 
            0.2: "(1/5)",
            0.25: "(1/4)",
            0.33: "(1/3)"
        }
        
        # Find closest fraction
        closest = min(fractions.keys(), key=lambda x: abs(x - ratio))
        if abs(closest - ratio) < 0.02:  # Within 2%
            return fractions[closest]
        return ""

    def set_tracking_mode(self, mode):
        """Set tracking mode (specific or any)"""
        self.tracking_mode.set(mode)
        self.tracked_vehicle_id = None  # Reset tracked vehicle
        self.update_controls()  # Refresh UI
        print(f"Tracking mode set to: {mode}")

    def update_mode_buttons(self):
        """Update tracking mode button colors"""
        if self.tracking_mode.get() == "specific":
            self.specific_mode_btn.configure(fg_color=("gray75", "gray25"))  # Active
            self.any_mode_btn.configure(fg_color=("gray85", "gray15"))      # Inactive
        else:
            self.any_mode_btn.configure(fg_color=("gray75", "gray25"))      # Active
            self.specific_mode_btn.configure(fg_color=("gray85", "gray15")) # Inactive

    def find_best_vehicle_to_track(self, detected_vehicles):
        """
        Find the best vehicle to track in 'any' mode
        Priority: 1) Currently tracked vehicle if still visible
                2) Largest vehicle (closest/most prominent)
                3) Most centered vehicle
        """
        if not detected_vehicles:
            return None
            
        # If we're already tracking a vehicle, try to find it again
        if self.tracked_vehicle_id is not None:
            for vehicle in detected_vehicles:
                if vehicle['id'] == self.tracked_vehicle_id:
                    return vehicle
        
        # Find best new vehicle to track
        best_vehicle = None
        best_score = -1
        
        frame_center_x = 0.5  # Normalized center
        frame_center_y = 0.5
        
        for vehicle in detected_vehicles:
            # Calculate score based on size and distance from center
            size_score = vehicle['size_ratio'] * 2  # Larger vehicles get higher score
            
            # Distance from center (closer to center = higher score)
            center_x = vehicle['center_norm'][0]
            center_y = vehicle['center_norm'][1]
            distance_from_center = ((center_x - frame_center_x)**2 + (center_y - frame_center_y)**2)**0.5
            center_score = max(0, 1.0 - distance_from_center)
            
            # Combined score (size weighted more heavily)
            total_score = size_score + center_score * 0.5
            
            if total_score > best_score:
                best_score = total_score
                best_vehicle = vehicle
        
        return best_vehicle

    def go_home(self):
        """Return PTZ camera to home position"""
        ptz_controller.go_home()
        
    def update_ptz_position(self):
        """Update PTZ position display (only when in PTZ mode)"""
        if self.current_mode.get() == "ptz":
            pan, tilt, zoom = ptz_controller.get_position()
            position_text = f"Position: Pan={pan}, Tilt={tilt}, Zoom={zoom}"
            if hasattr(self, 'position_label'):
                self.position_label.configure(text=position_text)
            # Schedule next update
            self.root.after(1000, self.update_ptz_position)

    def toggle_tracking(self):
        self.tracking_enabled = not self.tracking_enabled
        self.track_button.configure(text="Stop Tracking" if self.tracking_enabled else "Start Tracking")
        self.track_status.set("Tracking" if self.tracking_enabled else "Not Tracking")
        if not self.tracking_enabled:
            self.vehicle_position.set("N/A")

    def record_and_save(self):
        """Simple overlay recording function"""
        if self.overlay_recorder.is_recording:
            self.overlay_recorder.stop_recording()
            self.record_button.configure(text="Start Recording")
        else:
            success = self.overlay_recorder.start_recording(frame_size=(854, 480), fps=30)
            if success:
                self.record_button.configure(text="Stop Recording")
            else:
                print("Failed to start overlay recording")

    def add_metadata_overlay(self, frame):
        """Add metadata overlay to top-left corner of frame"""
        # Get current PTZ position
        pan, tilt, zoom = ptz_controller.get_position()
        
        # Prepare metadata text
        metadata_lines = [
            f"Pan: {pan}",
            f"Tilt: {tilt}", 
            f"Zoom: {zoom}",
            f"PID P: {self.pid_px.get():.1f}, {self.pid_py.get():.1f}, {self.pid_pz.get():.1f}",
            f"PID I: {self.pid_ix.get():.2f}, {self.pid_iy.get():.2f}, {self.pid_iz.get():.2f}",
            f"Target Size: {self.target_vehicle_size.get():.2f}",
            f"Auto-Zoom: {'ON' if self.zoom_enabled.get() else 'OFF'}",
            f"Mode: {self.tracking_mode.get().title()}"
        ]
        
        # Background rectangle dimensions
        line_height = 20
        padding = 5
        bg_width = 320
        bg_height = len(metadata_lines) * line_height + padding * 2
        
        # Draw semi-transparent background
        overlay = frame.copy()
        cv2.rectangle(overlay, (0, 0), (bg_width, bg_height), (0, 0, 0), -1)
        alpha = 0.7  # Transparency level
        cv2.addWeighted(overlay, alpha, frame, 1 - alpha, 0, frame)
        
        # Add text lines
        font = cv2.FONT_HERSHEY_SIMPLEX
        font_scale = 0.5
        color = (255, 255, 255)  # White text
        thickness = 1
        
        for i, line in enumerate(metadata_lines):
            y_position = padding + (i + 1) * line_height
            cv2.putText(frame, line, (padding, y_position), font, font_scale, color, thickness)

    def classify_vehicle(self, roi_tensor, logit_threshold=2, entropy_threshold=0.5):
        """Runs CNN classification and applies both logit thresholding and entropy filtering."""
        with torch.no_grad():
            output = self.classification_model(roi_tensor)
            probabilities = F.softmax(output, dim=1)
            print(f"Probabilities: {probabilities}")
            max_logit, pred_class = torch.max(output, 1)
            print(f"Max logit: {max_logit.item()}, Predicted class index: {pred_class.item()}")
            predicted_class_name = self.class_labels[pred_class.item()]
            print(f"Predicted class: {predicted_class_name}, Logit: {max_logit.item()}")
            max_logit = max_logit.item()
            print(f"Max logit: {max_logit}")
            entropy = -torch.sum(probabilities * torch.log(probabilities + 1e-10)).item()

            return f"{predicted_class_name} ({max_logit:.2f}, entropy: {entropy:.2f})"

    def find_best_vehicle_to_track(self, detected_vehicles):
        """
        Simple tracking for any vehicle mode - pick largest vehicle
        """
        if not detected_vehicles:
            return None
            
        # For "any" mode, just pick the largest/most confident vehicle
        if self.tracking_mode.get() == "any":
            return max(detected_vehicles, key=lambda v: v['size_ratio'] * v['confidence'])
        
        # For "specific" mode, use original logic
        selected_class = self.selected_label.get()
        for vehicle in detected_vehicles:
            if vehicle['class_name'] == selected_class:
                return vehicle
        return None

    def update_frame(self):
        try:
            frame_start_time = time.time()
            
            with self.lock:
                ret, img = self.cap.read()
            if not ret:
                print("Error: Could not read frame from webcam")
                self.root.after(100, self.update_frame)
                return
            
            # YOLO inference timing
            yolo_start = time.time()
            img_rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
            results = self.yolov9_model.predict(img_rgb, classes=[2], verbose=False, imgsz=480)
            self.debug_timing['yolo_time'] = (time.time() - yolo_start) * 1000
            
            annotated_frame = img_rgb.copy()
            vehicle_found = False
            vehicle_positions = []
            threads = []
            detected_vehicles = []

            tracking_vehicle_x = 0.0
            tracking_vehicle_y = 0.0
            tracking_bbox = None
            vehicle_size_ratio = 0.0
            tracked_vehicle_class = ""
            
            # Classification timing
            classification_start = time.time()
            
            if hasattr(results[0], 'boxes') and len(results[0].boxes) > 0:
                detected_vehicles = []
                
                # Check if we need classification (only for "specific" mode)
                need_classification = (self.tracking_mode.get() == "specific")
                
                for idx, box in enumerate(results[0].boxes):
                    x1, y1, x2, y2 = map(int, box.xyxy[0])
                    conf = box.conf[0].item()
                    if conf > 0.3:
                        # Compute center coordinates normalized for PID
                        x_center, y_center = (x1 + x2) / (2 * img_rgb.shape[1]) , (y1 + y2) / (2 * img_rgb.shape[0])
                        x_center_pixel, y_center_pixel = (x1 + x2) / 2, (y1 + y2) / 2

                        # Calculate vehicle size ratio
                        bbox_area = (x2 - x1) * (y2 - y1)
                        frame_area = img_rgb.shape[1] * img_rgb.shape[0]
                        current_size_ratio = bbox_area / frame_area

                        # Only classify if in "specific" mode
                        if need_classification:
                            # Extract ROI for classification
                            roi = img_rgb[y1:y2, x1:x2]
                            if roi.size > 0:
                                roi_pil = Image.fromarray(roi)
                                roi_tensor = self.transform(roi_pil).unsqueeze(0).to(self.device)
                                classification_result = self.classify_vehicle(roi_tensor)
                                vehicle_class_name = classification_result.split(" (")[0]
                            else:
                                classification_result = "Unknown"
                                vehicle_class_name = "Unknown"
                        else:
                            # Skip classification for "any" mode
                            classification_result = f"Vehicle (conf: {conf:.2f})"
                            vehicle_class_name = "Vehicle"

                        # Store vehicle info
                        vehicle_info = {
                            'id': idx,
                            'bbox': (x1, y1, x2, y2),
                            'center_norm': (x_center, y_center),
                            'center_pixel': (x_center_pixel, y_center_pixel),
                            'size_ratio': current_size_ratio,
                            'class_name': vehicle_class_name,
                            'classification_result': classification_result,
                            'confidence': conf
                        }
                        detected_vehicles.append(vehicle_info)

                        
                        # Run classification in a separate thread
                        thread = Thread(target=lambda: vehicle_positions.append(
                            f"Vehicle {idx+1}: {classification_result} ({x_center_pixel:.0f}, {y_center_pixel:.0f}) Size: {current_size_ratio:.3f}"
                        ))
                        threads.append(thread)
                        thread.start()

            # Wait for all classification threads to finish
            for thread in threads:
                thread.join()
                
            self.debug_timing['class_time'] = (time.time() - classification_start) * 1000

            # Determine which vehicle to track based on mode
            target_vehicle = None
            
            if self.tracking_enabled:
                if self.tracking_mode.get() == "specific":
                    selected_class = self.selected_label.get()
                    for vehicle in detected_vehicles:
                        if vehicle['class_name'] == selected_class:
                            target_vehicle = vehicle
                            break
                elif self.tracking_mode.get() == "any":
                    target_vehicle = self.find_best_vehicle_to_track(detected_vehicles)
                    if target_vehicle:
                        self.tracked_vehicle_id = target_vehicle['id']

            # Draw bounding boxes and handle tracking
            for vehicle in detected_vehicles:
                x1, y1, x2, y2 = vehicle['bbox']
                
                if target_vehicle and vehicle['id'] == target_vehicle['id']:
                    bbox_color = (0, 255, 0)  # Green for tracked vehicle
                    vehicle_found = True
                    self.vehicle_position.set(f"({vehicle['center_pixel'][0]:.0f}, {vehicle['center_pixel'][1]:.0f})")
                    tracking_vehicle_x = vehicle['center_norm'][0]
                    tracking_vehicle_y = vehicle['center_norm'][1]
                    tracking_bbox = vehicle['bbox']
                    vehicle_size_ratio = vehicle['size_ratio']
                    tracked_vehicle_class = vehicle['class_name']
                    
                    # Calculate vehicle speed
                    self.debug_timing['vehicle_speed'] = self.calculate_vehicle_speed(
                        vehicle['center_norm'][0], vehicle['center_norm'][1], img_rgb.shape[1])
                    
                    # Update vehicle size display
                    percentage = vehicle_size_ratio * 100
                    self.vehicle_size_var.set(f"{percentage:.1f}% of screen")
                    
                    # Update tracked vehicle info
                    if self.tracking_mode.get() == "any":
                        self.tracked_vehicle_info.set(f"{tracked_vehicle_class} (ID: {vehicle['id']})")
                    else:
                        self.tracked_vehicle_info.set(f"{tracked_vehicle_class}")
                else:
                    bbox_color = (255, 255, 255)  # Default white

                cv2.rectangle(annotated_frame, (x1, y1), (x2, y2), bbox_color, 2)
                
                # Add vehicle ID for "any" mode
                if self.tracking_mode.get() == "any":
                    cv2.putText(annotated_frame, f"ID:{vehicle['id']}", (x1, y1-10),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.5, bbox_color, 1)

            # Display vehicle positions
            y_offset = annotated_frame.shape[0] - 40
            for position in vehicle_positions:
                cv2.putText(annotated_frame, position, (10, y_offset),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)
                y_offset -= 30

            # Handle tracking status and frame counting
            if vehicle_found:
                self.frames_since_detection = 0
            else:
                self.frames_since_detection += 1

            is_tracking_lost = self.tracking_enabled and not vehicle_found
            
            if self.tracking_enabled and vehicle_found:
                if self.tracking_mode.get() == "any":
                    self.track_status.set(f"Tracking Any Vehicle")
                else:
                    self.track_status.set(f"Tracking {tracked_vehicle_class}")
            elif is_tracking_lost:
                self.track_status.set("Lost")
                self.tracked_vehicle_id = None
            else:
                self.track_status.set("Not Tracking")
            
            if is_tracking_lost or not self.tracking_enabled:
                self.vehicle_position.set("N/A")
                if hasattr(self, 'vehicle_size_var'):
                    self.vehicle_size_var.set("N/A")
                if hasattr(self, 'tracked_vehicle_info'):
                    self.tracked_vehicle_info.set("N/A")
            
            # PID Control with timing
            pid_start = time.time()
            if self.tracking_enabled and vehicle_found:
                # Calculate PID error for debug
                x_error = tracking_vehicle_x - 0.5
                y_error = tracking_vehicle_y - 0.5
                self.debug_timing['pid_x_error'] = x_error
                self.debug_timing['pid_y_error'] = y_error
                self.debug_timing['pid_error'] = math.sqrt(x_error*x_error + y_error*y_error)
                
                # Use enhanced PID with zoom control
                new_time = time.time()
                dt = new_time - frame_start_time
                frame_dims = (img_rgb.shape[1], img_rgb.shape[0])
                
                PID_with_zoom(tracking_vehicle_x, tracking_vehicle_y, tracking_bbox, frame_dims, dt, vehicle_found)
            else:
                self.debug_timing['pid_x_error'] = 0.0
                self.debug_timing['pid_y_error'] = 0.0
                self.debug_timing['pid_error'] = 0.0
                PID_with_zoom(0.0, 0.0, None, None, 0.0, False)
            
            # Calculate pan rate
            self.debug_timing['pan_rate'] = self.calculate_pan_rate()
            
            # Get PTZ command timing
            if hasattr(ptz_controller, 'last_cmd_time'):
                self.debug_timing['last_cmd_time'] = ptz_controller.last_cmd_time

            # Add metadata overlay to top-left corner
            self.add_metadata_overlay(annotated_frame)
            
            # Add debug overlay to top-right corner
            self.add_debug_overlay(annotated_frame)

            # Add overlay frame to recorder
            if self.overlay_recorder.is_recording:
                self.overlay_recorder.add_frame(annotated_frame)

            # Calculate total frame time
            self.debug_timing['frame_time'] = (time.time() - frame_start_time) * 1000

            # Convert frame for Tkinter display
            display_frame = cv2.resize(annotated_frame, (640, 360))
            frame_pil = Image.fromarray(display_frame)
            frame_tk = ImageTk.PhotoImage(frame_pil)
            self.video_label.configure(image=frame_tk)
            self.video_label.image = frame_tk
            
        except Exception as e:
            print(f"Error in processing loop: {e}")

        # Schedule next update
        self.root.after(30, self.update_frame)


    def on_closing(self):
        print("Shutting down...")
        
        if self.overlay_recorder.is_recording:
            self.overlay_recorder.stop_recording()
        
        # Release camera
        if self.cap.isOpened():
            self.cap.release()
        cv2.destroyAllWindows()

        # Close the app window
        self.root.destroy()
        
def main():
    root = tk.Tk()
    app = VehicleTrackerApp(root)
    root.protocol("WM_DELETE_WINDOW", app.on_closing)
    root.mainloop()

if __name__ == '__main__':
    main()
