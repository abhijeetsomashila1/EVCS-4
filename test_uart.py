import serial
import time

print("Starting UART Test Script for WSTK...")
try:
    ser = serial.Serial('/dev/ttyACM0', 115200, timeout=1)
    print("Successfully connected to /dev/ttyACM0")
except Exception as e:
    print(f"Error opening serial port: {e}")
    exit(1)

while True:
    csv_string = "V:230.5,A:10.25,W:2362.6,Wh:15.0\n"
    print(f"Sending: {csv_string.strip()}")
    try:
        ser.write(csv_string.encode())
    except Exception as e:
        print(f"Failed to write: {e}")
    time.sleep(5)  # send every 5 seconds
