import socket 
import threading 
import time 
import socket


class VISCAController:
    def __init__(self, ip="192.168.100.88", tcp_port=5678, udp_port=1259, timeout=2, protocol="tcp", verbose = False):
        """Initialize camera controller with connection parameters."""
        self.ip = ip
        self.timeout = timeout
        self.protocol = protocol
        self.tcp_port = tcp_port
        self.udp_port = udp_port
        self.socket = None
        self.verbose = verbose

    def _log(self, message):
        if self.verbose:
            print(f"[VISCA] {message}")
    
    def connect(self):
        if not hasattr(self, 'socket') or not self.socket:
            self.socket = self.create_socket()
        return self.socket      

    def dec_to_signed_hex(self, val, bits=16):
        return hex((val + (1 << bits)) % (1 << bits))[2:].upper().zfill(bits // 4)
    
    def _unsigned_to_signed(self, val, bits=16):
        """Convert camera's unsigned response to signed position"""
        if val >= (1 << (bits - 1)):
            return val - (1 << bits)
        return val

    def create_socket(self):
        """single responsibility - to create the socket rather than storing it"""
        if self.protocol == "tcp":
            s1 = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s1.connect((self.ip, self.tcp_port))
        elif self.protocol == "udp":
            s1 = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s1.settimeout(self.timeout)
        self._log(f"Connected to {self.ip} on port {self.tcp_port if self.protocol == 'tcp' else self.udp_port}")
        return s1
    
    def send_command(self, cmd):
        if not hasattr(self, 'socket') or not self.socket:
            self.connect() 
        if self.protocol == "tcp":
            self.socket.send(bytes.fromhex(cmd))
        elif self.protocol == "udp":
            self.socket.sendto(bytes.fromhex(cmd), (self.ip, self.udp_port))
        self._log(f"Sent command: {cmd}")


    def build_pan_tilt_command(self, y_pan_position, z_tilt_position, v_pan_speed="18", w_tilt_speed="18"):
        y_pan_hex_position = self.dec_to_signed_hex(y_pan_position)
        z_tilt_hex_position = self.dec_to_signed_hex(z_tilt_position)
        v1, v2 = v_pan_speed[0], v_pan_speed[1]
        w1, w2 = w_tilt_speed[0], w_tilt_speed[1]
        y1, y2, y3, y4 = y_pan_hex_position[0], y_pan_hex_position[1], y_pan_hex_position[2], y_pan_hex_position[3]
        z1, z2, z3, z4 = z_tilt_hex_position[0], z_tilt_hex_position[1], z_tilt_hex_position[2], z_tilt_hex_position[3]
        cmd = f"81010602{v1}{v2}{w1}{w2}0{y1}0{y2}0{y3}0{y4}0{z1}0{z2}0{z3}0{z4}FF"
        return cmd
    
    def query_pan_tilt_position(self):
        if not hasattr(self, 'socket') or not self.socket:
            self.connect()
        cmd = "81090612FF"
        self.send_command(cmd)
        if self.protocol == "tcp":
            response = self.socket.recv(32).hex()
        elif self.protocol == "udp":    
            response, addr = self.socket.recvfrom(32)
            response = response.hex()
        self._log(f"Received pan/tilt response: {response}")
        
        try:
            pan_nibbles = response[4:12]
            pan_unsigned = int(pan_nibbles[1] + pan_nibbles[3] + pan_nibbles[5] + pan_nibbles[7], 16)
            pan = self._unsigned_to_signed(pan_unsigned)

            tilt_nibbles = response[12:20]
            tilt_unsigned = int(tilt_nibbles[1] + tilt_nibbles[3] + tilt_nibbles[5] + tilt_nibbles[7], 16)
            tilt = self._unsigned_to_signed(tilt_unsigned)
            self._log(f"Pan: {pan}, Tilt: {tilt}")
            return pan, tilt
        except Exception as e:
            self._log(f"Error parsing pan/tilt response: {e}")
            return None, None


def main():
    protocol = input("Enter protocol (tcp/udp): ").strip().lower()
    if protocol not in ["tcp", "udp"]:
        print("Invalid protocol. Please enter 'tcp' or 'udp'.")
        return
    verbose = input("Enable verbose logging? (yes/no): ").strip().lower() == "yes"
    controller = VISCAController(protocol=protocol, verbose=verbose)

    controller.connect()
    while True:
        pan, tilt = controller.query_pan_tilt_position()
        print(pan,tilt)
        controller.send_command(controller.build_pan_tilt_command(y_pan_position=int(input("Enter Y Pan Position (decimal): ")),
                                                                z_tilt_position=int(input("Enter Z Tilt Position (decimal): "))))
        # if controller.protocol == "tcp":
        #     response = controller.socket.recv(32).hex()
        # elif controller.protocol == "udp":    
        #     response, addr = controller.socket.recvfrom(32)
        #     response = response.hex()
        # controller._log(f"Received pan/tilt response: {response}")
        # print("main 1")




    # y_pan_position = int(input("Enter Y Pan Position (decimal): "))
    # z_tilt_position = int(input("Enter Z Tilt Position (decimal): "))
    # v_pan_speed = input("Enter V Pan Speed (2 digits, e.g., '18'): ")
    # w_tilt_speed = input("Enter W Tilt Speed (2 digits, e.g., '18'): ")
    # cmd = controller.build_pan_tilt_command(y_pan_position, z_tilt_position, v_pan_speed, w_tilt_speed)
    # controller.send_command(cmd)

if __name__ == "__main__":
    main()

