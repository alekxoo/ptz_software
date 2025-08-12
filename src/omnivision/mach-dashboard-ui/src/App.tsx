import { useEffect, useState } from "react";
import { fetchDevices, fetchAlerts } from "./lib/api";
import { useAppStore } from "./store/useAppStore";
import DeviceCard from "./components/DeviceCard";
import AlertsPanel from "./components/AlertsPanel";
import MetricChart from "./components/Chart";
import AddDeviceButton from "./components/AddDevice";

export default function App() {
  const { devices, alerts, setDevices, setAlerts } = useAppStore();
  const [selectedDeviceId, setSelectedDeviceId] = useState<string | undefined>();

  // Fetch devices (used on mount and after adding a device)
  const loadDevices = async () => {
    try {
      const d = await fetchDevices();
      setDevices(d);
      // Default chart target = first device if none selected
      if (!selectedDeviceId && d.length > 0) {
        setSelectedDeviceId(d[0].id);
      }
    } catch (e) {
      console.warn("loadDevices error:", e);
    }
  };

  // Initial + interval polling for devices/alerts
  useEffect(() => {
    let mounted = true;

    const load = async () => {
      try {
        const [d, a] = await Promise.all([fetchDevices(), fetchAlerts()]);
        if (!mounted) return;
        setDevices(d);
        setAlerts(a);
        if (!selectedDeviceId && d.length > 0) {
          setSelectedDeviceId(d[0].id);
        }
      } catch (e) {
        console.warn(e);
      }
    };

    load();
    const id = setInterval(load, 3000);
    return () => {
      mounted = false;
      clearInterval(id);
    };
  }, [setDevices, setAlerts, selectedDeviceId]);

  const currentId = selectedDeviceId || (devices[0]?.id ?? ""); // safe fallback

  return (
    <div className="h-screen grid grid-cols-12 grid-rows-12 gap-3 p-3">
      {/* Left: Devices + Charts */}
      <div className="col-span-8 row-span-12 space-y-4">
        <div className="flex items-center justify-between">
          <div className="text-sm font-semibold">Devices</div>
          <AddDeviceButton onAdded={loadDevices} />
        </div>

        {/* Device cards */}
        <div className="grid gap-2">
          {devices.map((d) => (
            <div key={d.id} onClick={() => setSelectedDeviceId(d.id)}>
              {/* DeviceCard supports optional onSelect; click wrapper works with all versions */}
              <DeviceCard d={d} />
            </div>
          ))}
          {devices.length === 0 && (
            <div className="text-xs text-gray-500">No devices yet</div>
          )}
        </div>

        {/* Monitor charts */}
        <div className="text-sm font-semibold">Monitor</div>
        {currentId ? (
          <div className="grid gap-3">
            <MetricChart
              deviceId={currentId}
              field="battery_percentage"
              range="6h"
              interval="5m"
              unit="%"
            />
            <MetricChart
              deviceId={currentId}
              field="battery_temperature"
              range="6h"
              interval="5m"
              unit="°C"
            />
            <MetricChart
              deviceId={currentId}
              field="latency_manual_ms"
              range="1h"
              interval="1m"
              unit="ms"
            />
          </div>
        ) : (
          <div className="text-xs text-gray-500">
            Select or add a device to view charts.
          </div>
        )}
      </div>

      {/* Right: Alerts */}
      <div
        className="col-span-4 row-span-12 rounded-xl border p-3"
        style={{ borderColor: "var(--panel-border)" }}
      >
        <div className="text-sm font-semibold mb-2">Alerts</div>
        <AlertsPanel alerts={alerts} />
      </div>
    </div>
  );
}
