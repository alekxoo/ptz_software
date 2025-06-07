import cv2
from ultralytics import YOLO
import torch
from torchvision import models, transforms
from threading import Thread
from PIL import Image, ImageTk # creates image from a numpy array 

ret, img = cap.read()
            
img_resized = cv2.resize(img, (854, 480))
img_rgb = cv2.cvtColor(img_resized, cv2.COLOR_BGR2RGB)


device = torch.device("cuda:0" if torch.cuda.is_available() else "cpu")
yolov9_model = YOLO("./yoloModels/yolov9s.pt").to(device)
results = yolov9_model.predict(img_rgb, classes=[2], verbose=True, imgsz=480)


annotated_frame = img_resized.copy()
vehicle_found = False
vehicle_positions = []
threads = []

transform = transforms.Compose([
    # transforms.Resize((224, 224)),
    transforms.CenterCrop((224, 224)),
    transforms.ToTensor(),
    transforms.Normalize([0.485, 0.456, 0.406], [0.229, 0.224, 0.225])
])

if hasattr(results[0], 'boxes') and len(results[0].boxes) > 0:
    for idx, box in enumerate(results[0].boxes):
        x1, y1, x2, y2 = map(int, box.xyxy[0])
        conf = box.conf[0].item()
        if conf > 0.3:
            # Compute center coordinates.
            print("Computing center coordinates")
            print(f"x1: {x1} x2: {x2}\n")
            print(f"y1: {y1} y2: {y2}\n")

            x_center, y_center = (x1 + x2) / (2) , (y1 + y2) / (2)
            print(f"x center: {x_center}\n")
            print(f"y center: {y_center}\n")

            # Extract ROI for classification
            roi = img_rgb[y1:y2, x1:x2]
            print(f"roi: {roi}")

            if roi.size > 0:
                roi_pil = Image.fromarray(roi)
                roi_tensor = transform(roi_pil).unsqueeze(0).to(device)
                bbox_color = (255, 255, 255) 
                cv2.rectangle(annotated_frame, (x1, y1), (x2, y2), bbox_color, 2)

