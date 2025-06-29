import cv2
from ultralytics import YOLO
import torch
from torchvision import models, transforms
from threading import Thread
from PIL import Image, ImageTk # creates image from a numpy array 
import torch.nn.functional as F
import torch.nn as nn


import pandas as pd
import numpy as np



device = torch.device("cuda:0" if torch.cuda.is_available() else "cpu")
yolov9_model = YOLO("./yoloModels/yolov9s.pt").to(device)

def load_yaml(file_path):
    import yaml
    with open(file_path, 'r') as file:
        data = yaml.safe_load(file)
    return data

def parse_class_data(data):
    class_labels = [cls['label'] for cls in data['classes']]
    num_classes = data['num_classes']
    return class_labels, num_classes

yaml_data = load_yaml("/home/machvision/Documents/ptz_software/src/ml/object_detection/preprocessing/config_a8621af6.yaml")
class_labels, num_classes = parse_class_data(yaml_data)

classification_model = models.resnet18(weights='IMAGENET1K_V1')
classification_model.fc = nn.Linear(classification_model.fc.in_features, num_classes)
classification_model.load_state_dict(torch.load("/home/machvision/Documents/ptz_software/src/ml/object_detection/training/best.pt"))
classification_model.to(device) 
classification_model.eval()



def get_visible_cars_at_timestamp(detection_timestamp, csv_path='all_car_positions.csv', 
                                width=854, height=480, max_time_diff=5000):
    """
    Find cars visible on screen at a given detection timestamp.
    
    Args:
        detection_timestamp (float): Timestamp from extracted_timestamps.csv
        csv_path (str): Path to all_car_positions.csv file
        width (int): Screen width for projection
        height (int): Screen height for projection
        max_time_diff (float): Maximum allowed difference between timestamps
    
    Returns:
        list: List of tuples (car_id, (screen_x, screen_y)) for visible cars
    """
    
    def project_to_screen(car_pos, camera_pos, camera_look, fov):
        car_height_offset = 0.5  # Start with 1.0, adjust as needed
        car_visual_center = car_pos + np.array([0, car_height_offset, 0])

        """Project 3D car position to 2D screen coordinates"""
        # Calculate vector from camera to car
        # to_car = car_pos - camera_pos
        to_car = car_visual_center - camera_pos  # Use visual center instead of car_pos
        # Normalize camera look direction
        look_dir = camera_look / np.linalg.norm(camera_look)
        
        # Calculate camera up vector (assuming mostly upright camera)
        world_up = np.array([0, 1, 0])
        right = np.cross(look_dir, world_up)
        
        # Handle case where look_dir is parallel to world_up
        if np.linalg.norm(right) < 1e-6:
            # Use a different up vector
            world_up = np.array([0, 0, 1])
            right = np.cross(look_dir, world_up)
        
        right = right / np.linalg.norm(right)
        up = np.cross(right, look_dir)
        
        # Create camera rotation matrix
        rotation_matrix = np.array([right, up, -look_dir])
        
        # Transform to camera space
        camera_space = rotation_matrix @ to_car
        
        # If behind camera, don't render
        if camera_space[2] >= 0:
            return None
        
        # Convert FOV to radians
        fov_rad = np.radians(fov)
        
        # Calculate projection
        aspect_ratio = width / height
        f = 1.0 / np.tan(fov_rad / 2.0)
        
        # Project to normalized device coordinates
        x_ndc = (f / aspect_ratio) * camera_space[0] / -camera_space[2]
        y_ndc = f * camera_space[1] / -camera_space[2]
        
        # Convert to screen coordinates
        screen_x = (x_ndc + 1) * 0.5 * width
        screen_y = (1 - y_ndc) * 0.5 * height  # Flip Y axis
        
        return int(screen_x), int(screen_y)
    

    def calculate_projected_size(car_pos, camera_pos, camera_look, fov, width, height, 
                           car_length=4.5, car_height=1.5):
        """Calculate how big a car would appear on screen in pixels"""
        # Calculate distance from camera to car
        to_car = car_pos - camera_pos
        
        # Normalize camera look direction
        look_dir = camera_look / np.linalg.norm(camera_look)
        
        # Calculate distance along camera's forward direction
        distance = np.dot(to_car, look_dir)
        
        # If behind camera, return None
        if distance <= 0:
            return None
        
        # Convert FOV to radians and calculate focal length
        fov_rad = np.radians(fov)
        focal_length = 1.0 / np.tan(fov_rad / 2.0)
        
        # Calculate projected size in pixels
        # Use car_width for screen width projection (side view)
        # Use car_height for screen height projection
        width_pixels = (car_length * focal_length * width) / distance
        height_pixels = (car_height * focal_length * height) / distance
        
        return abs(width_pixels), abs(height_pixels)
    
    try:
        # Read the CSV file
        df = pd.read_csv(csv_path)
        
        if df.empty:
            return []
        
        # Find the closest timestamp
        time_differences = np.abs(df['timestamp'] - detection_timestamp)
        closest_idx = time_differences.idxmin()
        min_diff = time_differences.iloc[closest_idx]
        
        # Check if the closest timestamp is within threshold
        if min_diff > max_time_diff:
            print(f"No matching timestamp found within {max_time_diff} units. Closest difference: {min_diff}")
            return []
        
        closest_timestamp = df.loc[closest_idx, 'timestamp']
        
        # Get all cars for this timestamp
        frame_data = df[df['timestamp'] == closest_timestamp]
        
        if frame_data.empty:
            return []
        
        # Extract camera data from first row (same for all cars in a frame)
        camera_pos = np.array([
            frame_data.iloc[0]['camera_pos_x'],
            frame_data.iloc[0]['camera_pos_y'],
            frame_data.iloc[0]['camera_pos_z']
        ])
        camera_look = np.array([
            frame_data.iloc[0]['camera_look_x'],
            frame_data.iloc[0]['camera_look_y'],
            frame_data.iloc[0]['camera_look_z']
        ])
        fov = frame_data.iloc[0]['camera_fov']
        
        visible_cars = []
        min_width, min_height = 50, 30  # ADD THIS LINE - minimum detectable size
        
        # Project and check visibility for each car
        for _, row in frame_data.iterrows():
            car_id = int(row['car_id'])
            car_pos = np.array([row['x'], row['y'], row['z']])

            projected_size = calculate_projected_size(car_pos, camera_pos, camera_look, fov, width, height)

            if projected_size is None:
                continue  # Behind camera

            width_pixels, height_pixels = projected_size
            
            # ADD THIS: Skip cars that are too small to detect
            if width_pixels < min_width or height_pixels < min_height:
                print(f"Car {car_id} too small to detect: width={width_pixels}, height={height_pixels}")
                continue  # Too small for YOLO to detect

            # Project to screen
            screen_coords = project_to_screen(car_pos, camera_pos, camera_look, fov)
            
            if screen_coords is not None:
                x, y = screen_coords
                # Check if within screen bounds
                if 0 <= x <= width and 0 <= y <= height:
                    visible_cars.append((car_id, (x, y)))
        
        print(f"Found {len(visible_cars)} visible cars at timestamp {closest_timestamp} (diff: {min_diff:.2f})")
        return visible_cars
        
    except Exception as e:
        print(f"Error processing timestamp {detection_timestamp}: {e}")
        return []


