"""
wisun_bridge.py  -  EV Charger Wi-SUN Bridge + Local Display
Combines the Wi-SUN serial command listener with the fullscreen
Tkinter dashboard.
"""

import serial
import time
import threading
import sys
import re
import tkinter as tk

import Charger_script

WISUN_PORT       = "/dev/ttyACM0"
BAUD_RATE        = 115200
SERVER_IP        = "fd12:3456::92fd:9fff:feee:9d54"
SERVER_UDP_PORT  = "5000"
NODE_LISTEN_PORT = "5001"

try:
    ser = serial.Serial(WISUN_PORT, BAUD_RATE, timeout=1)
    print("[Wi-SUN Bridge] Connected to EFR32 on " + WISUN_PORT)
    time.sleep(2)
except Exception as e:
    print("[Wi-SUN Bridge] FAILED TO CONNECT TO EFR32: " + str(e))
    sys.exit(1)


def send_wisun_cmd(cmd, wait=1):
    ser.write((cmd + "\n").encode())
    time.sleep(wait)


class GuiWiSunSocket:
    def __init__(self, gui_app):
        self.gui = gui_app

    def send(self, data):
        msg = data.decode("utf-8").strip()

        if "METRICS:" in msg:
            try:
                parts = msg.split(":")[1].split("|")
                if len(parts) >= 5:
                    pct = float(parts[0])
                    v   = float(parts[1])
                    i   = float(parts[2])
                    p   = float(parts[3])
                    e   = float(parts[4])
                    print("[PZEM] V=%.1fV  I=%.2fA  P=%.1fW  E=%.2fWh  (%.1f%%)" % (v, i, p, e, pct))
                    self.gui.after(0, self.gui.update_metrics, pct, v, i, p, e)
                    for sock_id in range(10):
                        send_wisun_cmd(f'wisun socket_writeto {sock_id} {SERVER_IP} {SERVER_UDP_PORT} "PROGRESS:{pct:.1f}"', wait=0.05)
            except Exception as ex:
                print("[GuiWiSunSocket] METRICS parse error: " + str(ex))

        elif "CHARGING" in msg:
            self.gui.after(0, self.gui.update_status, "CHARGING", "orange")
            for sock_id in range(10):
                send_wisun_cmd(f'wisun socket_writeto {sock_id} {SERVER_IP} {SERVER_UDP_PORT} "CHARGING"', wait=0.05)

        elif "COMPLETE" in msg:
            self.gui.after(0, self.gui.update_status, "COMPLETE", "blue")
            self.gui.after(0, self.gui.reset_metrics)
            for sock_id in range(10):
                send_wisun_cmd(f'wisun socket_writeto {sock_id} {SERVER_IP} {SERVER_UDP_PORT} "COMPLETE"', wait=0.05)

        elif "AVAILABLE" in msg:
            self.gui.after(0, self.gui.update_status, "AVAILABLE", "green")
            self.gui.after(0, self.gui.reset_metrics)
            for sock_id in range(10):
                send_wisun_cmd(f'wisun socket_writeto {sock_id} {SERVER_IP} {SERVER_UDP_PORT} "AVAILABLE"', wait=0.05)

        elif "FAULT" in msg:
            self.gui.after(0, self.gui.update_status, "FAULT", "red")
            for sock_id in range(10):
                send_wisun_cmd(f'wisun socket_writeto {sock_id} {SERVER_IP} {SERVER_UDP_PORT} "FAULT"', wait=0.05)


def serial_listener(gui_app):
    gui_sock = GuiWiSunSocket(gui_app)

    while True:
        try:
            if ser.in_waiting:
                line = ser.readline().decode(errors="ignore").strip()
                if not line:
                    continue

                print("[EFR32] " + line)

                if "START" in line.upper():
                    print("[Wi-SUN Bridge] Received START command! Raw: " + line)

                    target_amount = 0.1
                    try:
                        if "START:" in line.upper():
                            amount_str = line.upper().split("START:")[1].strip()
                            match = re.search(r"[\d\.]+", amount_str)
                            if match:
                                target_amount = float(match.group())
                    except Exception as parse_err:
                        print("[Wi-SUN Bridge] Amount parse error, using 0.1: " + str(parse_err))

                    print("[Wi-SUN Bridge] Charging %.1f units" % target_amount)
                    gui_app.after(0, gui_app.update_status, "CHARGING (%.1f units)" % target_amount, "orange")
                    gui_app.after(0, gui_app.reset_metrics)

                    t = threading.Thread(
                        target=Charger_script.Charger,
                        kwargs={
                            "amount":           target_amount,
                            "ui_socket":        gui_sock
                        },
                        daemon=True
                    )
                    t.start()

                elif "STOP" in line.upper():
                    print("[Wi-SUN Bridge] Received STOP command!")
                    Charger_script.stop_charging()
                    gui_app.after(0, gui_app.update_status, "STOPPED", "red")

        except Exception as e:
            print("[serial_listener] error: " + str(e))
            time.sleep(1)


