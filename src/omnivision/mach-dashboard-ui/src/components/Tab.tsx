import { useState } from "react";
import type { Alert } from "../lib/api";
import DeviceCard from "./DeviceCard";
// import MetricChart from "./Chart";

type Device = {
  device_id?: string;
  name?: string;
  status?: "online" | "offline";
  connected?: boolean;
  lastSeen?: string;
  battery?: number;
  battery_percentage?: number;
  battery_temperature?: number;
  tempC?: number;
  tracking?: boolean;
};

type TabsProps = {
  devices: Device[]; // full list of all devices
  selectedDeviceIds: string[]; // currently selected device IDs
  setSelectedDeviceIds: React.Dispatch<React.SetStateAction<string[]>>;
  alerts: Alert[];
};

export default function Tabs({ devices, selectedDeviceIds, setSelectedDeviceIds, alerts }: TabsProps) {
  const [activeTab, setActiveTab] = useState<string | null>(selectedDeviceIds[0] ?? null);
  const [showSetup, setShowSetup] = useState(false);

  const selectedDevices = devices.filter(d => selectedDeviceIds.includes(d.device_id || ""));
  const activeDevice = selectedDevices.find(d => d.device_id === activeTab);

  const handleAddDevice = (id: string) => {
    setSelectedDeviceIds(prev => prev.includes(id) ? prev : [...prev, id]);
    setActiveTab(id); // switch to the new tab
  };

  const handleRemoveDevice = (id: string) => {
    setSelectedDeviceIds(prev => prev.filter(x => x !== id));
    if (activeTab === id) {
      const remaining = selectedDeviceIds.filter(x => x !== id);
      setActiveTab(remaining[0] ?? null);
    }
  };


  return (
    <>
      {/* Chrome-style tab bar */}
      <div className="flex items-center h-10 px-2 bg-[#2b2b2b] border-b border-gray-600 overflow-x-auto space-x-1">
        {selectedDevices.length > 0 ? (
          selectedDevices.map(d => (
            <div
              key={d.device_id}
              onClick={() => setActiveTab(d.device_id ?? "")}
              className={`flex items-center px-4 py-1.5 rounded-t-md cursor-pointer text-sm
                ${activeTab === d.device_id ? "bg-[#1e1e1e] text-white" : "bg-[#3a3a3a] text-gray-300 hover:bg-[#2e2e2e]"}`}
            >
              {d.device_id}
              <button
                className="ml-2 text-xs text-gray-400 hover:text-red-400"
                onClick={(e) => {
                  e.stopPropagation();
                  handleRemoveDevice(d.device_id ?? "");
                }}
              >
                ✕
              </button>
            </div>
          ))
        ) : (
          <div className="text-gray-500 text-sm">No active devices</div>
        )}

        {/* Add button */}
        <div
          onClick={() => setShowSetup(true)}
          className="ml-2 px-3 py-1.5 rounded-t-md bg-[#3a3a3a] hover:bg-[#2e2e2e] text-white cursor-pointer"
        >
          ＋
        </div>
      </div>

      {/* Add device setup panel */}
      {showSetup && (
        <div className="absolute top-12 left-0 right-0 bg-black border-t border-gray-700 p-4 z-50">
          <div className="flex justify-between items-center mb-2">
            <span className="text-white font-medium">Add Device Tab</span>
            <button className="text-gray-400 hover:text-white" onClick={() => setShowSetup(false)}>✕</button>
          </div>

          <ul className="text-sm text-gray-300 space-y-1">
            {devices.map(d => (
              <li key={d.device_id} className="flex justify-between items-center border-b border-gray-600 pb-1">
                <span>{d.device_id}</span>
                <button
                  className="text-blue-400 hover:text-blue-200 text-xs"
                  onClick={() => handleAddDevice(d.device_id ?? "")}
                >
                  Add
                </button>
              </li>
            ))}
          </ul>
        </div>
      )}

      {/* Render DeviceCard for active tab */}
      <div className="p-4">
        {activeDevice ? (
            // <>
            //     {devices.map(d => (
                    
            //     <span key={d.device_id}>{d.device_id}</span>
                
            //     ))}
            //     <MetricChart deviceId={activeDevice.device_id} />
            //  </>
            <DeviceCard
                key={activeDevice.device_id}
                d={activeDevice}
                onRemove={(id) => handleRemoveDevice(id)}
                alerts={alerts.filter(a => a.device_id === activeDevice.device_id)}
                tracking={true}
                onTrackingDeviceId={() => {}}
            />
            ) : (
            <div className="text-gray-500 text-sm p-4">Select a device tab to view its info.</div>
            )}
      </div>
    </>
  );
}
