#!/usr/bin/env python3

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

POLL_INTERVAL_SECONDS = 2.0

# Relay control uses BCM GPIO numbering.
# GPIO17 is physical pin 11 on the Raspberry Pi header.
RELAY_PIN_BCM = 17

# SSR-25DA input turns ON when GPIO17 is HIGH.
RELAY_ACTIVE_HIGH = True

# Dummy capacity used only for prototype testing.
MOCK_BATTERY_CAPACITY_WH = 100.0


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
    """Return voltage, current, active_power.

    Replace this function with your existing PZEM-004T read function if needed.
    The rest of the loop expects values in volts, amps, and watts.
    """
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

    def cleanup(self):
        self.turn_off()
        GPIO.cleanup(self.pin_bcm)


print_lock = threading.Lock()


def safe_print(message):
    with print_lock:
        print(message, flush=True)


def command_listener(command_queue):
    while True:
        try:
            command = input("Command [on/off/q]: ").strip().lower()
        except EOFError:
            command_queue.put("q")
            break

        if command:
            command_queue.put(command)

        if command in ("q", "quit", "exit"):
            break


def charging_telemetry_loop(pzem, relay, stop_event):
    energy_consumed_wh = 0.0
    last_sample_time = time.monotonic()

    safe_print("Charging started: relay GPIO17 HIGH")

    while not stop_event.is_set():
        try:
            voltage, current, active_power = read_pzem_values(pzem)

            now = time.monotonic()
            elapsed_hours = (now - last_sample_time) / 3600.0
            last_sample_time = now

            energy_consumed_wh += max(active_power, 0.0) * elapsed_hours
            charge_percent = min(
                (energy_consumed_wh / MOCK_BATTERY_CAPACITY_WH) * 100.0,
                100.0,
            )

            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            safe_print(
                f"[{timestamp}] "
                f"V={voltage:7.2f} V | "
                f"I={current:7.3f} A | "
                f"P={active_power:8.2f} W | "
                f"Energy={energy_consumed_wh:7.3f} Wh | "
                f"Charge={charge_percent:6.2f}%"
            )

            if charge_percent >= 100.0:
                safe_print("Simulated charge reached 100%. Turning relay OFF.")
                relay.turn_off()
                stop_event.set()
                break

        except (
            minimalmodbus.NoResponseError,
            minimalmodbus.InvalidResponseError,
            minimalmodbus.IllegalRequestError,
            serial.SerialException,
            OSError,
        ) as exc:
            last_sample_time = time.monotonic()
            safe_print(f"Read Error/Timeout: {exc}")

        except Exception as exc:
            last_sample_time = time.monotonic()
            safe_print(f"Unexpected telemetry error: {exc}")

        stop_event.wait(POLL_INTERVAL_SECONDS)

    relay.turn_off()
    safe_print("Charging stopped: relay GPIO17 LOW")


def main():
    pzem = create_pzem()
    relay = RelayController(RELAY_PIN_BCM, RELAY_ACTIVE_HIGH)

    command_queue = queue.Queue()
    telemetry_stop_event = threading.Event()
    telemetry_thread = None

    listener_thread = threading.Thread(
        target=command_listener,
        args=(command_queue,),
        daemon=True,
    )
    listener_thread.start()

    safe_print("Ready. Type 'on' to start charging, 'off' to stop, or 'q' to exit.")

    try:
        while True:
            command = command_queue.get()

            if command == "on":
                if telemetry_thread and telemetry_thread.is_alive():
                    safe_print("Charging is already running.")
                    continue

                telemetry_stop_event.clear()
                relay.turn_on()
                telemetry_thread = threading.Thread(
                    target=charging_telemetry_loop,
                    args=(pzem, relay, telemetry_stop_event),
                    daemon=True,
                )
                telemetry_thread.start()

            elif command == "off":
                if telemetry_thread and telemetry_thread.is_alive():
                    telemetry_stop_event.set()
                    relay.turn_off()
                    telemetry_thread.join(timeout=3.0)
                else:
                    relay.turn_off()
                    safe_print("Charging is already stopped.")

            elif command in ("q", "quit", "exit"):
                safe_print("Exiting...")
                break

            else:
                safe_print("Unknown command. Use: on, off, q")

    except KeyboardInterrupt:
        safe_print("\nKeyboardInterrupt received. Shutting down safely.")

    finally:
        telemetry_stop_event.set()
        relay.turn_off()

        if telemetry_thread and telemetry_thread.is_alive():
            telemetry_thread.join(timeout=3.0)

        relay.cleanup()
        safe_print("Relay OFF and GPIO cleaned up.")


if __name__ == "__main__":
    main()
