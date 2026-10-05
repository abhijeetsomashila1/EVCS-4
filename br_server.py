#!/usr/bin/env python3

import socket
import json

HOST = "::"       # Listen on all IPv6 interfaces
PORT = 5000       # UDP port

sock = socket.socket(socket.AF_INET6, socket.SOCK_DGRAM)
sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

sock.bind((HOST, PORT))

print(f"UDP server listening on [{HOST}]:{PORT}")
print("Waiting for EV charger data...\n")

while True:
    try:
        data, addr = sock.recvfrom(4096)

        message = data.decode("utf-8", errors="replace").strip()

        print(f"Received from {addr[0]}:{addr[1]}")
        print(f"Raw data: {message}")

        # Try to interpret the message as JSON
        try:
            ev_data = json.loads(message)

            print("JSON data:")
            print(json.dumps(ev_data, indent=2))

        except json.JSONDecodeError:
            print("Message is not valid JSON.")

        print("-" * 60)

    except KeyboardInterrupt:
        print("\nServer stopped.")
        break

    except Exception as e:
        print(f"Server error: {e}")

sock.close()