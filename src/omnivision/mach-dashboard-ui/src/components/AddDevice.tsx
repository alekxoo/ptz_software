import { useState } from "react";
import axios from "axios";

export default function AddDeviceButton({ onAdded }: { onAdded: () => void }) {
    const [showModal, setShowModal] = useState(false);
    const [deviceId, setDeviceId] = useState("");
    const [name, setName] = useState("");
    const [location, setLocation] = useState("");
    const [loading, setLoading] = useState(false);
    const API_BASE = import.meta.env.VITE_API_BASE;

    const handleAdd = async () => {
        setLoading(true);
        try {
            const { data } = await axios.post(`${API_BASE}/api/devices`, {
                device_id: deviceId,
                name,
                location,
            });
            console.log(data);
            onAdded(); // Refresh parent list/chart
            setShowModal(false);
            setDeviceId("");
            setName("");
            setLocation("");
        } catch (err) {
            console.error(err);
            alert("Failed to add device");
        } finally {
            setLoading(false);
        }
    };

return (
    <>
    <button
        onClick={() => setShowModal(true)}
        className="px-4 py-2 bg-blue-600 text-white rounded hover:bg-blue-700"
    >
        ➕ Add Device
    </button>

        {showModal && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center">
            <div className="bg-white rounded-lg shadow-lg p-6 w-96">
            <h2 className="text-xl font-semibold mb-4">Add New Device</h2>

            <input
                type="text"
                placeholder="Device ID"
                value={deviceId}
                onChange={(e) => setDeviceId(e.target.value)}
                className="border rounded w-full p-2 mb-3"
            />
            <input
                type="text"
                placeholder="Device Name"
                value={name}
                onChange={(e) => setName(e.target.value)}
                className="border rounded w-full p-2 mb-3"
            />
            <input
                type="text"
                placeholder="Location"
                value={location}
                onChange={(e) => setLocation(e.target.value)}
                className="border rounded w-full p-2 mb-4"
            />

            <div className="flex justify-end space-x-2">
                <button
                    onClick={() => setShowModal(false)}
                    className="px-4 py-2 bg-gray-300 rounded hover:bg-gray-400"
                >
                Cancel
                </button>
                <button
                onClick={handleAdd}
                disabled={loading}
                className="px-4 py-2 bg-green-600 text-white rounded hover:bg-green-700"
                >
                    {loading ? "Adding..." : "Add"}
                </button>
                </div>
            </div>
            </div>
        )}
    </>
    );
}
