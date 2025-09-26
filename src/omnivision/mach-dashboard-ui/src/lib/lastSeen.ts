export type LastSeenInfo = { label: string; connected: boolean }

function enforceCDT(s: string): string {
  return s.replace(/\bCST\b/g, 'CDT')
}

// Format an ISO timestamp into TailScale-like display in Central time (with CDT label)
function formatIsoTailScale(iso: string): string {
  const d = new Date(iso)
  if (isNaN(d.getTime())) return iso

  const nowC = new Date(new Date().toLocaleString('en-US', { timeZone: 'America/Chicago' }))
  const dtC = new Date(d.toLocaleString('en-US', { timeZone: 'America/Chicago' }))
  const msDiff = nowC.getTime() - dtC.getTime()
  const oneDayMs = 24 * 60 * 60 * 1000

  if (msDiff < oneDayMs) {
    const t = dtC.toLocaleString('en-US', {
      hour: 'numeric', minute: '2-digit', hour12: true,
      timeZone: 'America/Chicago', timeZoneName: 'short'
    })
    return enforceCDT(t)
  }
  if (msDiff <= 1 * oneDayMs) {
    const datePart = dtC.toLocaleString('en-US', { month: 'short', day: 'numeric' })
    const timeRaw = dtC.toLocaleString('en-US', {
      hour: 'numeric', minute: '2-digit', hour12: true,
      timeZone: 'America/Chicago', timeZoneName: 'short'
    })
    return `${datePart}, ${enforceCDT(timeRaw)}`
  }
  return dtC.toLocaleString('en-US', { month: 'short', day: 'numeric' })
}

function isoIsWithinOneDay(iso: string): boolean {
  const d = new Date(iso)
  if (isNaN(d.getTime())) return false
  const nowC = new Date(new Date().toLocaleString('en-US', { timeZone: 'America/Chicago' }))
  const dtC = new Date(d.toLocaleString('en-US', { timeZone: 'America/Chicago' }))
  const msDiff = nowC.getTime() - dtC.getTime()
  return msDiff < 24 * 60 * 60 * 1000
}

// Check if an ISO timestamp is between 1 and 3 days old (Central time),
// and if so, return a TailScale-style label like "Sep 6, 2:27 PM CDT".
// Returns null when outside that window or if the ISO is invalid.
export function isoWithinOneToThreeDaysLabel(iso: string): string | null {
  const d = new Date(iso)
  if (isNaN(d.getTime())) return null
  const nowC = new Date(new Date().toLocaleString('en-US', { timeZone: 'America/Chicago' }))
  const dtC = new Date(d.toLocaleString('en-US', { timeZone: 'America/Chicago' }))
  const oneDayMs = 24 * 60 * 60 * 1000
  const msDiff = nowC.getTime() - dtC.getTime()
  if (msDiff >= oneDayMs && msDiff <= 5 * oneDayMs) {
    const datePart = dtC.toLocaleString('en-US', { month: 'short', day: 'numeric' })
    const timeRaw = dtC.toLocaleString('en-US', {
      hour: 'numeric', minute: '2-digit', hour12: true,
      timeZone: 'America/Chicago', timeZoneName: 'short'
    })
    return `${datePart}, ${enforceCDT(timeRaw)}`
  }
  return null
}

function humanTimeIsTodayCentral(s: string): boolean {
  // e.g., "7:10 AM CDT" → treat as today
  const m = /^\s*\d{1,2}:\d{2}\s*(AM|PM)\s*(CDT|CST)\s*$/i.exec(s)
  if (!m) return false
  return true
}

// Convert a time-only string like "2:27 PM CDT" into "Mon DD, h:mm AM/PM CDT"
// by attaching yesterday's date in Central time.
function humanTimeToYesterdayLabelCentral(s: string): string {
  const m = /^\s*(\d{1,2}):(\d{2})\s*(AM|PM)\s*(CDT|CST)\s*$/i.exec(s)
  if (!m) return enforceCDT(s)
  const hour12 = parseInt(m[1], 10)
  const minute = parseInt(m[2], 10)
  const ampm = m[3].toUpperCase()
  let hour = hour12 % 12
  if (ampm === 'PM') hour += 12
  const nowC = new Date(new Date().toLocaleString('en-US', { timeZone: 'America/Chicago' }))
  const yesterday = new Date(nowC)
  yesterday.setDate(nowC.getDate() - 1)
  const dtC = new Date(yesterday.getFullYear(), yesterday.getMonth(), yesterday.getDate(), hour, minute, 0, 0)
  const datePart = dtC.toLocaleString('en-US', { month: 'short', day: 'numeric' })
  const timePart = dtC.toLocaleString('en-US', { hour: 'numeric', minute: '2-digit', hour12: true, timeZone: 'America/Chicago', timeZoneName: 'short' })
  return `${datePart}, ${enforceCDT(timePart)}`
}

