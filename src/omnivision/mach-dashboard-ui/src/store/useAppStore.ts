import { create } from 'zustand'
import type { Device, Alert } from '../lib/api'

interface AppState {
  devices: Device[]
  alerts: Alert[]
  setDevices: (d: Device[]) => void
  setAlerts: (a: Alert[]) => void
}

export const useAppStore = create<AppState>((set) => ({
  devices: [],
  alerts: [],
  setDevices: (devices) => set({ devices }),
  setAlerts: (alerts) => set({ alerts }),
}))
