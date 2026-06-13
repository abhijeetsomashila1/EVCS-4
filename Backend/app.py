import os
import mysql.connector
import threading
import socket
import math
from flask import Flask, jsonify, request, render_template
from flask_cors import CORS

app = Flask(__name__)
CORS(app)

UDP_LISTEN_PORT = 5000

# MySQL Config
MYSQL_HOST = 'localhost'
MYSQL_USER = 'root'
MYSQL_PASSWORD = 'Bujji@2709'
MYSQL_DB = 'evcharger'

# =========================================================
# DATABASE SETUP
# =========================================================

def get_db_connection():
    return mysql.connector.connect(
        host=MYSQL_HOST,
        user=MYSQL_USER,
        password=MYSQL_PASSWORD,
        database=MYSQL_DB
    )

def init_db():
    # Connect without database first to create it
    conn = mysql.connector.connect(
        host=MYSQL_HOST,
        user=MYSQL_USER,
        password=MYSQL_PASSWORD
    )
    c = conn.cursor()
    c.execute(f"CREATE DATABASE IF NOT EXISTS {MYSQL_DB}")
    conn.commit()
    conn.close()
    
    # Connect to the database and create tables
    conn = get_db_connection()
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS chargers (
            id VARCHAR(50) PRIMARY KEY,
            status VARCHAR(50),
            lat FLOAT,
            lon FLOAT,
            wisun_ip VARCHAR(100),
            progress FLOAT
        )
    ''')
    
    # Insert some dummy chargers for the prototype
    try:
        c.execute("INSERT IGNORE INTO chargers VALUES ('EV001', 'AVAILABLE', 17.4447, 78.3484, '', 0.0)")
        c.execute("INSERT IGNORE INTO chargers VALUES ('EV002', 'AVAILABLE', 17.4450, 78.3489, '', 0.0)")
        c.execute("INSERT IGNORE INTO chargers VALUES ('EV003', 'AVAILABLE', 17.4430, 78.3470, '', 0.0)")
    except Exception as e:
        print("Insert Error:", e)
        
    conn.commit()
    conn.close()

try:
    init_db()
    print("MySQL Database Initialized!")
except Exception as e:
    print(f"Failed to connect to MySQL: {e}")
    print("Make sure your MySQL server (e.g. XAMPP) is running!")

# =========================================================
# UDP LISTENER (FROM BORDER ROUTER)
# =========================================================

def udp_listener():
    """Listens for incoming Wi-SUN UDP packets on port 5000"""
    try:
        sock = socket.socket(socket.AF_INET6, socket.SOCK_DGRAM)
        sock.bind(('::', UDP_LISTEN_PORT))
        print(f"[UDP] Listening for Wi-SUN packets on IPv6 port {UDP_LISTEN_PORT}")
    except Exception as e:
        print(f"[UDP] IPv6 bind failed ({e}), falling back to IPv4 0.0.0.0")
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.bind(('0.0.0.0', UDP_LISTEN_PORT))
        
    while True:
        try:
            data, addr = sock.recvfrom(1024)
            msg = data.decode('utf-8').strip()
            sender_ip = addr[0]
            
            print(f"[UDP_RECV] from {sender_ip}: {msg}")
            
            if "PROGRESS" in msg:
                try:
                    pct = float(msg.split(":")[1])
                    conn = get_db_connection()
                    c = conn.cursor()
                    c.execute("UPDATE chargers SET progress=%s, wisun_ip=%s, status='CHARGING' WHERE id='EV001'", (pct, sender_ip))
                    conn.commit()
                    conn.close()
                except Exception as e:
                    print(f"DB Error: {e}")
            elif "HELLO" in msg:
                try:
                    charger_id = msg.split(":")[1]
                    conn = get_db_connection()
                    c = conn.cursor()
                    c.execute("UPDATE chargers SET wisun_ip=%s, status='AVAILABLE' WHERE id=%s", (sender_ip, charger_id))
                    conn.commit()
                    conn.close()
                    print(f"[UDP_RECV] Successfully registered dynamic IP for {charger_id}: {sender_ip}")
                except Exception as e:
                    print(f"DB Error: {e}")
                    
        except Exception as e:
            print(f"UDP Listener error: {e}")

# Start listener thread
t = threading.Thread(target=udp_listener, daemon=True)
t.start()

# =========================================================
# API ROUTES (CALLED BY THE PWA)
# =========================================================

@app.route('/api/status/<charger_id>')
def get_status(charger_id):
    try:
        conn = get_db_connection()
        c = conn.cursor()
        c.execute("SELECT * FROM chargers WHERE id=%s", (charger_id,))
        row = c.fetchone()
        conn.close()
        
        if not row:
            return jsonify({"error": "Charger not found"}), 404
            
        return jsonify({
            "id": row[0],
            "status": row[1],
            "lat": row[2],
            "lon": row[3],
            "wisun_ip": row[4],
            "progress": row[5]
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/start/<charger_id>', methods=['POST'])
def start_charging(charger_id):
    try:
        conn = get_db_connection()
        c = conn.cursor()
        c.execute("SELECT wisun_ip FROM chargers WHERE id=%s", (charger_id,))
        row = c.fetchone()
        
        if not row or not row[0]:
            conn.close()
            return jsonify({"error": "Charger offline or no Wi-SUN IP known"}), 400
            
        wisun_ip = row[0]
        
        # Send START command over UDP to the EFR32 Node
        if ":" in wisun_ip:
            s = socket.socket(socket.AF_INET6, socket.SOCK_DGRAM)
        else:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            
        s.sendto(b"START", (wisun_ip, 5001))
        s.close()
        print(f"[API] Sent START command to {wisun_ip}:5001")
        
        # Update DB
        c.execute("UPDATE chargers SET status='CHARGING', progress=0.0 WHERE id=%s", (charger_id,))
        conn.commit()
        conn.close()
        
        return jsonify({"success": True})
        
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/stop/<charger_id>', methods=['POST'])
def stop_charging(charger_id):
    try:
        conn = get_db_connection()
        c = conn.cursor()
        c.execute("SELECT wisun_ip FROM chargers WHERE id=%s", (charger_id,))
        row = c.fetchone()
        
        if not row or not row[0]:
            conn.close()
            return jsonify({"error": "Charger offline or no Wi-SUN IP known"}), 400
            
        wisun_ip = row[0]
        
        # Send STOP command over UDP to the EFR32 Node
        if ":" in wisun_ip:
            s = socket.socket(socket.AF_INET6, socket.SOCK_DGRAM)
        else:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            
        s.sendto(b"STOP", (wisun_ip, 5001))
        s.close()
        print(f"[API] Sent STOP command to {wisun_ip}:5001")
        
        # Update DB back to AVAILABLE
        c.execute("UPDATE chargers SET status='AVAILABLE', progress=0.0 WHERE id=%s", (charger_id,))
        conn.commit()
        conn.close()
        
        return jsonify({"success": True})
        
    except Exception as e:
        return jsonify({"error": str(e)}), 500

def haversine(lat1, lon1, lat2, lon2):
    R = 6371 # km
    dLat = math.radians(lat2 - lat1)
    dLon = math.radians(lon2 - lon1)
    a = math.sin(dLat/2) * math.sin(dLat/2) + math.cos(math.radians(lat1)) \
        * math.cos(math.radians(lat2)) * math.sin(dLon/2) * math.sin(dLon/2)
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))
    return R * c

@app.route('/api/nearby/<charger_id>')
def get_nearby(charger_id):
    try:
        conn = get_db_connection()
        c = conn.cursor()
        
        c.execute("SELECT lat, lon FROM chargers WHERE id=%s", (charger_id,))
        target = c.fetchone()
        
        if not target:
            conn.close()
            return jsonify({"error": "Charger not found"}), 404
            
        c.execute("SELECT id, lat, lon FROM chargers WHERE status='AVAILABLE' AND id!=%s", (charger_id,))
        available = c.fetchall()
        conn.close()
        
        results = []
        for row in available:
            dist_km = haversine(target[0], target[1], row[1], row[2])
            results.append({
                "id": row[0],
                "distance_m": round(dist_km * 1000)
            })
            
        results.sort(key=lambda x: x["distance_m"])
        return jsonify(results[:2])
    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    # We changed the Flask API port to 5005 to avoid TCP conflicts on the Border Router.
    # The UDP Wi-SUN listener still safely uses UDP port 5000!
    app.run(host='0.0.0.0', port=5005, debug=True, use_reloader=False)
