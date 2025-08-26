// src/components/MetricChart.tsx
import { useEffect, useState } from "react";
import axios from "axios";
import {
  LineChart, Line, CartesianGrid, XAxis, YAxis, Tooltip, ResponsiveContainer,
} from "recharts";

const API_BASE = import.meta.env.VITE_API_BASE || "http://localhost:8000";

type Point = { t: string; avg: number };

export default function MetricChart({
  deviceId,
  field,
  range = "1h",
  interval = "1m",
  unit,
  title,
}: {
  deviceId: string;
  field: string;
  range?: string;
  interval?: string;
  unit?: string;
  title?: string;
}) {
  const [data, setData] = useState<Point[]>([]);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;

    const load = async () => {
      try {
        const res = await axios.get(`${API_BASE}/api/metrics`, {
          params: { device_id: deviceId, field, range, interval },
        });
        if (!alive) return;
        const pts = (res.data?.points || []).map((p: any) => ({
          t: new Date(p.t).toLocaleTimeString(),
          avg: Number(p.avg),
        }));
        setData(pts);
        setErr(null);
      } catch (e: any) {
        if (!alive) return;
        setErr(e?.message || "Failed to load");
      } finally {
        if (alive) setLoading(false);
      }
    };

    load();
    const id = setInterval(load, 5000); // poll every 5s
    return () => { alive = false; clearInterval(id); };
  }, [deviceId, field, range, interval]);

  return (
    <div className="rounded-xl border p-3 m-2" style={{borderColor: "var(--panel-border)", background: "var(--panel-bg)"}}>
      <div className="text-sm mb-2">
        {title || field} {unit ? <span className="text-gray-400">({unit})</span> : null}
      </div>

      <div className="h-60 w-full">
        {loading ? (
          <div className="h-full flex items-center justify-center text-xs text-gray-500">Loading…</div>
        ) : err ? (
          <div className="h-full flex items-center justify-center text-xs text-red-400">{err}</div>
        ) : data.length === 0 ? (
          <div className="h-full flex items-center justify-center text-xs text-gray-500">No data</div>
        ) : (
          <ResponsiveContainer>
            <LineChart data={data}>
              <CartesianGrid strokeDasharray="3 3" />
              <XAxis dataKey="t" minTickGap={20} />
              <YAxis />
              <Tooltip />
              <Line type="monotone" dataKey="avg" dot={false} />
            </LineChart>
          </ResponsiveContainer>
        )}
      </div>
    </div>
  );
}
