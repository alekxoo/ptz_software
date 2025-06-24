import matplotlib.pyplot as plt
from mpl_toolkits.mplot3d import Axes3D
import csv
import cv2
import torch
from torchvision import models, transforms
from threading import Thread
from PIL import Image, ImageTk
from extract_data_from_img import extract_number_from_image
import time
import gc
import psutil
from yolo import vehicle_detection, class_labels, num_classes

# Classification
transform = transforms.Compose([
    # transforms.Resize((224, 224)),
    transforms.CenterCrop((224, 224)),
    transforms.ToTensor(),
    transforms.Normalize([0.485, 0.456, 0.406], [0.229, 0.224, 0.225])
])

# Camera Initialization
input_video_path = "/home/machvision/Downloads/training_video1.mkv"
cap = cv2.VideoCapture(input_video_path)
width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
if not cap.isOpened():
    print("Error: Could not open video.")
    exit()           

start_time = time.time()
print(f"Starting video processing:{start_time}")
frame_count = 0

header = ['Timestamp', 'Relative Time', 'Vehicle Detected (Bool)']
header += class_labels 


with open('extracted_timestamps.csv', 'w', newline='') as csvfile:
    writer = csv.writer(csvfile)
    writer.writerow(header)

    while (cap.isOpened()):
        ret, img = cap.read()
        if not ret:
            break
        frame_count += 1
        if frame_count % 600 == 0:
            timestamp = extract_number_from_image(img)
            relative_time = round(timestamp / 1000, 2)  
            
            # bool = True if want to save detected images
            car_coords = vehicle_detection(img, True, relative_time, timestamp)
            print(f"Frame {frame_count}: Detected {len(car_coords)} vehicles.")
            vehicle_detected = 'Y' if len(car_coords) > 0 else 'N'
            car_dict = {car_id: (x1, y1, x2, y2) for car_id, x1, y1, x2, y2 in car_coords}
            print(car_dict)

            # Prepare car columns: up to 6 cars, fill with '' if fewer
            car_columns = []
            for car_id in class_labels:
                if car_id in car_dict:
                    car_columns.append(str(car_dict[car_id]))
                else:
                    car_columns.append('')

            row = [timestamp, relative_time, vehicle_detected] + car_columns
            writer.writerow(row)
            print(f"Extracted timestamp frame {frame_count}: {timestamp}")

        # if frame_count % 50 == 0:
        #     memory_percent = psutil.virtual_memory().percent
        #     print(f"Memory usage: {memory_percent}%")
        #     if memory_percent > 85:
        #         gc.collect()
        # if frame_count > 5000:
        #     print("Processed 5000 frames, exiting.")
        #     break
        
    print(f"Total time taken for video processing: {time.time() - start_time} seconds")
    cap.release()
    cv2.destroyAllWindows()
    print("Video processing complete.")

print("Timestamps extracted and saved to 'extracted_timestamps.csv'.")

