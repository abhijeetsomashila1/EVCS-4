"""
PZEM-004T Power Measurement Module
====================================
Measures Voltage, Current, Power, and Energy (registered power)
from the PZEM-004T sensor over serial (USB or TTL).

Protocol: 7-byte command frames over 9600 baud, 8N1.
Compatible with: Raspberry Pi (USB /dev/ttyUSB0 or TTL /dev/ttyAMA0)

Based on: BLE_App/PZEM_BLE_UI/Charger_script.py
Repo:     https://github.com/guptarohan6502/EV_charger
"""

import serial
import struct
import time
import threading


# =============================================================================
# HELPER: Thread subclass that returns a value from its target function
# =============================================================================

class ThreadWithReturnValue(threading.Thread):
    def __init__(self, group=None, target=None, name=None, args=(), kwargs={}, Verbose=None):
        super().__init__(group=group, target=target, name=name, args=args, kwargs=kwargs)
        self._return = None

    def run(self):
        if self._target is not None:
            self._return = self._target(*self._args, **self._kwargs)

    def join(self, timeout=None):
        super().join(timeout)
        return self._return


# =============================================================================
# PZEM-004T CLASS
# =============================================================================

class PZEM:
    """
    Driver for the PZEM-004T AC power measurement module.

    Command bytes (7-byte frames):
      [cmd, IP3, IP2, IP1, IP0, 0x00, checksum]
    Default device IP: 192.168.1.1  -> 0xC0, 0xA8, 0x01, 0x01

    Response frames are also 7 bytes; last byte is checksum (sum % 256).
    """

    # 7-byte command frames
    setAddrBytes      = [0xB4, 0xC0, 0xA8, 0x01, 0x01, 0x00, 0x1E]
    readVoltageBytes  = [0xB0, 0xC0, 0xA8, 0x01, 0x01, 0x00, 0x1A]
    readCurrentBytes  = [0xB1, 0xC0, 0xA8, 0x01, 0x01, 0x00, 0x1B]
    readPowerBytes    = [0xB2, 0xC0, 0xA8, 0x01, 0x01, 0x00, 0x1C]
    readRegPowerBytes = [0xB3, 0xC0, 0xA8, 0x01, 0x01, 0x00, 0x1D]

    def __init__(self, com="/dev/ttyUSB0", timeout=10.0):
        """
        Initialize serial connection to PZEM-004T.

        Args:
            com     : Serial port. Common options:
                        "/dev/ttyUSB0"  -> USB-to-TTL adapter (Linux)
                        "/dev/ttyAMA0"  -> Raspberry Pi hardware UART
                        "/dev/rfcomm0"  -> Bluetooth serial
                        "COM3"          -> Windows
            timeout : Read timeout in seconds (default 10.0)

        Tip: Run `dmesg | grep tty` on Linux to find your port.
        """
        self.ser = serial.Serial(
            port=com,
            baudrate=2400,
            parity=serial.PARITY_NONE,
            stopbits=serial.STOPBITS_ONE,
            bytesize=serial.EIGHTBITS,
            timeout=timeout
        )
        if self.ser.isOpen():
            self.ser.close()
        self.ser.open()

    # -------------------------------------------------------------------------
    # Internal helpers
    # -------------------------------------------------------------------------

    def _checkChecksum(self, _tuple):
        """Verify response checksum (last byte == sum of preceding bytes % 256)."""
        _list = list(_tuple)
        _checksum = _list[-1]
        _list.pop()
        _sum = sum(_list)
        if _checksum == _sum % 256:
            return True
        else:
            raise Exception("PZEM checksum mismatch — check wiring/baud rate.")

    def _send_and_receive(self, cmd_bytes, n_response=7):
        """Send a command and return unpacked response bytes."""
        self.ser.write(serial.to_bytes(cmd_bytes))
        rcv = self.ser.read(n_response)
        if len(rcv) != n_response:
            raise serial.SerialTimeoutException(
                f"Timeout: expected {n_response} bytes, got {len(rcv)}"
            )
        unpacked = struct.unpack(f"!{n_response}B", rcv)
        self._checkChecksum(unpacked)
        return unpacked

    # -------------------------------------------------------------------------
    # Public API
    # -------------------------------------------------------------------------

    def isReady(self):
        """
        Ping the PZEM-004T by setting its address.
        Returns True if the device responds correctly.
        """
        self.ser.write(serial.to_bytes(self.setAddrBytes))
        rcv = self.ser.read(7)
        if len(rcv) == 7:
            unpacked = struct.unpack("!7B", rcv)
            if self._checkChecksum(unpacked):
                return True
        else:
            raise serial.SerialTimeoutException("Timeout setting address — is PZEM-004T connected?")

    def readVoltage(self):
        """
        Read AC voltage.

        Returns:
            float: Voltage in Volts (resolution 0.1 V)
        """
        data = self._send_and_receive(self.readVoltageBytes)
        # Bytes [1] and [2] encode voltage: high byte * 256 + low byte, scaled by 10
        # Byte [3] encodes tenths digit
        voltage = (data[1] * 256 + data[2]) + data[3] / 10.0
        return voltage

    def readCurrent(self):
        """
        Read AC current.

        Returns:
            float: Current in Amperes (resolution 0.01 A)
        """
        data = self._send_and_receive(self.readCurrentBytes)
        # Bytes [1] and [2] = integer part, byte [3] = fractional (hundredths)
        current = (data[1] * 256 + data[2]) + data[3] / 100.0
        return current

    def readPower(self):
        """
        Read active (real) power.

        Returns:
            float: Power in Watts (resolution 1 W)
        """
        data = self._send_and_receive(self.readPowerBytes)
        # Bytes [1] and [2] encode integer Watts
        power = data[1] * 256 + data[2]
        return float(power)

    def readEnergy(self):
        """
        Read cumulative energy (registered power / energy counter).

        Returns:
            float: Energy in Wh (Watt-hours)
        """
        data = self._send_and_receive(self.readRegPowerBytes)
        # Bytes [1], [2], [3] encode energy in Wh (3-byte big-endian)
        energy = data[1] * 65536 + data[2] * 256 + data[3]
        return float(energy)

    def readAll(self):
        """
        Convenience method — read all four measurements in sequence.

        Returns:
            dict: {
                'voltage_V'  : float,
                'current_A'  : float,
                'power_W'    : float,
                'energy_Wh'  : float
            }
        """
        return {
            'voltage_V' : self.readVoltage(),
            'current_A' : self.readCurrent(),
            'power_W'   : self.readPower(),
            'energy_Wh' : self.readEnergy(),
        }

    def close(self):
        """Close the serial port."""
        if self.ser.isOpen():
            self.ser.close()


# =============================================================================
# STANDALONE TEST  (run: python pzem004t.py)
# =============================================================================

if __name__ == "__main__":
    PORT    = "/dev/ttyUSB0"   # Change to your port
    TIMEOUT = 10.0

    print(f"Connecting to PZEM-004T on {PORT} ...")
    pzem = PZEM(com=PORT, timeout=TIMEOUT)

    try:
        if pzem.isReady():
            print("PZEM-004T is READY\n")

        print("Reading measurements every 2 seconds. Press Ctrl+C to stop.\n")
        while True:
            readings = pzem.readAll()
            print(
                f"Voltage : {readings['voltage_V']:.1f} V  | "
                f"Current : {readings['current_A']:.2f} A  | "
                f"Power   : {readings['power_W']:.1f} W  | "
                f"Energy  : {readings['energy_Wh']:.1f} Wh"
            )
            time.sleep(2)

    except KeyboardInterrupt:
        print("\nStopped by user.")
    except Exception as e:
        print(f"Error: {e}")
    finally:
        pzem.close()
        print("Serial port closed.")
