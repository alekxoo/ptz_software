# Blu0: http://100.78.248.18:8080/
# Blu1: http://100.89.255.106:8080/
# Blu2: http://100.114.70.62:8080/
# Motorolla0: http://100.99.14.124:8080/

import requests
import time
from datetime import datetime


device_ips = {
    "blu": [
        "100.78.248.18",
        "100.89.255.106",
        "100.114.70.62"
    ],
    "motorola": [
        "100.99.14.124"
    ]
}

# for phone_type, ips in device_ips.items():
#     for ip in ips:
#         url = f"http://{ip}:8080/videostatus"
#         try:
#             start_time = time.time()
#             response = requests.get(url, timeout=2)
#             print(f"[{ip} - {phone_type}] Response time: {time.time() - start_time:.2f} seconds")
#             response.raise_for_status()
#             print(f"[{ip} - {phone_type}] Connection successful!")
#         except requests.exceptions.RequestException as e:
#             print(f"[{ip} - {phone_type}] Connection failed: {e}")


import requests

# Query sensor data from the IP Webcam server
url = "http://100.99.14.124:8080/sensors.json"
params = {
    "sense": "battery_level,battery_temp,battery_voltage,battery_charging"
}

response = requests.get(url, params=params)
data = response.json()

# Helper to extract the latest value from each sensor
def latest(sensor):
    try:
        return data[sensor]["data"][-1][1][0]
    except (KeyError, IndexError):
        return None

# Get latest values
battery_level = latest("battery_level")
battery_temp = latest("battery_temp")
battery_voltage = latest("battery_voltage")
battery_charging = latest("battery_charging")

# Print results
print(f"🔋 Battery Level:     {battery_level}%")
print(f"🌡️  Battery Temp:      {battery_temp}°C")
print(f"⚡ Battery Voltage:   {battery_voltage}V")
print(f"🔌 Charging:          {'Yes' if battery_charging == 1.0 else 'No'}")
