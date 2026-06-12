import serial
import time
import threading
import sys

# Import the actual charger script (assuming it is in the same folder)
import Charger_script

# =========================================================
# CONFIGURATION
# =========================================================

WISUN_PORT = "/dev/ttyACM1"     # Change if needed
BAUD_RATE = 115200

# The IPv6 address of your PC (Border Router Backend)
SERVER_IP = "fd00::1" 
SERVER_UDP_PORT = "5000"

# The port this node will listen on for commands from the backend
NODE_LISTEN_PORT = "5001"

# =========================================================
# OPEN SERIAL CONNECTION
# =========================================================

try:
    ser = serial.Serial(WISUN_PORT, BAUD_RATE, timeout=1)
    print("\n[Wi-SUN Bridge] Connected to EFR32MG12")
    time.sleep(2)
except Exception as e:
    print(f"\n[Wi-SUN Bridge] FAILED TO CONNECT TO EFR32: {e}")
    sys.exit(1)

# =========================================================
# HELPER TO SEND AT COMMANDS
# =========================================================

def send_wisun_cmd(cmd, wait=1):
    ser.write((cmd + '\n').encode())
    time.sleep(wait)

# =========================================================
# MOCK SOCKET CLASS FOR CHARGER PROGRESS
# =========================================================
# Charger_script.py expects a socket to send UI updates.
# We will intercept those updates and send them as Wi-SUN UDP packets!

class WiSunUdpSocket:
    def send(self, data):
        # Convert bytes to string, strip whitespace
        msg = data.decode('utf-8').strip()
        safe_message = msg.replace(" ", "_")
        
        # We reuse the UDP server socket (Socket ID 1) that was opened at boot
        # using the socket_writeto command to avoid opening/closing new client sockets.
        wisun_packet_cmd = f'wisun socket_writeto 1 {SERVER_IP} {SERVER_UDP_PORT} {safe_message}'
        send_wisun_cmd(wisun_packet_cmd, wait=0.1)

wisun_sock = WiSunUdpSocket()

# =========================================================
# SERIAL LISTENER THREAD
# =========================================================

def serial_listener():
    """Continuously reads from the EFR32 and parses incoming UDP commands."""
    while True:
        try:
            if ser.in_waiting:
                line = ser.readline().decode(errors='ignore').strip()
                if not line:
                    continue
                
                print(f"[EFR32] {line}")
                
                # Check if it's an incoming UDP message containing a command
                # The exact format depends on Silicon Labs firmware, but usually
                # it prints something like: [rx] START
                
                if "START" in line.upper():
                    print("\n[Wi-SUN Bridge] Received START command from Cloud!")
                    
                    # You could parse the exact units from the packet, 
                    # but for this prototype we will default to 0.1 units (100 Wh)
                    target_amount = 0.1 
                    
                    # Launch charging session in background
                    t = threading.Thread(
                        target=Charger_script.Charger,
                        kwargs={
                            "Rfid_valid": True,
                            "amount": target_amount,
                            "arduino_socket_q": [],
                            "arduino_socks": wisun_sock
                        }
                    )
                    t.daemon = True
                    t.start()
                    
                elif "STOP" in line.upper():
                    print("\n[Wi-SUN Bridge] Received STOP command from Cloud!")
                    # In a full implementation, you would add a stop flag in Charger_script
                    pass
                
        except Exception as e:
            print(f"[serial_listener] error: {e}")
            time.sleep(1)

# =========================================================
# MAIN INITIALIZATION
# =========================================================

if __name__ == "__main__":
    print("\n[Wi-SUN Bridge] Initializing Wi-SUN Network...")
    
    # 1. Start the serial listener so we can see all responses
    listener_thread = threading.Thread(target=serial_listener)
    listener_thread.daemon = True
    listener_thread.start()

    # 2. Join the Wi-SUN Network
    send_wisun_cmd("wisun join_fan11", wait=5)
    
    # 3. Open a UDP server to listen for commands from the backend
    send_wisun_cmd(f"wisun udp_server {NODE_LISTEN_PORT}", wait=2)
    
    print("\n[Wi-SUN Bridge] Ready and waiting for commands!")
    
    # Keep main thread alive
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nExiting...")
        ser.close()
