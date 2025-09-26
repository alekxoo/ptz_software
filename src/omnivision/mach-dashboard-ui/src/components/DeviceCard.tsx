import React, { useEffect, useMemo, useState } from 'react';
import type { Alert } from '../lib/api';
import { fetchAlerts, startCamera, stopCamera, checkWebcam, startTracking as apiStartTracking, stopTracking as apiStopTracking } from '../lib/api';
import MetricChart from "./Chart";
import { computeLastSeenLabel } from '../lib/lastSeen';

export type DeviceCardProps = {
  d: {
    id?: string;
    device_id?: string;
    name?: string;
    status?: "online" | "offline";
    connected?: boolean;
    lastSeen?: string;
    battery_level_num?: number;
    battery_temp_num?: number;
    is_charging?: boolean;
    tracking?: boolean;
  };
  onRemove: (id: string) => void;
  alerts: Alert[];
  tracking: boolean;
  onTrackingDeviceId: React.Dispatch<React.SetStateAction<string[]>>;
};

export default function DeviceCard({ d, onRemove, alerts, tracking, onTrackingDeviceId }: DeviceCardProps) {
  const id = d.device_id || "";
  const displayName = (d as any).displayName || d.name || id || "?";
  const battery = d.battery_level_num;
  const temp = d.battery_temp_num;
  const charging = d.is_charging;
  const tailscaleIp = (d as any).tailscaleIp as string | undefined;
  const defaultWebcamPort = 8080; // IP Webcam Pro default
  const webcamPort = defaultWebcamPort;

  const handleStartCamera = async () => {
    if (disableStartCam) {
      alert('Cannot start: Tailscale is disconnected. Connect Tailscale and bring camera online.');
      return;
    }
    if (camSessionActive) return;
    try {
      await startCamera(id);
      alert('Start camera command queued');
      setCamSessionActive(true);
    } catch (e) {
      console.error('Start camera failed', e);
      alert('Failed to queue start camera');
    }
  };

  const handleStopCamera = async () => {
    try {
      await stopCamera(id);
      alert('Stop camera command queued');
      setCamSessionActive(false);
    } catch (e) {
      console.error('Stop camera failed', e);
      alert('Failed to queue stop camera');
    }
  };

  const handleRemove = async () => {
    if (tracking) {
      alert("This device is currently being monitored.\nPlease stop tracking before removing.");
      return;
    }
    if (!window.confirm("Are you sure you want to remove this device?")) return;
    onRemove(id);
  };

  const [liveStartAt, setLiveStartAt] = useState<number | null>(null);
  const [rangeFromStr, setRangeFromStr] = useState<string>("");
  const [rangeToStr, setRangeToStr] = useState<string>("");
  const rangeFrom = useMemo(() => (rangeFromStr ? new Date(rangeFromStr).getTime() : undefined), [rangeFromStr]);
  const rangeTo = useMemo(() => (rangeToStr ? new Date(rangeToStr).getTime() : undefined), [rangeToStr]);
  const [alertsLocal, setAlertsLocal] = useState<Alert[]>(alerts || []);
  const isFetchAlert = (a: Alert) => {
    const m = (a.message || '').toLowerCase();
    return m.includes('fetch failed') || m.includes('failed to fetch') || m.includes('lastjackerydata');
  };
  const criticalCount = useMemo(() => alertsLocal.filter(a => a.level === 'critical').length, [alertsLocal]);
  const fetchCount = useMemo(() => alertsLocal.filter(isFetchAlert).length, [alertsLocal]);
  const totalCount = alertsLocal.length;
  const [alertFilter, setAlertFilter] = useState<'all' | 'critical' | 'fetch'>('all');
  const filteredAlerts = useMemo(() => {
    if (alertFilter === 'critical') return alertsLocal.filter(a => a.level === 'critical');
    if (alertFilter === 'fetch') return alertsLocal.filter(isFetchAlert);
    return alertsLocal;
  }, [alertsLocal, alertFilter]);
  const [alertsCollapsed, setAlertsCollapsed] = useState<boolean>(false);

  // Load cached alerts from localStorage (avoid flicker on first render)
  useEffect(() => {
    if (!id) return;
    try {
      const raw = localStorage.getItem(`alerts:${id}`);
      if (raw) {
        setAlertsLocal(JSON.parse(raw) as Alert[]);
      }
    } catch {}
  }, [id]);

  // Do not mirror incoming alerts to avoid flicker; rely on cache + poll

  // Poll alerts while tracking
  useEffect(() => {
    if (!id) return;
    if (!tracking) return;
    let cancelled = false;
    const keyOf = (a: Alert) => `${a.timestamp}|${a.message}`;
    const load = async () => {
      try {
        const data = await fetchAlerts(id);
        if (cancelled) return;
        setAlertsLocal(prev => {
          const map = new Map<string, Alert>();
          [...prev, ...data].forEach(a => map.set(keyOf(a), a));
          const merged = Array.from(map.values())
            .sort((a, b) => new Date(b.timestamp).getTime() - new Date(a.timestamp).getTime());
          // Only update state if there is a real change to avoid re-render flicker
          const prevKeys = prev.map(keyOf);
          const mergedKeys = merged.map(keyOf);
          const same = prevKeys.length === mergedKeys.length && prevKeys.every((k, i) => k === mergedKeys[i]);
          if (!same) {
            try { localStorage.setItem(`alerts:${id}`, JSON.stringify(merged)); } catch {}
            return merged;
          }
          return prev;
        });
      } catch (e) {
        if (!cancelled) console.debug('alerts poll failed', e);
      }
    };
    load();
    const t = window.setInterval(load, 3000);
    return () => { cancelled = true; window.clearInterval(t); };
  }, [id, tracking]);

  // Persisted collapse state (per device)
  useEffect(() => {
    if (!id) return;
    try {
      const v = localStorage.getItem(`alertsCollapsed:${id}`);
      setAlertsCollapsed(v === '1');
    } catch {}
  }, [id]);

  const toggleAlertsCollapsed = () => {
    setAlertsCollapsed(prev => {
      const next = !prev;
      try { localStorage.setItem(`alertsCollapsed:${id}`, next ? '1' : '0'); } catch {}
      return next;
    });
  };

  const toggleTracking = async () => {
    if (!tracking && disableStartTracking) {
      alert('Cannot start: both Tailscale and camera are disconnected. Connect Tailscale or bring camera online.');
      return;
    }
    const next = !tracking;
    try {
      const payload = next ? await apiStartTracking(id) : await apiStopTracking(id);
      const stored = JSON.parse(localStorage.getItem("trackedDeviceIds") || "[]");
      const updated = next ? [...new Set([...stored, id])] : stored.filter((x: string) => x !== id);
      localStorage.setItem("trackedDeviceIds", JSON.stringify(updated));
      onTrackingDeviceId(updated);
      if (next) {
        const startedAtMs = payload?.started_at ? new Date(payload.started_at).getTime() : Date.now();
        setLiveStartAt(startedAtMs);
      } else {
        setLiveStartAt(null);
      }
    } catch (e) {
      console.error("Failed to toggle tracking", e);
      alert("Failed to toggle tracking");
    }
  };

  // Camera (IP Webcam) reachability check via backend/agent
  const [webcamReachable, setWebcamReachable] = useState<boolean | null>(null);
  const [webcamLastChecked, setWebcamLastChecked] = useState<number | null>(null);
  const [camSessionActive, setCamSessionActive] = useState<boolean>(false);
  useEffect(() => {
    let cancelled = false;
    const isConnected = !!d.connected;
    if (!tailscaleIp || !isConnected) {
      setWebcamReachable(null);
      setWebcamLastChecked(null);
      return;
    }
    const check = async () => {
      try {
        const resp = await checkWebcam(id);
        if (!cancelled) {
          setWebcamReachable(resp?.reachable === true);
          setWebcamLastChecked(Date.now());
        }
      } catch (e) {
        if (!cancelled) {
          setWebcamReachable(false);
          setWebcamLastChecked(Date.now());
        }
      }
    };
    // Initial and poll every 10s (only when TS shows connected)
    check();
    const interval = window.setInterval(check, 10000);
    return () => { cancelled = true; window.clearInterval(interval); };
  }, [tailscaleIp, webcamPort, d.connected]);

  // Start Cam enablement logic
  const isTailscaleConnected = !!d.connected && !!tailscaleIp;
  const isCameraAccessible = webcamReachable === true;
  // Disable Start Cam only when BOTH TS is disconnected and camera is not accessible
  const disableStartCam = !isCameraAccessible && !isTailscaleConnected;
  const startCamTitle = disableStartCam
    ? 'Start requires Tailscale connection or camera online'
    : (isCameraAccessible ? 'Camera online — you can restart if needed' : 'Tailscale connected — try starting camera');

  // Disable Start (tracking) when both Tailscale and Camera are disconnected
  const disableStartTracking = !tracking && !isTailscaleConnected && !isCameraAccessible;
  const startTrackingTitle = disableStartTracking
    ? 'Start requires Tailscale connection or camera online'
    : (tracking ? 'Stop tracking' : (isCameraAccessible ? 'Camera online — start tracking' : 'Tailscale connected — start tracking'));

  const statusPillTS = (() => {
    const { label } = computeLastSeenLabel((d as any).lastSeen, d.connected);
    const isConnected = !!d.connected;
    const display = isConnected ? 'Connected' : label;
    return (
      <div className="flex items-center gap-2 text-xs">
        <span className={isConnected ? 'text-green-500 font-semibold' : 'text-red-500'} title={`Tailscale: ${display}`}>{display}</span>
        <span className="text-gray-500">•</span>
        <span
          title={tailscaleIp ? `IP Webcam @ ${tailscaleIp}:${webcamPort}${webcamLastChecked ? ` (checked ${new Date(webcamLastChecked).toLocaleTimeString()})` : ''}` : 'No Tailscale IP'}
          className={webcamReachable ? 'text-green-400 font-semibold' : (webcamReachable === false ? 'text-red-500' : 'text-gray-400')}
        >
          {tailscaleIp ? (webcamReachable ? 'Camera Online' : (webcamReachable === false ? 'Camera Offline' : 'No Camera Access')) : 'No IP'}
        </span>
      </div>
    );
  })();

  const chartsBlock = useMemo(() => (
    <div className="grid grid-cols-1 md:grid-cols-2 gap-2 relative">
      <div className="col-span-1 md:col-span-2 flex flex-wrap md:flex-nowrap items-center gap-x-2 gap-y-1 text-xxs text-gray-300 relative z-20 p-2">
        <label className="flex items-center gap-1 w-1/2 md:w-auto">
          <span className="whitespace-nowrap">From</span>
          <input type="datetime-local" value={rangeFromStr} onChange={(e) => setRangeFromStr(e.target.value)} className="bg-slate-700 text-white text-xxs rounded px-2 py-1 flex-1 min-w-0 md:w-48 md:flex-none" />
        </label>
        <label className="flex items-center gap-1 w-1/2 md:w-auto">
          <span className="whitespace-nowrap">To</span>
          <input type="datetime-local" value={rangeToStr} onChange={(e) => setRangeToStr(e.target.value)} className="bg-slate-700 text-white text-xxs rounded px-2 py-1 flex-1 min-w-0 md:w-48 md:flex-none" />
        </label>
        <button className="px-2 py-1 rounded bg-slate-700 hover:bg-slate-600 w-full md:w-auto" onClick={() => { setRangeFromStr(""); setRangeToStr(""); }}>Clear</button>
      </div>

      {/* History charts */}
      <MetricChart deviceId={id} title="Battery % (All Logs)" unit="%" mode="history" metric="battery" from={rangeFrom} to={rangeTo} />
      <MetricChart deviceId={id} title="Battery Temp (All Logs)" unit="°C" mode="history" metric="temperature" from={rangeFrom} to={rangeTo} />

      {/* Live charts (only when tracking) */}
      {tracking && (
        <>
          <MetricChart key={`live-batt-${liveStartAt ?? 'na'}`} deviceId={id} title="Battery % (Live)" unit="%" mode="live" metric="battery" startAt={liveStartAt ?? undefined} pollMs={3000} />
          <MetricChart key={`live-temp-${liveStartAt ?? 'na'}`} deviceId={id} title="Battery Temp (Live)" unit="°C" mode="live" metric="temperature" startAt={liveStartAt ?? undefined} pollMs={3000} />
        </>
      )}
    </div>
  ), [id, tracking, liveStartAt, rangeFrom, rangeTo, rangeFromStr, rangeToStr]);
  const startCamTitleFinal = camSessionActive
    ? 'Camera running — click Stop to re-enable Start'
    : startCamTitle;

  return (
    <div className="rounded-xl p-3 border" style={{ borderColor: "var(--panel-border)", background: "var(--panel-bg)" }}>
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <div className="font-medium">{displayName}</div>
          {statusPillTS}
          {/* Type counters */}
          <div className="flex items-center gap-1">
            <button
              className={`px-2 py-0.5 rounded text-xs border ${alertFilter === 'all' ? 'bg-slate-600 text-white' : 'bg-slate-700 hover:bg-slate-600'} `}
              style={{ borderColor: 'var(--panel-border)' }}
              onClick={() => setAlertFilter('all')}
              aria-pressed={alertFilter === 'all'}
              title="Show all alerts"
            >
              All {totalCount}
            </button>
            <button
              className={`px-2 py-0.5 rounded text-xs border ${alertFilter === 'critical' ? 'bg-red-600 text-white' : 'bg-slate-700 hover:bg-slate-600'}`}
              style={{ borderColor: 'var(--panel-border)' }}
              onClick={() => setAlertFilter('critical')}
              aria-pressed={alertFilter === 'critical'}
              title="Show critical only"
            >
              Critical {criticalCount}
            </button>
            <button
              className={`px-2 py-0.5 rounded text-xs border ${alertFilter === 'fetch' ? 'bg-yellow-400 text-black' : 'bg-slate-700 hover:bg-slate-600'}`}
              style={{ borderColor: 'var(--panel-border)' }}
              onClick={() => setAlertFilter('fetch')}
              aria-pressed={alertFilter === 'fetch'}
              title="Show fetch alerts only"
            >
              Fetch {fetchCount}
            </button>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <button
            className="px-3 py-1.5 rounded bg-slate-700 hover:bg-slate-600 text-xs"
            onClick={toggleAlertsCollapsed}
            aria-pressed={alertsCollapsed}
            title={alertsCollapsed ? 'Show' : 'Hide'}
          >
            {alertsCollapsed ? 'Show' : 'Hide'}
          </button>
          <span title={tracking ? "Stop tracking before removing" : ""}>
            <button
              onClick={handleRemove}
              aria-label="Remove device"
              title="Remove"
              className="w-8 h-8 rounded-full bg-red-600 hover:bg-red-500 text-white flex items-center justify-center border border-red-700 focus:outline-none focus:ring-2 focus:ring-red-400 focus:ring-offset-1"
            >
              <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} className="w-4 h-4">
                <path strokeLinecap="round" strokeLinejoin="round" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6M9 7h6m2 0H7m3-3h4a1 1 0 011 1v2H8V5a1 1 0 011-1z" />
              </svg>
            </button>
          </span>
        </div>
      </div>

      <div className="mt-2 grid grid-cols-3 gap-2 text-xs text-gray-300">
        <div>Battery: {tracking && battery != null ? `${battery}%` : "--"}</div>
        <div>Temp: {tracking && temp != null ? `${temp}°C` : "--"}</div>
        <div>Charging: {tracking && charging != null ? (charging ? "Yes" : "No") : "--"}</div>
        <button
          onClick={toggleTracking}
          title={startTrackingTitle}
          className={`px-3 py-1.5 rounded bg-slate-700 hover:bg-slate-600 text-xs`}
        >
          {tracking ? "Stop" : "Start"}
        </button>
        <button
          onClick={handleStartCamera}
          disabled={camSessionActive}
          title={startCamTitleFinal}
          className={`px-2 py-1 rounded text-xs ${camSessionActive ? 'bg-slate-800 opacity-50 cursor-not-allowed' : 'bg-slate-700 hover:bg-slate-600'}`}
        >
          Start Cam
        </button>
        <button
          onClick={handleStopCamera}
          disabled={!camSessionActive}
          title={camSessionActive ? 'Stop camera' : 'Start camera first'}
          className={`px-2 py-1 rounded text-xs ${!camSessionActive ? 'bg-slate-800 opacity-50 cursor-not-allowed' : 'bg-slate-700 hover:bg-slate-600'}`}
        >
          Stop Cam
        </button>
      </div>

      <div className="h-full overflow-y-auto overflow-x-hidden space-y-3 custom-scroll">
        {!alertsCollapsed && (
          <div className="space-y-2 max-h-48 overflow-y-auto pr-1">
            {filteredAlerts.map((a) => (
              <div key={`${a.timestamp}|${a.message}`} className="text-sm p-2 rounded border" style={{ borderColor: 'var(--panel-border)', background: 'var(--panel-bg)' }}>
                <div className="flex items-center justify-between">
                  <span className={a.level === 'critical' ? 'text-red-500' : 'text-yellow-300'}>{a.level.toUpperCase()}</span>
                  <span className="text-xxs text-gray-400">{new Date(a.timestamp).toLocaleString()}</span>
                </div>
                <div className="mt-1 text-xxs">{a.message}</div>
              </div>
            ))}
            {filteredAlerts.length === 0 && (<div className="text-xxs text-gray-500">No alerts</div>)}
          </div>
        )}
        {chartsBlock}
      </div>
    </div>
  );
}
