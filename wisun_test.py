import serial
import time

PORT = "/dev/serial/by-id/usb-Silicon_Labs_J-Link_Pro_OB_A3AE_000440288199-if00"

ser = serial.Serial(
    port=PORT,
    baudrate=115200,
    bytesize=serial.EIGHTBITS,
    parity=serial.PARITY_NONE,
    stopbits=serial.STOPBITS_ONE,
    timeout=0.5,
)

print("Connected to FG25 VCOM")

# Give the port a moment to settle
time.sleep(1)

# Send an existing FG25 CLI command
command = "wisun udp_client\r\n"

print("Sending:", command.strip())

ser.write(command.encode("ascii"))
ser.flush()

# Read FG25 response for a few seconds
end_time = time.time() + 3

while time.time() < end_time:
    data = ser.readline()

    if data:
        print("FG25:", data.decode("utf-8", errors="replace").rstrip())

ser.close()
print("Done")