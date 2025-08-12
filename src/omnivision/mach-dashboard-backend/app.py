from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware

from datetime import datetime, timezone, timedelta
from dotenv import load_dotenv
from pymongo import MongoClient, ASCENDING, DESCENDING
import os

load_dotenv()

MONGO_URI = os.getenv("MongoDB_URI")
MONGO_DB = os.getenv("MongoDB_DB", "monitoring_system")
OFFLINE_SECS = int(os.getenv("DEVICE_OFFLINE_SECONDS", "180"))

# CORS
origins = [o.strip() for o in os.getenv("CORS_ALLOW_ORIGINS", "*").split(",") if o.strip()]

client = MongoClient(MONGO_URI)
db = client[MONGO_DB]
col_status = db["phone_status"]
col_alerts = db["alerts"]
col_weather = db.get_collection("weather")

app = FastAPI(title="Mach Backend")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"] if origins == ["*"] else origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

def parse_ts_utc(val):
    """
    Accepts ISO string or datetime from Mongo and returns a tz-aware UTC datetime.
    Returns None if parsing fails.
    """
    if val is None:
        return None
    if isinstance(val, datetime):
        # If naive, assume UTC; if aware, convert to UTC
        return val.replace(tzinfo=timezone.utc) if val.tzinfo is None else val.astimezone(timezone.utc)
    if isinstance(val, str):
        s = val.strip()
        # Support '...Z' by converting to +00:00
        if s.endswith("Z"):
            s = s[:-1] + "+00:00"
        try:
            dt = datetime.fromisoformat(s)
            return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt.astimezone(timezone.utc)
        except Exception:
            return None
    return None

# ----- Utility: latest status per device -----
def latest_status_per_device():
    pipeline = [
        {"$sort": {"device_id": ASCENDING, "timestamp": DESCENDING}},
        {"$group": {
            "_id": "$device_id",
            "doc": {"$first": "$$ROOT"}
        }},
        {"$replaceRoot": {"newRoot": "$doc"}},
        {"$sort": {"device_id": ASCENDING}}
    ]
    return list(col_status.aggregate(pipeline))

@app.get("/api/devices")
def get_devices():
    now = datetime.now(timezone.utc)
    items = latest_status_per_device()
    out = []
    for d in items:
        ts = parse_ts_utc(d.get("timestamp"))
        # If we couldn't parse, treat as very old
        age_secs = (now - ts).total_seconds() if ts else 10**9
        status = "online" if age_secs <= OFFLINE_SECS else "offline"

        out.append({
            "id": d.get("device_id"),
            "name": d.get("device_name") or d.get("device_id"),
            "tailscaleIp": d.get("tailscale_ip"),
            "status": status,
            "battery": d.get("battery_percentage"),
            "tempC": d.get("battery_temperature"),
            "latencyMs": d.get("latency_manual_ms") or d.get("latency_first_byte_ms"),
            "lastSeen": (ts.isoformat().replace("+00:00","Z") if ts else None),
        })
    return out


@app.get("/api/alerts")
def get_alerts(limit: int = Query(50, ge=1, le=500)):
    docs = list(col_alerts.find({}, {"_id": 0})
                .sort("timestamp", DESCENDING)
                .limit(limit))
    return docs

@app.get("/api/weather/latest")
def weather_latest():
    if not col_weather:
        return {}
    doc = col_weather.find_one({}, sort=[("timestamp", DESCENDING)], projection={"_id": 0})
    return doc or {}

@app.get("/api/healthz")
def healthz():
    # Basic check that Mongo works
    try:
        col_status.estimated_document_count()
        return {"ok": True}
    except Exception as e:
        return {"ok": False, "error": str(e)}
