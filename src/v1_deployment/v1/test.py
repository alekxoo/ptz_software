#!/usr/bin/env python3
"""
PTZ Wiggle Test - Visual Movement Verification
Just wiggles the camera left/right at different frequencies so you can SEE if it's actually moving

Usage: python ptz_wiggle_test.py
"""

import time
import subprocess
import signal
import sys

class PTZWiggleTest:
    def __init__(self):
        # Camera limits (adjust to your camera)
        self.CENTER_PAN = 0
        self.WIGGLE_AMOUNT = 10000  # How far left/right to wiggle
    
        # Test frequencies to try
        self.test_frequencies = [10, 20, 30, 50, 75, 100, 150, 200, 300, 500]
        
        # Position states
        self.left_position = self.CENTER_PAN - self.WIGGLE_AMOUNT
        self.right_position = self.CENTER_PAN + self.WIGGLE_AMOUNT
        
    def send_pan_command(self, position):
        """Send pan command quickly"""
        try:
            subprocess.run(
                ["v4l2-ctl", f"--set-ctrl=pan_absolute={position}"], 
                capture_output=True, 
                timeout=0.1
            )
            return True
        except:
            return False
    
    def wiggle_at_frequency(self, frequency_hz, duration=5.0):
        """
        Wiggle camera left/right at specified frequency
        
        Args:
            frequency_hz: How many times per second to change direction
            duration: How long to wiggle for
        """
        print(f"\n🔄 WIGGLE TEST: {frequency_hz} Hz for {duration} seconds")
        print(f"   Should change direction {frequency_hz} times per second")
        print(f"   Watch the camera - does it wiggle {frequency_hz} times per second?")
        
        interval = 1.0 / frequency_hz  # Time between direction changes
        total_changes = int(frequency_hz * duration)
        
        print("   Starting in 2 seconds... GET READY TO WATCH!")
        time.sleep(2)
        
        print(f"   🟢 WIGGLING NOW at {frequency_hz} Hz!")
        
        start_time = time.time()
        position_state = False  # False = left, True = right
        
        for i in range(total_changes):
            # Alternate between left and right
            if position_state:
                self.send_pan_command(self.right_position)
                print("→", end="", flush=True)
            else:
                self.send_pan_command(self.left_position)
                print("←", end="", flush=True)
            
            position_state = not position_state
            
            # Sleep until next change
            target_time = start_time + (i + 1) * interval
            current_time = time.time()
            sleep_time = target_time - current_time
            
            if sleep_time > 0:
                time.sleep(sleep_time)
        
        print(f"\n   ✅ Sent {total_changes} direction changes in {time.time() - start_time:.2f}s")
        
        # Return to center
        self.send_pan_command(self.CENTER_PAN)
        print("   📍 Returned to center")
    
    def run_visual_test(self):
        """Run the complete visual wiggle test"""
        print("PTZ Visual Wiggle Test")
        print("=" * 50)
        print("This test will wiggle your camera left/right at different speeds.")
        print("WATCH THE CAMERA and see if it actually moves at the claimed frequency!")
        print()
        print("🎯 What to look for:")
        print("   • Low frequencies (10-30 Hz): Should see clear back-and-forth motion")
        print("   • Medium frequencies (50-100 Hz): Should see rapid wiggling")  
        print("   • High frequencies (200+ Hz): May not wiggle if camera can't keep up")
        print()
        
        response = input("Ready to start wiggle test? (y/N): ")
        if response.lower() != 'y':
            print("Test cancelled.")
            return
        
        # Center the camera first
        print("\n📍 Centering camera...")
        self.send_pan_command(self.CENTER_PAN)
        time.sleep(1)
        
        # Run tests at each frequency
        for freq in self.test_frequencies:
            try:
                self.wiggle_at_frequency(freq, duration=3.0)
                
                # Ask user what they observed
                print(f"\n❓ What did you see at {freq} Hz?")
                print("   1 = Smooth wiggling at expected speed")
                print("   2 = Some wiggling but slower than expected") 
                print("   3 = Barely moving or not moving")
                print("   4 = Skip/next")
                
                while True:
                    try:
                        observation = input(f"   Your observation for {freq} Hz (1-4): ").strip()
                        if observation in ['1', '2', '3', '4']:
                            break
                        print("   Please enter 1, 2, 3, or 4")
                    except KeyboardInterrupt:
                        return
                
                # Record result
                if observation == '1':
                    print(f"   ✅ {freq} Hz: WORKS - Camera keeping up")
                elif observation == '2':
                    print(f"   ⚠️  {freq} Hz: PARTIAL - Camera struggling")
                elif observation == '3':
                    print(f"   ❌ {freq} Hz: FAILED - Camera can't keep up")
                elif observation == '4':
                    print(f"   ⏭️  {freq} Hz: SKIPPED")
                
                time.sleep(1)  # Brief pause before next test
                
            except KeyboardInterrupt:
                print("\n\nTest interrupted by user.")
                break
        
        # Final center
        print("\n📍 Returning to center position...")
        self.send_pan_command(self.CENTER_PAN)
        
        print("\n🎯 VISUAL TEST COMPLETE!")
        print("Based on what you observed, you now know your camera's real limits!")
    
    def quick_wiggle_demo(self, frequency=50):
        """Quick demo wiggle"""
        print(f"Quick wiggle demo at {frequency} Hz for 2 seconds...")
        self.wiggle_at_frequency(frequency, 2.0)

def signal_handler(sig, frame):
    print("\n\nTest interrupted - centering camera...")
    # Try to center camera before exit
    try:
        subprocess.run(["v4l2-ctl", "--set-ctrl=pan_absolute=0"], timeout=1)
    except:
        pass
    sys.exit(0)

def main():
    signal.signal(signal.SIGINT, signal_handler)
    
    print("PTZ Wiggle Test")
    print("This will wiggle your camera to visually test frequency limits.")
    print("Make sure your camera is in a safe position!")
    
    tester = PTZWiggleTest()
    
    print("\nOptions:")
    print("1 = Full test (all frequencies)")
    print("2 = Quick demo (50 Hz)")
    print("3 = Custom frequency")
    
    choice = input("Choose option (1-3): ").strip()
    
    try:
        if choice == '1':
            tester.run_visual_test()
        elif choice == '2':
            tester.quick_wiggle_demo()
        elif choice == '3':
            freq = int(input("Enter frequency (Hz): "))
            duration = float(input("Enter duration (seconds): ") or "3")
            tester.wiggle_at_frequency(freq, duration)
        else:
            print("Invalid choice")
            
    except KeyboardInterrupt:
        signal_handler(None, None)
    except Exception as e:
        print(f"Error: {e}")
        # Try to center camera
        try:
            subprocess.run(["v4l2-ctl", "--set-ctrl=pan_absolute=0"], timeout=1)
        except:
            pass

if __name__ == "__main__":
    main()