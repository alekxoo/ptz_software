# app.py
import os
import json
import asyncio
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, List, Optional, Tuple

from bson.json_util import dumps
import certifi
import httpx
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from pymongo import MongoClient, ASCENDING, DESCENDING
from pymongo.errors import PyMongoError
from dotenv import load_dotenv
from fastapi.responses import JSONResponse
from bson import ObjectId
try:
    # When running as a package (recommended)
    from . import local_store as offline
except Exception:
    # When running as a standalone module (fallback)
    import local_store as offline  # type: ignore
# ──────────────────────────────────────────────────────────────────────────────
# ENV & CONFIG
# ──────────────────────────────────────────────────────────────────────────────
# Load .env from current working dir and also from this module's directory
_ENV_NEARBY = os.path.join(os.path.dirname(__file__), ".env")
load_dotenv()  # CWD or parent
if os.path.exists(_ENV_NEARBY):
    load_dotenv(_ENV_NEARBY)

MONGO_URI  = os.getenv("MongoDB_URI", "mongodb://localhost:27017")
MONGO_DB   = os.getenv("MongoDB_DB",  "monitoring_system")
OFFLINE_ONLY = os.getenv("OFFLINE_ONLY", "false").strip().lower() in {"1", "true", "yes"}

# CORS
CORS_ALLOW_ORIGINS = os.getenv("CORS_ALLOW_ORIGINS", "*")

# Tailscale Admin API
TS_API_KEY  = os.getenv("TS_API_KEY")          # tskey-xxxxx
TS_TAILNET  = os.getenv("TS_TAILNET")          # e.g. yourdomain.com
TS_API_BASE = os.getenv("TS_API_BASE", "https://api.tailscale.com/api/v2")
TS_CONNECTED_WINDOW_SECONDS = int(os.getenv("TS_CONNECTED_WINDOW_SECONDS", "120"))

# Optional static devices JSON (for bootstrap/fallback)
DEVICES_JSON = os.getenv("DEVICES_JSON", "[]")

# Device ports
PHONE_SVR_PORT = int(os.getenv("PHONE_SVR_PORT", "1821"))  # phone-server endpoints
WEBCAM_PORT    = int(os.getenv("WEBCAM_PORT", "8080"))     # IP Webcam default

# Polling cadence & freshness
POLL_INTERVAL_SECONDS      = int(os.getenv("POLL_INTERVAL_SECONDS", "30"))
DEVICE_STALENESS_SECONDS   = int(os.getenv("DEVICE_STALENESS_SECONDS", "180"))

