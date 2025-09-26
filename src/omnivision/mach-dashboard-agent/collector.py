import asyncio
import json
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

import httpx


BACKEND_BASE = "https://mach-dashboard-backend-290982618858.us-central1.run.app"
if not BACKEND_BASE:
    raise SystemExit("BACKEND_BASE env var is required")

WEBCAM_PORT = int(os.environ.get("WEBCAM_PORT", "8080"))
PHONE_SVR_PORT = int(os.environ.get("PHONE_SVR_PORT", "1821"))
POLL_INTERVAL = float(os.environ.get("POLL_INTERVAL", "5"))
CONCURRENCY = int(os.environ.get("CONCURRENCY", "8"))
# Alert thresholds (configurable)
CRIT_BATT_PCT = int(os.environ.get("CRIT_BATT_PCT", "10"))
WARN_BATT_PCT = int(os.environ.get("WARN_BATT_PCT", "20"))
# Temperature thresholds (Pixel devices should stay under 43°C)
CRIT_BATT_TEMP_C = float(os.environ.get("CRIT_BATT_TEMP_C", "43"))
WARN_BATT_TEMP_C = float(os.environ.get("WARN_BATT_TEMP_C", "41"))
DEVICES_SOURCE = os.environ.get("DEVICES_SOURCE", "backend").lower()
DEVICES_JSON_ENV = os.environ.get("DEVICES_JSON", "[]")


@dataclass
class Target:
    device_id: str
    ip: str
    port: int


def _now() -> datetime:
    return datetime.now(timezone.utc)


async def fetch_discovered(client: httpx.AsyncClient) -> List[Target]:
    url = f"{BACKEND_BASE}/api/devices"
    try:
        r = await client.get(url, timeout=10)
        r.raise_for_status()
        rows = r.json()
        targets: List[Target] = []
        for row in rows:
            if not row.get("connected"):
                continue
            ip = row.get("tailscaleIp")
            if not ip:
                continue
            devid = row.get("device_id") or row.get("name") or ip
            targets.append(Target(device_id=str(devid), ip=str(ip), port=WEBCAM_PORT))
        return targets
    except Exception as e:
        print(f"[discovery] failed: {e}")
        return []


async def fetch_tracked(client: httpx.AsyncClient) -> List[str]:
    url = f"{BACKEND_BASE}/api/tracking"
    try:
        r = await client.get(url, timeout=10)
        r.raise_for_status()
        data = r.json() or {}
        tracked = data.get("tracked")
        if isinstance(tracked, list):
            return [str(x).lower() for x in tracked]
        # Backward-compat: maybe a plain list
        if isinstance(data, list):
            return [str(x).lower() for x in data]
    except Exception as e:
        print(f"[tracking] fetch failed: {e}")
    return []


def load_targets_from_env() -> List[Target]:
    try:
        arr = json.loads(DEVICES_JSON_ENV)
        out: List[Target] = []
        for it in arr:
            devid = it.get("device_id") or it.get("name") or it.get("ip")
            ip = it.get("ip")
            port = int(it.get("port") or WEBCAM_PORT)
            if devid and ip:
                out.append(Target(device_id=str(devid), ip=str(ip), port=port))
        return out
    except Exception as e:
        print(f"[env] DEVICES_JSON parse failed: {e}")
        return []


def _to_bool(v: Any) -> Optional[bool]:
    if v is None:
        return None
    if isinstance(v, bool):
        return v
    s = str(v).strip().lower()
    if s in {"true", "yes", "1", "charging"}:
        return True
    if s in {"false", "no", "0", "disconnected", "not_charging"}:
        return False
    return None


def _to_int(v: Any) -> Optional[int]:
    try:
        if v is None:
            return None
        return int(float(str(v).strip().replace("%", "")))
    except Exception:
        return None


def _to_float(v: Any) -> Optional[float]:
    try:
        if v is None:
            return None
        s = str(v).strip().replace("â„ƒ", "").replace("Â°C", "")
        return float(s)
    except Exception:
        return None


