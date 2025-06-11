import torch 
import torch.nn as nn
from torchvision import models, transforms 
import os

device = torch.device("cuda:0" if torch.cuda.is_available() else "cpu")
print(f"Using device: {device}")

print(f"PyTorch version: {torch.__version__}")

x = torch.tensor([1,2,3,4])
print(f"Basic tensor: {x}")
print(f"Tensor shape: {x.shape}")
print(f"Tensor device: {x.device}")

x_gpu = x.to(device)
print(f"Tensor on GPU: {x_gpu}")

print("\n" + "="*50)
print("STEP 2: Loading Pre-trained ResNet")
print("="*50)

model = models.resnet18(weights='IMAGENET1K_V1')
print("✅ ResNet18 loaded with ImageNet weights")

print(f"\nModel type: {type(model)}")
print(f"Model device: {next(model.parameters()).device}")

# Check the final layer (this is what we'll modify for car classification)
print(f"\nOriginal final layer: {model.fc}")
print(f"Input features to final layer: {model.fc.in_features}")
print(f"Output classes (ImageNet): {model.fc.out_features}")

model = model.to(device)
print(f"Model moved to: {next(model.parameters()).device}")

dummy_input = torch.randn(1, 3, 224, 224).to(device)  # batch_size=1, channels=3, height=224, width=224
print(f"\nDummy input shape: {dummy_input.shape}")

# Run inference
model.eval()  # Set to evaluation mode
with torch.no_grad():  # Don't compute gradients (saves memory)
    output = model(dummy_input)

print(f"Model output shape: {output.shape}")
print(f"Output represents probabilities for {output.shape[1]} ImageNet classes")
print(f"Raw output (first 10 values): {output[0][:10]}")

print("\n" + "="*50)
print("STEP 3: Modifying Model for Car Classification")
print("="*50)

# Let's say we want to classify 3 types of cars
car_classes = ['honda', 'toyota', 'bmw']
num_car_classes = len(car_classes)
print(f"Our car classes: {car_classes}")
print(f"Number of classes: {num_car_classes}")

model.fc = nn.Linear(model.fc.in_features, num_car_classes)
print("New layer weights:")
print(model.fc.weight.data)
print("New layer biases:")
print(model.fc.bias.data)

print(f"New final layer: {model.fc}")

# Move the modified model to GPU
model = model.to(device)

# Test the modified model
model.eval()
with torch.no_grad():
    car_output = model(dummy_input)

print(f"\nCar classification output shape: {car_output.shape}")
print(f"Raw logits for car classes: {car_output[0]}")

import torch.nn.functional as F
probabilities = F.softmax(car_output, dim=1)
print(f"Probabilities: {probabilities[0]}")

# Get the predicted class
predicted_class_idx = torch.argmax(car_output, dim=1)
predicted_class_name = car_classes[predicted_class_idx.item()]
confidence = probabilities[0][predicted_class_idx].item()

print(f"\nPredicted class index: {predicted_class_idx.item()}")
print(f"Predicted class name: {predicted_class_name}")
print(f"Confidence: {confidence:.1%}")

print(f"\n💡 Note: This prediction is random because we haven't trained the model yet!")


print("\n" + "="*50)
print("STEP 4: Image Preprocessing Pipeline")
print("="*50)
transform = transforms.Compose([
    transforms.CenterCrop((224, 224)),
    transforms.ToTensor(),
    transforms.Normalize([0.485, 0.456, 0.406], [0.229, 0.224, 0.225])
])

print("Transform pipeline:")
for i, t in enumerate(transform.transforms):
    print(f"  {i+1}. {t}")