import { memo, useEffect, useRef, useState } from "react";
import { LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid } from "recharts";

const API_BASE = 'https://mach-dashboard-backend-290982618858.us-central1.run.app';
// const API_BASE = 'http://localhost:8000'; // for local dev

type Metric = 'battery' | 'temperature';

type MetricChartProps = {
  deviceId: string;
  unit?: string;
  title?: string;
  mode?: "history" | "live"; // history = /logs/all, live = poll /logs since startAt
  startAt?: number; // epoch ms; only used in live mode to filter points since Start was clicked
  from?: number; // epoch ms; optional lower bound (history mode)
  to?: number;   // epoch ms; optional upper bound (history mode)
  pollMs?: number; // live polling interval
  metric?: Metric; // which value to plot
};

type DataPoint = {
  x: Date;
  y: number;
};

function MetricChart({
  deviceId,
  unit = "",
  title = "Battery %",
  mode = "history",
  startAt,
  from,
  to,
  pollMs = 3000,
  metric = 'battery',
}: MetricChartProps) {
  const [data, setData] = useState<DataPoint[]>([]);
  const [loading, setLoading] = useState(true);
  const pollRef = useRef<number | null>(null);

  // HISTORY: one-shot fetch of all logs
  useEffect(() => {
    if (mode !== "history") return;
    let cancelled = false;
    const fetchLogs = async () => {
      setLoading(true);
      try {
        const res = await fetch(`${API_BASE}/api/devices/${deviceId}/logs/all`);
        const raw = await res.json();
        if (cancelled) return;
        const parsed = raw
          .map((log: any) => {
            const timestamp = log.timestamp?.$date;
            const val = metric === 'battery'
              ? (log.battery_level_num ?? (log["battery level"] != null ? Number(log["battery level"]) : undefined))
              : (log.battery_temp_num ?? (log["battery temperature"] != null ? Number(log["battery temperature"]) : undefined));
            if (!timestamp || val === undefined) return null;
            return { x: new Date(timestamp), y: Number(val) };
          })
          .filter((point: DataPoint | null): point is DataPoint => !!point)
          .filter((p: DataPoint) => (from ? p.x.getTime() >= from : true))
          .filter((p: DataPoint) => (to ? p.x.getTime() <= to : true));
        setData(parsed);
      } catch (err) {
        console.error("Failed to load device logs:", err);
      } finally {
        if (!cancelled) setLoading(false);
      }
    };
    fetchLogs();
    return () => {
      cancelled = true;
    };
  }, [deviceId, mode, from, to, metric]);

  // LIVE: poll recent logs and accumulate since startAt
  useEffect(() => {
    if (mode !== "live") return;
    // reset data when device or startAt changes
    setData([]);
    setLoading(true);

    const doPoll = async () => {
      try {
        const qs = startAt ? `?since=${encodeURIComponent(String(startAt))}` : "";
        const res = await fetch(`${API_BASE}/api/devices/${deviceId}/logs${qs}`);
        const raw = await res.json();
        const parsed: DataPoint[] = raw
          .map((log: any) => {
            const timestamp = log.timestamp?.$date;
            // backend attaches numeric *_num; fall back to string fields
            const val = metric === 'battery'
              ? (log.battery_level_num ?? (log["battery level"] != null ? Number(log["battery level"]) : undefined))
              : (log.battery_temp_num ?? (log["battery temperature"] != null ? Number(log["battery temperature"]) : undefined));
            if (!timestamp || val === undefined) return null;
            return { x: new Date(timestamp), y: Number(val) };
          })
          .filter((p: DataPoint | null): p is DataPoint => !!p)
          .filter((p: DataPoint) => (startAt ? p.x.getTime() >= startAt : true));

        // Keep unique by timestamp, sorted
        const byTs = new Map<number, DataPoint>();
        [...data, ...parsed].forEach((p: DataPoint) => byTs.set(p.x.getTime(), p));
        const merged = Array.from(byTs.values()).sort((a: DataPoint, b: DataPoint) => a.x.getTime() - b.x.getTime());
        setData(merged);
      } catch (e) {
        console.error("Live poll failed", e);
      } finally {
        setLoading(false);
      }
    };

    // immediate poll, then interval
    doPoll();
    pollRef.current = window.setInterval(doPoll, pollMs);
    return () => {
      if (pollRef.current) window.clearInterval(pollRef.current);
    };
  }, [deviceId, mode, startAt, pollMs]);

  return (
    <div className="p-2 border rounded bg-slate-800 text-white" style={{ height: "200px" }}>
      <div className="text-xs mb-1 font-semibold">{title}</div>

      {loading ? (
        <div className="text-xxs text-gray-400">Loading...</div>
      ) : data.length === 0 ? (
        <div className="text-xxs text-gray-400">No data available</div>
      ) : (
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={data}>
            <CartesianGrid strokeDasharray="3 3" stroke="#444" />
            <XAxis
              dataKey="x"
              tickFormatter={(tick) => new Date(tick).toLocaleTimeString()}
              stroke="#ccc"
              fontSize={10}
            />
            <YAxis unit={unit} stroke="#ccc" fontSize={10} />
            <Tooltip
              labelFormatter={(label) => new Date(label).toLocaleString()}
              formatter={(value: number) => [`${value}${unit}`, title]}
              contentStyle={{ backgroundColor: "#222", border: "none" }}
            />
            <Line type="monotone" dataKey="y" stroke="#66ccff" dot={false} strokeWidth={2} isAnimationActive={false} />
          </LineChart>
        </ResponsiveContainer>
      )}
    </div>
  );
}

export default memo(MetricChart);
