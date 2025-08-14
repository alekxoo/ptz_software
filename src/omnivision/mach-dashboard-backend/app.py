# app.py
import os
import json
import time
import asyncio
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional

import certifi
import httpx
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from pymongo import MongoClient, ASCENDING, DESCENDING
from pymongo.errors import PyMongoError
from dotenv import load_dotenv

# -----------------------------
# Env & Config
# -----------------------------
load_dotenv()

MONGO_URI = os.getenv("MongoDB_URI", "mongodb://localhost:27017")
MONGO_DB = os.getenv("MongoDB_DB", "monitoring_system")

CORS_ALLOW_ORIGINS = os.getenv(
    "CORS_ALLOW_ORIGINS",
    "http://localhost:5173,http://localhost:3000"
).split(",")

# Tailscale discovery (optional but recommended)
TS_API_KEY = os.getenv("TS_API_KEY")     # e.g., tskey-xxxx
TS_TAILNET = os.getenv("TS_TAILNET")     # e.g., machdynamics.ai

# Fallback / override device list
# Example: DEVICES_JSON='[{"id":"cam01","name":"phone-server","tailscaleIp":"100.64.0.10"}]'
DEVICES_JSON = os.getenv("DEVICES_JSON", "[]")

# Device ports
PHONE_SVR_PORT = int(os.getenv("PHONE_SVR_PORT", "1821"))  # phone-server endpoints
WEBCAM_PORT    = int(os.getenv("WEBCAM_PORT", "8080"))     # IP Webcam default

# Polling cadence
POLL_INTERVAL_SECONDS = int(os.getenv("POLL_INTERVAL_SECONDS", "30"))  # 30 or 60

# When listing devices, consider docs older than this "offline" (not used in storage)
DEVICE_STALENESS_SECONDS = int(os.getenv("DEVICE_STALENESS_SECONDS", "180"))

# -----------------------------
# FastAPI app
# -----------------------------
app = FastAPI(title="Mach Local Monitor")
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ALLOW_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# -----------------------------
# MongoDB
# -----------------------------
try:
    use_tls = ("mongodb.net" in MONGO_URI) or MONGO_URI.startswith("mongodb+srv")
    client = MongoClient(
        MONGO_URI,
        tls=use_tls,
        tlsCAFile=certifi.where() if use_tls else None,
        serverSelectionTimeoutMS=20000,
    )
    db = client[MONGO_DB]
    col_status  = db["phone_status"]   # main collection (what your UI will read)
    col_power   = db["power_status"]   # optional numeric snapshot of Jackery
    col_alerts  = db["alerts"]         # warnings/errors
    col_devices = db["devices"]        # discovered devices

    # indexes
    col_status.create_index([("device_id", ASCENDING), ("timestamp", DESCENDING)])
    col_power.create_index([("device_id", ASCENDING), ("ts", DESCENDING)])
    col_alerts.create_index([("timestamp", DESCENDING)])
    col_devices.create_index([("tailscaleIp", ASCENDING)], unique=True)
    col_device_snapshots = db["device_snapshots"]
    col_device_latest = db["device_latest"]

    col_device_snapshots.create_index([("device_id", ASCENDING), ("timestamp", DESCENDING)])
    col_device_latest.create_index([("device_id", ASCENDING)], unique=True)

except Exception as e:
    print(f"[WARN] Mongo init issue (checked in /api/healthz): {e}")
    db = col_status = col_power = col_alerts = col_devices = None  # will be caught in healthz

# -----------------------------
# Models (for POST ingestion)
# -----------------------------
class PhoneStatusIn(BaseModel):
    device_id: str
    timestamp: datetime
    battery_percentage: Optional[float] = None
    is_charging: Optional[bool] = None
    battery_temperature: Optional[float] = None
    recording: Optional[bool] = None
    storage_used: Optional[float] = None
    signal: Optional[int] = None
    network_type: Optional[str] = "tailscale"
    latency_manual_ms: Optional[float] = None
    raw: Optional[Dict[str, Any]] = None

# -----------------------------
# Helpers
# -----------------------------
def _now() -> datetime:
    return datetime.now(timezone.utc)

def _last_value(series: dict) -> Optional[float]:
    """IP Webcam sensors.json -> last scalar value"""
    try:
        data = series.get("data") or []
        if not data:
            return None
        _, val = data[-1]
        if isinstance(val, list):
            val = val[-1]
        return float(val)
    except Exception:
        return None

def _num_from_unit(s: Optional[str], unit_suffix: str) -> Optional[float]:
    if s is None:
        return None
    try:
        return float(str(s).replace(unit_suffix, "").strip())
    except Exception:
        return None

def _add_unit_once(val: Optional[str], unit: str) -> Optional[str]:
    if val is None:
        return None
    s = str(val).strip().strip('"').strip()
    # remove trailing unit if already there (case-insensitive), then add once
    if s.lower().endswith(unit.lower()):
        s = s[: -len(unit)].strip()
    return f"{s}{unit}"

