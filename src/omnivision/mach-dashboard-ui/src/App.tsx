import { useEffect, useRef, useState } from 'react'
import { fetchDevices, fetchAlerts, type Device /*, bulkAddDevices*/ } from './lib/api'
import { useAppStore } from './store/useAppStore'
import DeviceCard from './components/DeviceCard'
import AlertsPanel from './components/AlertsPanel'
import AddFromDiscovery from './components/AddDevice'
import MetricChart from './components/Chart'
import './App.css'


const API_BASE = import.meta.env.API_BASE || 'http://localhost:8000'
const did = (d: Device) => (d.device_id || '').toLowerCase()

export default function App() {
  const { devices, alerts, setDevices, setAlerts } = useAppStore()
  const [localAdded, setLocalAdded] = useState<Device[]>([]) // ← sticky client set
  const firstDeviceId = 'h2r-pixel-1.tail9e9110.ts.net'
  // Merge helper: union by device_id, prefer polled data over local stubs
  const mergeDevices = (polled: Device[], locals: Device[]) => {
    const map = new Map<string, Device>()
    for (const d of locals) map.set(did(d), d)
    for (const d of polled) map.set(did(d), d) // polled wins
    // filter out empties
    return Array.from(map.values()).filter(d => d.device_id)
  }

  useEffect(() => {
    let mounted = true
    const load = async () => {
      try {
        const [d, a] = await Promise.all([fetchDevices(), fetchAlerts()])
        if (!mounted) return
        setDevices(mergeDevices(d, localAdded))
        setAlerts(a)
      } catch (e) {
        console.warn('poll error', e)
        // even on error, keep showing localAdded merged with whatever we had
        setDevices(mergeDevices(devices, localAdded))
      }
    }
    load()
    const id = setInterval(load, 3000)
    return () => { mounted = false; clearInterval(id) }
  }, [setDevices, setAlerts, localAdded])

  // When the modal returns picks, keep them sticky and (optionally) persist
  const handlePicked = async (picks: Device[]) => {
    // 1) Put cards on screen immediately and keep them sticky
    setLocalAdded(prev => {
      const seen = new Set(prev.map(did))
      const merged = [...prev]
      for (const p of picks) {
        if (!p.device_id) continue
        const key = did(p)
        if (!seen.has(key)) { merged.push(p); seen.add(key) }
      }
      return merged
    })
    // 2) Reflect in the UI right away
    setDevices(mergeDevices(devices, picks))

    // 3) Persist to backend in background (uncomment if endpoint exists)
    // try { await bulkAddDevices(picks) } catch (e) { console.warn('bulkAdd failed', e) }
  }

  // Discovery fetcher for the modal
  const fetchDiscovered = async () => {
    const res = await fetch(`${API_BASE}/api/devices/discovered`)
    if (!res.ok) throw new Error(`discovered ${res.status}`)
    return await res.json()
  }

  return (
    <div className="h-screen grid grid-cols-12 grid-rows-12 p-3">
      {/* Devices + Add */}
      <div className="col-span-8 row-span-12 space-y-3">
        <div className="flex items-center justify-between">
          <div className="text-sm font-semibold">Devices</div>
          <AddFromDiscovery
            existing={devices}
            onPicked={handlePicked}
            fetchDiscovered={fetchDiscovered}
          />
        </div>

        <div className="grid md:grid-cols-2 gap-2">
          {devices.map(d => (
            <DeviceCard key={d.device_id || d.name} d={d} />
          ))}
          {devices.length === 0 && (
            <div className="text-xs text-gray-500">No devices yet</div>
          )}
        </div>

         <div className="text-sm font-semibold mb-2">Monitor</div>
          <div className="grid md:grid-cols-2 gap-2">
             <MetricChart
              title="Battery %"
              deviceId={firstDeviceId}
              field="battery_percentage"
              range="6h"
              interval="5m"
              unit="%"
            />
            <MetricChart
              title="Battery Temp"
              deviceId={firstDeviceId}
              field="battery_temperature"
              range="6h"
              interval="5m"
              unit="°C"
            />
            <MetricChart
              title="Latency"
              deviceId={firstDeviceId}
              field="latency_manual_ms"
              range="1h"
              interval="1m"
              unit="ms"
            />
          </div>
      </div>
      

      {/* Alerts */}
      <div className="col-span-4 row-span-12 rounded-xl border p-5" style={{ borderColor: 'var(--panel-border)' }}>
        <div className="text-sm font-semibold mb-2">Alerts</div>
        <AlertsPanel alerts={alerts} />
      </div>
    </div>
  )
}