# ──────────────────────────────────────────────────────────────────────────────
# FASTAPI
# ──────────────────────────────────────────────────────────────────────────────
app = FastAPI(title="Mach Local Monitor")
app.add_middleware(
    CORSMiddleware,
        allow_origins=["https://mach-dashboard-7aa42.web.app"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Helper to persist /api/devices output locally for debugging/exports
def _save_devices_json(items: List[Dict[str, Any]]):
    try:
        default_path = os.path.join(os.path.dirname(__file__), "devices_snapshot.json")
        export_path = os.getenv("DEVICES_EXPORT_PATH", default_path)
        dir_name = os.path.dirname(export_path)
        if dir_name:
            os.makedirs(dir_name, exist_ok=True)
        with open(export_path, "w", encoding="utf-8") as f:
            json.dump(items, f, ensure_ascii=False, indent=2, default=str)
        print(f"[INFO] /api/devices snapshot written to: {os.path.abspath(export_path)}")
    except Exception as e:
        # Non-fatal: just log
        print(f"[WARN] Failed to write devices JSON: {e}")

# Offline queue directory (for fallback when Mongo is unavailable)
OFFLINE_QUEUE_DIR = "C:/Users/Lemon/iCloudDrive/Documents/AboutMe/Work/MyJob/vscode/ptz_software/src/omnivision/mach-dashboard-backend/offline_queue"

# ──────────────────────────────────────────────────────────────────────────────
# MONGO
# ──────────────────────────────────────────────────────────────────────────────
try:
    use_tls = ("mongodb.net" in MONGO_URI) or MONGO_URI.startswith("mongodb+srv")
    client = MongoClient(
        MONGO_URI,
        tls=use_tls,
        tlsCAFile=certifi.where() if use_tls else None,
        serverSelectionTimeoutMS=20000,
    )
    db = client[MONGO_DB]
    # col_logs = db.["logs"]

    col_status   = db["phone_status"]      # canonical per-sample series (final API shape)
    col_power    = db["power_status"]      # optional numeric Jackery samples
    col_alerts   = db["alerts"]            # warnings/errors
    col_devices  = db["devices"]           # discovery cache (tailscale)
    col_snap     = db["device_snapshots"]  # append-only snapshots of device_doc
    col_latest   = db["device_latest"]     # last-known device_doc
    col_commands = db["commands"]          # queued control commands for agent

    col_status.create_index([("device_id", ASCENDING), ("timestamp", DESCENDING)])
    col_power.create_index([("device_id", ASCENDING), ("ts", DESCENDING)])
    col_alerts.create_index([("timestamp", DESCENDING)])
    col_devices.create_index([("tailscaleIp", ASCENDING)], unique=True)
    col_snap.create_index([("device_id", ASCENDING), ("timestamp", DESCENDING)])
    col_latest.create_index([("device_id", ASCENDING)], unique=True)
    col_commands.create_index([("status", ASCENDING), ("created_at", DESCENDING)])
except Exception as e:
    print(f"[WARN] Mongo init issue: {e}")
    db = col_status = col_power = col_alerts = col_devices = col_snap = col_latest = None
    col_commands = None

# ──────────────────────────────────────────────────────────────────────────────
# MODELS
# ──────────────────────────────────────────────────────────────────────────────
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

class AddDevice(BaseModel):
    device_id: str
    name: str
    location: Optional[str] = None
    tailscaleIp: Optional[str] = None

class AlertIn(BaseModel):
    device_id: str
    level: str  # 'warning' | 'critical'
    message: str
    timestamp: Optional[datetime] = None

# ──────────────────────────────────────────────────────────────────────────────
# HELPERS
# ──────────────────────────────────────────────────────────────────────────────
def _now() -> datetime:
    # project asked for UTC minus 5h in earlier iterations; keep UTC and
    # subtract display-side if needed. If you truly want UTC-5 persisted:
    return datetime.now(timezone.utc)  # or: - timedelta(hours=5)


def _format_last_seen_display(value: Any, now: datetime) -> str:
    """Return one of: "Connected" | "1:00 AM CDT" | "Aug 17".
    - Preserve provided friendly strings (e.g., "1:00 AM CDT", "Aug 17", "Connected").
    - If ISO datetime is provided, convert to US Central and choose format
      based on freshness (<24h -> time with CDT/CST, else -> Mon DD).
    """
    # Pass-through common friendly strings from discovery
    if isinstance(value, str):
        s = value.strip()
        if not s:
            return s
        if s.lower() == "connected":
            return "Connected"
        # If looks like '1:00 AM CDT' or 'Aug 17', keep it
        parts = s.split()
        if len(parts) == 3 and parts[1].upper() in {"AM", "PM"}:
            return s  # e.g., '1:00 AM CDT'
        try:
            # e.g., 'Aug 17' or 'August 17'
            datetime.strptime(s, "%b %d")
            return s
        except Exception:
            try:
                datetime.strptime(s, "%B %d")
                return s
            except Exception:
                pass

    # Try to parse to datetime (ISO or datetime)
    dt: Optional[datetime] = None
    if isinstance(value, datetime):
        dt = value
    elif isinstance(value, str):
        try:
            dt = datetime.fromisoformat(value)
        except Exception:
            dt = None

    if dt is None:
        # Unknown, return string form
        return str(value) if value is not None else ""

    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)

    # Approximate US Central DST: Mar–Nov as CDT (-5), else CST (-6)
    month = (dt.astimezone(timezone.utc)).month
    is_dst = 3 <= month <= 11
    offset_hours = -5 if is_dst else -6
    tz_central = timezone(timedelta(hours=offset_hours))
    dt_c = dt.astimezone(tz_central)

    abbr = "CDT" if is_dst else "CST"
    # Compare local Central calendar days to decide label shape
    try:
        now_c = now.astimezone(tz_central)
    except Exception:
        now_c = now
    days_diff = (now_c.date() - dt_c.date()).days
    if days_diff == 0:
        # today -> time only
        return f"{dt_c.strftime('%I:%M %p').lstrip('0')} {abbr}"
    if days_diff == 1:
        # yesterday -> date + time
        return f"{dt_c.strftime('%b %d, %I:%M %p').replace(' 0', ' ').lstrip('0')} {abbr}"
    # older -> date only
    return dt_c.strftime("%b %d")


# ──────────────────────────────────────────────────────────────────────────────
# API ENDPOINTS
# ──────────────────────────────────────────────────────────────────────────────
@app.get("/api/healthz")
def healthz():
    try:
        client.admin.command("ping")
        return {"ok": True, "mongo": True}
    except Exception as e:
        return {"ok": False, "mongo": False, "error": str(e)}

@app.get("/api/devices")
def api_devices(download: bool = Query(False, description="If true, force JSON download")):
    """Return devices directly from Tailscale Admin API when configured.
    Falls back to existing Mongo-backed view if TS creds are missing or call fails.
    """
    # Prefer live data from Tailscale Admin API
    if TS_API_KEY and TS_TAILNET:
        try:
            url = f"{TS_API_BASE}/tailnet/{TS_TAILNET}/devices"
            headers = {"Authorization": f"Bearer {TS_API_KEY}"}
            with httpx.Client(timeout=20) as client:
                r = client.get(url, headers=headers)
                r.raise_for_status()
                payload = r.json()
            raw_devices = payload.get("devices", payload if isinstance(payload, list) else [])
            now = _now()

            def pick_100_addr(addrs: List[str]) -> Optional[str]:
                if not addrs:
                    return None
                for a in addrs:
                    if isinstance(a, str) and a.startswith("100."):
                        return a
                return addrs[0]

            items: List[Dict[str, Any]] = []
            for dev in raw_devices:
                name = dev.get("name") or dev.get("hostname") or dev.get("id")
                addrs = dev.get("addresses") or dev.get("ipAddresses") or []
                tailscale_ip = pick_100_addr(addrs)
                last_seen = dev.get("lastSeen")  # ISO or null/absent when connected
                online = dev.get("online")
                # Derive connected per Tailscale semantics: explicitly online, or null/empty lastSeen
                connected = bool(online) or (last_seen in (None, ""))
                # If last_seen is a recent ISO (within TS_CONNECTED_WINDOW_SECONDS), treat as connected
                if last_seen not in (None, ""):
                    try:
                        iso_str = str(last_seen)
                        if iso_str.endswith('Z'):
                            iso_str = iso_str.replace('Z', '+00:00')
                        dt_ls = datetime.fromisoformat(iso_str)
                        if dt_ls.tzinfo is None:
                            dt_ls = dt_ls.replace(tzinfo=timezone.utc)
                        if (now - dt_ls).total_seconds() <= TS_CONNECTED_WINDOW_SECONDS:
                            connected = True
                    except Exception:
                        pass
                # Format lastSeen label
                if last_seen in (None, ""):
                    last_seen_label = "Connected"
                else:
                    try:
                        last_seen_label = _format_last_seen_display(str(last_seen), now)
                    except Exception:
                        last_seen_label = str(last_seen)

                item = {
                    "device_id": name,
                    "name": name,
                    "displayName": name.split(".tail", 1)[0] if isinstance(name, str) and ".tail" in name else name,
                    "tailscaleIp": tailscale_ip,
                    "connected": connected,
                    "lastSeen": last_seen_label,
                    "os": dev.get("os"),
                    "status": "online" if connected else "offline",
                }
                items.append(item)

            # Enrich with latest battery/charging from Mongo if available
            try:
                latest_docs = list(col_latest.find({}, {"_id": 0, "device_id": 1, "battery_level_num": 1, "battery_temp_num": 1, "is_charging": 1})) if col_latest is not None else []
            except Exception:
                latest_docs = []
            latest_map = {str(doc.get("device_id", "")).lower(): doc for doc in latest_docs}
            for it in items:
                key = str(it.get("device_id") or it.get("name") or "").lower()
                doc = latest_map.get(key)
                if doc:
                    if "battery_level_num" in doc:
                        it["battery_level_num"] = doc.get("battery_level_num")
                    if "battery_temp_num" in doc:
                        it["battery_temp_num"] = doc.get("battery_temp_num")
                    if "is_charging" in doc:
                        it["is_charging"] = doc.get("is_charging")

            items.sort(key=lambda x: (x.get("device_id") or x.get("name") or ""))
            _save_devices_json(items)
            if download:
                return JSONResponse(content=items, headers={
                    "Content-Disposition": "attachment; filename=devices.json"
                })
            return items
        except Exception as e:
            # Fall back to previous behavior if TS call fails
            print(f"[WARN] Tailscale API fetch failed: {e}")

    # Fallback: previous Mongo-backed behavior
    now = _now()
    # Pull latest device snapshots, newest first
    if col_latest is not None:
        try:
            items = list(col_latest.find({}, {"_id": 0}).sort("timestamp", DESCENDING))
        except Exception:
            # Fallback to unsorted if sort not available
            items = list(col_latest.find({}, {"_id": 0}))
    else:
        items = []
    disc_map: Dict[str, Dict[str, Any]] = {}
    try:
        for d in db.devices.find({}, {"_id": 0, "name": 1, "device_id": 1, "tailscaleIp": 1, "connected": 1, "lastSeen": 1, "os": 1}):
            key = (d.get("device_id") or d.get("name") or d.get("tailscaleIp") or "").lower()
            disc_map[key] = d
    except Exception:
        pass

    for d in items:
        ts = d.get("timestamp")
        if isinstance(ts, str):
            try:
                ts = datetime.fromisoformat(ts)
            except:
                ts = now
        if ts and ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        d["updatedAt"] = ts.isoformat() if isinstance(ts, datetime) else d.get("timestamp")
        key = (d.get("device_id") or d.get("name") or "").lower()
        disc = disc_map.get(key)
        if disc:
            ls_raw = disc.get("lastSeen")
            conn = bool(disc.get("connected", False))
            if isinstance(ls_raw, str):
                try:
                    iso = ls_raw
                    if iso.endswith('Z'):
                        iso = iso.replace('Z', '+00:00')
                    dt_ls = datetime.fromisoformat(iso)
                    if dt_ls.tzinfo is None:
                        dt_ls = dt_ls.replace(tzinfo=timezone.utc)
                    if (now - dt_ls).total_seconds() <= TS_CONNECTED_WINDOW_SECONDS:
                        conn = True
                        d["lastSeen"] = _format_last_seen_display(ls_raw, now)
                    else:
                        d["lastSeen"] = ls_raw
                except Exception:
                    d["lastSeen"] = ls_raw
            else:
                d["lastSeen"] = ls_raw
            d["connected"] = conn
            if "tailscaleIp" in disc:
                d["tailscaleIp"] = disc.get("tailscaleIp")
            if "os" in disc:
                d["os"] = disc.get("os")
            nm = disc.get("device_id") or disc.get("name") or d.get("device_id")
            if isinstance(nm, str) and ".tail" in nm:
                d["displayName"] = nm.split(".tail", 1)[0]
            elif isinstance(nm, str):
                d["displayName"] = nm
        d["status"] = "online" if d.get("connected") else "offline"
    # Order by most recent update first (using ISO string is fine as it's tz-aware)
    def _sort_key(d: Dict[str, Any]):
        return d.get("updatedAt") or d.get("timestamp") or ""
    items.sort(key=_sort_key, reverse=True)
    _save_devices_json(items)
    if download:
        return JSONResponse(content=items, headers={
            "Content-Disposition": "attachment; filename=devices.json"
        })
    return items

@app.get("/api/alerts")
def api_alerts(device_id: str, limit: int = 50):
    # Determine tracking status: prefer in-memory state, then fallback to Mongo flag
    is_tracking = False
    try:
        key = (device_id or "").lower()
        ts = tracking_state.get(key)
        if isinstance(ts, dict):
            is_tracking = bool(ts.get("is_tracking"))
        elif isinstance(ts, bool):
            is_tracking = ts
    except Exception:
        is_tracking = False

    if not is_tracking:
        try:
            device = col_devices.find_one({"device_id": device_id}) if col_devices is not None else None
            is_tracking = bool(device and device.get("tracking", False))
        except Exception:
            is_tracking = False

    if not is_tracking:
        return []
    if col_alerts is None:
        return []
    q = {"device_id": device_id}
    return list(col_alerts.find(q, {"_id": 0}).sort("timestamp", DESCENDING).limit(int(limit)))

@app.post("/api/alerts")
def api_alerts_post(payload: AlertIn):
    doc = {
        "device_id": payload.device_id,
        "level": payload.level,
        "message": payload.message,
        "timestamp": payload.timestamp or _now(),
    }
    try:
        if OFFLINE_ONLY:
            raise RuntimeError("offline-only")
        if col_alerts is not None:
            col_alerts.insert_one(doc)
        else:
            raise RuntimeError("col_alerts unavailable")
    except Exception:
        # Fallback to offline queue
        offline.enqueue("alerts", doc, OFFLINE_QUEUE_DIR)
    return {"ok": True}


@app.post("/api/status")
def ingest_status(payload: PhoneStatusIn):
    try:
        # Normalize numeric fields expected by UI and metrics
        ts: datetime = payload.timestamp if isinstance(payload.timestamp, datetime) else _now()
        doc_status = {
            "device_id": payload.device_id,
            "timestamp": ts,
            "battery_level_num": payload.battery_percentage,
            "battery_temp_num": payload.battery_temperature,
            "is_charging": payload.is_charging,
            "recording": payload.recording,
            "storage_used": payload.storage_used,
            "signal": payload.signal,
            "network_type": payload.network_type or "tailscale",
            "latency_manual_ms": payload.latency_manual_ms,
            "raw": payload.raw,
        }

        # Insert time-series sample (fallback to offline queue if needed)
        try:
            if OFFLINE_ONLY:
                raise RuntimeError("offline-only")
            if col_status is not None:
                col_status.insert_one(doc_status)
            else:
                raise RuntimeError("col_status unavailable")
        except Exception:
            offline.enqueue("phone_status", doc_status, OFFLINE_QUEUE_DIR)

        # Maintain latest snapshot for /api/devices
        device_latest = {
            "device_id": payload.device_id,
            "timestamp": ts,
            "battery_level_num": payload.battery_percentage,
            "battery_temp_num": payload.battery_temperature,
            "is_charging": payload.is_charging,
            "network_type": payload.network_type or "tailscale",
        }
        try:
            if OFFLINE_ONLY:
                raise RuntimeError("offline-only")
            if col_latest is not None:
                col_latest.update_one(
                    {"device_id": payload.device_id},
                    {"$set": device_latest},
                    upsert=True,
                )
            else:
                raise RuntimeError("col_latest unavailable")
        except Exception:
            offline.enqueue("device_latest", device_latest, OFFLINE_QUEUE_DIR)

        # Optional legacy snapshot for /logs endpoints and backward-compat keys
        legacy_snapshot = {
            "device_id": payload.device_id,
            "timestamp": ts,
            # Keep legacy string keys alongside numeric for existing UI paths
            "battery level": str(int(payload.battery_percentage)) if payload.battery_percentage is not None else None,
            "battery temperature": payload.battery_temperature,
            "battery charging": payload.is_charging,
        }
        try:
            if OFFLINE_ONLY:
                raise RuntimeError("offline-only")
            if col_snap is not None:
                col_snap.insert_one(legacy_snapshot)
            else:
                raise RuntimeError("col_snap unavailable")
        except Exception:
            offline.enqueue("device_snapshots", legacy_snapshot, OFFLINE_QUEUE_DIR)

        return {"ok": True}
    except PyMongoError as e:
        return {"ok": False, "error": str(e)}

# Camera control: queue commands for agent to execute on device phone-server
@app.post("/api/devices/{device_id}/camera/start")
def camera_start(device_id: str):
    doc = {
        "device_id": device_id,
        "type": "camera",
        "action": "start",
        "status": "pending",
        "created_at": _now(),
        "last_error": None,
        "attempts": 0,
    }
    try:
        if OFFLINE_ONLY:
            raise RuntimeError("offline-only")
        if col_commands is not None:
            res = col_commands.insert_one(doc)
            return {"ok": True, "id": str(res.inserted_id)}
        else:
            raise RuntimeError("col_commands unavailable")
    except Exception:
        # Fallback to offline queue (agent does not read this yet, but preserves intent)
        path = offline.enqueue("commands", doc, OFFLINE_QUEUE_DIR)
        return {"ok": True, "offline_path": path}


@app.post("/api/devices/{device_id}/camera/stop")
def camera_stop(device_id: str):
    doc = {
        "device_id": device_id,
        "type": "camera",
        "action": "stop",
        "status": "pending",
        "created_at": _now(),
        "last_error": None,
        "attempts": 0,
    }
    try:
        if OFFLINE_ONLY:
            raise RuntimeError("offline-only")
        if col_commands is not None:
            res = col_commands.insert_one(doc)
            return {"ok": True, "id": str(res.inserted_id)}
        else:
            raise RuntimeError("col_commands unavailable")
    except Exception:
        path = offline.enqueue("commands", doc, OFFLINE_QUEUE_DIR)
        return {"ok": True, "offline_path": path}


# Agent polling endpoints
@app.get("/api/commands/pending")
def commands_pending(limit: int = 20):
    if col_commands is None:
        return []
    try:
        cur = col_commands.find({"status": "pending"}).sort("created_at", ASCENDING).limit(int(limit))
        rows = list(cur)
        # normalize _id to string for frontend/agent
        out = []
        for r in rows:
            r2 = dict(r)
            try:
                r2["id"] = str(r2.pop("_id"))
            except Exception:
                pass
            out.append(json.loads(dumps(r2)))
        return out
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to list commands: {e}")


class CommandCompleteIn(BaseModel):
    status: str  # "success" | "failed"
    message: Optional[str] = None


@app.post("/api/commands/{cmd_id}/complete")
def command_complete(cmd_id: str, body: CommandCompleteIn):
    if col_commands is None:
        raise HTTPException(status_code=500, detail="commands collection unavailable")
    try:
        oid = ObjectId(cmd_id)
    except Exception:
        raise HTTPException(status_code=400, detail="invalid command id")
    try:
        res = col_commands.update_one(
            {"_id": oid},
            {"$set": {"status": body.status, "completed_at": _now(), "last_error": body.message}},
        )
        if res.matched_count == 0:
            raise HTTPException(status_code=404, detail="command not found")
        return {"ok": True}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to update command: {e}")


@app.get("/api/devices/{device_id}/webcam/reachable")
async def webcam_reachable(device_id: str, timeout_seconds: int = 8):
    """Ask the agent to probe IP Webcam (`/sensors.html`) reachability for a device.
    Returns a quick boolean based on command completion.
    """
    if OFFLINE_ONLY or col_commands is None:
        raise HTTPException(status_code=503, detail="command queue unavailable")

    # Enqueue a probe command
    doc = {
        "device_id": device_id,
        "type": "probe",
        "action": "webcam",
        "status": "pending",
        "created_at": _now(),
        "last_error": None,
        "attempts": 0,
    }
    try:
        res = col_commands.insert_one(doc)
        cmd_id = res.inserted_id
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"failed to enqueue probe: {e}")

    # Poll for completion up to timeout_seconds
    waited = 0.0
    interval = 0.5
    status = "pending"
    message: Optional[str] = None
    created_at = _now()
    while waited < max(1, timeout_seconds):
        try:
            row = col_commands.find_one({"_id": cmd_id}, {"status": 1, "last_error": 1, "created_at": 1, "completed_at": 1})
            if row:
                status = row.get("status", status)
                message = row.get("last_error")
                created_at = row.get("created_at") or created_at
                if status in ("success", "failed"):
                    break
        except Exception:
            pass
        await asyncio.sleep(interval)
        waited += interval

    reachable = True if status == "success" else False if status == "failed" else None
    # Compose response; include basic timing info
    now = _now()
    took_ms = None
    try:
        if isinstance(created_at, datetime):
            took_ms = int((now - created_at).total_seconds() * 1000)
    except Exception:
        took_ms = None
    return {"device_id": device_id, "reachable": reachable, "status": status, "message": message, "tookMs": took_ms}

