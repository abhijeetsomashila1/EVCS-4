import tkinter as tk
from tkinter import ttk
import queue

# A thread-safe queue to receive metrics from the background Wi-SUN/Serial thread
_ui_queue = queue.Queue()

def update_metrics(msg):
    """
    msg format: "METRICS:45.0|230.1|12.5|2875|1.5"
    """
    _ui_queue.put({"type": "METRICS", "data": msg})

def update_status(msg):
    """
    msg format: "CHARGING" or "AVAILABLE"
    """
    _ui_queue.put({"type": "STATUS", "data": msg})

class ChargerUI:
    def __init__(self, root):
        self.root = root
        self.root.title("EV Charger Display")
        # Go full screen for the LCD display
        self.root.attributes('-fullscreen', True)
        self.root.configure(bg='#121212') # Sleek dark theme
        
        # --- Configure Grid Weight for Centering ---
        self.root.rowconfigure(0, weight=1)
        self.root.rowconfigure(1, weight=3)
        self.root.rowconfigure(2, weight=1)
        self.root.columnconfigure(0, weight=1)
        
        # --- Top Section: Status ---
        self.status_var = tk.StringVar(value="AVAILABLE")
        self.status_label = tk.Label(
            self.root, 
            textvariable=self.status_var,
            font=("Helvetica", 32, "bold"),
            fg="#4ade80", # Greenish
            bg="#121212"
        )
        self.status_label.grid(row=0, column=0, sticky="s", pady=20)
        
        # --- Middle Section: Metrics ---
        self.metrics_frame = tk.Frame(self.root, bg="#1a1a1a", bd=0)
        self.metrics_frame.grid(row=1, column=0, padx=40, pady=20, sticky="nsew")
        
        # Configure columns inside metrics frame
        for i in range(4):
            self.metrics_frame.columnconfigure(i, weight=1)
        self.metrics_frame.rowconfigure(0, weight=1)
        
        # Metric Labels
        self.voltage_var = tk.StringVar(value="0.0")
        self.current_var = tk.StringVar(value="0.00")
        self.power_var = tk.StringVar(value="0.0")
        self.energy_var = tk.StringVar(value="0.00")
        
        self.create_metric_box(self.metrics_frame, "Voltage (V)", self.voltage_var, 0)
        self.create_metric_box(self.metrics_frame, "Current (A)", self.current_var, 1)
        self.create_metric_box(self.metrics_frame, "Power (W)", self.power_var, 2)
        self.create_metric_box(self.metrics_frame, "Energy (Wh)", self.energy_var, 3)
        
        # --- Bottom Section: Progress Bar ---
        self.progress_frame = tk.Frame(self.root, bg="#121212")
        self.progress_frame.grid(row=2, column=0, sticky="n", pady=20, padx=40)
        
        # Custom styling for progress bar
        style = ttk.Style()
        style.theme_use('default')
        style.configure(
            "TProgressbar", 
            thickness=40,
            troughcolor='#262626',
            background='#3b82f6' # Blue progress
        )
        
        self.progress_var = tk.DoubleVar(value=0.0)
        self.progress_bar = ttk.Progressbar(
            self.progress_frame, 
            style="TProgressbar",
            orient="horizontal", 
            length=600, 
            mode="determinate", 
            variable=self.progress_var
        )
        self.progress_bar.pack(side="top")
        
        self.progress_text = tk.StringVar(value="0.0% Complete")
        self.progress_label = tk.Label(
            self.progress_frame, 
            textvariable=self.progress_text,
            font=("Helvetica", 16),
            fg="#9ca3af",
            bg="#121212"
        )
        self.progress_label.pack(side="top", pady=10)
        
        # --- Exit button (hidden in top right corner for easy exiting during dev) ---
        exit_btn = tk.Button(self.root, text="X", command=self.root.destroy, bg="#121212", fg="#333333", bd=0, highlightthickness=0)
        exit_btn.place(relx=0.95, rely=0.02)
        
        # Start checking the queue
        self.root.after(100, self.process_queue)
        
    def create_metric_box(self, parent, title, var, col):
        frame = tk.Frame(parent, bg="#1a1a1a")
        frame.grid(row=0, column=col, sticky="nsew", padx=10, pady=20)
        
        title_lbl = tk.Label(frame, text=title, font=("Helvetica", 16), fg="#9ca3af", bg="#1a1a1a")
        title_lbl.pack(side="top", pady=(20, 5))
        
        val_lbl = tk.Label(frame, textvariable=var, font=("Helvetica", 36, "bold"), fg="#ffffff", bg="#1a1a1a")
        val_lbl.pack(side="top", pady=(0, 20))
        
    def process_queue(self):
        try:
            while True: # Process all items currently in the queue
                item = _ui_queue.get_nowait()
                if item["type"] == "STATUS":
                    status_text = item["data"].strip()
                    self.status_var.set(status_text)
                    if "CHARGING" in status_text:
                        self.status_label.config(fg="#3b82f6") # Blue
                    elif "FAULT" in status_text:
                        self.status_label.config(fg="#ef4444") # Red
                    else:
                        self.status_label.config(fg="#4ade80") # Green
                        # Reset metrics when available
                        self.voltage_var.set("0.0")
                        self.current_var.set("0.00")
                        self.power_var.set("0.0")
                        self.energy_var.set("0.00")
                        self.progress_var.set(0.0)
                        self.progress_text.set("0.0% Complete")
                        
                elif item["type"] == "METRICS":
                    # Format: METRICS:Progress|Voltage|Current|Power|Energy
                    parts = item["data"].split(":")[1].split("|")
                    if len(parts) >= 5:
                        progress = float(parts[0])
                        self.progress_var.set(progress)
                        self.progress_text.set(f"{progress:.1f}% Complete")
                        
                        self.voltage_var.set(parts[1])
                        self.current_var.set(parts[2])
                        self.power_var.set(parts[3])
                        self.energy_var.set(parts[4])
        except queue.Empty:
            pass
        finally:
            # Re-schedule the next queue check
            self.root.after(100, self.process_queue)

def start_ui():
    root = tk.Tk()
    app = ChargerUI(root)
    root.mainloop()

if __name__ == "__main__":
    start_ui()
