import tkinter as tk
from tkinter import ttk, messagebox
import threading
import time

# Import the actual charger script that controls the GPIO and PZEM
try:
    import Charger_script
except ImportError:
    print("Warning: Charger_script.py not found! Ensure it is in the same directory.")
    sys.exit(1)

# =========================================================
# FAKE SOCKET FOR INTERCEPTING METRICS
# =========================================================
# Charger_script.py expects a socket object to send live metrics to.
# We will create a fake socket that intercepts those messages and updates our GUI instead!
class GuiSocket:
    def __init__(self, gui_app):
        self.gui = gui_app

    def send(self, data):
        msg = data.decode('utf-8').strip()
        
        # We must use 'after' to safely update Tkinter from a background thread
        if "METRICS:" in msg:
            try:
                parts = msg.split(":")[1].split("|")
                if len(parts) >= 5:
                    v, i, p, e = float(parts[1]), float(parts[2]), float(parts[3]), float(parts[4])
                    print(f"➜ [Terminal] Voltage: {v:.1f}V | Current: {i:.2f}A | Power: {p:.1f}W | Energy: {e:.2f}Wh")
                    self.gui.after(0, self.gui.update_metrics, float(parts[0]), v, i, p, e)
            except: pass
            
        elif "PROGRESS:" in msg:
            try:
                pct = float(msg.split(":")[1])
                self.gui.after(0, self.gui.update_metrics, pct)
            except: pass
            
        elif "AVAILABLE" in msg:
            self.gui.after(0, self.gui.update_status, "AVAILABLE", "green")
            self.gui.after(0, self.gui.reset_metrics)
            
        elif "COMPLETE" in msg:
            self.gui.after(0, self.gui.update_status, "COMPLETE", "blue")
            
        elif "FAULT" in msg:
            self.gui.after(0, self.gui.update_status, "FAULT", "red")

