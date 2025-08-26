import type { Device } from '../lib/api'

export default function DeviceCard({ d }: { d: Device }) {
  const statusColor = d.status === 'online' ? 'bg-green-500' : 'bg-red-500'
  return (
    <div className="rounded-xl p-3 border m-2" style={{borderColor: 'var(--panel-border)', background: 'var(--panel-bg)'}}>
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <span className={`w-2 h-2 rounded-full ${statusColor}`} />
          <div className="font-medium"> {d.name || d.device_id || d.tailscaleIp || 'Unknown device'}</div>
        </div>
      </div>

      <div className="mt-2 grid grid-cols-3 gap-2 text-xs text-gray-300">
        <div>Battery %: <span className={d.battery_level_num! < 20 ? 'text-red-400':'text-green-400'}>
          {d.battery_level_num ?? '--'}%
        </span></div>
        <div>Temp: {d.battery_temp_num ?? '--'}°C</div>
        <div>Charging: {d.is_charging === true ? 'Yes' : d.is_charging === false ? 'No' : '--'}</div>
      </div>
    </div>
  )
}
