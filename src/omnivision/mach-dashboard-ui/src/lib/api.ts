import axios from 'axios'

const API_BASE= "https://mach-dashboard-backend-290982618858.us-central1.run.app"
export type Device = {
  device_id: string         
  timestamp?: string
  is_charging?: boolean | null
  battery_level_num?: number | null 
  battery_temp_num?: number | null   
  name?: string
  tailscaleIp?: string
  status?: 'online' | 'offline'
  tracking?: boolean
  webcam_online?: boolean | null
  phone_online?: boolean | null
}

export type Alert = {
  device_id: string
  level: 'warning' | 'critical'
  message: string
  timestamp: string
}

// Used in AddFromDiscovery
export type DiscoveryRow = {
  id?: string
  device_id?: string
  name?: string
  tailscaleIp?: string
  addresses?: string[]
  connected?: boolean
  lastSeen?: string
}

// Existing dashboard devices
export async function fetchDevices(): Promise<Device[]> {
  const { data } = await axios.get(`${API_BASE}/api/devices`)
  return data
}

// Device alerts
export async function fetchAlerts(deviceId: string, limit = 0): Promise<Alert[]> {
  const { data } = await axios.get(`${API_BASE}/api/alerts`, {
    params: {
      device_id: deviceId,
      limit,
    },
  });
  return data;
}

// Discoverable devices (e.g., Tailscale)
export async function fetchDiscovered(): Promise<DiscoveryRow[]> {
  const { data } = await axios.get(`${API_BASE}/api/devices`)
  return data
}

// Offline queue status
export type OfflineStatus = { pending_total: number; per_collection: Record<string, number> }
export async function getOfflineStatus(): Promise<OfflineStatus> {
  const { data } = await axios.get(`${API_BASE}/api/offline/status`)
  return data
}

// Trigger a test write to the local offline queue
export async function testOfflineWrite(message?: string): Promise<{ ok: boolean; path?: string; status?: OfflineStatus }>{
  const { data } = await axios.post(`${API_BASE}/api/offline/test`, { message })
  return data
}

// Camera control (queued command, executed by agent)
export async function startCamera(deviceId: string): Promise<{ ok: boolean } | any> {
  const { data } = await axios.post(`${API_BASE}/api/devices/${encodeURIComponent(deviceId)}/camera/start`)
  return data
}

export async function stopCamera(deviceId: string): Promise<{ ok: boolean } | any> {
  const { data } = await axios.post(`${API_BASE}/api/devices/${encodeURIComponent(deviceId)}/camera/stop`)
  return data
}

// Probe IP Webcam reachability via backend/agent
export async function checkWebcam(deviceId: string): Promise<{ device_id: string; reachable: boolean | null; status: string; message?: string; tookMs?: number }> {
  const { data } = await axios.get(`${API_BASE}/api/devices/${encodeURIComponent(deviceId)}/webcam/reachable`)
  return data
}

// Tracking control
export async function startTracking(deviceId: string): Promise<any> {
  const { data } = await axios.post(`${API_BASE}/api/devices/${encodeURIComponent(deviceId)}/tracking/start`)
  return data
}

export async function stopTracking(deviceId: string): Promise<any> {
  const { data } = await axios.post(`${API_BASE}/api/devices/${encodeURIComponent(deviceId)}/tracking/stop`)
  return data
}