def _save_device_doc(doc: dict):
    """
    Persist ONE device doc in two places:
      - device_snapshots: append-only history
      - device_latest: upsert last-known
    Expects `doc` to already be the FINAL API shape you want.
    """

    allow_device_id = ["h2r-pixel-1.tail9e9110.ts.net", "h2r-pixel-3.tail9e9110.ts.net"]
    if doc.get("device_id") not in allow_device_id:
        #         # Only allow these devices to be saved
        return
            
    if col_device_snapshots is not None:
        try:
            col_device_snapshots.insert_one({**doc})
        except Exception:
            pass
        
    if col_device_latest is not None:
        try:
            col_device_latest.replace_one({"device_id": doc.get("device_id")}, {**doc}, upsert=True)
        except Exception:
            pass

# -----------------------------
# Discovery
# -----------------------------
async def tailscale_list_devices() -> List[Dict[str, Any]]:
    """Return devices from Tailscale: [{id,name,tailscaleIp,os}]"""
    if not TS_API_KEY or not TS_TAILNET:
        return []
    url = f"https://api.tailscale.com/api/v2/tailnet/{TS_TAILNET}/devices"
    # Tailscale Basic auth: (username=API_KEY, password="")
    async with httpx.AsyncClient(timeout=25.0, auth=(TS_API_KEY, "")) as cx:
        r = await cx.get(url)
        r.raise_for_status()
        data = r.json()

    out: List[Dict[str, Any]] = []
    for dev in data.get("devices", []):
        addrs = dev.get("addresses", [])
        ip = next((a for a in addrs if a.startswith("100.")), addrs[0] if addrs else None)
        if not ip:
            continue
        item = {
            "id": dev.get("id") or dev.get("name") or ip,
            "name": dev.get("name") or ip,
            "tailscaleIp": ip,
            "os": dev.get("os"),
        }
        out.append(item)
        # upsert for visibility
        if col_devices is not None:
            col_devices.update_one(
                {"tailscaleIp": ip},
                {"$set": {"name": item["name"], "os": item["os"], "updatedAt": _now()}},
                upsert=True
            )
    return out

def static_devices() -> List[Dict[str, Any]]:
    try:
        items = json.loads(DEVICES_JSON)
        return items if isinstance(items, list) else []
    except Exception:
        return []

async def discover_devices() -> List[Dict[str, Any]]:
    """Merge static + tailscale list (tailscale wins on same IP)"""
    merged: Dict[str, Dict[str, Any]] = {}
    for d in static_devices():
        key = d.get("tailscaleIp") or d.get("id")
        if key:
            merged[key] = d
    for d in await tailscale_list_devices():
        key = d.get("tailscaleIp") or d.get("id")
        if key:
            merged[key] = d
    return list(merged.values())