def add_sim_cars_to_image(annotated_frame, timestamp, csv_path='all_car_positions.csv'):
    """
    Add simulation car dots to the annotated frame.
    
    Args:
        annotated_frame: OpenCV image (854x480) to draw on
        timestamp: Detection timestamp to match with simulation
        csv_path: Path to all_car_positions.csv
    
    Returns:
        annotated_frame: Image with sim car dots added
    """
    # Get visible sim cars for this timestamp
    visible_cars = get_visible_cars_at_timestamp(timestamp, csv_path, width=854, height=480)
    
    # Color palette for sim car dots (different from YOLO green boxes)
    sim_colors = [
        (255, 0, 0),    # Red
        (0, 0, 255),    # Blue  
        (255, 255, 0),  # Yellow
        (255, 0, 255),  # Magenta
        (0, 255, 255),  # Cyan
        (255, 128, 0),  # Orange
        (128, 0, 255),  # Purple
        (255, 255, 255),# White
        (128, 255, 0),  # Lime
        (255, 128, 128),# Light Red
    ]
    
    # Draw sim car dots
    for i, (car_id, (x, y)) in enumerate(visible_cars):
        color = sim_colors[i % len(sim_colors)]
        
        # Draw filled circle for sim car
        cv2.circle(annotated_frame, (x, y), 8, color, -1)
        
        # Draw black border around circle for visibility
        cv2.circle(annotated_frame, (x, y), 8, (0, 0, 0), 2)
        
        # Add sim car ID label (offset to avoid overlap with YOLO labels)
        if 0 <= car_id <= len(class_labels):
            car_label = class_labels[car_id]  # Convert 1-based to 0-based indexing
        else:
            car_label = f"Car{car_id}"  # Fallback for out-of-range IDs

        label = f"{car_label}"  # Now shows "S_1_Miata_red", etc.
        text_size, _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.4, 1)
        label_x = x - text_size[0] // 2
        label_y = y + 20  # Below the dot
        
        # Draw label background for readability
        cv2.rectangle(annotated_frame, 
                     (label_x - 2, label_y - text_size[1] - 2),
                     (label_x + text_size[0] + 2, label_y + 2),
                     (0, 0, 0), -1)
        
        # Draw label text
        cv2.putText(annotated_frame, label, (label_x, label_y), 
                   cv2.FONT_HERSHEY_SIMPLEX, 0.4, color, 1)
    
    return annotated_frame