export function computeLastSeenLabel(lastSeen?: any, _connected?: boolean): LastSeenInfo {
  const ls = typeof lastSeen === 'string' ? lastSeen.trim() : ''
  // Treat empty/null lastSeen as Connected
  if (!ls) {
    return { label: 'Connected', connected: true }
  }
  // If a lastSeen string is present, it takes precedence over the boolean flag
  if (ls.toLowerCase() === 'connected') return { label: 'Connected', connected: true }
  if (ls.includes('T')) {
    // ISO timestamps: today -> time only; 1–3 days -> Mon DD, time; older -> Mon DD
    const midLabel = isoWithinOneToThreeDaysLabel(ls)
    const label = midLabel ?? formatIsoTailScale(ls)
    return { label, connected: false }
  }
  // Human string: if it's a time-only like '7:10 AM CDT' (today), treat as connected
  if (humanTimeIsTodayCentral(ls)) {
    // Convert time-only to yesterday's date+time label (e.g., 'Sep 6, 2:27 PM CDT')
    return { label: humanTimeToYesterdayLabelCentral(ls), connected: false }
  }
  return { label: enforceCDT(ls), connected: false }
}

// Produce a numeric sort key for lastSeen where larger means more recent.
// Shapes handled (Central time expected from backend):
//  - "Connected" → very recent (Infinity-like)
//  - "h:mm AM/PM CDT" → today with that time
//  - "Mon DD, h:mm AM/PM CDT" → date + time
//  - "Mon DD" → date only (00:00 that day)
//  - ISO string fallback
export function lastSeenSortKey(lastSeen?: string): number {
  if (!lastSeen) return 0
  const s = lastSeen.trim()
  if (!s) return 0
  if (s.toLowerCase() === 'connected') return Number.MAX_SAFE_INTEGER

  // Central now
  const nowC = new Date(new Date().toLocaleString('en-US', { timeZone: 'America/Chicago' }))
  const year = nowC.getFullYear()

  // Mon DD, h:mm AM/PM CDT
  let m = /^(\w{3})\s+(\d{1,2}),\s+(\d{1,2}:\d{2})\s+(AM|PM)\s+(CDT|CST)$/i.exec(s)
  if (m) {
    const [_, mon, dd, time, ampm] = m
    const str = `${mon} ${dd}, ${year} ${time} ${ampm}`
    const dt = new Date(str)
    return dt.getTime() || 0
  }

  // Mon DD
  m = /^(\w{3})\s+(\d{1,2})$/i.exec(s)
  if (m) {
    const [_, mon, dd] = m
    const str = `${mon} ${dd}, ${year} 00:00 AM`
    const dt = new Date(str)
    return dt.getTime() || 0
  }

  // h:mm AM/PM CDT → assume today
  m = /^(\d{1,2}:\d{2})\s+(AM|PM)\s+(CDT|CST)$/i.exec(s)
  if (m) {
    const [_, time, ampm] = m
    const mon = nowC.toLocaleString('en-US', { month: 'short' })
    const dd = nowC.getDate()
    const str = `${mon} ${dd}, ${year} ${time} ${ampm}`
    const dt = new Date(str)
    return dt.getTime() || 0
  }

  // Fallback: try ISO
  const iso = new Date(s)
  return isNaN(iso.getTime()) ? 0 : iso.getTime()
}

// For CSV rows that only have Created/Last seen (no explicit connected flag):
// - If Last seen is empty, treat as Connected.
// - Else format using TailScale-like rules and mark disconnected.
export function computeLastSeenFromCsv(_created?: string, lastSeen?: string): LastSeenInfo {
  const ls = typeof lastSeen === 'string' ? lastSeen.trim() : ''
  if (!ls) return { label: 'Connected', connected: true }
  if (ls.includes('T')) {
    const label = formatIsoTailScale(ls)
    const isToday = isoIsWithinOneDay(ls)
    if (isToday) return { label, connected: false }
    return { label, connected: false }
  }
  if (humanTimeIsTodayCentral(ls)) {
    return { label: humanTimeToYesterdayLabelCentral(ls), connected: false }
  }
  return { label: enforceCDT(ls), connected: false }
}
