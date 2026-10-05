import serial
import json
import time

# --------------------------------------------------------------------
# FG25 USB/VCOM
# --------------------------------------------------------------------

SERIAL_PORT = "/dev/ttyACM0"
BAUDRATE = 115200

# --------------------------------------------------------------------
# Wi-SUN destination
# --------------------------------------------------------------------

BR_IPV6 = "fd12:3456::92fd:9fff:feee:9d54"
BR_UDP_PORT = 5000

# Replace this with the socket number returned by:
#     wisun udp_client
SOCKET_ID = 13

SEND_INTERVAL = 5

# --------------------------------------------------------------------
# Open USB/VCOM connection to FG25
# --------------------------------------------------------------------

ser = serial.Serial(
    port=SERIAL_PORT,
    baudrate=BAUDRATE,
    bytesize=serial.EIGHTBITS,
    parity=serial.PARITY_NONE,
    stopbits=serial.STOPBITS_ONE,
    timeout=0.1,
    rtscts=False,
    dsrdtr=False,
    xonxoff=False,
)

print("Connected to FG25:", SERIAL_PORT)


# --------------------------------------------------------------------
# Replace this function with your actual EV charger readings
# --------------------------------------------------------------------

def get_ev_readings():
    """
    Replace these example values with the values calculated/read
    by your existing EV charger software.
    """

    energy_kwh = 12.48
    power_kw = 7.21
    current_a = 31.4
    voltage_v = 229.6
    status = "CHARGING"

    return {
        "energy_kwh": energy_kwh,
        "power_kw": power_kw,
        "current_a": current_a,
        "voltage_v": voltage_v,
        "status": status,
    }


# --------------------------------------------------------------------
# Main loop
# --------------------------------------------------------------------

try:

    while True:

        readings = get_ev_readings()

        # Compact JSON: no spaces/newlines
        payload = json.dumps(
            readings,
            separators=(",", ":")
        )

        # FG25 CLI command
        command = (
            f"wisun socket_write "
            f"{SOCKET_ID} "
            f"{BR_IPV6} "
            f"{BR_UDP_PORT} "
            f"{payload}\r"
        )

        print("Sending:")
        print(payload)

        ser.write(command.encode("utf-8"))
        ser.flush()

        time.sleep(SEND_INTERVAL)

except KeyboardInterrupt:

    print("\nStopping...")

finally:

    ser.close()