async def poll_one(client: httpx.AsyncClient, target: Target) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    # Try a few common endpoints/ports for different device apps
    ports = [target.port]
    if WEBCAM_PORT not in ports:
        ports.append(WEBCAM_PORT)
    if PHONE_SVR_PORT not in ports:
        ports.append(PHONE_SVR_PORT)
    paths = [
        "/sensors.json?sense=battery_charging,battery_level,battery_temp",
        "/sensors.json",
        "/sensor.json",
    ]
    last_err: Optional[Exception] = None
    last_err_msg: Optional[str] = None
    for port in ports:
        for path in paths:
            url = f"http://{target.ip}:{port}{path}"
            try:
                r = await client.get(url, timeout=5)
                r.raise_for_status()
                data = r.json()
                last_err_msg = None
                # success
                break
            except Exception as e:
                last_err = e
                last_err_msg = str(e)
                data = None
                continue
        if data is not None:
            break
    if data is None:
        err_text = last_err_msg or (str(last_err) if last_err else None)
        print(f"[poll] {target.device_id}@{target.ip} failed: {err_text}")
        return None, err_text

    # Support two shapes:
    # 1) Flat: {"battery_level": 99, "battery_temp": 43.7, "battery_charging": true}
    # 2) Series: { key: { unit: "...", data: [[ts, [val]], ...] } }

    def last_from_series(obj: dict) -> Optional[float]:
      try:
        arr = obj.get("data") or []
        if not arr:
          return None
        # pick the last sample
        last = arr[-1]
        # shape: [ts, [val]]
        if isinstance(last, (list, tuple)) and len(last) >= 2:
          vals = last[1]
          if isinstance(vals, (list, tuple)) and len(vals) >= 1:
            return float(vals[0])
        return None
      except Exception:
        return None

    # Try flat values
    level = _to_int(data.get("battery_level") or data.get("battery") or data.get("batteryPercent"))
    temp = _to_float(data.get("battery_temp") or data.get("batteryTemperature") or data.get("battery_temp_c"))
    charging = _to_bool(data.get("battery_charging") or data.get("charging"))

    # If missing, try series shape
    if level is None and isinstance(data.get("battery_level"), dict):
      lv = last_from_series(data.get("battery_level", {}))
      level = _to_int(lv)
    if temp is None and isinstance(data.get("battery_temp"), dict):
      tv = last_from_series(data.get("battery_temp", {}))
      temp = _to_float(tv)
    if charging is None and isinstance(data.get("battery_charging"), dict):
      cv = last_from_series(data.get("battery_charging", {}))
      # some sources use 0/1/10; treat >0 as True
      charging = _to_bool(bool(cv and float(cv) > 0))

    payload: Dict[str, Any] = {
        "device_id": target.device_id,
        "timestamp": _now().isoformat(),
        "battery_percentage": level,
        "battery_temperature": temp,
        "is_charging": charging,
        "network_type": "tailscale",
        "raw": data,
    }
    return payload, None

async def post_status(client: httpx.AsyncClient, payload: Dict[str, Any]) -> None:
    url = f"{BACKEND_BASE}/api/status"
    try:
        r = await client.post(url, json=payload, timeout=10)
        r.raise_for_status()
    except Exception as e:
        print(f"[status] post failed for {payload.get('device_id')}: {e}")


async def post_alert(client: httpx.AsyncClient, device_id: str, level: str, message: str) -> None:
    url = f"{BACKEND_BASE}/api/alerts"
    body = {
        "device_id": device_id,
        "level": level,
        "message": message,
        "timestamp": _now().isoformat(),
    }
    try:
        r = await client.post(url, json=body, timeout=10)
        r.raise_for_status()
    except Exception as e:
        print(f"[alert] post failed for {device_id}: {e}")


