#!/usr/bin/env python3
"""
VISCA Acceleration Profile Test
Tests how camera movement changes with duration to understand acceleration
"""

import socket
import time

class VISCAAccelerationTester:
    def __init__(self, camera_ip="192.168.100.88", camera_port=5678):
        self.camera_ip = camera_ip
        self.camera_port = camera_port
        self.socket = None
        self.connected = False
        self.manual_speed = 0x10  # Medium speed
        self.connect()
        
    def connect(self):
        """Connect to VISCA camera"""
        try:
            self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.socket.settimeout(3.0)
            self.socket.connect((self.camera_ip, self.camera_port))
            self.connected = True
            print(f"✓ Connected to VISCA camera at {self.camera_ip}:{self.camera_port}")
            return True
        except Exception as e:
            print(f"✗ Connection failed: {e}")
            return False
    
    def send_visca_command(self, cmd, description=""):
        """Send VISCA command"""
        if not self.connected:
            return False
        try:
            self.socket.send(bytes(cmd))
            if description:
                print(f"SENT: {description}")
            return True
        except Exception as e:
            print(f"Command failed: {e}")
            return False
    
    def send_visca_inquiry(self, cmd):
        """Send VISCA inquiry and return response"""
        if not self.connected:
            return None
        try:
            # Clear buffer first
            self.socket.settimeout(0.1)
            try:
                while True:
                    self.socket.recv(1024)
            except:
                pass
            
            # Send inquiry
            self.socket.settimeout(3.0)
            self.socket.send(bytes(cmd))
            response = self.socket.recv(11)
            return response
        except Exception as e:
            print(f"Inquiry failed: {e}")
            return None
    
    def parse_pan_tilt_response(self, response):
        """Parse VISCA pan/tilt position response"""
        if not response or len(response) < 11:
            return None, None
            
        if response[0] != 0x90 or response[1] != 0x50:
            return None, None
            
        try:
            # Extract pan position
            pan_bytes = response[2:6]
            pan = (pan_bytes[0] << 12) | (pan_bytes[1] << 8) | (pan_bytes[2] << 4) | pan_bytes[3]
            
            # Extract tilt position
            tilt_bytes = response[6:10]
            tilt = (tilt_bytes[0] << 12) | (tilt_bytes[1] << 8) | (tilt_bytes[2] << 4) | tilt_bytes[3]
            
            # Convert to signed
            if pan > 32767:
                pan -= 65536
            if tilt > 32767:
                tilt -= 65536
                
            return pan, tilt
        except:
            return None, None
    
    def get_position(self):
        """Get current pan/tilt position"""
        response = self.send_visca_inquiry([0x81, 0x09, 0x06, 0x12, 0xFF])
        if response:
            return self.parse_pan_tilt_response(response)
        return None, None
    
    def go_home(self):
        """Move to home position"""
        print("Moving to HOME...")
        cmd = [0x81, 0x01, 0x06, 0x04, 0xFF]
        self.send_visca_command(cmd, "HOME")
        time.sleep(3.0)  # Wait for home movement
    
    def stop_movement(self):
        """Stop all movement"""
        cmd = [0x81, 0x01, 0x06, 0x01, self.manual_speed, self.manual_speed, 0x03, 0x03, 0xFF]
        self.send_visca_command(cmd, "STOP")
    
    def test_pan_acceleration_profile(self, direction="right"):
        """Test how pan movement changes with duration"""
        print(f"\n{'='*60}")
        print(f"TESTING PAN {direction.upper()} ACCELERATION PROFILE")
        print(f"{'='*60}")
        
        # Test different durations
        durations = [0.1, 0.2, 0.3, 0.5, 0.8, 1.0, 1.5, 2.0, 3.0, 5.0]
        results = []
        
        # Direction command
        if direction == "right":
            cmd = [0x81, 0x01, 0x06, 0x01, self.manual_speed, self.manual_speed, 0x02, 0x03, 0xFF]
        else:  # left
            cmd = [0x81, 0x01, 0x06, 0x01, self.manual_speed, self.manual_speed, 0x01, 0x03, 0xFF]
        
        for duration in durations:
            # Go home first
            self.go_home()
            time.sleep(0.5)
            
            # Get starting position
            start_pan, start_tilt = self.get_position()
            if start_pan is None:
                print(f"Failed to get starting position for {duration}s test")
                continue
            
            print(f"\nTesting {duration}s movement...")
            print(f"  Start position: Pan={start_pan}")
            
            # Start movement
            self.send_visca_command(cmd, f"Pan {direction} for {duration}s")
            
            # Let it move for specified duration
            time.sleep(duration)
            
            # Stop movement
            self.stop_movement()
            time.sleep(0.2)  # Brief pause for camera to settle
            
            # Get ending position
            end_pan, end_tilt = self.get_position()
            if end_pan is None:
                print(f"  Failed to get ending position")
                continue
            
            # Calculate movement
            movement = end_pan - start_pan
            if direction == "left":
                movement = -movement  # Make positive for easier reading
            
            # Calculate rate
            rate = movement / duration if duration > 0 else 0
            
            print(f"  End position: Pan={end_pan}")
            print(f"  Total movement: {movement} units")
            print(f"  Rate: {rate:.1f} units/second")
            
            results.append({
                'duration': duration,
                'movement': movement,
                'rate': rate,
                'start_pan': start_pan,
                'end_pan': end_pan
            })
        
        # Analysis
        print(f"\n{'='*60}")
        print(f"PAN {direction.upper()} ACCELERATION ANALYSIS")
        print(f"{'='*60}")
        print(f"Duration  Movement   Rate(u/s)  Notes")
        print(f"--------  --------   ---------  -----")
        
        max_rate = 0
        for i, result in enumerate(results):
            d = result['duration']
            m = result['movement']
            r = result['rate']
            
            # Determine acceleration phase
            if i == 0:
                phase = "Starting"
            elif r > max_rate * 0.9:
                phase = "Max speed"
                max_rate = max(max_rate, r)
            elif r > results[0]['rate'] * 2:
                phase = "Accelerating"
            else:
                phase = "Slow start"
            
            print(f"{d:6.1f}s   {m:6.0f}     {r:7.1f}    {phase}")
            max_rate = max(max_rate, r)
        
        print(f"\nMax rate achieved: {max_rate:.1f} units/second")
        
        # Calculate when camera reaches ~90% of max speed
        target_rate = max_rate * 0.9
        accel_time = None
        for result in results:
            if result['rate'] >= target_rate:
                accel_time = result['duration']
                break
        
        if accel_time:
            print(f"Time to reach 90% max speed: ~{accel_time:.1f} seconds")
        
        return results
    
    def test_different_speeds(self):
        """Test acceleration at different VISCA speeds"""
        print(f"\n{'='*60}")
        print("TESTING DIFFERENT VISCA SPEEDS")
        print(f"{'='*60}")
        
        speeds = [0x05, 0x0A, 0x10, 0x15, 0x18]  # Slow to fast
        speed_names = ["Very Slow", "Slow", "Medium", "Fast", "Max"]
        
        results = []
        test_duration = 2.0  # 2 seconds for each speed test
        
        for speed, name in zip(speeds, speed_names):
            print(f"\nTesting {name} (0x{speed:02X})...")
            
            # Update speed
            old_speed = self.manual_speed
            self.manual_speed = speed
            
            # Go home
            self.go_home()
            time.sleep(0.5)
            
            # Get start position
            start_pan, _ = self.get_position()
            if start_pan is None:
                continue
            
            # Move right for test duration
            cmd = [0x81, 0x01, 0x06, 0x01, speed, speed, 0x02, 0x03, 0xFF]
            self.send_visca_command(cmd, f"{name} pan right")
            time.sleep(test_duration)
            self.stop_movement()
            time.sleep(0.2)
            
            # Get end position
            end_pan, _ = self.get_position()
            if end_pan is None:
                continue
            
            movement = end_pan - start_pan
            rate = movement / test_duration
            
            print(f"  Movement: {movement} units in {test_duration}s")
            print(f"  Rate: {rate:.1f} units/second")
            
            results.append({
                'speed_hex': speed,
                'speed_name': name,
                'movement': movement,
                'rate': rate
            })
            
            # Restore original speed
            self.manual_speed = old_speed
        
        # Summary
        print(f"\n{'='*40}")
        print("SPEED COMPARISON")
        print(f"{'='*40}")
        print(f"Speed      Rate(u/s)   Movement")
        print(f"---------  ---------   --------")
        for result in results:
            print(f"{result['speed_name']:9s}  {result['rate']:7.1f}     {result['movement']:6.0f}")
        
        return results
    
    def run_comprehensive_acceleration_test(self):
        """Run complete acceleration profile test"""
        if not self.connected:
            print("Not connected to camera!")
            return
        
        print("VISCA ACCELERATION PROFILE TESTING")
        print("This will test how camera movement changes with duration")
        print("to understand acceleration characteristics.\n")
        
        # Test pan right acceleration
        pan_right_results = self.test_pan_acceleration_profile("right")
        
        # Test different speeds
        speed_results = self.test_different_speeds()
        
        # Final summary
        print(f"\n{'='*60}")
        print("FINAL ANALYSIS FOR PID CONTROL")
        print(f"{'='*60}")
        
        if pan_right_results:
            # Find minimum effective duration
            min_effective = None
            for result in pan_right_results:
                if result['movement'] >= 10:  # At least 10 units of movement
                    min_effective = result['duration']
                    break
            
            if min_effective:
                print(f"Minimum effective movement duration: {min_effective}s")
                print(f"Recommendation: Use movement durations >= {min_effective}s")
            
            # Find when acceleration stops
            max_rate = max(r['rate'] for r in pan_right_results)
            steady_state = None
            for result in pan_right_results:
                if result['rate'] >= max_rate * 0.95:
                    steady_state = result['duration']
                    break
            
            if steady_state:
                print(f"Camera reaches steady-state speed at: ~{steady_state}s")
        
        print(f"\nFor your PID system:")
        print(f"1. Camera has significant acceleration time")
        print(f"2. Very short movements (< 0.5s) are ineffective")
        print(f"3. Consider using longer movement pulses or continuous movement")
        print(f"4. Position feedback should account for acceleration delay")
    
    def disconnect(self):
        """Disconnect from camera"""
        if self.socket:
            self.stop_movement()
            time.sleep(0.1)
            self.socket.close()
            self.connected = False
            print("Disconnected from camera")

def main():
    print("VISCA Acceleration Profile Tester")
    print("Tests camera movement characteristics vs duration")
    
    tester = VISCAAccelerationTester()
    
    if not tester.connected:
        return
    
    try:
        tester.run_comprehensive_acceleration_test()
    except KeyboardInterrupt:
        print("\nTest interrupted")
    finally:
        tester.disconnect()

if __name__ == "__main__":
    main()