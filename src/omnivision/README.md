weatherAPI.py
- Pulls weather data and logs it 

status.py
- FastAPI Server that receives and stores phone status reports



HOW TO RUN:
1. weatherAPI.py
    Make sure using API key
    Then run: 'python weatherAPI.py'

    Expected Output: JSON Object with data printed to the terminal

2. status.oy
    Run: uvicorn status:app --reload --host 0.0.0.0 --port 8000
    (This start the dev server at: http://localhost:8000)

    Then you can test on Postman with URL: http://localhost:8000/status with POST method
    You can adjust the Body message to something like this for testing purposes:
    {
        "device_id": "cam01",
        "timestamp": "2025-08-04T19:00:00Z",
        "battery_percentage": 92,
        "is_charging": true,
        "battery_temperature": 37.0,
        "recording": true,
        "storage_used": 2100,
        "signal": -78,
        "network_type": "LTE"
    }


    Then go to http://localhost:8000/status/logs which will save the status logs in the local computer for now