# Add at global level
# Track per-device tracking status and server start time
tracking_state: Dict[str, Dict[str, Any]] = {}

@app.post("/api/devices/{device_id}/tracking/start")
async def start_tracking(device_id: str):
    started_at = _now()
    key = (device_id or "").lower()
    tracking_state[key] = {"is_tracking": True, "started_at": started_at}

    # Persist tracking flag so agent/collector (and multi-instance backends) can see it
    try:
        if OFFLINE_ONLY:
            raise RuntimeError("offline-only")
        if col_devices is not None:
            col_devices.update_one(
                {"device_id": device_id},
                {"$set": {"tracking": True, "updatedAt": started_at}},
                upsert=True,
            )
    except Exception:
        # Best-effort only; in offline-only mode the in-memory state will still control
        pass

    return {"status": "started", "device_id": device_id, "started_at": started_at}

@app.post("/api/devices/{device_id}/tracking/stop")
async def stop_tracking(device_id: str):
    key = (device_id or "").lower()
    tracking_state[key] = {"is_tracking": False, "started_at": None}

    # Persist tracking flag to false
    try:
        if OFFLINE_ONLY:
            raise RuntimeError("offline-only")
        if col_devices is not None:
            col_devices.update_one(
                {"device_id": device_id},
                {"$set": {"tracking": False, "updatedAt": _now()}},
                upsert=True,
            )
    except Exception:
        pass

    return {"status": "stopped", "device_id": device_id}

