"""
Charger_script.py  —  EV Charger with PZEM-004T Power Measurement
===================================================================
Pricing model:
  PRICE_PER_UNIT = ₹25  (cost of 1 electricity unit)
  WH_PER_UNIT    = 1000 Wh  (1 unit = 1 kWh, standard electricity unit)

  Examples:
    APP:2   →  2 units  →   2 000 Wh =  2 kWh
    APP:10  → 10 units  →  10 000 Wh = 10 kWh
    APP:25  → 25 units  →  25 000 Wh = 25 kWh

Flow:
  1. App sends "APP:<units>"  →  any unit amount (e.g. 5)
  2. Relay turns OFF           →  EV starts charging
  3. PZEM-004T measures voltage, current, power every second
  4. Energy (Wh) is accumulated in real time
  5. When energy_delivered >= target_Wh, relay turns ON
  6. UI receives live PZEM readings through the arduino_socks socket

PZEM-004T wiring:
  TX  → RPi RX (GPIO15 / pin 10)  or USB-to-TTL adapter
  RX  → RPi TX (GPIO14 / pin 8)
  VCC → 5V
  GND → GND
  The AC measurement side connects in-line with the load.

Serial port options (set PZEM_PORT below):
  "/dev/ttyUSB0"   USB-to-TTL adapter
  "/dev/ttyAMA0"   Raspberry Pi hardware UART
"""

import RPi.GPIO as GPIO
import serial
import time
import threading
import minimalmodbus

# Global lock to prevent serial port collisions between threads
pzem_port_lock = threading.Lock()
shared_pzem_instance = None
stop_flag = False

def stop_charging():
    global stop_flag
    stop_flag = True


# =========================================================
# CONFIGURATION
# =========================================================

RELAY_PIN   = 17          # BCM GPIO pin controlling the relay
PZEM_PORT   = "/dev/serial/by-id/usb-FTDI_FT232R_USB_UART_A50285BI-if00-port0"
PZEM_BAUD   = 9600
PZEM_TIMEOUT = 10.0       # seconds

# ---- Pricing & energy constants ----
PRICE_PER_UNIT = 25       # ₹ per electricity unit
WH_PER_UNIT    = 1000     # Wh per unit  (1 unit = 1 kWh, standard electricity unit)
READ_INTERVAL  = 1.0      # seconds between PZEM polls

# Example: APP:2 → 2 units → 2×1000 = 2 000 Wh = 2 kWh

# =========================================================
# GPIO SETUP
# =========================================================

GPIO.setmode(GPIO.BCM)
GPIO.setwarnings(False)
GPIO.setup(RELAY_PIN, GPIO.OUT)

# Relay starts OFF (no charging)
GPIO.output(RELAY_PIN, GPIO.LOW)

print("SYSTEM READY")
print("Relay OFF")


# =========================================================
# PZEM-004T DRIVER
# =========================================================

class PZEM:
    """
    Driver for PZEM-004T v3.0 using Modbus RTU (via minimalmodbus).
    Replaces the old v1.0 proprietary 7-byte protocol.
    """

    def __init__(self, com=PZEM_PORT, timeout=PZEM_TIMEOUT):
        self.instrument = minimalmodbus.Instrument(com, 1)
        self.instrument.serial.baudrate = PZEM_BAUD
        self.instrument.serial.bytesize = 8
        self.instrument.serial.parity = serial.PARITY_NONE
        self.instrument.serial.stopbits = 1
        self.instrument.serial.timeout = 1.0  # Modbus needs fast timeouts

    def isReady(self):
        with pzem_port_lock:
            try:
                # Read voltage to verify it's responding
                self.instrument.read_register(0, 1, functioncode=4)
                return True
            except Exception:
                return False

    def readAll(self):
        """Read all four measurements. Returns dict."""
        with pzem_port_lock:
            # Matches exactly how pzem_test.py reads
            voltage = self.instrument.read_register(0, 1, functioncode=4)
            current = self.instrument.read_register(1, 2, functioncode=4)
            power   = self.instrument.read_register(3, 1, functioncode=4)
            
            # Energy (Wh) is stored in two registers (5 and 6)
            try:
                energy_regs = self.instrument.read_registers(5, 2, functioncode=4)
                energy_Wh = energy_regs[0] + (energy_regs[1] << 16)
            except Exception:
                # Fallback to single register if dual-register read fails
                energy_Wh = self.instrument.read_register(5, 0, functioncode=4)

            return {
                "voltage_V" : voltage,
                "current_A" : current,
                "power_W"   : power,
                "energy_Wh" : float(energy_Wh),
            }

    def close(self):
        with pzem_port_lock:
            if self.instrument.serial.isOpen():
                self.instrument.serial.close()


# =========================================================
# SHARED PZEM INSTANCE
# =========================================================

