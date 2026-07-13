"""
Charger_script.py  —  EV Charger PZEM-004T Local Monitor
===================================================================
Continuously monitors the PZEM-004T and displays the real-time 
metrics on the 7-inch LCD screen using a Tkinter fullscreen GUI.

The relay is controlled externally (e.g. via WSTK board).
"""

import serial
import time
import threading
import minimalmodbus
import tkinter as tk
import os

PZEM_PORT   = "/dev/serial/by-id/usb-FTDI_FT232R_USB_UART_A50285BI-if00-port0"
PZEM_BAUD   = 9600
PZEM_TIMEOUT = 10.0       # seconds
READ_INTERVAL  = 1.0      # seconds between PZEM polls

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
        # add_metric(metrics_frame, "Units Delivered",  self.energy_var)
        # add_metric(metrics_frame, "Target Units",     self.target_var)

        # Temporarily removed QR code as requested
        # qr_frame = tk.Frame(content, bg="#1a1a2e")
        # qr_frame.pack(side=tk.RIGHT, padx=30, pady=10)

        # tk.Label(qr_frame, text="Scan to Charge", bg="#1a1a2e", fg="#aaaacc",
        #          font=("Helvetica", 16)).pack(pady=(0, 8))
        # try:
        #     self.qr_image = tk.PhotoImage(file="qr.png")
        #     tk.Label(qr_frame, image=self.qr_image, bg="#1a1a2e").pack()
        # except Exception:
        #     tk.Label(qr_frame, text="[ QR Missing ]", fg="#666699", bg="#1a1a2e",
        #              font=("Helvetica", 16)).pack()

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
        os._exit(0)

def monitor_pzem(app):
    print("Starting PZEM continuous monitoring...")
    pzem = PZEM()

    while not pzem.isReady():
        print("Waiting for PZEM to connect...")
        time.sleep(2)

    print("PZEM CONNECTED. Monitoring...")

    while True:
        try:
            readings = pzem.readAll()
            print(f"PZEM: V={readings['voltage_V']:.1f}V  I={readings['current_A']:.2f}A  P={readings['power_W']:.1f}W  Units={readings['energy_Wh']:.1f}")
            
            # Read the target units from the file written by the backend
            try:
                with open("target.txt", "r") as f:
                    target_val = float(f.read().strip())
                    if target_val > 0:
                        app.after(0, lambda v=target_val: app.target_var.set(f"{v:.1f} Units"))
                    else:
                        app.after(0, lambda: app.target_var.set("--- Units"))
            except Exception:
                app.after(0, lambda: app.target_var.set("--- Units"))
            
            # Update Tkinter safely from this background thread
            app.after(0, app.update_metrics, 
                      readings['voltage_V'], 
                      readings['current_A'], 
                      readings['power_W'], 
                      readings['energy_Wh'])

        except Exception as e:
            print(f"PZEM read error: {e}")

        time.sleep(READ_INTERVAL)

if __name__ == "__main__":
    print("=== EV Charger Display Started ===")
    app = ChargerDashboard()
    
    # Start the background polling thread
    monitor_thread = threading.Thread(target=monitor_pzem, args=(app,), daemon=True)
    monitor_thread.start()
    
    # Start the Tkinter UI event loop
    app.mainloop()