@app.get("/api/tracking")
def get_tracking():
    try:
        out_list: List[Dict[str, Any]] = []
        tracked: Dict[str, Dict[str, Any]] = {}

        # In-memory state
        for devid, st in tracking_state.items():
            if isinstance(st, dict) and st.get("is_tracking"):
                started_at = st.get("started_at")
                if isinstance(started_at, datetime):
                    started_at = started_at.isoformat()
                tracked[devid] = {"device_id": devid, "started_at": started_at}

        # Persisted state (Mongo) as fallback/merge
        try:
            if col_devices is not None:
                cur = col_devices.find({"tracking": True}, {"_id": 0, "device_id": 1})
                for row in cur or []:
                    devid = str(row.get("device_id") or "").lower()
                    if not devid:
                        continue
                    tracked.setdefault(devid, {"device_id": devid, "started_at": None})
        except Exception:
            # Ignore DB errors; return in-memory state
            pass

        tracked_ids = sorted(list(tracked.keys()))
        out_list = list(tracked.values())
        return {"tracked": tracked_ids, "devices": out_list}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to read tracking state: {e}")

@app.get("/api/devices/{device_id}/logs")
def get_device_logs(device_id: str, since: Optional[str] = None):
    if col_snap is None:
        raise HTTPException(status_code=500, detail="Log collection not found")

    query: Dict[str, Any] = {
        "device_id": device_id,
        "timestamp": {"$exists": True},
        "$or": [
            {"battery level": {"$exists": True}},
            {"battery temperature": {"$exists": True}},
        ],
    }
    # Optional lower bound filter
    if since:
        dt: Optional[datetime] = None
        try:
            # allow ms epoch
            if since.isdigit():
                dt = datetime.fromtimestamp(int(since) / 1000, tz=timezone.utc)
            else:
                s = since
                if s.endswith('Z'):
                    s = s.replace('Z', '+00:00')
                dt = datetime.fromisoformat(s)
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
        except Exception:
            dt = None
        if dt is not None:
            query["timestamp"] = {"$gte": dt}
    projection = {"_id": 0, "battery level": 1, "battery temperature": 1, "timestamp": 1}

    try:
        cursor = col_snap.find(query, projection).sort("timestamp", DESCENDING).limit(100)
        logs = list(cursor)[::-1]  # return oldest → newest

        for log in logs:
            # Convert strings to numbers where applicable
            battery_str = log.get("battery level")
            temp_str = log.get("battery temperature")
            try:
                log["battery_level_num"] = int(battery_str) if battery_str is not None else None
            except Exception:
                log["battery_level_num"] = None
            try:
                # Accept either int/float strings
                log["battery_temp_num"] = float(temp_str) if temp_str is not None else None
            except Exception:
                log["battery_temp_num"] = None

        return json.loads(dumps(logs))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch logs: {e}")