def get_shared_pzem():
    global shared_pzem_instance
    with pzem_port_lock:
        if shared_pzem_instance is None:
            shared_pzem_instance = PZEM(com=PZEM_PORT, timeout=PZEM_TIMEOUT)
        return shared_pzem_instance

def close_shared_pzem():
    global shared_pzem_instance
    with pzem_port_lock:
        if shared_pzem_instance is not None:
            try:
                if shared_pzem_instance.instrument.serial.isOpen():
                    shared_pzem_instance.instrument.serial.close()
            except Exception:
                pass
            shared_pzem_instance = None


# =========================================================
# RELAY TIMER  (legacy — fixed time, no PZEM)
# =========================================================

def relay_timer(arduino_socks):
    """
    Original fixed-time relay function (kept for backwards compatibility).
    Prefer using Charger() which uses PZEM for energy-based cutoff.
    """
    try:
        GPIO.output(RELAY_PIN, GPIO.HIGH)
        print("Relay ON (Charging)")

        try:
            arduino_socks.send(b"CHARGING\n")
        except Exception:
            pass

        time.sleep(5)

        GPIO.output(RELAY_PIN, GPIO.LOW)
        print("Relay OFF (Standby)")

        try:
            arduino_socks.send(b"AVAILABLE\n")
        except Exception:
            pass

    except Exception as e:
        print(f"relay_timer error: {e}")
        GPIO.output(RELAY_PIN, GPIO.LOW)


# =========================================================
# PZEM CHARGING SESSION
# =========================================================

def pzem_charging_session(target_Wh, arduino_socks):
    """
    Controls the relay based on real PZEM-004T power readings.

    Args:
        target_Wh     : Energy to deliver in Wh (e.g. 30000 for 30 kWh)
        arduino_socks : Socket to send live readings and status to the UI

    Steps:
      1. Open PZEM serial connection
      2. Turn relay OFF  →  charging begins
      3. Poll PZEM every READ_INTERVAL seconds
      4. Accumulate energy  (Wh = Power_W * dt / 3600)
      5. Send live data to UI via socket
      6. Stop when energy_delivered >= target_Wh
      7. Turn relay ON  →  charging ends
    """

    pzem = None

    try:

        # --------------------------------------------------
        # RELAY ON  →  START CHARGING & POWER PZEM
        # --------------------------------------------------

        print("Activating relay to power PZEM/Load...")
        GPIO.output(RELAY_PIN, GPIO.HIGH)
        
        # Give the PZEM time to boot up if it is wired downstream of the relay
        time.sleep(2.0)

        # --------------------------------------------------
        # CONNECT PZEM
        # --------------------------------------------------

        print(f"\nConnecting to PZEM-004T on {PZEM_PORT} ...")

        pzem = get_shared_pzem()

        if not pzem.isReady():
            raise Exception("PZEM-004T not responding even after relay ON")

        print("PZEM-004T READY")

        print("=================================")
        print("CHARGING STARTED")
        print(f"Target energy : {target_Wh:.0f} Wh ({target_Wh/1000:.1f} kWh)")
        print("=================================")

        try:
            arduino_socks.send(b"CHARGING\n")
        except Exception:
            pass

        # --------------------------------------------------
        # MEASUREMENT LOOP
        # --------------------------------------------------

        energy_Wh   = 0.0          # accumulated energy this session
        t_prev      = time.time()  # timestamp of last reading

        while energy_Wh < target_Wh and not stop_flag:

            time.sleep(READ_INTERVAL)

            try:
                readings = pzem.readAll()

            except Exception as e:
                print(f"PZEM read error: {e}")
                continue

            # ---- time delta since last reading ----
            t_now  = time.time()
            dt_h   = (t_now - t_prev) / 3600.0   # convert seconds → hours
            t_prev = t_now

            # ---- accumulate energy  (Wh = W × h) ----
            energy_Wh += readings["power_W"] * dt_h

            # ---- progress ----
            progress_pct = (energy_Wh / target_Wh) * 100.0
            if progress_pct > 100.0: progress_pct = 100.0
            
            print(f"PZEM: V={readings['voltage_V']:.1f}V  I={readings['current_A']:.2f}A  "
                  f"P={readings['power_W']:.1f}W  E={energy_Wh:.1f}Wh / {target_Wh:.1f}Wh ({progress_pct:.1f}%)")

            # ---- send to UI ----
            try:
                msg = f"PROGRESS:{progress_pct:.1f}\n"
                arduino_socks.send(msg.encode())
            except Exception:
                pass

        # --------------------------------------------------
        # TARGET REACHED  →  RELAY OFF
        # --------------------------------------------------

        GPIO.output(RELAY_PIN, GPIO.LOW)

        print("=================================")
        print(f"CHARGING COMPLETE — {energy_Wh:.1f} Wh delivered")
        print("Relay OFF")
        print("=================================")

        try:
            arduino_socks.send(
                f"COMPLETE:Energy={energy_Wh:.1f}Wh\n".encode()
            )
            arduino_socks.send(b"AVAILABLE\n")
        except Exception:
            pass

    except Exception as e:

        print(f"pzem_charging_session error: {e}")

        GPIO.output(RELAY_PIN, GPIO.LOW)

        try:
            arduino_socks.send(b"FAULT\n")
        except Exception:
            pass

    finally:
        # Don't fully close the shared connection here, as the monitor thread needs it.
        pass


