import serial
import time
import sys

# =========================================================
# Wi-SUN HARDWARE TEST SCRIPT (STEP 1 - STEP 6)
# =========================================================
# This script is for you to manually verify the connection 
# between the Pi, the EFR32MG12, and your Border Router.

WISUN_PORT = "/dev/ttyACM1"     # Change this to your EFR32 port
BAUD_RATE = 115200
SERVER_IP = "fd00::1"           # Replace with Border Router/PC IP
SERVER_UDP_PORT = "5000"

try:
    ser = serial.Serial(WISUN_PORT, BAUD_RATE, timeout=1)
    print("\n[STEP 4] SUCCESS: Connected to EFR32MG12 via UART/USB!")
except Exception as e:
    print(f"\n[ERROR] Could not connect to EFR32 on {WISUN_PORT}: {e}")
    sys.exit(1)

def send_cmd(cmd, wait=2):
    print(f"\n>>> Sending to EFR32: {cmd}")
    ser.write((cmd + '\n').encode())
    time.sleep(wait)
    
    # Read the response
    while ser.in_waiting:
        line = ser.readline().decode(errors='ignore').strip()
        if line:
            print(f"    [EFR32 RESPONSE] {line}")

# ---------------------------------------------------------
# STEP 5: Join Wi-SUN Network
# ---------------------------------------------------------
print("\n[STEP 5] Configuring EFR32 as Wi-SUN Node and joining network...")
send_cmd("wisun join_fan11", wait=10)

# ---------------------------------------------------------
# STEP 6: Connect to Border Router
# ---------------------------------------------------------
print("\n[STEP 6] Testing UDP connection to Border Router...")
print(f"We are sending 'EV001 AVAILABLE' to IP: {SERVER_IP} Port: {SERVER_UDP_PORT}")

test_packet = f'wisun udp_client {SERVER_IP} {SERVER_UDP_PORT} "EV001 AVAILABLE"'
send_cmd(test_packet, wait=2)

print("\n=======================================================")
print("TEST COMPLETE.")
print("If you see 'Node Joined Successfully' and no errors, ")
print("your hardware is perfectly ready for the full system!")
print("=======================================================\n")

ser.close()
