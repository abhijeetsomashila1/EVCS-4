import serial
import time
import sys

# =========================================================
# EFR32 INTERACTIVE COMMAND SENDER
# =========================================================
# Run this on your Raspberry Pi to test sending specific 
# commands from the EFR32 node through the Wi-SUN network.

WISUN_PORT = "/dev/ttyACM1"     # Change this to your EFR32 port
BAUD_RATE = 115200

# The IP of the PC/Border Router receiving these commands
SERVER_IP = "fd00::1"           
SERVER_UDP_PORT = "5000"

try:
    ser = serial.Serial(WISUN_PORT, BAUD_RATE, timeout=1)
    print("\n[SUCCESS] Connected to EFR32MG12 via UART!")
except Exception as e:
    print(f"\n[ERROR] Could not connect to EFR32 on {WISUN_PORT}: {e}")
    sys.exit(1)

def send_wisun_packet(message):
    """Wraps the message in the Wi-SUN UDP Client command and sends it to EFR32"""
    safe_message = message.replace(" ", "_")
    
    # 1. Open the UDP Socket
    cmd_open = f'wisun udp_client {SERVER_IP} {SERVER_UDP_PORT}'
    ser.write((cmd_open + '\n').encode())
    time.sleep(0.5)
    
    sock_id = "1" # Default fallback
    while ser.in_waiting:
        line = ser.readline().decode(errors='ignore').strip()
        print(f"    [EFR32] {line}")
        if "[Opened:" in line:
            # Parse "[Opened: 1]"
            sock_id = line.split(":")[1].strip(" ]")
    
    # 2. Write to the specific Socket ID
    cmd_write = f'wisun socket_write {sock_id} {safe_message}'
    print(f"\n>>> Transmitting: '{safe_message}' on Socket {sock_id}")
    ser.write((cmd_write + '\n').encode())
    time.sleep(0.5)
    
    while ser.in_waiting:
        line = ser.readline().decode(errors='ignore').strip()
        if line:
            print(f"    [EFR32] {line}")
            
    # 3. Close the socket to prevent leaks
    cmd_close = f'wisun socket_close {sock_id}'
    ser.write((cmd_close + '\n').encode())
    time.sleep(0.2)

def main_menu():
    print("\n=========================================")
    print("      Wi-SUN COMMAND TESTER MENU")
    print("=========================================")
    print("1. Send 'Start Scan'")
    print("2. Send 'Stop Scan'")
    print("3. Send 'Relay ON'")
    print("4. Send 'Relay OFF'")
    print("5. Send RAW CLI Command (e.g., 'help')")
    print("6. Exit")
    print("=========================================")
    
    choice = input("Select an option (1-6): ")
    
    if choice == '1':
        send_wisun_packet("Start_Scan")
    elif choice == '2':
        send_wisun_packet("Stop_Scan")
    elif choice == '3':
        send_wisun_packet("Relay_ON")
    elif choice == '4':
        send_wisun_packet("Relay_OFF")
    elif choice == '5':
        custom = input("Enter RAW command: ")
        print(f"\n>>> Sending RAW: {custom}")
        ser.write((custom + '\n').encode())
        time.sleep(1)
        while ser.in_waiting:
            line = ser.readline().decode(errors='ignore').strip()
            if line:
                print(f"    [EFR32] {line}")
    elif choice == '6':
        print("Exiting...")
        ser.close()
        sys.exit(0)
    else:
        print("Invalid choice. Try again.")

if __name__ == "__main__":
    # Optional: You can add `send_wisun_packet("wisun join_fan11")` here 
    # if the board isn't already joined to the network.
    
    while True:
        main_menu()
        time.sleep(0.5)
