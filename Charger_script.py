"""
Charger_script.py  —  EV Charger PZEM-004T Local Monitor & Relay Controller
===================================================================
Continuously monitors the PZEM-004T and displays real-time metrics 
on the 7-inch LCD screen using a Tkinter fullscreen GUI.

Also directly controls the charger relay via Raspberry Pi GPIO 17 
based on charging targets written by the backend into /tmp/evcs_target.txt.
"""

import serial
import time
import threading
import minimalmodbus
import tkinter as tk
import os
import socket
import atexit

# =====================================================================
# GPIO & RELAY CONFIGURATION
# =====================================================================
RELAY_PIN = 17

# Set to True for Active-High relay (GPIO HIGH = Relay ON, GPIO LOW = Relay OFF)
# Set to False for Active-Low relay (GPIO LOW = Relay ON, GPIO HIGH = Relay OFF)
RELAY_ACTIVE_HIGH = True

try:
    import RPi.GPIO as GPIO
    GPIO_AVAILABLE = True
except ImportError:
    GPIO_AVAILABLE = False
    print("[Warning] RPi.GPIO library not found. Running in simulation mode.")

def init_gpio():
    pass

def set_relay(turn_on: bool):
    pass

def cleanup_gpio():
    pass

# =====================================================================
# SENSOR & TELEMETRY CONFIGURATION
# =====================================================================
PZEM_PORT   = "/dev/serial/by-id/usb-FTDI_FT232R_USB_UART_A50285BI-if00-port0"
PZEM_BAUD   = 9600
PZEM_TIMEOUT = 10.0       # seconds
READ_INTERVAL  = 1.0      # seconds between PZEM polls

LOCAL_UDP_IP = "127.0.0.1"
LOCAL_UDP_PORT = 5000

# =====================================================================
# EFR32FG25 / Wi-SUN CONFIGURATION
# =====================================================================
FG25_PORT = "/dev/serial/by-id/usb-Silicon_Labs_J-Link_Pro_OB_A3AE_000440288199-if00"
FG25_BAUD = 115200

FG25_SOCKET_ID = 5

BORDER_ROUTER_IPV6 = "fd12:3456::92fd:9fff:feee:9d54"
BORDER_ROUTER_UDP_PORT = 5000

WISUN_SEND_INTERVAL = 5.0

class PZEM:
    def __init__(self, com=PZEM_PORT, timeout=PZEM_TIMEOUT):
        self.instrument = minimalmodbus.Instrument(com, 1)
        self.instrument.serial.baudrate = PZEM_BAUD
        self.instrument.serial.bytesize = 8
        self.instrument.serial.parity = serial.PARITY_NONE
        self.instrument.serial.stopbits = 1
        self.instrument.serial.timeout = 1.0
        self.initial_energy = None

    def isReady(self):
        try:
            self.instrument.read_register(0, 1, functioncode=4)
            return True
        except Exception:
            return False

    def readAll(self):
        try:
            voltage = self.instrument.read_register(0, 1, functioncode=4)
            i_regs = self.instrument.read_registers(1, 2, functioncode=4)
            current = (i_regs[0] + (i_regs[1] << 16)) / 1000.0
            p_regs = self.instrument.read_registers(3, 2, functioncode=4)
            power = (p_regs[0] + (p_regs[1] << 16)) / 10.0
            e_regs = self.instrument.read_registers(5, 2, functioncode=4)
            raw_energy_Wh = float(e_regs[0] + (e_regs[1] << 16))
        except Exception:
            # Fallback
            voltage = self.instrument.read_register(0, 1, functioncode=4)
            current = self.instrument.read_register(1, 3, functioncode=4)
            power   = self.instrument.read_register(3, 1, functioncode=4)
            raw_energy_Wh = float(self.instrument.read_register(5, 0, functioncode=4))

        # Set the baseline energy on the very first successful read
        if self.initial_energy is None:
            self.initial_energy = raw_energy_Wh

        # Subtract the baseline to show only energy delivered this session
        session_energy_Wh = raw_energy_Wh - self.initial_energy

        return {
            "voltage_V" : voltage,
            "current_A" : current,
            "power_W"   : power,
            "energy_Wh" : session_energy_Wh,
        }

