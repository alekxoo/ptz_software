import axios from 'axios'
const API_BASE = import.meta.env.VITE_API_BASE || 'http://localhost:8000'

export type Device = {
  device_id: string
  name?: string
  tailscaleIp?: string
  status?: 'online'|'offline'
  battery_level_num?: number | null
  battery_temp_num?: number | null
  is_charging?: boolean | null
  timestamp?: string
}

export type Alert = {
  device_id: string
  level: 'warning'|'critical'
  message: string
  timestamp: string
}

export async function fetchDevices(): Promise<Device[]> {
  const { data } = await axios.get(`${API_BASE}/api/devices`)
  return data
}

export async function fetchAlerts(limit = 50): Promise<Alert[]> {
  const { data } = await axios.get(`${API_BASE}/api/alerts?limit=${limit}`)
  return data
}

export async function fetchDiscovered(): Promise<Device[]> {
  const { data } = await axios.get(`${API_BASE}/api/devices/discovered`)
  return data
}

export async function bulkAddDevices(payload: {device_id: string; name: string; location?: string; tailscaleIp?: string}[]) {
  const { data } = await axios.post(`${API_BASE}/api/devices/bulk_add`, payload)
  return data
}