# =========================================================
# MAIN CHARGER FUNCTION  (called from send_to_AR / EV_BLE)
# =========================================================

def units_to_wh(units):
    """
    Convert a unit amount to a Wh energy target.

    Formula:
        target_Wh = units * WH_PER_UNIT

    Examples:
        units_to_wh(2)   →  2 000 Wh
        units_to_wh(12)  → 12 000 Wh
    """
    target_Wh = float(units) * WH_PER_UNIT
    return target_Wh


def Charger(Rfid_valid, amount, arduino_socket_q, arduino_socks):
    """
    Entry point called when the app sends a unit amount (e.g. "APP:5").

    Args:
        Rfid_valid       : Bool   — RFID authentication result (unused here)
        amount           : int/str — unit value entered in the app
        arduino_socket_q : deque  — incoming message queue from Arduino
        arduino_socks    : socket — connection back to the UI

    Pricing:
        1 unit  = {WH_PER_UNIT} Wh  (1 kWh)
        target  = amount × {WH_PER_UNIT} Wh
    """

    try:
        global stop_flag
        stop_flag = False

        units = float(amount)

        # ---- must be a positive number ----
        if units <= 0:
            raise ValueError(f"Units must be > 0, got {units}")

        target_Wh = units_to_wh(units)

        # ---- safety guard ----
        if target_Wh <= 0:
            raise ValueError(f"Calculated target is 0 Wh. Check WH_PER_UNIT.")

        print("===================================")
        print("BLE USER CONNECTED")
        print(f"Units to charge : {units:.1f} unit(s)")
        print(f"Target energy   : {target_Wh:.0f} Wh  ({target_Wh/1000:.2f} kWh)")
        print(f"Estimated Cost  : ₹{units * PRICE_PER_UNIT:.2f} (@ ₹{PRICE_PER_UNIT}/unit)")
        print("===================================")

        # ---- send summary to UI ----
        try:
            arduino_socks.send(
                f"SESSION:Units={units:.1f} Target={target_Wh/1000:.2f}kWh Cost=Rs{units * PRICE_PER_UNIT:.0f}\n"
                .encode()
            )
        except Exception:
            pass

        # ---- launch PZEM charging session in background thread ----
        threading.Thread(
            target=pzem_charging_session,
            args=(target_Wh, arduino_socks),
            daemon=True
        ).start()

        return [1, 1]

    except Exception as e:

        print(f"Charger() error: {e}")

        GPIO.output(RELAY_PIN, GPIO.LOW)

        return [6, 0]


# =========================================================
# CLEANUP
# =========================================================

def cleanup():
    GPIO.output(RELAY_PIN, GPIO.LOW)
    GPIO.cleanup()


# =========================================================
# STANDALONE TEST  (python Charger_script.py)
# =========================================================

if __name__ == "__main__":

    import socket as _socket

    # --- Dummy socket that just prints to console ---
    class _FakeSock:
        def send(self, data):
            print(f"[SOCKET→UI] {data.decode().strip()}")

    print("=== PZEM-004T Standalone Test ===")
    print(f"PZEM port      : {PZEM_PORT}")
    print(f"Price per unit : ₹{PRICE_PER_UNIT}")
    print(f"Energy per unit: {WH_PER_UNIT} Wh ({WH_PER_UNIT/1000:.1f} kWh)")
    print()

    # ---- show test examples ----
    print("Pricing examples:")
    for u in [1, 2, 5, 10, 12.5]:
        wh = units_to_wh(u)
        print(f"  {u:>4.1f} unit(s)  →  {wh/1000:.2f} kWh  →  ₹{u * PRICE_PER_UNIT:.2f}")
    print()

    # ---- run test with 0.1 units (= 100 Wh) ----
    TEST_AMOUNT = 0.1
    print(f"Running test with {TEST_AMOUNT} units ...")
    Charger(
        Rfid_valid       = True,
        amount           = TEST_AMOUNT,
        arduino_socket_q = [],
        arduino_socks    = _FakeSock()
    )

    # Keep main thread alive so daemon thread can run
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nTest stopped by user.")
        cleanup()