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

import socket
import warnings
import sys
from datetime import datetime

# Import our new PTZ controller
from PTZControl import ptz_controller, vel_x, vel_y
from PIDControl import PID

sys.path.append("/home/machvision/Documents/senior-design/src/embedded")
warnings.filterwarnings("ignore", category=FutureWarning)
warnings.filterwarnings("ignore", category=UserWarning)
load_dotenv()

warnings.filterwarnings("ignore", category=FutureWarning)


class FullQualityVideoRecorder:
    def __init__(self):
        self.is_recording = False
        self.video_writer = None
        self.output_folder = "FullQualityVideos"
        os.makedirs(self.output_folder, exist_ok=True)
        self.frame_queue = []
        self.lock = threading.Lock()
        
    def start_recording(self, frame_size=(3840, 2160), fps=30):
        if self.is_recording:
            return False
            
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.output_path = os.path.join(self.output_folder, f"full_quality_{timestamp}.mp4")
        
        fourcc = cv2.VideoWriter_fourcc(*'mp4v')
        self.video_writer = cv2.VideoWriter(self.output_path, fourcc, fps, frame_size)
        
        if not self.video_writer.isOpened():
            print("ERROR: Could not open video writer!")
            return False
            
        self.is_recording = True
        self.frame_queue = []
        
        self.writer_thread = threading.Thread(target=self._write_frames_worker, daemon=True)
        self.writer_thread.start()
        
        print(f"Started recording: {self.output_path}")
        return True
    
    def add_frame(self, frame):
        if not self.is_recording:
            return
            
        with self.lock:
            self.frame_queue.append(frame.copy())
            if len(self.frame_queue) > 150:
                self.frame_queue.pop(0)
    
    def _write_frames_worker(self):
        while self.is_recording:
            frames_to_write = []
            
            with self.lock:
                if self.frame_queue:
                    frames_to_write = self.frame_queue.copy()
                    self.frame_queue.clear()
            
            for frame in frames_to_write:
                if self.video_writer and self.is_recording:
                    self.video_writer.write(frame)
            
            time.sleep(0.01)
    
    def stop_recording(self):
        if not self.is_recording:
            return
            
        self.is_recording = False
        
        if hasattr(self, 'writer_thread'):
            self.writer_thread.join(timeout=5.0)
        
        with self.lock:
            for frame in self.frame_queue:
                if self.video_writer:
                    self.video_writer.write(frame)
        
        if self.video_writer:
            self.video_writer.release()
            self.video_writer = None
        
        print(f"Video saved: {self.output_path}")


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
        
        # Set up device
        cudnn.benchmark = True
        self.device = torch.device("cuda:0" if torch.cuda.is_available() else "cpu")
        
        # Load models
        print("Loading YOLOv9s model...")
        self.yolov9_model = YOLO("./yoloModels/yolov9s.pt").to(self.device)

        # Load configuration and models
        yaml_data = load_yaml("/home/machvision/Documents/ptz_software/src/ml/object_detection/config/config_a8621af6.yaml")
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
        
        gst = ("v4l2src device=/dev/video0 ! "
            "image/jpeg,width=3840,height=2160,framerate=30/1 ! "
            "jpegparse ! tee name=t "
            "t. ! queue max-size-buffers=1 leaky=downstream ! "
            "avimux ! filesink location=video.avi "
            "t. ! queue max-size-buffers=1 leaky=downstream ! "
            "jpegdec ! videoscale ! "
            "video/x-raw,width=854,height=480,format=BGR ! "
            "videoconvert ! "
            "appsink sync=false drop=true max-buffers=1")

        self.cap = cv2.VideoCapture(gst, cv2.CAP_GSTREAMER)

        if not self.cap.isOpened():
            print("Error: Could not open webcam")
            return
        
        # Tracking variables
        self.tracking_enabled = False
        self.selected_label = tk.StringVar()
        self.track_status = tk.StringVar(value="Not Tracking")
        self.vehicle_position = tk.StringVar(value="N/A")
        
        # Video recording variables
        self.is_recording = False
        self.out = None  # For writing video

        # Schedule the first update of the webcam frame
        self.full_quality_recorder = FullQualityVideoRecorder()
        self.create_ui()
        self.update_frame()

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
            
            self.track_button = ctk.CTkButton(self.mode_content_frame, text="Start Tracking", command=self.toggle_tracking)
            self.track_button.pack(pady=5)
            
            ctk.CTkLabel(self.mode_content_frame, text="Select Vehicle:").pack(pady=(10, 0))
            self.vehicle_menu = ctk.CTkComboBox(self.mode_content_frame, values=self.class_labels, variable=self.selected_label)
            self.vehicle_menu.pack(pady=5)
            
            # Status display
            status_frame = ctk.CTkFrame(self.mode_content_frame)
            status_frame.pack(fill="x", pady=10)
            
            ctk.CTkLabel(status_frame, text="Status:", font=("Arial", 12, "bold")).pack()
            ctk.CTkLabel(status_frame, textvariable=self.track_status, font=("Arial", 12)).pack()
            
            ctk.CTkLabel(status_frame, text="Position:", font=("Arial", 12, "bold")).pack(pady=(10, 0))
            ctk.CTkLabel(status_frame, textvariable=self.vehicle_position, font=("Arial", 12)).pack()

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
        if self.full_quality_recorder.is_recording:
            self.full_quality_recorder.stop_recording()
            self.record_button.configure(text="Start Recording")
        else:
            self.full_quality_recorder.start_recording(frame_size=(3840, 2160), fps=30)
            self.record_button.configure(text="Stop Recording")

    #function to compute max logit of classification and entropy loss
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

    def update_frame(self):
        try:
            with self.lock:
                ret, img = self.cap.read()
            if not ret:
                print("Error: Could not read frame from webcam")
                self.root.after(100, self.update_frame)
                return
            
            if self.full_quality_recorder.is_recording:
                self.full_quality_recorder.add_frame(img)
            old_time = time.time()
            
            # Scale down for inference to 480p
            img_rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)

            print("running yolo detection")
            results = self.yolov9_model.predict(img_rgb, classes=[2], verbose=False, imgsz=480)
            annotated_frame = img_rgb.copy()
            vehicle_found = False
            vehicle_positions = []
            threads = []

            tracking_vehicle_x = 0.0
            tracking_vehicle_y = 0.0
            
            if hasattr(results[0], 'boxes') and len(results[0].boxes) > 0:
                for idx, box in enumerate(results[0].boxes):
                    x1, y1, x2, y2 = map(int, box.xyxy[0])
                    conf = box.conf[0].item()
                    if conf > 0.3:
                        # Compute center coordinates normalized for PID
                        x_center, y_center = (x1 + x2) / (2 * img_rgb.shape[1]) , (y1 + y2) / (2 * img_rgb.shape[0])
                        x_center_pixel, y_center_pixel = (x1 + x2) / 2, (y1 + y2) / 2

                        # Extract ROI for classification
                        roi = img_rgb[y1:y2, x1:x2]

                        if roi.size > 0:
                            roi_pil = Image.fromarray(roi)
                            roi_tensor = self.transform(roi_pil).unsqueeze(0).to(self.device)

                            # Get classification result synchronously
                            classification_result = self.classify_vehicle(roi_tensor)
                            vehicle_class_name = classification_result.split(" (")[0]  # Extract just the class name
                            
                            # Run classification in a separate thread
                            thread = Thread(target=lambda: vehicle_positions.append(
                                f"Vehicle {idx+1}: {classification_result} ({x_center_pixel:.0f}, {y_center_pixel:.0f})"
                            ))
                            threads.append(thread)
                            thread.start()

                            if self.tracking_enabled and vehicle_class_name == self.selected_label.get(): 
                                bbox_color = (0, 255, 0)  # Green for tracked vehicle
                                vehicle_found = True
                                self.vehicle_position.set(f"({x_center_pixel:.0f}, {y_center_pixel:.0f})")
                                tracking_vehicle_x = x_center
                                tracking_vehicle_y = y_center
                            else:
                                bbox_color = (255, 255, 255)  # Default white

                            cv2.rectangle(annotated_frame, (x1, y1), (x2, y2), bbox_color, 2)

            # Wait for all classification threads to finish
            for thread in threads:
                thread.join()

            # Display vehicle positions
            y_offset = annotated_frame.shape[0] - 40
            for position in vehicle_positions:
                cv2.putText(annotated_frame, position, (10, y_offset),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)
                y_offset -= 30

            # Handle tracking status
            is_tracking_lost = self.tracking_enabled and not vehicle_found
            self.track_status.set("Tracking" if self.tracking_enabled and vehicle_found else
                                "Lost" if is_tracking_lost else "Not Tracking")
            if is_tracking_lost:
                self.vehicle_position.set("N/A")
            
            if self.tracking_enabled and vehicle_found:
                # Use normalized coordinates for PID control
                new_time = time.time()
                dt = new_time - old_time
                PID(tracking_vehicle_x, tracking_vehicle_y, dt, vehicle_found)
                print(f"Frame processing time: {dt:.3f}s")
            else:
                PID(0.0, 0.0, 0.0, False) # Reset PID when not tracking

            # Convert frame for Tkinter display (resize to fit GUI)
            display_frame = cv2.resize(annotated_frame, (640, 360))  # Resize for display
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
        
        if self.full_quality_recorder.is_recording:
            self.full_quality_recorder.stop_recording()
        
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