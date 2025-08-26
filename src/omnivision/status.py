from fastapi import FastAPI
from datetime import datetime
from pymongo import MongoClient
from dotenv import load_dotenv
import requests
import time
import os

load_dotenv()

app = FastAPI()

CAMERA_IP = os.getenv("Blu_B160v")  # Tailscale or local IP
MONGO_URI = os.getenv("MongoDB_URI")
MONGO_DB = os.getenv("MongoDB_DB", "monitoring_system")

# Fetch sensor data from the IP Webcam server
try:
    response = requests.get(f"{CAMERA_IP}/sensors.json?sense=battery_charging,battery_level,battery_temp")
    data = response.json()
    start_time = time.time()
    responses = requests.get(CAMERA_IP)
    end_time = time.time()
    battery_charging = data.get("battery_charging", {}).get("unit", [[None, [None]]])
    battery_level = data.get("battery_level", {}).get("data", [[None, [None]]])[0][1][0]
    battery_temp = data.get("battery_temp", {}).get("data", [[None, [None]]])[0][1][0]
    response_time = end_time - start_time
    elapsed_time = responses.elapsed.total_seconds()


    doc = {
        "device_id": "Blu_B160v",
        "timestamp": datetime.now().isoformat(),
        "response_time": end_time - start_time,
        "elapsed_time": responses.elapsed.total_seconds(),
        "battery_charging": battery_charging,
        "battery_percentage": battery_level,
        "battery_temperature": battery_temp,
    }

    print("Parsed data:", doc)
    # Calculate response time (Manual timing- measure before call .get() until response is received)
    print(f"Response time: {end_time - start_time} s")

    # Elapsed time for the request is measured the time when response is sent to the first byte of response received
    print(f"Request elapsed time: {responses.elapsed.total_seconds()} s")

except Exception as e:
    print("Failed to fetch sensor data:", e)
    exit()

# Insert the document into MongoDB
try:
    client = MongoClient(MONGO_URI)
    db = client[MONGO_DB]
    status_collection = db["phone_status"]
    result = status_collection.insert_one(doc)
    print("Inserted into MongoDB:", result.inserted_id)

except Exception as e:
    print("Failed to insert into MongoDB:", e)