# =========================================================
# GUI CLASS
# =========================================================
class PiChargerDashboard(tk.Tk):
    def __init__(self):
        super().__init__()
        # Make the GUI fullscreen
        self.attributes('-fullscreen', True)
        self.title("Raspberry Pi Hardware Test (No Wi-SUN)")
        self.configure(bg="#2d2d2d")
        
        # Press ESC to exit fullscreen/close app
        self.bind("<Escape>", lambda e: self.quit_app())
        
        style = ttk.Style(self)
        style.theme_use("clam")
        style.configure("TLabel", background="#2d2d2d", foreground="white", font=("Helvetica", 20))
        style.configure("TFrame", background="#2d2d2d")
        style.configure("TButton", font=("Helvetica", 18, "bold"))
        
        # Status Label
        self.status_var = tk.StringVar(value="STATUS: READY")
        self.status_lbl = tk.Label(self, textvariable=self.status_var, bg="#2d2d2d", fg="green", font=("Helvetica", 28, "bold"), pady=15)
        self.status_lbl.pack(fill=tk.X)

        # Content Frame to hold both Metrics and QR code
        content_frame = ttk.Frame(self, padding=10)
        content_frame.pack(fill=tk.BOTH, expand=True)

        # Metrics Frame (Left Side)
        metrics_frame = ttk.Frame(content_frame)
        metrics_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        
        # QR Frame (Right Side)
        qr_frame = ttk.Frame(content_frame)
        qr_frame.pack(side=tk.RIGHT, padx=20)
        
        try:
            # Keep a reference to prevent garbage collection
            self.qr_image = tk.PhotoImage(file="qr.png")
            tk.Label(qr_frame, image=self.qr_image, bg="#2d2d2d").pack()
        except Exception as e:
            tk.Label(qr_frame, text="[ QR Missing ]", fg="gray", bg="#2d2d2d").pack()

        # Metric Variables
        self.volts_var = tk.StringVar(value="0.0 V")
        self.amps_var = tk.StringVar(value="0.0 A")
        self.watts_var = tk.StringVar(value="0.0 W")
        self.energy_var = tk.StringVar(value="0.0 Wh")
        
        def add_metric(parent, label_text, var):
            f = ttk.Frame(parent)
            f.pack(fill=tk.X, pady=8)
            ttk.Label(f, text=label_text, width=15).pack(side=tk.LEFT)
            ttk.Label(f, textvariable=var, font=("Helvetica", 24, "bold"), foreground="#4CAF50").pack(side=tk.RIGHT)

        add_metric(metrics_frame, "Voltage:", self.volts_var)
        add_metric(metrics_frame, "Current:", self.amps_var)
        add_metric(metrics_frame, "Power:", self.watts_var)
        add_metric(metrics_frame, "Energy Delivered:", self.energy_var)

        # Buttons Frame
        btn_frame = ttk.Frame(self, padding=10)
        btn_frame.pack(fill=tk.X, side=tk.BOTTOM, pady=10)
        
        start_btn = tk.Button(btn_frame, text="START (0.1 Units)", bg="#4CAF50", fg="white", font=("Helvetica", 18, "bold"), height=2, command=self.start_charge)
        start_btn.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=10)

        stop_btn = tk.Button(btn_frame, text="STOP", bg="#f44336", fg="white", font=("Helvetica", 18, "bold"), height=2, command=self.stop_charge)
        stop_btn.pack(side=tk.RIGHT, fill=tk.X, expand=True, padx=10)
        
        # Internal fake socket
        self.fake_sock = GuiSocket(self)

    def start_charge(self):
        self.update_status("CHARGING", "orange")
        self.reset_metrics()
        
        # Launch Charger_script in a background thread so the GUI doesn't freeze
        t = threading.Thread(
            target=Charger_script.Charger,
            kwargs={
                "Rfid_valid": True,
                "amount": 0.1,  # Test amount: 0.1 units = 100 Wh
                "arduino_socket_q": [],
                "arduino_socks": self.fake_sock
            }
        )
        t.daemon = True
        t.start()

    def stop_charge(self):
        self.update_status("STOPPING...", "red")
        Charger_script.stop_charging()

    def update_status(self, text, color):
        self.status_var.set(f"STATUS: {text}")
        self.status_lbl.configure(fg=color)
        
    def update_metrics(self, progress=None, voltage=None, current=None, power=None, energy=None):
        if voltage is not None: self.volts_var.set(f"{voltage:.1f} V")
        if current is not None: self.amps_var.set(f"{current:.2f} A")
        if power is not None: self.watts_var.set(f"{power:.1f} W")
        if energy is not None: self.energy_var.set(f"{energy:.2f} Wh")
        
    def reset_metrics(self):
        self.volts_var.set("0.0 V")
        self.amps_var.set("0.0 A")
        self.watts_var.set("0.0 W")
        self.energy_var.set("0.0 Wh")

    def quit_app(self):
        self.stop_charge()
        import os
        os._exit(0)

# =========================================================
# CLI LISTENER THREAD
# =========================================================
def cli_listener(app):
    print("\n" + "="*50)
    print("  Raspberry Pi Charger (Hybrid GUI + CLI Test)")
    print("="*50)
    print("Commands you can type here:")
    print("  start  - Turn the relay ON")
    print("  stop   - Turn the relay OFF")
    print("  exit   - Quit the program")
    print("="*50 + "\n")
    
    while True:
        try:
            cmd = input().strip().lower()
            if cmd == "start":
                print("\n[CLI] Command accepted: starting charger...")
                app.start_charge()
            elif cmd == "stop":
                print("\n[CLI] Command accepted: stopping charger...")
                app.stop_charge()
            elif cmd == "exit" or cmd == "quit":
                print("\nExiting...")
                app.stop_charge()
                import os
                os._exit(0) # Force exit both threads
            elif cmd != "":
                print(f"Unknown command: '{cmd}'. Try 'start' or 'stop'.")
        except (KeyboardInterrupt, EOFError):
            app.stop_charge()
            import os
            os._exit(0)

if __name__ == "__main__":
    app = PiChargerDashboard()
    
    # Run the CLI listener in the background
    t = threading.Thread(target=cli_listener, args=(app,), daemon=True)
    t.start()
    
    app.mainloop()
