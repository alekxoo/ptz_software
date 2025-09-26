Mach Dashboard Collector (Tailscale)

Purpose
- Polls device sensors.json endpoints over Tailscale and posts normalized samples to the backend `/api/status`.

Quick Start (GCE VM on your tailnet)
- Install Python and httpx:
  - sudo apt update && sudo apt install -y python3 python3-venv
  - python3 -m venv ~/.venvs/mach-agent && source ~/.venvs/mach-agent/bin/activate
  - pip install httpx
- Set env and run:
  - export BACKEND_BASE="https://<your-backend>"
  - export WEBCAM_PORT=8080
  - export POLL_INTERVAL=5
  - python src/omnivision/mach-dashboard-agent/collector.py

Use discovered devices (default)
- The agent calls `${BACKEND_BASE}/api/devices/discovered` and filters `connected==true`.
- Ensure your backend discovery job fills `tailscaleIp` and `connected`.

Static devices (fallback)
- export DEVICES_SOURCE=env
- export DEVICES_JSON='[{"device_id":"phone-1","ip":"100.70.1.2","port":8080}]'

Systemd unit (example)
- Copy `mach-agent.service` to `/etc/systemd/system/` and edit the `User`, `WorkingDirectory`, and `Environment` lines.
- sudo systemctl daemon-reload
- sudo systemctl enable --now mach-agent

Notes
- The VM must be joined to the same Tailscale tailnet as devices.
- The agent posts fields expected by backend `PhoneStatusIn` (battery_percentage, battery_temperature, is_charging, network_type, raw).

