import cv2

# pipeline = "gst-launch-1.0 v4l2src device=/dev/video0 ! \
#   'video/x-h264, stream-format=byte-stream, alignment=au, width=3840, height=2160, framerate=30/1' ! \
#   h264parse ! \
#   queue max-size-buffers=1 max-size-bytes=0 max-size-time=0 ! \
#   nvv4l2decoder disable-dpb=true enable-max-performance=1 ! \
#   nvvidconv ! \
#   'video/x-raw(memory:NVMM), format=NV12' ! \
#   nv3dsink sync=false async=false qos=false"

pipeline = "gst-launch-1.0 v4l2src device=/dev/video0 ! \
  'video/x-h264, stream-format=byte-stream, alignment=au, width=3840, height=2160, framerate=30/1' ! \
  h264parse ! \
  queue max-size-buffers=1 max-size-bytes=0 max-size-time=0 ! \
  nvv4l2decoder disable-dpb=true enable-max-performance=1 ! \
  nvvidconv ! \
  'video/x-raw, format=(string)BGR ! appsink drop=1"

cap = cv2.VideoCapture(pipeline, cv2.CAP_GSTREAMER)
if not cap.isOpened():
    print("Error: Could not open webcam")

while True:
    # Read a frame from the pipeline
    ret, frame = cap.read()

    # Check if a frame was successfully read
    if not ret:
        print('Error: Unable to read frame')
        break

    # Display the frame
    cv2.imshow('Frame', frame)

    # Check if the user pressed 'q' to quit
    if cv2.waitKey(1) & 0xFF == ord('q'):
        break
    
cap.release()
cv2.destroyAllWindows()