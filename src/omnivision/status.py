from fastapi import FastAPI
from datetime import datetime
from pydantic import BaseModel
from pymongo import MongoClient
from dotenv import load_dotenv
import os

load_dotenv()

app = FastAPI()

MONGO_URI = os.getenv("MongoDB_URI")
MONGO_DB = os.getenv("MongoDB_DB", "monitoring_system")

client = MongoClient(MONGO_URI)
db = client[MONGO_DB]
status_collection = db["phone_status"]


class PhoneStatus(BaseModel):
    device_id: str
    timestamp: datetime
    battery_percentage: int
    is_charging: bool
    battery_temperature: float
    recording: bool
    storage_used: int
    signal: int
    network_type: str


@app.post("/status")
async def log_status(status: PhoneStatus):
    status_dict = status.dict()
    status_collection.insert_one(status_dict)
    print(f"[{status.timestamp}] Status logged for device {status.device_id}")
    return {"message": "Status logged successfully", "device_id": status.device_id}


@app.get("/status/logs")
async def get_logs():
    logs = list(status_collection.find({}, {"_id": 0}))
    print(f"Retrieved {len(logs)} logs from the database")
    return {"logs": logs}