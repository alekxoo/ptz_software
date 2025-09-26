# System Design

This document outlines the major components in the Mach Dashboard system and how they interact. It includes a high-level component diagram and a request flow sequence diagram.

## Components Overview


```mermaid
flowchart TB
  %% Cloud side
  subgraph Cloud
    UI[Dashboard UI]
    BE[Backend API]
    DB[MongoDB]
    TS[Tailscale API]
    Alerts[Alerts]
  end

  %% Edge side
  subgraph Edge
    Agent[Collector Agent]
    Cam[IP Webcam 8080]
    Phone[Phone Server 1821]
  end

  User[User Browser]

  User --> UI
  UI --> BE
  BE --> DB
  BE --> TS
  Agent --> BE
  Agent --> Cam
  Agent --> Phone
  BE --> Alerts
  UI --> Alerts
```

Key notes

- Backend endpoint sources (FastAPI):
  - `GET /api/devices` discovers via Tailscale Admin API when configured; otherwise falls back to Mongo. See `src/omnivision/mach-dashboard-backend/app.py:221`.
  - `GET /api/alerts`, `POST /api/alerts` to read/write alerts. See `src/omnivision/mach-dashboard-backend/app.py:379` and `src/omnivision/mach-dashboard-backend/app.py:407`.
  - `POST /api/status` ingests time-series status from the agent. See `src/omnivision/mach-dashboard-backend/app.py:421`.
  - `GET /api/devices/{device_id}/logs` (recent) and `/logs/all` (full) power history charts. See `src/omnivision/mach-dashboard-backend/app.py:493` and `src/omnivision/mach-dashboard-backend/app.py:548`.
  - `GET /api/metrics` serves aggregated buckets for charts. See `src/omnivision/mach-dashboard-backend/app.py` (metrics section below logs).

- Agent behavior (Python):
  - Discovers targets from backend `GET /api/devices` or `DEVICES_JSON`. See `src/omnivision/mach-dashboard-agent/collector.py:20` and discovery at `fetch_discovered`.
  - Polls device endpoints over Tailscale 100.x IPs (`:8080 /sensors.json`, `:1821 /sensor.json`). See `src/omnivision/mach-dashboard-agent/collector.py`.
  - Posts status to `POST /api/status` and alerts to `POST /api/alerts` using simple threshold rules.

## Request Flow

```mermaid
sequenceDiagram
  participant U as User
  participant UI as UI React
  participant BE as Backend API
  participant TS as Tailscale API
  participant AG as Agent
  participant DEV as Device
  participant DB as MongoDB
  participant Q as Offline Queue

  U->>UI: Load dashboard
  UI->>BE: GET devices
  BE->>TS: list devices
  TS-->>BE: devices
  BE-->>UI: devices

  AG->>BE: get devices
  BE-->>AG: devices
  loop every N seconds
    AG->>DEV: poll sensors
    DEV-->>AG: readings
    AG->>BE: post status
    opt threshold breached
      AG->>BE: post alert
    end
    BE->>DB: write status
    alt db error
      BE->>Q: enqueue write
    end
  end

  UI->>BE: get alerts
  BE->>DB: read alerts
  DB-->>BE: alerts
  BE-->>UI: alerts

  UI->>BE: tracking start or stop
  BE-->>UI: tracking state
```

Implementation pointers

- UI data access: `src/omnivision/mach-dashboard-ui/src/lib/api.ts` and components under `src/omnivision/mach-dashboard-ui/src/components/` (e.g., `DeviceCard.tsx`, `Chart.tsx`, `AddDevice.tsx`).
- Agent loop and thresholds: `src/omnivision/mach-dashboard-agent/collector.py`.
- Backend API and Mongo persistence: `src/omnivision/mach-dashboard-backend/app.py`.

This file uses Mermaid diagrams which many IDEs and code hosts can render directly.



