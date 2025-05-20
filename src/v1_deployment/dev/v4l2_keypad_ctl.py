#                    pan_absolute 0x009a0908 (int)    : min=-612000 max=612000 step=1 default=0 value=21200
#                   tilt_absolute 0x009a0909 (int)    : min=-108000 max=324000 step=1 default=0 value=0
#                   zoom_absolute 0x009a090d (int)    : min=0 max=6368 step=1 default=0 value=0




import time 
import subprocess 
from pynput import keyboard
from pynput.keyboard import Key

pan_value = 0
tilt_value = 0
zoom_value = 0
pan_increment = 2500
tilt_increment = 2500
zoom_increment = 100

def on_key_release(key):
    global pan_value
    global tilt_value
    global zoom_value

    if key == Key.right:
        pan_value = pan_value + pan_increment
        print(pan_value)
        args = ["v4l2-ctl", "--set-ctrl=pan_absolute=" + str(pan_value)]
        ans = subprocess.call(args)
    elif key == Key.left:
        pan_value = pan_value - pan_increment
        print(pan_value)
        args = ["v4l2-ctl", "--set-ctrl=pan_absolute=" + str(pan_value)]
        ans = subprocess.call(args)
    elif key == Key.up:
        tilt_value = tilt_value + tilt_increment
        print(tilt_value)
        args = ["v4l2-ctl", "--set-ctrl=tilt_absolute=" + str(tilt_value)]
        ans = subprocess.call(args)
    elif key == Key.down:
        tilt_value = tilt_value - tilt_increment
        print(tilt_value)
        args = ["v4l2-ctl", "--set-ctrl=tilt_absolute=" + str(tilt_value)]
        ans = subprocess.call(args)
    elif key == Key.page_up:
        zoom_value = zoom_value + zoom_increment
        print(zoom_value)
        args = ["v4l2-ctl", "--set-ctrl=zoom_absolute=" + str(zoom_value)]
        ans = subprocess.call(args)
    elif key == Key.page_down:
        zoom_value = zoom_value - zoom_increment
        print(zoom_value)
        args = ["v4l2-ctl", "--set-ctrl=zoom_absolute=" + str(zoom_value)]
        ans = subprocess.call(args)
    elif key == Key.esc:
        exit()

args = ["v4l2-ctl", "--set-ctrl=pan_absolute=" + str(pan_value)]
ans = subprocess.call(args)
args = ["v4l2-ctl", "--set-ctrl=tilt_absolute=" + str(tilt_value)]
ans = subprocess.call(args)
args = ["v4l2-ctl", "--set-ctrl=zoom_absolute=" + str(zoom_value)]
ans = subprocess.call(args)


with keyboard.Listener(on_release=on_key_release) as listener:
    listener.join() 


