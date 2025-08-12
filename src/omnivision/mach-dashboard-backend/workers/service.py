#!/usr/bin/env python3
import os, time, json, threading, queue, requests, certifi
from datetime import datetime, timezone, timedelta
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pymongo import MongoClient, ASCENDING
from pymongo.errors import PyMongoError
from dotenv import load_dotenv

load_dotenv()
# --------- ENV ---------
PHONE_BASE = os.getenv("PHONE_BASE", "http://phone-server:1821")
POLL_EVERY_S = int(os.getenv("POLL_EVERY_S", "120"))  # 2 minutes
MONGO_URI = os.getenv("MongoDB_URI")  # SRV URI
MONGO_DB = os.getenv("MongoDB_DB", "monitoring_system")
BUFFER_FILE = os.getenv("BUFFER_FILE", "./mongo_buffer.ndjson")

# --------- MONGO ---------
client = MongoClient(MONGO_URI, tlsCAFile=certifi.where(), serverSelectionTimeoutMS=15000)
db = client[MONGO_DB]
col_power  = db["jackery_power"]
col_cmd    = db["command_log"]
col_alerts = db["alerts"]
col_power.create_index([("ts", ASCENDING)])

# --------- APP ---------
app = FastAPI(title="Phone-Server Bridge")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], allow_methods=["*"], allow_headers=["*"], allow_credentials=True
)

last_poll_ts = None
consec_fail = 0
lock = threading.Lock()

# --------- Helpers ---------
def now_utc(): return datetime.now(timezone.utc)

def parse_last_row(text: str):
    """CSV last row: epoch, 34.9°C, 0W, 3W -> (ts, temp_c, in_w, out_w)"""
    # get the last non-empty line
    line = [ln for ln in text.strip().splitlines() if ln.strip()][-1]
    parts = [p.strip() for p in line.split(",")]
    if len(parts) < 4:
        raise ValueError(f"bad CSV row: {line}")
    epoch = int(parts[0])
    ts = datetime.fromtimestamp(epoch, tz=timezone.utc)
    def to_num(s):  # strip units
        s = s.replace("°C", "").replace("W", "").strip()
        return float(s) if s else 0.0
    temp_c = to_num(parts[1])
    in_w   = to_num(parts[2])
    out_w  = to_num(parts[3])
    return ts, temp_c, in_w, out_w, line

def safe_mongo_insert(col, doc):
    """Try insert; if Mongo fails, append to local buffer file for later replay."""
    try:
        col.insert_one(doc)
        return True
    except PyMongoError as e:
        # buffer locally
        payload = {"collection": col.name, "doc": doc}
        with open(BUFFER_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps(payload) + "\n")
        return False

def replay_buffer():
    """On each poll, try to replay locally buffered docs into Mongo."""
    if not os.path.exists(BUFFER_FILE):
        return
    tmp = BUFFER_FILE + ".tmp"
    os.replace(BUFFER_FILE, tmp)
    ok_lines = []
    with open(tmp, "r", encoding="utf-8") as f:
        for line in f:
            try:
                item = json.loads(line)
                col = {"jackery_power": col_power, "command_log": col_cmd, "alerts": col_alerts}.get(item["collection"])
                if col:
                    col.insert_one(item["doc"])
                else:
                    ok_lines.append(line)  # unknown collection; keep
            except Exception:
                ok_lines.append(line)  # keep failed lines
    if ok_lines:
        with open(BUFFER_FILE, "a", encoding="utf-8") as f:
            f.writelines(ok_lines)
    os.remove(tmp)

def http_get(url, timeout=5, retries=3, backoff=1.5):
    err = None
    for i in range(retries):
        try:
            r = requests.get(url, timeout=timeout)
            r.raise_for_status()
            return r
        except Exception as e:
            err = e
            time.sleep(backoff ** i)
    raise err

# --------- Poller ---------
def poller():
    global last_poll_ts, consec_fail
    while True:
        try:
            replay_buffer()
            r = http_get(f"{PHONE_BASE}/LastJackeryData", timeout=6, retries=4, backoff=1.7)
            ts, temp_c, in_w, out_w, raw = parse_last_row(r.text)
            doc = {"source": "phone-server", "ts": ts, "temp_c": temp_c, "input_w": in_w, "output_w": out_w, "raw": raw, "ingested_at": now_utc()}
            ok = safe_mongo_insert(col_power, doc)

            with lock:
                last_poll_ts = now_utc()
                consec_fail = 0

            if not ok:
                safe_mongo_insert(col_alerts, {"ts": now_utc(), "level": "warning", "where": "poller", "message": "mongo down; buffered one power doc"})

        except Exception as e:
            with lock:
                consec_fail += 1
            # log alert only on thresholds (to avoid spam)
            if consec_fail in (3, 10, 30):
                safe_mongo_insert(col_alerts, {
                    "ts": now_utc(),
                    "level": "warning",
                    "where": "poller",
                    "message": f"failed to fetch LastJackeryData x{consec_fail}",
                })

        time.sleep(POLL_EVERY_S)

threading.Thread(target=poller, daemon=True).start()

# --------- API: control ---------
def call_phone(endpoint: str):
    url = f"{PHONE_BASE}/{endpoint}"
    try:
        r = http_get(url, timeout=6, retries=3, backoff=1.7)
        body = r.text[:2000]
        safe_mongo_insert(col_cmd, {
            "ts": now_utc(), "command": endpoint, "target": "phone-server",
            "status": "success", "http_status": r.status_code, "response_body": body
        })
        return {"ok": True, "status": r.status_code, "body": body}
    except Exception as e:
        safe_mongo_insert(col_cmd, {
            "ts": now_utc(), "command": endpoint, "target": "phone-server",
            "status": "failed", "http_status": None, "error": repr(e)
        })
        raise HTTPException(status_code=502, detail=f"phone call failed: {e}")

@app.post("/api/power/toggle-dc")
def toggle_dc():
    return call_phone("ToggleDC")

@app.post("/api/power/toggle-ac")
def toggle_ac():
    return call_phone("ToggleAC")

# --------- API: health ---------
@app.get("/healthz")
def healthz():
    try:
        client.admin.command("ping")
        mongo_ok = True
    except Exception as e:
        mongo_ok = False
    with lock:
        lp = last_poll_ts
        fails = consec_fail
    age = (now_utc() - lp).total_seconds() if lp else None
    return {"mongo_ok": mongo_ok, "last_poll_ts": lp.isoformat().replace("+00:00","Z") if lp else None, "last_poll_age_s": age, "poll_failures": fails}
