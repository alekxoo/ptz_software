import type { Alert } from '../lib/api'

export default function AlertsPanel({ alerts }: { alerts: Alert[] }) {
  return (
<div className="h-full overflow-auto space-y-3 custom-scroll">
  {alerts.map((a) => (
    <div
      key={a.timestamp + a.message}
      className="text-sm p-2 rounded border"
      style={{
        borderColor: 'var(--panel-border)',
        background: 'var(--panel-bg)'
      }}
    >
      <div className="flex items-center justify-between">
        <span className={a.level === 'critical' ? 'text-red-500' : 'text-yellow-300'}>
          {a.level.toUpperCase()}
        </span>
        <span className="text-xxs text-gray-400">
          {new Date(a.timestamp).toLocaleTimeString()}
        </span>
      </div>
      <div className="mt-1 text-xxs">{a.message}</div>
    </div>
  ))}
  {alerts.length === 0 && (
    <div className="text-xxs text-gray-500">No alerts</div>
  )}
</div>
  )
}