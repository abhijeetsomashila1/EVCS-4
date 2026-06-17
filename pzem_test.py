#!/usr/bin/env python3

import os
import queue
import threading
import time
from datetime import datetime

import minimalmodbus
import serial

try:
    import RPi.GPIO as GPIO
except ImportError:
    GPIO = None


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

# Relay control uses BCM GPIO numbering.
# GPIO17 is physical pin 11 on the Raspberry Pi header.
RELAY_PIN_BCM = 17

# Set this to False if your relay module is active-low.
# Many relay boards turn ON when the GPIO output is LOW.
RELAY_ACTIVE_HIGH = True


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


class RelayController:
    def __init__(self, pin_bcm, active_high=True):
        if GPIO is None:
            raise RuntimeError(
                "RPi.GPIO is not installed. Install it with: "
                "sudo apt install -y python3-rpi.gpio"
            )

        self.pin_bcm = pin_bcm
        self.active_high = active_high
        self.is_on = False

        GPIO.setwarnings(False)
        GPIO.setmode(GPIO.BCM)
        GPIO.setup(self.pin_bcm, GPIO.OUT, initial=self._inactive_level())

    def _active_level(self):
        return GPIO.HIGH if self.active_high else GPIO.LOW

    def _inactive_level(self):
        return GPIO.LOW if self.active_high else GPIO.HIGH

    def turn_on(self):
        GPIO.output(self.pin_bcm, self._active_level())
        self.is_on = True

    def turn_off(self):
        GPIO.output(self.pin_bcm, self._inactive_level())
        self.is_on = False

    def toggle(self):
        if self.is_on:
            self.turn_off()
        else:
            self.turn_on()

    def cleanup(self):
        self.turn_off()
        GPIO.cleanup(self.pin_bcm)


def keyboard_listener(command_queue):
    while True:
        try:
            command = input().strip().lower()
        except EOFError:
            break

        if command:
            command_queue.put(command)

        if command in ("q", "quit", "exit"):
            break


def process_relay_commands(relay, command_queue):
    message = None

    while True:
        try:
            command = command_queue.get_nowait()
        except queue.Empty:
            break

        if command in ("t", "toggle"):
            relay.toggle()
            message = "Relay toggled"
        elif command == "on":
            relay.turn_on()
            message = "Relay turned ON"
        elif command == "off":
            relay.turn_off()
            message = "Relay turned OFF"
        elif command in ("q", "quit", "exit"):
            raise KeyboardInterrupt
        else:
            message = f"Unknown command: {command}"

    return message


def print_dashboard(
    relay,
    voltage=None,
    current=None,
    active_power=None,
    error=None,
    command_message=None,
):
    os.system("clear")

    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    relay_state = "ON" if relay.is_on else "OFF"

    print("+--------------------------------------+")
    print("|        PZEM-004T V3.0 Monitor        |")
    print("+--------------------------------------+")
    print(f"| Timestamp    : {timestamp:<20} |")
    print(f"| Relay GPIO17 : {relay_state:<20} |")

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

    print("Commands: t/toggle, on, off, q/quit")
    if command_message:
        print(f"Last command: {command_message}")


def main():
    pzem = create_pzem()
    relay = RelayController(RELAY_PIN_BCM, RELAY_ACTIVE_HIGH)
    command_queue = queue.Queue()
    command_thread = threading.Thread(
        target=keyboard_listener,
        args=(command_queue,),
        daemon=True,
    )
    command_thread.start()
    last_command_message = None

    try:
        while True:
            try:
                last_command_message = (
                    process_relay_commands(relay, command_queue)
                    or last_command_message
                )
                voltage, current, active_power = read_pzem_values(pzem)
                print_dashboard(
                    relay,
                    voltage,
                    current,
                    active_power,
                    command_message=last_command_message,
                )

            except (
                minimalmodbus.NoResponseError,
                minimalmodbus.InvalidResponseError,
                minimalmodbus.IllegalRequestError,
                serial.SerialException,
                OSError,
            ) as exc:
                print_dashboard(
                    relay,
                    error=exc,
                    command_message=last_command_message,
                )

            except KeyboardInterrupt:
                print("\nStopped by user.")
                break

            except Exception as exc:
                print_dashboard(
                    relay,
                    error=f"Unexpected error: {exc}",
                    command_message=last_command_message,
                )

            time.sleep(POLL_INTERVAL_SECONDS)

    finally:
        relay.cleanup()


if __name__ == "__main__":
    main()
