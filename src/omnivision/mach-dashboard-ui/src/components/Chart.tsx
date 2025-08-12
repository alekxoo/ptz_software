// src/components/MetricChart.tsx
import { useEffect, useState } from "react";
import axios from "axios";
import { LineChart, Line, CartesianGrid, XAxis, YAxis, Tooltip, ResponsiveContainer } from "recharts";

const API_BASE = import.meta.env.API_BASE;

export default function MetricChart({deviceId, field, range="1h", interval="1m", unit}: { deviceId: string; field: string; range?: string; interval?: string; unit?: string }) {
    const [data, setData] = useState<{t:string; avg:number}[]>([]);

    useEffect(() => {
    let alive = true;
    const load = async () => {
        const { data } = await axios.get(`${API_BASE}/api/metrics`, {
        params: { device_id: deviceId, field, range, interval }
    });
    if (!alive) return;
    setData(data.points.map((p:any) => ({ t: new Date(p.t).toLocaleTimeString(), avg: p.avg })));
    };
    load();
    const id = setInterval(load, 5000); // poll every 5s (swap to WS later)
    return () => { alive = false; clearInterval(id); };
}, [deviceId, field, range, interval]);

return (
    <>
    <div className="h-60 w-full m-2">
        <ResponsiveContainer >
            <LineChart data={data}>
                <CartesianGrid strokeDasharray="3 3" />
                <XAxis dataKey="t" />
                <YAxis />
                <Tooltip />
                <Line type="monotone" dataKey="avg" dot={false} />
            </LineChart>
        </ResponsiveContainer>
        <div className="text-xs text-gray-400 mb-1">{field} {unit ? `(${unit})` : ""}</div>
    </div>
    </>
);
}