class ChargerDashboard(tk.Tk):
    def __init__(self):
        super().__init__()
        self.attributes("-fullscreen", True)
        self.title("EV Charger - Power Monitor")
        self.configure(bg="#1a1a2e")
        self.bind("<Escape>", lambda e: self._quit())
        self.protocol("WM_DELETE_WINDOW", self._quit)

        self.status_var = tk.StringVar(value="STATUS: MONITORING LIVE POWER")
        self.status_lbl = tk.Label(
            self, textvariable=self.status_var,
            bg="#1a1a2e", fg="#00e676",
            font=("Helvetica", 30, "bold"), pady=18
        )
        self.status_lbl.pack(fill=tk.X)

        tk.Frame(self, bg="#333366", height=2).pack(fill=tk.X)

        content = tk.Frame(self, bg="#1a1a2e")
        content.pack(fill=tk.BOTH, expand=True, padx=20, pady=10)

        metrics_frame = tk.Frame(content, bg="#1a1a2e")
        metrics_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        self.volts_var    = tk.StringVar(value="--- V")
        self.amps_var     = tk.StringVar(value="--- A")
        self.watts_var    = tk.StringVar(value="--- W")
        self.energy_var   = tk.StringVar(value="--- Units")
        self.target_var   = tk.StringVar(value="--- Units")

        def add_metric(parent, label, var):
            row = tk.Frame(parent, bg="#16213e")
            row.pack(fill=tk.X, pady=12, ipady=12, padx=10)
            tk.Label(row, text=label, bg="#16213e", fg="#aaaacc",
                     font=("Helvetica", 24), anchor="w", width=18).pack(side=tk.LEFT, padx=16)
            tk.Label(row, textvariable=var, bg="#16213e", fg="#00e676",
                     font=("Helvetica", 32, "bold")).pack(side=tk.RIGHT, padx=16)

        tk.Label(metrics_frame, text="LIVE METRICS", bg="#1a1a2e", fg="#6666aa",
                 font=("Helvetica", 16, "bold")).pack(anchor="w", padx=10, pady=(0, 4))

        add_metric(metrics_frame, "Voltage",          self.volts_var)
        add_metric(metrics_frame, "Current",          self.amps_var)
        add_metric(metrics_frame, "Power",            self.watts_var)

        # QR Code Display
        qr_frame = tk.Frame(content, bg="#1a1a2e")
        qr_frame.pack(side=tk.RIGHT, padx=(0, 20), pady=10)

        tk.Label(qr_frame, text="Scan to Charge", bg="#1a1a2e", fg="#aaaacc",
                 font=("Helvetica", 12)).pack(pady=(0, 4))
        try:
            raw_qr = tk.PhotoImage(file="evqr.png")
            self.qr_image = raw_qr.subsample(8, 8)
            tk.Label(qr_frame, image=self.qr_image, bg="#1a1a2e").pack()
        except Exception:
            tk.Label(qr_frame, text="[ evqr.png Missing ]", fg="#666699", bg="#1a1a2e",
                     font=("Helvetica", 16)).pack()

        tk.Frame(self, bg="#333366", height=2).pack(fill=tk.X)
        tk.Label(self, text="EV Charger  |  SCRC, IIIT Hyderabad",
                 bg="#1a1a2e", fg="#555577", font=("Helvetica", 12)).pack(pady=8)

    def update_metrics(self, voltage=None, current=None, power=None, energy=None):
        if voltage  is not None: self.volts_var.set("%.1f V" % voltage)
        if current  is not None: self.amps_var.set("%.2f A" % current)
        if power    is not None: self.watts_var.set("%.1f W" % power)
        if energy   is not None: 
            # Convert raw Watt-hours to standard Units (kWh)
            units = energy / 1000.0
            self.energy_var.set("%.3f Units" % units)

    def _quit(self):
        cleanup_gpio()
        os._exit(0)
        
def send_ev_data_to_fg25(fg25_serial, readings):
    """
    Send EV charger readings to the FG25.

    Compact JSON is used because the FG25 CLI has a limited
    command-line length.
    """

    voltage = float(readings["voltage_V"])
    current = float(readings["current_A"])
    power = float(readings["power_W"])
    energy_kwh = float(readings["energy_Wh"]) / 1000.0

    # Temporary status determination
    if current > 0.1:
        status = "CHARGING"
    else:
        status = "IDLE"

    # Short JSON field names to keep the CLI command small:
    # v = voltage
    # i = current
    # p = power
    # e = energy in kWh
    # s = status
    payload = (
        '{"v":%.1f,"i":%.2f,"p":%.1f,"e":%.3f,"s":"%s"}'
        % (
            voltage,
            current,
            power,
            energy_kwh,
            status
        )
    )

    command = (
        f"wisun socket_write "
        f"{FG25_SOCKET_ID} "
        f"{BORDER_ROUTER_IPV6} "
        f"{BORDER_ROUTER_UDP_PORT} "
        f"{payload}\r"
    )

    fg25_serial.write(command.encode("utf-8"))
    fg25_serial.flush()

    print("Wi-SUN TX:", payload)
    
