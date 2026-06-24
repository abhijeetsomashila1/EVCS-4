import threading
import sys
import time

try:
    import Charger_script
except ImportError:
    print("Warning: Charger_script.py not found! Ensure it is in the same directory.")
    sys.exit(1)

# =========================================================
# FAKE SOCKET FOR INTERCEPTING METRICS
# =========================================================
class CliSocket:
    def send(self, data):
        msg = data.decode('utf-8').strip()
        
        if "METRICS:" in msg:
            try:
                parts = msg.split(":")[1].split("|")
                if len(parts) >= 5:
                    v, i, p, e = float(parts[1]), float(parts[2]), float(parts[3]), float(parts[4])
                    print(f"➜ [Live Data] Voltage: {v:.1f}V | Current: {i:.2f}A | Power: {p:.1f}W | Energy: {e:.2f}Wh")
            except: pass
            
        elif "AVAILABLE" in msg:
            print("\n[Status] Charger is AVAILABLE.")
            
        elif "COMPLETE" in msg:
            print("\n[Status] Charging COMPLETE.")
            
        elif "FAULT" in msg:
            print("\n[Status] FAULT detected!")

fake_sock = CliSocket()

# =========================================================
# COMMAND LINE INTERFACE
# =========================================================
def command_listener():
    print("\n" + "="*50)
    print("  Raspberry Pi Charger CLI Test")
    print("="*50)
    print("Commands you can type:")
    print("  start  - Turn the relay ON and begin reading power")
    print("  stop   - Turn the relay OFF")
    print("  exit   - Quit the program")
    print("="*50 + "\n")
    
    while True:
        try:
            cmd = input("").strip().lower()
            
            if cmd == "start":
                print("\n[Action] Starting charger...")
                t = threading.Thread(
                    target=Charger_script.Charger,
                    kwargs={
                        "Rfid_valid": True,
                        "amount": 0.1,  # Test amount: 0.1 units
                        "arduino_socket_q": [],
                        "arduino_socks": fake_sock
                    }
                )
                t.daemon = True
                t.start()
                
            elif cmd == "stop":
                print("\n[Action] Stopping charger...")
                Charger_script.stop_charging()
                
            elif cmd == "exit" or cmd == "quit":
                print("\nExiting...")
                Charger_script.stop_charging()
                sys.exit(0)
                
            elif cmd != "":
                print(f"Unknown command: '{cmd}'. Try 'start' or 'stop'.")
                
        except (KeyboardInterrupt, EOFError):
            print("\nExiting...")
            Charger_script.stop_charging()
            sys.exit(0)

if __name__ == "__main__":
    # Start the CLI listener loop
    command_listener()
