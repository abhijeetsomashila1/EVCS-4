#!/usr/bin/env python3

import os
import time
from datetime import datetime

import minimalmodbus
import serial


# Change this if your USB-to-TTL adapter appears as another port.
# Common options:
#   /dev/ttyUSB0
#   /dev/ttyUSB1
#   /dev/ttyAMA0
# Check available serial ports with:
#   ls /dev/ttyUSB* /dev/ttyAMA*
SERIAL_PORT = "/dev/ttyUSB0"

# Default Modbus slave address for many PZEM-004T V3.0 modules.
SLAVE_ADDRESS = 1

POLL_INTERVAL_SECONDS = 2


def create_pzem():
    instrument = minimalmodbus.Instrument(SERIAL_PORT, SLAVE_ADDRESS)
    instrument.serial.baudrate = 9600
    instrument.serial.bytesize = 8
    instrument.serial.parity = serial.PARITY_NONE
    instrument.serial.stopbits = 1
    instrument.serial.timeout = 1.5
    instrument.mode = minimalmodbus.MODE_RTU
    instrument.clear_buffers_before_each_transaction = True
    return instrument


def read_pzem_values(instrument):
    # PZEM-004T V3.0 input registers:
    # 0x0000 voltage, scale 0.1 V
    # 0x0001-0x0002 current, scale 0.001 A
    # 0x0003-0x0004 active power, scale 0.1 W
    registers = instrument.read_registers(
        registeraddress=0x0000,
        number_of_registers=5,
        functioncode=4,
    )

    voltage = registers[0] / 10.0

    raw_current = registers[1] | (registers[2] << 16)
    current = raw_current / 1000.0

    raw_power = registers[3] | (registers[4] << 16)
    active_power = raw_power / 10.0

    return voltage, current, active_power


def print_dashboard(voltage=None, current=None, active_power=None, error=None):
    os.system("clear")

    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    print("+--------------------------------------+")
    print("|        PZEM-004T V3.0 Monitor        |")
    print("+--------------------------------------+")
    print(f"| Timestamp    : {timestamp:<20} |")

    if error:
        print("| Status       : Read Error/Timeout    |")
        print("+--------------------------------------+")
        print(f"Warning: {error}")
    else:
        print("| Status       : OK                    |")
        print(f"| Voltage      : {voltage:>10.2f} V           |")
        print(f"| Current      : {current:>10.3f} A           |")
        print(f"| Active Power : {active_power:>10.2f} W           |")
        print("+--------------------------------------+")


def main():
    pzem = create_pzem()

    while True:
        try:
            voltage, current, active_power = read_pzem_values(pzem)
            print_dashboard(voltage, current, active_power)

        except (
            minimalmodbus.NoResponseError,
            minimalmodbus.InvalidResponseError,
            minimalmodbus.IllegalRequestError,
            serial.SerialException,
            OSError,
        ) as exc:
            print_dashboard(error=exc)

        except KeyboardInterrupt:
            print("\nStopped by user.")
            break

        except Exception as exc:
            print_dashboard(error=f"Unexpected error: {exc}")

        time.sleep(POLL_INTERVAL_SECONDS)


if __name__ == "__main__":
    main()
