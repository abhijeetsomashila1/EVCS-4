import socket
import sys

# =========================================================
# Wi-SUN UDP LISTENER TEST SCRIPT
# =========================================================
# Run this on your Windows PC (the Backend) to verify that 
# packets from the EFR32 / Border Router are successfully 
# arriving over the network!

UDP_LISTEN_PORT = 5000

print("=========================================")
print(f"   STARTING Wi-SUN LISTENER (Port {UDP_LISTEN_PORT})")
print("=========================================")

try:
    # We use IPv6 since Wi-SUN is natively IPv6
    sock = socket.socket(socket.AF_INET6, socket.SOCK_DGRAM)
    sock.bind(('::', UDP_LISTEN_PORT))
    print("[SUCCESS] Listening for incoming IPv6 UDP packets...")
except OSError:
    # Fallback to IPv4 if IPv6 isn't configured on this interface
    print("[WARNING] IPv6 bind failed. Falling back to IPv4 0.0.0.0")
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind(('0.0.0.0', UDP_LISTEN_PORT))
    print("[SUCCESS] Listening for incoming IPv4 UDP packets...")
except Exception as e:
    print(f"\n[ERROR] Could not start listener: {e}")
    sys.exit(1)

print("\nWaiting for EFR32 messages... (Press Ctrl+C to stop)\n")

try:
    while True:
        data, addr = sock.recvfrom(1024)
        msg = data.decode('utf-8').strip()
        sender_ip = addr[0]
        
        print(f"📥 [PACKET RECEIVED]")
        print(f"   From IP : {sender_ip}")
        print(f"   Message : '{msg}'\n")
        
except KeyboardInterrupt:
    print("\nListener stopped.")
    sock.close()
