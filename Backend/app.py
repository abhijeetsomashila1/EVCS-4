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
    conn = mysql.connector.connect(
        host=MYSQL_HOST,
        user=MYSQL_USER,
        password=MYSQL_PASSWORD
    )
    c = conn.cursor()
    c.execute(f"CREATE DATABASE IF NOT EXISTS {MYSQL_DB}")
    conn.commit()
    conn.close()
    
    conn = get_db_connection()
    c = conn.cursor()
    # Aligning with teammate's schema requirements
    c.execute('''
        CREATE TABLE IF NOT EXISTS chargers (
            charger_id VARCHAR(50) PRIMARY KEY,
            status VARCHAR(50),
            latitude FLOAT,
            longitude FLOAT,
            wisun_ip VARCHAR(100),
            progress FLOAT
        )
    ''')
    
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
    print("MySQL Database Initialized (Merged Schema)!")
except Exception as e:
    print(f"Failed to connect to MySQL: {e}")

# =========================================================
# UDP LISTENER (FROM BORDER ROUTER)
# =========================================================

def udp_listener():
    try:
        sock = socket.socket(socket.AF_INET6, socket.SOCK_DGRAM)
        sock.bind(('::', UDP_LISTEN_PORT))
    except Exception as e:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.bind(('0.0.0.0', UDP_LISTEN_PORT))
        
    while True:
        try:
            data, addr = sock.recvfrom(1024)
            msg = data.decode('utf-8').strip()
            sender_ip = addr[0]
            
            if "PROGRESS" in msg:
                try:
                    pct = float(msg.split(":")[1])
                    conn = get_db_connection()
                    c = conn.cursor()
                    c.execute("UPDATE chargers SET progress=%s, wisun_ip=%s, status='CHARGING' WHERE charger_id='EV001'", (pct, sender_ip))
                    conn.commit()
                    conn.close()
                except Exception as e:
                    print(f"DB Error: {e}")
            elif "HELLO" in msg:
                try:
                    charger_id = msg.split(":")[1]
                    conn = get_db_connection()
                    c = conn.cursor()
                    c.execute("UPDATE chargers SET wisun_ip=%s, status='AVAILABLE' WHERE charger_id=%s", (sender_ip, charger_id))
                    conn.commit()
                    conn.close()
                except Exception as e:
                    print(f"DB Error: {e}")
        except Exception as e:
            pass

t = threading.Thread(target=udp_listener, daemon=True)
t.start()

# =========================================================
# TEAMMATE's ROUTES
# =========================================================

@app.route("/")
def home():
    return render_template("charger.html")

@app.route("/page/<charger_id>")
def charger_page(charger_id):
    return render_template("charger.html")

@app.route("/charger/<charger_id>")
def get_charger(charger_id):
    db = get_db_connection()
    cursor = db.cursor(dictionary=True)
    query = "SELECT * FROM chargers WHERE charger_id=%s"
    cursor.execute(query,(charger_id,))
    charger = cursor.fetchone()
    cursor.close()
    db.close()
    return jsonify(charger)

@app.route("/chargers")
def get_all_chargers():
    db = get_db_connection()
    cursor = db.cursor(dictionary=True)
    cursor.execute("SELECT * FROM chargers")
    chargers = cursor.fetchall()
    cursor.close()
    db.close()
    return jsonify(chargers)

@app.route("/update_status", methods=["POST"])
def update_status():
    data = request.json
    charger_id = data["charger_id"]
    status = data["status"]
    
    db = get_db_connection()
    cursor = db.cursor()
    query = "UPDATE chargers SET status=%s WHERE charger_id=%s"
    cursor.execute(query, (status, charger_id))
    db.commit()
    cursor.close()
    db.close()
    
    return jsonify({"message": "Status updated successfully"})

@app.route("/nearby/<charger_id>")
def nearby_chargers(charger_id):
    db = get_db_connection()
    cursor = db.cursor(dictionary=True)
    
    cursor.execute("SELECT latitude, longitude FROM chargers WHERE charger_id=%s", (charger_id,))
    current = cursor.fetchone()
    
    cursor.execute("SELECT * FROM chargers WHERE status='AVAILABLE' AND charger_id!=%s", (charger_id,))
    chargers = cursor.fetchall()
    cursor.close()
    db.close()

    if not current:
        return jsonify({"error": "Charger not found"}), 404

    nearby = []
    for charger in chargers:
        distance = math.sqrt(
            (current["latitude"]-charger["latitude"])**2 +
            (current["longitude"]-charger["longitude"])**2
        )
        charger["distance"] = distance
        nearby.append(charger)

    return jsonify(nearby)


# =========================================================
# REACT PWA CORE ROUTES (Wi-SUN ENABLED)
# =========================================================

@app.route('/api/status/<charger_id>')
def api_get_status(charger_id):
    try:
        conn = get_db_connection()
        c = conn.cursor(dictionary=True)
        c.execute("SELECT * FROM chargers WHERE charger_id=%s", (charger_id,))
        row = c.fetchone()
        conn.close()
        
        if not row:
            return jsonify({"error": "Charger not found"}), 404
            
        # Map teammate's database schema back to React's expected JSON schema
        return jsonify({
            "id": row["charger_id"],
            "status": row["status"],
            "lat": row["latitude"],
            "lon": row["longitude"],
            "wisun_ip": row["wisun_ip"],
            "progress": row["progress"]
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/start/<charger_id>', methods=['POST'])
def api_start_charging(charger_id):
    try:
        conn = get_db_connection()
        c = conn.cursor(dictionary=True)
        c.execute("SELECT wisun_ip FROM chargers WHERE charger_id=%s", (charger_id,))
        row = c.fetchone()
        
        if not row or not row["wisun_ip"]:
            conn.close()
            return jsonify({"error": "Charger offline or no Wi-SUN IP known"}), 400
            
        wisun_ip = row["wisun_ip"]
        
        # Send START command over UDP to the EFR32 Node
        if ":" in wisun_ip:
            s = socket.socket(socket.AF_INET6, socket.SOCK_DGRAM)
        else:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            
        s.sendto(b"START", (wisun_ip, 5001))
        s.close()
        
        # Update DB
        c.execute("UPDATE chargers SET status='CHARGING', progress=0.0 WHERE charger_id=%s", (charger_id,))
        conn.commit()
        conn.close()
        
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/stop/<charger_id>', methods=['POST'])
def api_stop_charging(charger_id):
    try:
        conn = get_db_connection()
        c = conn.cursor(dictionary=True)
        c.execute("SELECT wisun_ip FROM chargers WHERE charger_id=%s", (charger_id,))
        row = c.fetchone()
        
        if not row or not row["wisun_ip"]:
            conn.close()
            return jsonify({"error": "Charger offline or no Wi-SUN IP known"}), 400
            
        wisun_ip = row["wisun_ip"]
        
        # Send STOP command over UDP to the EFR32 Node
        if ":" in wisun_ip:
            s = socket.socket(socket.AF_INET6, socket.SOCK_DGRAM)
        else:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            
        s.sendto(b"STOP", (wisun_ip, 5001))
        s.close()
        
        # Update DB back to AVAILABLE
        c.execute("UPDATE chargers SET status='AVAILABLE', progress=0.0 WHERE charger_id=%s", (charger_id,))
        conn.commit()
        conn.close()
        
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5005, debug=True, use_reloader=False)
