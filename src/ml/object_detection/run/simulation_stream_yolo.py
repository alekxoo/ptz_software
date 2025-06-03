import cv2

gst = "tcpserversrc host= 192.168.137.2 port=1234 ! tsdemux ! h264parse ! avdec_h264 ! videoconvert ! appsink sync=false drop=true"
cap = cv2.VideoCapture(gst, cv2.CAP_GSTREAMER)

if not cap.isOpened():
    print("Error: Could not open video stream")
    exit()

while True:
    ret, frame = cap.read()
    
    if not ret:
        print("Error: Could not read frame")
        break
    
    cv2.imshow('Video Stream', frame)
    
    # Break loop on 'q' key press
    if cv2.waitKey(1) & 0xFF == ord('q'):
        break

# Clean up
cap.release()
cv2.destroyAllWindows()