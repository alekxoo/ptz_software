import { clsx } from 'clsx'
import type { Device } from '../lib/api'

export default function DeviceCard({ d }: { d: Device }) {
  const statusColor = d.status === 'online' ? 'bg-green-500' : 'bg-red-500'
  return (
    <div className="rounded-xl p-3 border" style={{borderColor: 'var(--panel-border)', background: 'var(--panel-bg)'}}>
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <span className={clsx('w-2 h-2 rounded-full', statusColor)} />
          <div className="font-medium">{d.name || d.id}</div>
        </div>
      </div>
      <div className="mt-2 grid grid-cols-3 gap-2 text-xs text-gray-300">
        <div>Battery: <span className={d.battery! < 20 ? 'text-red-400':'text-green-400'}>{d.battery ?? '--'}%</span></div>
        <div>Temp: {d.tempC ?? '--'}°C</div>
        <div>Latency: {d.latencyMs ?? '--'} ms</div>
      </div>
    </div>
  )
}