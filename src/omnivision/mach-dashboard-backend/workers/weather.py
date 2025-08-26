import requests
import datetime
import json
import os
from dotenv import load_dotenv

load_dotenv()

API_KEY = os.getenv("OPENWEATHER_API_KEY")
LATITUDE = 29.92046
LONGITUDE = -97.87474
UNITS = "metric"  # or "imperial" for Fahrenheit


url = f"http://api.openweathermap.org/data/2.5/weather?lat={LATITUDE}&lon={LONGITUDE}&appid={API_KEY}&units={UNITS}"

response = requests.get(url)
weather_data = response.json()
# print(f"Weather data for {LATITUDE}, {LONGITUDE}: {weather_data}")

entry = {
    "location": {
        "latitude": LATITUDE,
        "longitude": LONGITUDE,
        "location_name": weather_data["name"]
    },
    "timestamp": datetime.datetime.now().isoformat(),
    "temperature": weather_data["main"]["temp"],
    "humidity": weather_data["main"]["humidity"],
    "wind_speed": weather_data["wind"]["speed"],
    "weather_description": weather_data["weather"][0]["description"],
    "cloudiness": weather_data["clouds"]["all"],
}


print(json.dumps(entry, indent=2))