class ChargerDashboard(tk.Tk):
    def __init__(self):
        super().__init__()
        self.attributes("-fullscreen", True)
        self.title("EV Charger - Wi-SUN Monitor")
        self.configure(bg="#1a1a2e")
        self.bind("<Escape>", lambda e: self._quit())

        self.status_var = tk.StringVar(value="STATUS: INITIALIZING...")
        self.status_lbl = tk.Label(
            self, textvariable=self.status_var,
            bg="#1a1a2e", fg="#ffaa00",
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
        self.energy_var   = tk.StringVar(value="--- Wh")
        self.progress_var = tk.StringVar(value="0 %")

        def add_metric(parent, label, var):
            row = tk.Frame(parent, bg="#16213e")
            row.pack(fill=tk.X, pady=8, ipady=12, padx=10)
            tk.Label(row, text=label, bg="#16213e", fg="#aaaacc",
                     font=("Helvetica", 20), anchor="w", width=22).pack(side=tk.LEFT, padx=16)
            tk.Label(row, textvariable=var, bg="#16213e", fg="#00e676",
                     font=("Helvetica", 26, "bold")).pack(side=tk.RIGHT, padx=16)

        tk.Label(metrics_frame, text="LIVE METRICS", bg="#1a1a2e", fg="#6666aa",
                 font=("Helvetica", 16, "bold")).pack(anchor="w", padx=10, pady=(0, 4))

        add_metric(metrics_frame, "Voltage",          self.volts_var)
        add_metric(metrics_frame, "Current",          self.amps_var)
        add_metric(metrics_frame, "Power",            self.watts_var)
        add_metric(metrics_frame, "Energy Delivered", self.energy_var)
        add_metric(metrics_frame, "Progress",         self.progress_var)

        qr_frame = tk.Frame(content, bg="#1a1a2e")
        qr_frame.pack(side=tk.RIGHT, padx=30, pady=10)

        tk.Label(qr_frame, text="Scan to Charge", bg="#1a1a2e", fg="#aaaacc",
                 font=("Helvetica", 16)).pack(pady=(0, 8))
        try:
            self.qr_image = tk.PhotoImage(file="qr.png")
            tk.Label(qr_frame, image=self.qr_image, bg="#1a1a2e").pack()
        except Exception:
            tk.Label(qr_frame, text="[ QR Missing ]", fg="#666699", bg="#1a1a2e",
                     font=("Helvetica", 16)).pack()

        tk.Frame(self, bg="#333366", height=2).pack(fill=tk.X)
        tk.Label(self, text="EV Charger  |  SCRC, IIIT Hyderabad  |  Wi-SUN Network",
                 bg="#1a1a2e", fg="#555577", font=("Helvetica", 12)).pack(pady=8)

    def update_status(self, text, color):
        self.status_var.set("STATUS: " + text)
        self.status_lbl.configure(fg=color)

    def update_metrics(self, progress=None, voltage=None, current=None, power=None, energy=None):
        if voltage  is not None: self.volts_var.set("%.1f V" % voltage)
        if current  is not None: self.amps_var.set("%.2f A" % current)
        if power    is not None: self.watts_var.set("%.1f W" % power)
        if energy   is not None: self.energy_var.set("%.2f Wh" % energy)
        if progress is not None: self.progress_var.set("%.1f %%" % progress)

    def reset_metrics(self):
        self.volts_var.set("--- V")
        self.amps_var.set("--- A")
        self.watts_var.set("--- W")
        self.energy_var.set("--- Wh")
        self.progress_var.set("0 %")

    def _quit(self):
        Charger_script.stop_charging()
        import os
        os._exit(0)


if __name__ == "__main__":
    print("[Wi-SUN Bridge] Starting...")

    app = ChargerDashboard()

    threading.Thread(target=serial_listener, args=(app,), daemon=True).start()

    def wisun_init():
        print("[Wi-SUN Bridge] Closing old sockets to prevent bind errors...")
        send_wisun_cmd("wisun socket_close 0", wait=0.5)
        send_wisun_cmd("wisun socket_close 1", wait=0.5)
        send_wisun_cmd("wisun socket_close 2", wait=0.5)
        send_wisun_cmd("wisun socket_close 3", wait=0.5)

        print("[Wi-SUN Bridge] Joining Wi-SUN network (waiting 80s for IPv6 address)...")
        send_wisun_cmd("wisun join_fan11", wait=80)
        
        print("[Wi-SUN Bridge] Opening UDP socket directly...")
        send_wisun_cmd("wisun udp_server " + NODE_LISTEN_PORT, wait=1.0)
        
        print("[Wi-SUN Bridge] Ready!")
        app.after(0, app.update_status, "AVAILABLE", "#00e676")
        
        print("[Wi-SUN Bridge] Starting HELLO heartbeat...")
        # Loop forever, sending a heartbeat every 30 seconds.
        # This guarantees connection even if the Wi-SUN network takes 5+ minutes to assign an IP!
        while True:
            for sock_id in range(10):
                send_wisun_cmd(f'wisun socket_writeto {sock_id} {SERVER_IP} {SERVER_UDP_PORT} "HELLO:EV001"', wait=0.05)
            time.sleep(30)

    threading.Thread(target=wisun_init, daemon=True).start()

    app.mainloop()
