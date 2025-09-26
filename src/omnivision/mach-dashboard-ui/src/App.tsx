import { useEffect, useMemo, useState } from 'react'
import { fetchDevices, fetchDiscovered as fetchDiscoveredApi, type Device, getOfflineStatus, testOfflineWrite } from './lib/api'
import { useAppStore } from './store/useAppStore'
import DeviceCard from './components/DeviceCard'
import AddDevice from './components/AddDevice'
// import Tabs from './components/Tab'
import './App.css'

// const API_BASE = 'https://mach-dashboard-backend-290982618858.us-central1.run.app';
// const API_BASE = ['http://localhost:8000']; // for local dev with proxy
const STORAGE_KEY = 'activeDeviceIds';
const keyOf = (d: any) =>
  String(d?.device_id || d?.id || d?.tailscaleIp || '').trim().toLowerCase();
const norm = (s: string) => String(s || '').trim().toLowerCase();

export default function App() {
  const { devices, alerts, setDevices } = useAppStore()
  const [selectedIds, setSelectedIds] = useState<string[]>([]) // controls what shows on the dashboard
  const [trackingDeviceId, setTrackingDeviceId] = useState<string[]>([]);
  const [offlinePending, setOfflinePending] = useState<number>(0);
  const [offlineMsg, setOfflineMsg] = useState<string>("");


  // Restore selection on load
  useEffect(() => {
    try {
      const raw = localStorage.getItem(STORAGE_KEY)
      if (raw) setSelectedIds(JSON.parse(raw))
      const t = localStorage.getItem('trackedDeviceIds')
      if (t) setTrackingDeviceId(JSON.parse(t))
    } catch {}
  }, [])

  // Persist selection
  useEffect(() => {
    try { localStorage.setItem(STORAGE_KEY, JSON.stringify(selectedIds)) } catch {}
  }, [selectedIds])

  // Persist tracked device IDs so Start/Stop survives reloads
  useEffect(() => {
    try { localStorage.setItem('trackedDeviceIds', JSON.stringify(trackingDeviceId)) } catch {}
  }, [trackingDeviceId])

  // Poll devices & alerts (devices = latest polled status from backend)
  useEffect(() => {
    let mounted = true
    const load = async () => {
      try {
        const [d, s] = await Promise.all([fetchDevices(), getOfflineStatus().catch(() => ({ pending_total: 0 }))])
        
        if (!mounted) return
        setDevices(d)
        setOfflinePending((s as any).pending_total ?? 0)
      } catch (e) {
        console.warn('poll error', e)
      }
    }
    load()
    const id = setInterval(load, 3000)
    return () => { mounted = false; clearInterval(id) }
  }, [setDevices])

  // What to display: only selected device IDs
  const activeDevices = useMemo(() => {
  const want = new Set(selectedIds.map(norm));
  return devices
    .filter(d => want.has(keyOf(d)))
    .map(d => ({ ...d, tracking: d.tracking ?? false })); //
}, [devices, selectedIds]);


  // Add picks from the modal (expects an array of Device objects)
  const handlePicked = (picks: Device[]) => {
  const addKeys = picks
    .map(keyOf)
    .filter(Boolean)
    .filter(k => !selectedIds.includes(k));
  if (addKeys.length) setSelectedIds(prev => [...prev, ...addKeys]);
};


  // Remove handler passed to each card
  const handleRemove = (id: string) => {
  const k = norm(id);
  setSelectedIds(prev => prev.filter(x => x !== k));
};


// Discovery fetcher for the modal (use centralized API client)
const fetchDiscovered = async () => {
  return await fetchDiscoveredApi()
}


  return (
    <div className="h-screen grid grid-cols-16 grid-rows-12 p-3">
      {/* Devices + Add */}
      <div className="col-span-8 row-span-12 space-y-3">
        <div className="flex items-center justify-between">
          <AddDevice
            // 'existing' is optional; pass currently selected so modal can avoid duplicates if it wants
            existing={activeDevices}
            onPicked={handlePicked}
            fetchDiscovered={fetchDiscovered}
          />
          <div className="flex items-center gap-2">
            <button
              className="text-xs px-2 py-1 bg-blue-600 text-white rounded"
              onClick={async () => {
                setOfflineMsg('')
                try {
                  const res = await testOfflineWrite('clicked from UI')
                  setOfflinePending(res.status?.pending_total ?? offlinePending)
                  setOfflineMsg(res.ok ? 'Saved locally ✓' : 'Save failed')
                } catch (e) {
                  setOfflineMsg('Save failed')
                }
              }}
            >
              Test Local Save
            </button>
            <div className="text-xxs text-gray-600">
              Offline queue: {offlinePending}
              {offlineMsg && <span className="ml-2 text-gray-700">{offlineMsg}</span>}
            </div>
          </div>
        </div>

        <div className="grid md:grid-cols-2 gap-2">
          {activeDevices.map(d => (
              <DeviceCard
                key={keyOf(d)}
                d={{
                  ...d,
                battery_level_num: d.battery_level_num ?? (d as any)["battery level"],
                battery_temp_num: d.battery_temp_num ?? (d as any)["battery temperature"],
                is_charging: d.is_charging ?? (d as any)["battery charging"]
              }}
              onRemove={(id) => handleRemove(id)}
              alerts={alerts.filter(a => a.device_id === d.device_id)}
              tracking={trackingDeviceId.includes(d.device_id)}
              onTrackingDeviceId={setTrackingDeviceId}
            />


          ))}
          {activeDevices.length === 0 && (
            <div className="text-xs text-gray-500">
              No devices yet. Click <span className="font-medium">Add Device</span> to select phones to track.
            </div>
          )}
        </div>

        {/* <div className="text-xxs text-gray-400 mt-2">
            <Tabs
              devices={devices} // full list
              selectedDeviceIds={selectedIds}
              setSelectedDeviceIds={setSelectedIds}
              alerts={alerts}
            />
        </div> */}

        {/* Monitor (optional: only show when at least one selected) */}
        {/* {firstSelectedId && (
          <>
            <div className="text-sm font-semibold mb-2">Monitor</div>
            <div className="grid md:grid-cols-2 gap-2">
              <MetricChart
                title="Battery %"
                deviceId={firstSelectedId}
                field="battery_percentage"

                interval="5m"
                unit="%"
              />
              <MetricChart
                title="Battery Temp"
                deviceId={firstSelectedId}
                field="battery_temperature"
                range="6h"
                interval="5m"
                unit="°C"
              />
              <MetricChart
                title="Latency"
                deviceId={firstSelectedId}
                field="latency_manual_ms"
                range="1h"
                interval="1m"
                unit="ms"
              />
            </div>
          </>
        )} */}
      </div>

    </div>
  )
}
