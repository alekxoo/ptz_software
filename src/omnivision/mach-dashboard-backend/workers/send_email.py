import os, time, datetime, argparse, requests
from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail

from dotenv import load_dotenv

load_dotenv()

def getenv_f(key, default): 
    v = os.getenv(key); 
    return float(v) if v and v.strip() else default
def getenv_i(key, default): 
    v = os.getenv(key); 
    return int(v) if v and v.strip() else default

CHECK_URL = os.getenv("CHECK_URL", "").strip()
DEVICE_ID = os.getenv("DEVICE_ID", "cam01")

SENDGRID_API_KEY = os.getenv("SENDGRID_API_KEY", "").strip()
ALERT_FROM = os.getenv("ALERT_FROM", "").strip()
ALERT_TO = os.getenv("ALERT_TO", "").strip()

TIMEOUT_S = getenv_f("TIMEOUT_S", 5.0)
WARN_ELAPSED_S = getenv_f("WARN_ELAPSED_S", 1.5)
WARN_MANUAL_S  = getenv_f("WARN_MANUAL_S", 2.0)
MAX_CONSEC_FAIL = getenv_i("MAX_CONSEC_FAIL", 3)
ALERT_COOLDOWN_S = getenv_i("ALERT_COOLDOWN_S", 300)

def send_email(subject: str, body: str):
    if not (SENDGRID_API_KEY and ALERT_FROM and ALERT_TO):
        print("[email] Missing SENDGRID_API_KEY/ALERT_FROM/ALERT_TO; skipping email.")
        return
    msg = Mail(from_email=ALERT_FROM, to_emails=ALERT_TO,subject=subject, plain_text_content=body)
    sg = SendGridAPIClient(SENDGRID_API_KEY)
    resp = sg.send(msg)
    print(f"[email] status={resp.status_code}")

def check_once():
    """Return dict: {ok, elapsed_s, manual_s, error}"""
    t0 = time.time()
    try:
        r = requests.get(CHECK_URL, timeout=TIMEOUT_S)
        manual_s = time.time() - t0
        r.raise_for_status()
        elapsed_s = r.elapsed.total_seconds()
        return {"ok": True, "elapsed_s": elapsed_s, "manual_s": manual_s, "error": None}
    except Exception as e:
        return {"ok": False, "elapsed_s": None, "manual_s": None, "error": repr(e)}

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--loop", type=int, default=0, help="Loop interval seconds (0 = run once).")
    args = parser.parse_args()

    if not CHECK_URL:
        raise SystemExit("Set CHECK_URL env var (e.g., http://100.x.x.x:8080/sensors.json)")

    consec_fail = 0
    last_alert_ts = 0

    def maybe_alert(level, message, detail=""):
        nonlocal last_alert_ts
        now = time.time()
        if now - last_alert_ts >= ALERT_COOLDOWN_S:
            ts = datetime.datetime.utcnow().isoformat()
            subject = f"[{level}] {DEVICE_ID} network check"
            body = f"{ts}\n{DEVICE_ID}\n{message}\n{detail}"
            print("[alert]", message, detail)
            send_email(subject, body)
            last_alert_ts = now
        else:
            print("[alert] (cooldown) ", message)

    def run_once():
        nonlocal consec_fail
        res = check_once()
        ts = datetime.datetime.utcnow().isoformat()

        if res["ok"]:
            consec_fail = 0
            el_ms = round(res["elapsed_s"]*1000, 2)
            man_ms = round(res["manual_s"]*1000, 2)
            print(f"{ts} {DEVICE_ID} OK  elapsed={el_ms}ms  manual={man_ms}ms")

            warn_msgs = []
            if res["elapsed_s"] > WARN_ELAPSED_S:
                warn_msgs.append(f"High first-byte latency: {el_ms} ms (> {int(WARN_ELAPSED_S*1000)} ms)")
            if res["manual_s"] > WARN_MANUAL_S:
                warn_msgs.append(f"High round-trip latency: {man_ms} ms (> {int(WARN_MANUAL_S*1000)} ms)")
            if warn_msgs:
                maybe_alert("WARNING", " / ".join(warn_msgs),
                            f"URL: {CHECK_URL}\nTimeout: {TIMEOUT_S}s")
        else:
            consec_fail += 1
            print(f"{ts} {DEVICE_ID} FAIL  err={res['error']}  consec_fail={consec_fail}")
            if consec_fail >= MAX_CONSEC_FAIL:
                maybe_alert("CRITICAL",
                            f"{consec_fail} consecutive failures to reach device",
                            f"URL: {CHECK_URL}\nTimeout: {TIMEOUT_S}s\nLast error: {res['error']}")

    if args.loop > 0:
        while True:
            run_once()
            time.sleep(args.loop)
    else:
        run_once()

if __name__ == "__main__":
    main()