import cv2
from ultralytics import YOLO 
import torch
import os
import glob

mkv_files = glob.glob("/home/machvision/Documents/ptz_software/src/v1_deployment/sim_vehicle_dataset/**/*.mkv", recursive=True)
storage_path = "/home/machvision/Downloads/vds" 
os.makedirs(storage_path, exist_ok=True)

car_number = 0
for file in mkv_files:
    print(file)
    car_number = car_number + 1
    unique_storage_path = f"{storage_path}/{car_number}"
    os.makedirs(unique_storage_path, exist_ok=True)

    cap = cv2.VideoCapture(file)

    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    fps = cap.get(cv2.CAP_PROP_FPS)

    print(f"Total Frames: {total_frames}, FPS: {fps}\n")

    device = torch.device("cuda:0" if torch.cuda.is_available() else "cpu")
    yolov9_model = YOLO("./yoloModels/yolov9s.pt").to(device)    

    while True: 
        # data type of frame is numpy array 
        ret, frame = cap.read()
        if not ret: 
            break

        current_frame = int(cap.get(cv2.CAP_PROP_POS_FRAMES))
        img_resized = frame
        img_rgb = cv2.cvtColor(img_resized, cv2.COLOR_BGR2RGB)
        results = yolov9_model.predict(img_rgb, classes=[2], imgsz=480, verbose = False)
        if hasattr(results[0], 'boxes') and len(results[0].boxes) > 0:
            for idx, box in enumerate(results[0].boxes):
                x1, y1, x2, y2 = map(int, box.xyxy[0])
                conf = box.conf[0].item()
                if conf > 0.2:
                    roi = img_rgb[y1:y2, x1:x2]
                    roi_bgr = cv2.cvtColor(roi, cv2.COLOR_RGB2BGR)
                    unique_file_name = f"capture_frame{current_frame}_{car_number}.jpg"
                    cv2.imwrite(os.path.join(unique_storage_path, unique_file_name), roi_bgr)
            
cap.release()  