def monitor_pzem(app):
    print("Starting PZEM continuous monitoring...")

    pzem = PZEM()

    # Track relay state locally
    current_relay_state = False

    # Existing local backend UDP
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

    print(
        f"Ready to send telemetry to "
        f"{LOCAL_UDP_IP}:{LOCAL_UDP_PORT}"
    )

    # ---------------------------------------------------------------
    # Connect to EFR32FG25 through WSTK USB/VCOM
    # ---------------------------------------------------------------

    fg25_serial = serial.Serial(
        port=FG25_PORT,
        baudrate=FG25_BAUD,
        bytesize=serial.EIGHTBITS,
        parity=serial.PARITY_NONE,
        stopbits=serial.STOPBITS_ONE,
        timeout=0.2,
        rtscts=False,
        dsrdtr=False,
        xonxoff=False
    )

    print("FG25 connected:", FG25_PORT)

    # Give FG25 CLI time to become ready
    time.sleep(3)

    # ---------------------------------------------------------------
    # Automatically create a new UDP socket
    # ---------------------------------------------------------------

    try:
        fg25_socket_id = create_wisun_socket(fg25_serial)

    except Exception as e:
        print("ERROR creating FG25 UDP socket:", e)
        fg25_serial.close()
        return

    print("Using FG25 socket:", fg25_socket_id)

    # Timer for 5-second transmissions
    last_wisun_send = 0.0

    # ---------------------------------------------------------------
    # Wait for PZEM
    # ---------------------------------------------------------------

    while not pzem.isReady():
        print("Waiting for PZEM to connect...")
        time.sleep(2)

    print("PZEM CONNECTED. Monitoring...")

    # ---------------------------------------------------------------
    # Main monitoring loop
    # ---------------------------------------------------------------

    while True:
        try:
            readings = pzem.readAll()

            print(
                f"PZEM: "
                f"V={readings['voltage_V']:.1f}V  "
                f"I={readings['current_A']:.2f}A  "
                f"P={readings['power_W']:.1f}W  "
                f"Units={readings['energy_Wh']:.1f}"
            )

            # -------------------------------------------------------
            # Send EV readings to FG25 every 5 seconds
            # -------------------------------------------------------

            now = time.monotonic()

            if now - last_wisun_send >= WISUN_SEND_INTERVAL:
                try:
                    send_ev_data_to_fg25(
                        fg25_serial,
                        fg25_socket_id,
                        readings
                    )

                    last_wisun_send = now

                except Exception as e:
                    print("FG25 send error:", e)

            # -------------------------------------------------------
            # Existing local backend telemetry
            # -------------------------------------------------------

            pzem_string = "V:%.1f,A:%.2f,W:%.1f,Wh:%.1f\n" % (
                readings["voltage_V"],
                readings["current_A"],
                readings["power_W"],
                readings["energy_Wh"]
            )

            try:
                sock.sendto(
                    pzem_string.encode("utf-8"),
                    (LOCAL_UDP_IP, LOCAL_UDP_PORT)
                )
            except Exception as udp_err:
                print("UDP Write Error:", udp_err)

            # -------------------------------------------------------
            # Read target units from backend
            # -------------------------------------------------------

            target_val = 0.0

            try:
                with open("/tmp/evcs_target.txt", "r") as f:
                    content = f.read().strip()
                    target_val = float(content) if content else 0.0

                if target_val > 0:
                    app.after(
                        0,
                        lambda v=target_val:
                        app.target_var.set(f"{v:.1f} Units")
                    )
                else:
                    app.after(
                        0,
                        lambda:
                        app.target_var.set("--- Units")
                    )

            except Exception:
                target_val = 0.0

                app.after(
                    0,
                    lambda:
                    app.target_var.set("--- Units")
                )

            # -------------------------------------------------------
            # Update Tkinter GUI
            # -------------------------------------------------------

            app.after(
                0,
                app.update_metrics,
                readings["voltage_V"],
                readings["current_A"],
                readings["power_W"],
                readings["energy_Wh"]
            )

        except Exception as e:
            print("PZEM read error:", e)

        time.sleep(READ_INTERVAL)

if __name__ == "__main__":
    print("=== EV Charger Display & Relay Controller Started ===")
    
    # Initialize GPIO 17
    init_gpio()

    app = ChargerDashboard()
    
    # Start the background polling thread
    monitor_thread = threading.Thread(target=monitor_pzem, args=(app,), daemon=True)
    monitor_thread.start()
    
    # Start the Tkinter UI event loop
    try:
        app.mainloop()
    finally:
        cleanup_gpio()