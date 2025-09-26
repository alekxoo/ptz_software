import { useEffect, useMemo, useState } from 'react'
import { computeLastSeenLabel, lastSeenSortKey } from '../lib/lastSeen'
import type { Device } from '../lib/api'                              

/** The shape your discovery endpoint returns */
type Row = {
  id?: string
  device_id?: string
  name?: string
  tailscaleIp?: string
  addresses?: string[]     // optional list of IPs; we prefer 100.x if present
  connected?: boolean
  lastSeen?: string
  os?: string
  displayName?: string
}

/** Normalize an ID if present */
const normId = (d: any) => (d?.device_id ?? d?.id ?? '').toString().toLowerCase()

/** Always produce a non-empty stable key for UI state */
const rowKey = (r: Row, idx: number) => {
  const id = normId(r)
  return id || `row-${idx}`        // fallback so checkbox & IP map always work
}

function maskIp(ip: string): string {
  const parts = ip.split('.');
  if (parts.length === 4) {
    return `${parts[0]}.x.x.${parts[3]}`;
  }
  return 'x.x.x.x'; // fallback
}


export default function AddDevice({
  existing,
  onPicked,
  fetchDiscovered,   // () => Promise<Row[]>
}: {
  existing: Device[]
  onPicked: (picks: Device[]) => void
  fetchDiscovered: () => Promise<Row[]>
}) {
  const [open, setOpen] = useState(false)
  const [loading, setLoading] = useState(false)
  const [rows, setRows] = useState<Row[]>([])
  const [selected, setSelected] = useState<Record<string, boolean>>({})
  const [ipChoice, setIpChoice] = useState<Record<string, string>>({})
  const [q, setQ] = useState('')

  // we don't block selection anymore, but we keep this for a small label
  const existingIds = useMemo(() => new Set(
    existing.map(e => (e.device_id ?? '').toString().toLowerCase()).filter(Boolean)
  ), [existing])

  const primeIp = (list: Row[]) => {
    const map: Record<string, string> = {}
    list.forEach((r, i) => {
      const key = rowKey(r, i)
      const addr =
        r.tailscaleIp ||
        r.addresses?.find(a => a.startsWith('100.')) ||
        r.addresses?.[0] ||
        ''
      map[key] = addr
    })
    setIpChoice(map)
  }

  const load = async () => {
    setLoading(true)
    try {
      const list = await fetchDiscovered()
      setRows(list)
      primeIp(list)
    } catch (e) {
      console.error(e)
      alert('Failed to load discovered devices')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { if (open) load() }, [open])

  const filtered = rows.filter((r, i) => {
    const key = rowKey(r, i)
    const ip = ipChoice[key] || ''
    const term = q.trim().toLowerCase()
    if (!term) return true
    const id = normId(r)
    const name = (r.name || '').toLowerCase()
    return name.includes(term) || id.includes(term) || ip.toLowerCase().includes(term)
  }).sort((a, b) => {
    // Connected first
    const ac = !!a.connected ? 1 : 0
    const bc = !!b.connected ? 1 : 0
    if (ac !== bc) return bc - ac
    // Then by lastSeen recency (desc)
    const aKey = lastSeenSortKey(a.lastSeen)
    const bKey = lastSeenSortKey(b.lastSeen)
    return bKey - aKey
  })

  const toggle = (k: string) => setSelected(s => ({ ...s, [k]: !s[k] }))

  const addSelected = () => {
    const picks: Device[] = filtered.map((r, i) => {
      const key = rowKey(r, i)
      if (!selected[key]) return null

      // Real device_id (best effort): prefer actual id/device_id, else name, else IP, else the row key
      const realId = normId(r) || r.name || ipChoice[key] || key

      return {
        device_id: realId.toString().toLowerCase(),
        name: r.name || realId,
        tailscaleIp: ipChoice[key] || r.tailscaleIp || '',
        status: 'offline',
        battery_percentage: null,
        battery_temperature: null,
        is_charging: null,
        timestamp: new Date().toISOString(),
      }
    }).filter(Boolean) as Device[]

    if (picks.length) onPicked(picks)
    setOpen(false)
    setSelected({})
  }

  return (
    <>
      <button
        className="px-3 py-2 rounded bg-indigo-700 hover:bg-indigo-600 text-sm m-2"
        onClick={() => setOpen(true)}
      >
        + Add Device
      </button>

      {open && (
        <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-50">
          <div className="w-[880px] max-h-[80vh] overflow-hidden rounded-xl border bg-[#0f1115]" style={{ borderColor: 'var(--panel-border)' }}>
            <div className="px-5 py-4 border-b" style={{ borderColor: 'var(--panel-border)' }}>
              <div className="text-lg font-semibold">Select Devices</div>
              <div className="mt-3 flex gap-2">
                <input
                  className="flex-1 rounded px-3 py-2 bg-[#0b0d12] border"
                  style={{ borderColor: 'var(--panel-border)' }}
                  placeholder="Search by name / device_id / IP"
                  value={q}
                  onChange={(e) => setQ(e.target.value)}
                />
                <button className="px-3 py-2 rounded bg-slate-700" onClick={load} disabled={loading}>
                  {loading ? 'Refreshing…' : 'Refresh'}
                </button>
              </div>
            </div>

            <div className="px-5 py-3 overflow-auto" style={{ maxHeight: '55vh' }}>
              <table className="w-full text-sm">
                <thead className="text-gray-400">
                  <tr className="text-left">
                    <th className="w-10"></th>
                    <th>Device ID</th>
                    <th style={{ minWidth: 220 }}>IP (choose or edit)</th>
                    <th>Last Seen</th>
                    <th>On Dashboard</th>
                  </tr>
                </thead>
                <tbody>
                  {filtered.map((r, i) => {
                    const key = rowKey(r, i)
                    const id = normId(r)
                    const already = existingIds.has(id)

                    return (
                      <tr key={key} className="border-t border-[#1f2430] align-top">
                        <td className="py-2">
                          <input
                            type="checkbox"
                            checked={already ? true : !!selected[key]}
                            onChange={() => toggle(key)}
                            disabled={already}
                            title={already ? 'Already on dashboard' : ''}
                            className={already ? 'opacity-50 cursor-not-allowed' : ''}
                          />
                        </td>
                        <td className="py-2">{r.displayName || r.device_id || r.name || '—'}</td>
                        <td className="py-2">
                          {ipChoice[key] ? maskIp(ipChoice[key]) : '—'}
                        </td>
                        <td>{(() => {
                          const { label } = computeLastSeenLabel(r.lastSeen, r.connected)
                          const isConnected = !!r.connected
                          const display = isConnected ? 'Connected' : label
                          return (
                            <span className={isConnected ? 'text-green-500 font-semibold' : 'text-red-500'}>{display}</span>
                          )
                        })()}</td>
                        <td>{already ? 'Yes' : 'No'}</td>
                      </tr>
                    )
                  })}
                  {filtered.length === 0 && (
                    <tr>
                      <td colSpan={7} className="text-center text-gray-500 py-6">No devices found</td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>

            <div className="px-5 py-4 border-t flex justify-end gap-2" style={{ borderColor: 'var(--panel-border)' }}>
              <button className="px-3 py-2 rounded bg-slate-700" onClick={() => setOpen(false)}>Cancel</button>
              <button className="px-3 py-2 rounded bg-green-600" onClick={addSelected}>Add Selected</button>
            </div>
          </div>
        </div>
      )}
    </>
  )
}
