import axios from 'axios'

const API_BASE = import.meta.env.API_BASE || 'http://localhost:8000'

export type Device = {
  id: string
  name: string
  tailscaleIp?: string
  status?: 'online'|'offline'
  battery?: number
  tempC?: number
  latencyMs?: number
}

export type Alert = {
  _id?: string
  device_id: string
  level: 'warning'|'critical'
  message: string
  timestamp: string
}

export async function fetchDevices(): Promise<Device[]> {
  const { data } = await axios.get(`${API_BASE}/api/devices`)
  return data
}

export async function fetchAlerts(): Promise<Alert[]> {
  const { data } = await axios.get(`${API_BASE}/api/alerts?limit=50`)
  return data
}