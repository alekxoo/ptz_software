import cv2
from ultralytics import YOLO 
import torch
import os
import glob
from PIL import Image
import pillow_heif
import numpy as np

# Register HEIF opener with Pillow
pillow_heif.register_heif_opener()

# Base path for your image folders
base_path = "/home/machvision/Downloads/images"
storage_path = "/home/machvision/Downloads/extracted_cars" 
os.makedirs(storage_path, exist_ok=True)

# Get all subdirectories (car folders)
car_folders = [d for d in os.listdir(base_path) if os.path.isdir(os.path.join(base_path, d))]

# Initialize YOLO model
device = torch.device("cuda:0" if torch.cuda.is_available() else "cpu")
yolov9_model = YOLO("./yoloModels/yolov9s.pt").to(device)

def convert_heic_to_opencv(heic_path):
    """Convert HEIC file to OpenCV format (BGR numpy array)"""
    try:
        # Open HEIC file with PIL
        pil_image = Image.open(heic_path)
        # Convert to RGB if not already
        if pil_image.mode != 'RGB':
            pil_image = pil_image.convert('RGB')
        # Convert PIL to OpenCV format (RGB to BGR)
        opencv_image = cv2.cvtColor(np.array(pil_image), cv2.COLOR_RGB2BGR)
        return opencv_image
    except Exception as e:
        print(f"Error converting {heic_path}: {e}")
        return None

def get_unique_filename(filepath):
    """Extract unique identifier from filename, handling duplicates like (1), (2)"""
    filename = os.path.basename(filepath)
    # Remove .HEIC extension
    name_without_ext = filename.replace('.HEIC', '')
    # Handle duplicates - extract base name
    if '(' in name_without_ext:
        base_name = name_without_ext.split('(')[0]
        return base_name
    return name_without_ext

car_number = 0
total_cars_extracted = 0

for folder in car_folders:
    print(f"\nProcessing folder: {folder}")
    car_number += 1
    
    # Create output folder for this car
    unique_storage_path = f"{storage_path}/{car_number}_{folder}"
    os.makedirs(unique_storage_path, exist_ok=True)
    
    # Get all HEIC files in this folder
    folder_path = os.path.join(base_path, folder)
    heic_files = glob.glob(os.path.join(folder_path, "*.HEIC"))
    
    print(f"Found {len(heic_files)} HEIC files")
    
    image_counter = 0
    cars_in_folder = 0
    
    for heic_file in heic_files:
        print(f"Processing: {os.path.basename(heic_file)}")
        
        # Convert HEIC to OpenCV format
        frame = convert_heic_to_opencv(heic_file)
        if frame is None:
            continue
            
        image_counter += 1
        
        # Convert to RGB for YOLO
        img_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        
        # Run YOLO detection for cars (class 2)
        results = yolov9_model.predict(img_rgb, classes=[2], imgsz=480, verbose=False)
        
        if hasattr(results[0], 'boxes') and len(results[0].boxes) > 0:
            car_detections = 0
            for idx, box in enumerate(results[0].boxes):
                x1, y1, x2, y2 = map(int, box.xyxy[0])
                conf = box.conf[0].item()
                
                if conf > 0.2:  # Confidence threshold
                    # Extract car region
                    roi = img_rgb[y1:y2, x1:x2]
                    roi_bgr = cv2.cvtColor(roi, cv2.COLOR_RGB2BGR)
                    
                    # Create unique filename
                    base_filename = get_unique_filename(heic_file)
                    unique_file_name = f"{base_filename}_car{idx+1}_conf{conf:.2f}.jpg"
                    
                    # Save extracted car image
                    output_path = os.path.join(unique_storage_path, unique_file_name)
                    cv2.imwrite(output_path, roi_bgr)
                    
                    car_detections += 1
                    cars_in_folder += 1
                    total_cars_extracted += 1
                    
            if car_detections > 0:
                print(f"  -> Extracted {car_detections} cars from {os.path.basename(heic_file)}")
    
    print(f"Folder {folder} complete: {cars_in_folder} cars extracted from {image_counter} images")

print(f"\n=== SUMMARY ===")
print(f"Total folders processed: {car_number}")
print(f"Total cars extracted: {total_cars_extracted}")
print(f"Output saved to: {storage_path}")