@app.get("/api/devices/{device_id}/logs/all")
def get_all_logs(device_id: str):
    logs = list(col_snap.find({"device_id": device_id}).sort("timestamp", 1))
    return json.loads(dumps(logs))


# ──────────────────────────────────────────────────────────────────────────────
# METRICS FOR CHARTS  (fixes 404 in your UI)
# ──────────────────────────────────────────────────────────────────────────────
# field -> (numeric field in col_status, default aggregation)
FIELD_MAP: Dict[str, str] = {
    "battery_percentage": "battery_level_num",
    "battery_temperature": "battery_temp_num",
    "latency_manual_ms": "latency_manual_ms",
}

def _parse_range(s: str) -> timedelta:
    # e.g. "6h", "30m", "1d"
    unit = s[-1].lower()
    n = int(s[:-1])
    return timedelta(hours=n) if unit == "h" else timedelta(minutes=n) if unit == "m" else timedelta(days=n)

def _parse_interval_to_seconds(s: str) -> int:
    unit = s[-1].lower()
    n = int(s[:-1])
    return n * 3600 if unit == "h" else n * 60 if unit == "m" else n

@app.get("/api/metrics")
def api_metrics(
    device_id: str = Query(...),
    field: str = Query(...),
    range: str = Query("1h"),
    interval: str = Query("1m"),
):
    num_field = FIELD_MAP.get(field)
    if not num_field:
        return {"points": []}

    now = _now()
    start = now - _parse_range(range)
    bucket_sec = _parse_interval_to_seconds(interval)

    pipeline = [
        {"$match": {
            "device_id": device_id,
            "timestamp": {"$gte": start, "$lte": now},
            num_field: {"$ne": None}
        }},
        {"$addFields": {
            "bucket": {
                "$toDate": {
                    "$multiply": [
                        {"$floor": {"$divide": [{"$toLong": "$timestamp"}, bucket_sec * 1000]}},
                        bucket_sec * 1000
                    ]
                }
            }
        }},
        {"$group": {"_id": "$bucket", "avg": {"$avg": f"${num_field}"}}},
        {"$project": {"t": "$_id", "avg": 1, "_id": 0}},
        {"$sort": {"t": 1}},
    ]
    rows = list(col_status.aggregate(pipeline)) if col_status else []
    # ensure ISO times for frontend
    for r in rows:
        if isinstance(r.get("t"), datetime):
            r["t"] = r["t"].isoformat()
    return {"points": rows}

# ──────────────────────────────────────────────────────────────────────────────
# STARTUP
# ──────────────────────────────────────────────────────────────────────────────
@app.on_event("startup")
async def _startup():
    print("[startup] Mach Local Monitor")


# Offline helper endpoints for UI
@app.get("/api/offline/status")
def offline_status():
    base = OFFLINE_QUEUE_DIR
    per: Dict[str, int] = {}
    total = 0
    try:
        if os.path.isdir(base):
            for name in os.listdir(base):
                if name == "failed":
                    continue
                cdir = os.path.join(base, name)
                if not os.path.isdir(cdir):
                    continue
                cnt = sum(1 for fn in os.listdir(cdir) if fn.endswith(".json"))
                if cnt:
                    per[name] = cnt
                    total += cnt
    except Exception:
        pass
    return {"pending_total": total, "per_collection": per}


class OfflineTestIn(BaseModel):
    message: Optional[str] = None


@app.post("/api/offline/test")
def offline_test(body: OfflineTestIn):
    doc = {
        "source": "ui",
        "timestamp": _now(),
        "message": body.message or "manual test",
    }
    path = offline.enqueue("debug_events", doc, OFFLINE_QUEUE_DIR)
    st = offline_status()
    return {"ok": True, "path": path, "status": st}

