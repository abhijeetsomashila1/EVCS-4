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

# Socket created on FG25 using:
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
# EV charger readings
#
# Short JSON fields:
# v = voltage (V)
# i = current (A)
# p = power (kW)
# e = energy (kWh)
# s = status
#
# Status:
# 0 = IDLE
# 1 = CHARGING
# 2 = FAULT
# 3 = DONE
# --------------------------------------------------------------------

def get_ev_readings():

    voltage_v = 229.6
    current_a = 31.4
    power_kw = 7.21
    energy_kwh = 12.48
    status = 1

    return {
        "v": voltage_v,
        "i": current_a,
        "p": power_kw,
        "e": energy_kwh,
        "s": status,
    }


# --------------------------------------------------------------------
# Main loop
# --------------------------------------------------------------------

try:

    while True:

        readings = get_ev_readings()

        # Compact JSON
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

        print("Sending:", payload)

        ser.write(command.encode("utf-8"))
        ser.flush()

        time.sleep(SEND_INTERVAL)

except KeyboardInterrupt:

    print("\nStopping...")

finally:

    ser.close()