img_path = "//home/machvision/Pictures/111.png"
img = cv2.imread(img_path)
annotated_image_path = "/home/machvision/Documents/ptz_software/src/v1_deployment/dev/annotated_images/"

transform = transforms.Compose([
            # transforms.Resize((224, 224)),
            transforms.CenterCrop((224, 224)),
            transforms.ToTensor(),
            transforms.Normalize([0.485, 0.456, 0.406], [0.229, 0.224, 0.225])
        ])
        


def scale_coordinates(x1, y1,x2, y2, original_width, original_height, resized_width, resized_height):
    """
    Scale the coordinates from resized image to original image dimensions.
    """
    width_scale = original_width / resized_width
    height_scale = original_height / resized_height
    
    x1_original = int(x1 * width_scale)
    y1_original = int(y1 * height_scale)
    x2_original = int(x2 * width_scale)
    y2_original = int(y2 * height_scale)
    
    return x1_original, y1_original, x2_original, y2_original




def classify_vehicle(roi_tensor, logit_threshold=2, entropy_threshold=0.5):
    """Runs CNN classification and applies both logit thresholding and entropy filtering."""

    with torch.no_grad():
        output = classification_model(roi_tensor)
        probabilities = F.softmax(output, dim=1)
        max_logit, pred_class = torch.max(output, 1)
        predicted_class_name = class_labels[pred_class.item()]
        max_logit = max_logit.item()
        entropy = -torch.sum(probabilities * torch.log(probabilities + 1e-10)).item()

        return predicted_class_name

def vehicle_classification(img_rgb, x1, y1, x2, y2):
    roi = img_rgb[y1:y2, x1:x2]
    if roi.size > 0:
        roi_pil = Image.fromarray(roi)
        roi_tensor = transform(roi_pil).unsqueeze(0).to(device)
        predicted_class_name = classify_vehicle(roi_tensor)
    
    return predicted_class_name

font = cv2.FONT_HERSHEY_SIMPLEX
font_scale = 0.3
font_thickness = 1

def vehicle_detection(img, save_bool=False, relative_time=None, timestamp=None):
    """
    Detect vehicles in the image using YOLOv9 model.
    """
    img_resized = cv2.resize(img, (854, 480))
    img_rgb = cv2.cvtColor(img_resized, cv2.COLOR_BGR2RGB)
    results = yolov9_model.predict(img_rgb, classes=[2], verbose=False, imgsz=480)

    car_coodinates = []
    if hasattr(results[0], 'boxes') and len(results[0].boxes) > 0:
        for idx, box in enumerate(results[0].boxes):
            x1, y1, x2, y2 = map(int, box.xyxy[0])
            conf = box.conf[0].item()
            if conf > 0.2:
                # x1_original, y1_original, x2_original, y2_original = scale_coordinates(x1,y1,x2,y2, img.shape[1], img.shape[0], 854, 480)
                # car_coodinates.append((x1_original, y1_original, x2_original, y2_original))
                predicted_car_id = vehicle_classification(img_rgb, x1,y1,x2,y2)
                car_coodinates.append((predicted_car_id, x1, y1, x2, y2))
    # Annotate image with all the bounding boxes and save as png if save_bool is True
    if save_bool and car_coodinates:
        annotated_frame = img_resized.copy()
        for predicted_car_id, x1, y1, x2, y2 in car_coodinates:
            cv2.rectangle(annotated_frame, (x1, y1), (x2, y2), (0, 255, 0), 2)
            text_size, _ = cv2.getTextSize(predicted_car_id, font, font_scale, font_thickness)
            text_x = x1
            text_y = y1 - 10 if y1 - 10 > 10 else y1 + text_size[1] + 10
            cv2.putText(annotated_frame, predicted_car_id, (text_x, text_y), font, font_scale, (0,255,0), font_thickness)
            annotated_frame = add_sim_cars_to_image(annotated_frame, timestamp)
        cv2.imwrite(f"{annotated_image_path}annotated_image_{relative_time}.png", annotated_frame)
    return car_coodinates