async def run_once() -> None:
    async with httpx.AsyncClient() as client:
        if DEVICES_SOURCE == "env":
            targets = load_targets_from_env()
        else:
            targets = await fetch_discovered(client)

        if not targets:
            print("[run] no targets found")
            # Still allow command processing later (ip_map empty)
            targets = []

        # Keep a map of all discovered devices for command resolution
        all_targets = list(targets)

        # Filter by backend tracking set (device_ids must match names returned by /api/devices)
        tracked_ids = await fetch_tracked(client)
        if tracked_ids:
            ids_set = set(tracked_ids)
            targets = [t for t in targets if t.device_id.lower() in ids_set]
        else:
            # No tracked devices -> skip polling to honor backend control
            print("[run] no tracked devices; skipping polling")
            targets = []

        # Map device_id -> ip for command execution
        ip_map = {t.device_id: t.ip for t in all_targets}

        sem = asyncio.Semaphore(CONCURRENCY)

        # keep minimal state for edge alerts (e.g., charging state changes)
        last_state: Dict[str, Dict[str, Any]] = {}

        async def worker(t: Target):
            async with sem:
                payload, err = await poll_one(client, t)
                if payload is None:
                    message = "IP Webcam sensors fetch failed"
                    if err:
                        message = f"{message}: {err}"
                    await post_alert(client, t.device_id, "warning", message)
                    return

                await post_status(client, payload)
                # simple alert rules
                devid = payload["device_id"]
                level = payload.get("battery_percentage")
                temp = payload.get("battery_temperature")
                charging = payload.get("is_charging")

                if isinstance(level, (int, float)):
                    if level <= CRIT_BATT_PCT:
                        await post_alert(client, devid, "critical", f"Battery critically low ({level}%)")
                    elif level <= WARN_BATT_PCT:
                        await post_alert(client, devid, "warning", f"Battery low ({level}%)")

                if isinstance(temp, (int, float)):
                    if temp >= CRIT_BATT_TEMP_C:
                        await post_alert(client, devid, "critical", f"Battery temperature high ({temp}C)")
                    elif temp >= WARN_BATT_TEMP_C:
                        await post_alert(client, devid, "warning", f"Battery temperature elevated ({temp}C)")

                prev = last_state.get(devid)
                if prev is None:
                    last_state[devid] = {"is_charging": charging}
                else:
                    if prev.get("is_charging") != charging and charging is not None:
                        state = "charging" if charging else "not charging"
                        await post_alert(client, devid, "warning", f"Charging state changed: {state}")
                        last_state[devid] = {"is_charging": charging}


        if targets:
            await asyncio.gather(*(worker(t) for t in targets))

        # After polling sensors, process any pending commands (e.g., camera start/stop)
        try:
            r = await client.get(f"{BACKEND_BASE}/api/commands/pending", params={"limit": 50}, timeout=10)
            r.raise_for_status()
            cmds = r.json() or []
        except Exception as e:
            print("[commands] fetch failed:", e)
            cmds = []

        for cmd in cmds:
            try:
                cmd_id = str(cmd.get("id") or cmd.get("_id") or "")
                device_id = str(cmd.get("device_id") or "")
                action = str(cmd.get("action") or "")
                ctype = str(cmd.get("type") or "")
                if not cmd_id or not device_id or not action:
                    continue
                ip = ip_map.get(device_id)
                if not ip:
                    # Mark as failed so it doesn't block queue
                    try:
                        await client.post(f"{BACKEND_BASE}/api/commands/{cmd_id}/complete", json={"status": "failed", "message": "device not found or offline"}, timeout=10)
                    except Exception:
                        pass
                    continue
                # Handle command types
                if ctype == "camera":
                    # Resolve URL to phone server control
                    if action == "start":
                        path = "/Startcamera"
                    elif action == "stop":
                        path = "/Stopcamera"
                    else:
                        try:
                            await client.post(f"{BACKEND_BASE}/api/commands/{cmd_id}/complete", json={"status": "failed", "message": f"unknown action: {action}"}, timeout=10)
                        except Exception:
                            pass
                        continue
                    url = f"http://{ip}:{WEBCAM_PORT}{path}"
                    ok = False
                    msg = None
                    try:
                        resp = await client.get(url, timeout=10)
                        if resp.status_code >= 200 and resp.status_code < 300:
                            ok = True
                        else:
                            msg = f"HTTP {resp.status_code}"
                    except Exception as e:
                        msg = f"request failed: {e}"
                    # Report completion
                    try:
                        await client.post(
                            f"{BACKEND_BASE}/api/commands/{cmd_id}/complete",
                            json={"status": "success" if ok else "failed", "message": msg},
                            timeout=10,
                        )
                    except Exception:
                        pass
                elif ctype == "probe" and action == "webcam":
                    # Probe IP Webcam sensors endpoint for reachability
                    url = f"http://{ip}:{WEBCAM_PORT}/sensors.html"
                    ok = False
                    msg = None
                    try:
                        resp = await client.get(url, timeout=5)
                        if 200 <= resp.status_code < 300:
                            ok = True
                        else:
                            msg = f"HTTP {resp.status_code}"
                    except Exception as e:
                        msg = f"request failed: {e}"
                    try:
                        await client.post(
                            f"{BACKEND_BASE}/api/commands/{cmd_id}/complete",
                            json={"status": "success" if ok else "failed", "message": msg},
                            timeout=10,
                        )
                    except Exception:
                        pass
                else:
                    # Unknown command; mark failed
                    try:
                        await client.post(
                            f"{BACKEND_BASE}/api/commands/{cmd_id}/complete",
                            json={"status": "failed", "message": f"unknown type/action: {ctype}/{action}"},
                            timeout=10,
                        )
                    except Exception:
                        pass
            except Exception as e:
                print("[commands] process error:", e)


async def main() -> None:
    print("collector started; backend:", BACKEND_BASE)
    while True:
        try:
            await run_once()
        except Exception as e:
            print("[loop] unexpected error:", e)
        await asyncio.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    asyncio.run(main())


