# WiSUN Based EVCS

This document serves as the "big picture" guide to how the entire system works from end to end. 

This project is a fully functional, IoT-enabled Electric Vehicle Charging Station. Unlike traditional chargers that rely on Wi-Fi or cellular networks, this system utilizes a **Wi-SUN (Wireless Smart Utility Network) mesh network**, making it highly scalable, resilient, and capable of operating in massive outdoor environments without internet dead zones.

---

## 1. Hardware Architecture

The system consists of three main hardware layers:

1. **The Border Router :** A Raspberry Pi that acts as the central coordinator for the mesh network. It hosts the backend database server and the web server.
2. ** EV Charger Nodes :** Silicon Labs EFR32 boards embedded inside the physical charging pillars. These boards receive commands over the Wi-SUN mesh network to physically open and close high-voltage AC relays.
3. ** PZEM Sensors :** PZEM-004T power meters connected to the EFR32 nodes that measure live voltage, current, power, and energy (`Wh`) flowing into the vehicle.

---

## 2. Software Architecture

The software is split into three main codebases, all communicating with each other in real-time.

### A. The Frontend (`EVCS-4-Website/frontend`)
- **Tech Stack:** React, TypeScript, Tailwind CSS, Vite PWA.
- **Role:** The user-facing mobile web application. Users scan a QR code on the physical charger, select how many "Units" (kWh) they want to charge, and watch a live progress bar as their vehicle charges.

### B. The Backend (`EVCS-4-Website/backend/EVCS-Backend`)
- **Tech Stack:** Node.js, Express, PostgreSQL.
- **Role:** The central traffic cop running on the Raspberry Pi. 
- It handles authentication and serves the frontend. 
- It maintains the PostgreSQL database of users, sessions, and billing.
- It translates web requests (like "Start Charging") into physical `CoAP` commands (`evon.sh`, `evoff.sh`) that are beamed over the Wi-SUN mesh network to the EFR32 nodes.

### C. The Hardware Script (`EVCS-4/Charger_script.py`)
- **Tech Stack:** Python, Tkinter, MinimalModbus.
- **Role:** This script runs on the Raspberry Pi and acts as a bridge. It constantly polls the physical PZEM sensor via a USB Modbus connection.
- It formats the live electrical data into a simple CSV string (`V:230,A:10,W:2300,Wh:15`) and pushes it via USB UART to the EFR32 board.
- The EFR32 board then takes this string and broadcasts it over the Wi-SUN network back to the backend.

---

## 3. The Lifecycle of a Charging Session

To truly understand the system, here is exactly what happens when a user charges their car:

1. **Scan & Start:** The user scans the QR code on the charger and clicks "Start Charging (5 Units)" on the web app.
2. **Database Entry:** The React frontend sends an HTTP request to the Node.js backend. The backend records a new active session for `5.0 units` in the PostgreSQL database.
3. **Power On:** The Node.js backend executes a shell script (`evon.sh`). This fires a CoAP packet over the Wi-SUN wireless mesh network to the EFR32 node. The EFR32 flips the physical AC relay, and electricity starts flowing to the car.
4. **Live Telemetry:** As electricity flows, the PZEM sensor measures it. The Python script reads this data, passes it to the EFR32 via UART, and the EFR32 broadcasts a UDP packet (`METRICS:...`) over the Wi-SUN network back to the backend every single second.
5. **Live Website:** The backend receives these metrics and forwards them to the React frontend, allowing the user to watch their progress bar fill up in real-time.
6. **Auto-Stop:** The backend constantly compares the live `Wh` metrics against the user's `5.0 unit` target. The millisecond the target is reached, the backend automatically fires `evoff.sh` over the mesh network.
7. **Power Off:** The EFR32 receives the stop command, cuts the physical relay, and the session is marked as "Completed" in the database.

---
