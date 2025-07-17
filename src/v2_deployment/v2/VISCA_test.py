import socket 
import threading 
import time 


camera_ip = "192.168.100.88"


import socket

# Connect and query pan/tilt position
try:
    s1 = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s1.connect((camera_ip, 5678))  # Replace with your camera IP
    s1.settimeout(2)
    print("Connected to camera for pan/tilt query")
except socket.error as e:
    print(f"Socket error: {e}")
    exit()

s1.send(bytes.fromhex("81090612FF"))
pan_tilt_response = s1.recv(32).hex()

# clears and limits pan/tilt movement
s1.send(bytes.fromhex("810106070100070f0f0f070f0f0fFF"))
s1.send(bytes.fromhex("810106070101070f0f0f070f0f0fFF"))

# # Connect and query zoom position
# s2 = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
# s2.connect(("192.168.1.100", 5678))  # Replace with your camera IP
# s2.send(bytes.fromhex("81090447FF"))
# zoom_response = s2.recv(1024).hex()
# s2.close()

# Parse responses

pan_nibbles = pan_tilt_response[4:12] # nibble = 4 bits
pan = int(pan_nibbles[1] + pan_nibbles[3] + pan_nibbles[5] + pan_nibbles[7], 16) # indicate that its hexadecimal
tilt_nibbles = pan_tilt_response[12:20]  
tilt = int(tilt_nibbles[1] + tilt_nibbles[3] + tilt_nibbles[5] + tilt_nibbles[7], 16)
# zoom = int(zoom_response[6:14], 16)

print(f"Pan: {pan}")
print(f"Tilt: {tilt}")
# print(f"Zoom: {zoom}")
# print(f"Raw Zoom Response: {zoom_response}")

s1.close()