# -----------------------------
# Per-device poll (combined)
# -----------------------------
async def poll_device_combined(device_id: str, device_name: str, ip: str):
    """
    One poll writes one doc into col_status with the exact fields requested:
      device_id, "battery charging", "battery level", "battery temperrature", JackeryData{...}
    Also writes numeric twins + an optional power snapshot to col_power.
    """
    now = _now()

    # ---- Battery from IP Webcam ----
    batt_level_s, batt_temp_s, batt_charging_s = None, None, None
    batt_level_num, batt_temp_num, is_charging = None, None, None

    try:
        sensors_url = f"http://{ip}:{WEBCAM_PORT}/sensors.json?sense=battery_charging,battery_level,battery_temp"
        async with httpx.AsyncClient(timeout=10.0) as cx:
            r = await cx.get(sensors_url)
            r.raise_for_status()
            j = r.json()

        level = _last_value(j.get("battery_level", {}))
        temp  = _last_value(j.get("battery_temp", {}))
        chg   = _last_value(j.get("battery_charging", {}))  # usually 0/1

        batt_level_num  = level
        batt_temp_num   = temp
        is_charging     = True if (chg is not None and float(chg) > 0.0) else (False if chg is not None else None)
        batt_level_s    = f"{int(level)}" if level is not None else None
        batt_temp_s     = f"{round(temp,1)}" if temp is not None else None
        batt_charging_s = "connected" if is_charging else ("disconnected" if is_charging is not None else None)

    except Exception as e:
        if col_alerts is not None:
            col_alerts.insert_one({
                "device_id": device_name,
                "level": "warning",
                "message": f"IP Webcam sensors fetch failed: {e}",
                "timestamp": now
            })

    # ---- Jackery from phone-server ----
    # ---- Jackery from phone-server ----
    jackery_str = {"temperature": None, "input_power": None, "output_power": None}
    try:
        url = f"http://100.121.57.115:{PHONE_SVR_PORT}/LastJackeryData"
        async with httpx.AsyncClient(timeout=10.0) as cx:
            r = await cx.get(url)
            r.raise_for_status()
            line = r.text.strip()
        # Expected CSV: utc, tempC, inputW, outputW
        parts = [p.strip().strip('"') for p in line.split(",")]  # strip any quotes
        temp_c = parts[1] if len(parts) > 1 else None
        in_w   = parts[2] if len(parts) > 2 else None
        out_w  = parts[3] if len(parts) > 3 else None

        # normalize so you never get duplicated units or stray quotes
        jackery_str["temperature"]  = _add_unit_once(temp_c, "℃")
        jackery_str["input_power"]  = _add_unit_once(in_w, "W")
        jackery_str["output_power"] = _add_unit_once(out_w, "W")

        # optional numeric snapshot for analysis
        if col_power is not None:
            def _num(s, unit): 
                if s is None: return None
                try: return float(str(s).strip().strip('"').replace(unit, '').strip())
                except: return None
            col_power.insert_one({
                "device_id": device_name,
                "ts": now,
                "temp_c": _num(temp_c, "℃"),
                "solar_w": _num(in_w, "W"),
                "load_w": _num(out_w, "W"),
                "raw": {"csv": line},
            })

    except Exception as e:
        if col_alerts is not None:
            col_alerts.insert_one({
                "device_id": device_name,
                "level": "warning",
                "message": f"Jackery LastJackeryData fetch failed: {e}",
                "timestamp": now
            })

    # ---- Build the FINAL device doc (same shape you want in Mongo and API) ----
    device_doc = {
        "device_id": device_name,
        "timestamp": now,                         # keep TZ-aware datetime
        "battery charging": batt_charging_s,      # exact key
        "battery level": batt_level_s,            # exact key
        "battery temperrature": batt_temp_s,      # exact key (spelling per request)
        "JackeryData": jackery_str,
        "battery_level_num": batt_level_num,      # numeric twins for charts
        "battery_temp_num": batt_temp_num,
        "is_charging": is_charging,
        "network_type": "tailscale",
    }

    # Write the canonical doc to the main series (as before)
    try:
        if col_status is not None:
            col_status.insert_one({**device_doc})
    except Exception as e:
        if col_alerts is not None:
            col_alerts.insert_one({
                "device_id": device_name,
                "level": "warning",
                "message": f"status insert failed: {e}",
                "timestamp": now
            })

    # NEW: also persist the *same* doc to snapshots and latest
    _save_device_doc(device_doc)


# -----------------------------
# Background poll loop
# -----------------------------
_running = False

async def poll_loop():
    global _running
    if _running:
        return
    _running = True
    print("[poll] started")

    while True:
        try:
            devices = await discover_devices()
            if not devices:
                devices = static_devices()

            tasks = []
            for d in devices:
                ip = d.get("tailscaleIp")
                if not ip:
                    continue
                dev_name = d.get("name") or d.get("id") or ip
                dev_id   = d.get("id") or dev_name
                tasks.append(poll_device_combined(dev_id, dev_name, ip))

            if tasks:
                await asyncio.gather(*tasks)

        except Exception as e:
            if col_alerts is not None:
                col_alerts.insert_one({
                    "device_id": "poller",
                    "level": "warning",
                    "message": f"poll loop error: {e}",
                    "timestamp": _now()
                })

        await asyncio.sleep(POLL_INTERVAL_SECONDS)

# -----------------------------
# API Endpoints
# -----------------------------
@app.get("/api/healthz")
def healthz():
    try:
        client.admin.command("ping")
        return {"ok": True, "mongo": True}
    except Exception as e:
        return {"ok": False, "mongo": False, "error": str(e)}

@app.get("/api/devices")
def api_devices():
    now = _now()
    items = list(col_device_latest.find({}, {"_id": 0}))  # already final shape
    # add status based on staleness
    for d in items:
        ts = d.get("timestamp")
        if isinstance(ts, str):
            try: ts = datetime.fromisoformat(ts)
            except: ts = now
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        age = (now - ts).total_seconds()
        d["status"] = "online" if age <= DEVICE_STALENESS_SECONDS else "offline"
    items.sort(key=lambda x: x.get("device_id", ""))
    return items

@app.get("/api/alerts")
def api_alerts(limit: int = 50):
    return list(col_alerts.find({}, {"_id": 0}).sort("timestamp", DESCENDING).limit(int(limit)))

@app.post("/api/status")
def ingest_status(payload: PhoneStatusIn):
    try:
        col_status.insert_one(payload.model_dump())
        return {"ok": True}
    except PyMongoError as e:
        return {"ok": False, "error": str(e)}

# -----------------------------
# Startup
# -----------------------------
@app.on_event("startup")
async def _startup():
    print("[startup] Mach Local Monitor")
    asyncio.create_task(poll_loop())
