import mysql.connector
import yaml
import time
import json
import logging
import asyncio
import websockets

# --- Logging ---
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

# --- WebSocket Clients ---
incident_clients = set()
action_clients = set()

async def incident_ws_handler(websocket):
    incident_clients.add(websocket)
    try:
        async for _ in websocket:
            pass
    finally:
        incident_clients.remove(websocket)

async def action_ws_handler(websocket):
    action_clients.add(websocket)
    try:
        async for _ in websocket:
            pass
    finally:
        action_clients.remove(websocket)

async def broadcast_incident(data):
    if incident_clients:
        await asyncio.gather(*[ws.send(json.dumps(data)) for ws in incident_clients])

async def broadcast_action(data):
    if action_clients:
        await asyncio.gather(*[ws.send(json.dumps(data)) for ws in action_clients])

# --- Load Config ---
def load_config():
    try:
        with open("../config.yaml", "r") as f:
            return yaml.safe_load(f)
    except FileNotFoundError:
        logging.error("config.yaml not found.")
        exit(1)

# --- Database Connection ---
def get_db_connection(config):
    try:
        conn = mysql.connector.connect(
            host=config["tidb"]["host"],
            port=config["tidb"]["port"],
            user=config["tidb"]["user"],
            password=config["tidb"]["password"],
            database=config["tidb"]["database"],
            ssl_verify_identity=True,
            ssl_ca="/etc/ssl/certs/ca-certificates.crt",
        )
        logging.info("✅ Connected to TiDB Serverless.")
        return conn
    except Exception as e:
        logging.error(f"Database connection failed: {e}")
        return None

# --- Mock LLM Analysis ---
def analyze_logs_with_llm(logs, config):
    if not logs:
        return None

    # For hackathon demo, just return mock AI output
    return {
        "summary": f"Detected {len(logs)} related suspicious logs for IP {logs[0]['ip_address']}.",
        "severity": "HIGH",
        "recommendation": "Action: BLOCK_IP\nAction: SLACK_ALERT\nAction: CREATE_TICKET"
    }

# --- Incident Processing ---
async def process_incidents(conn, config):
    cursor = conn.cursor(dictionary=True)

    cursor.execute("""
        SELECT id, timestamp, source, severity, message, ip_address
        FROM logs
        WHERE processed = FALSE AND severity IN ('CRITICAL','ALERT')
        ORDER BY timestamp DESC
        LIMIT 1
    """)
    trigger_log = cursor.fetchone()

    if not trigger_log:
        cursor.close()
        return

    logging.info(f"🚨 Trigger log {trigger_log['id']}: {trigger_log['message']}")

    cursor.execute("""
        SELECT id, timestamp, source, severity, message, ip_address
        FROM logs
        WHERE ip_address = %s
          AND timestamp BETWEEN %s - INTERVAL 5 MINUTE AND %s + INTERVAL 5 MINUTE
    """, (trigger_log["ip_address"], trigger_log["timestamp"], trigger_log["timestamp"]))
    related_logs = cursor.fetchall()
    log_ids = [log["id"] for log in related_logs]

    logging.info(f"📊 Found {len(related_logs)} related logs for IP {trigger_log['ip_address']}.")

    # Analyze with LLM
    analysis = analyze_logs_with_llm(related_logs, config)
    if not analysis:
        cursor.close()
        return

    recommendation = analysis["recommendation"]
    try:
        cursor.execute("""
            INSERT INTO incidents (log_ids, summary, severity, recommendation, status)
            VALUES (%s, %s, %s, %s, 'OPEN')
        """, (json.dumps(log_ids), analysis["summary"], analysis["severity"], recommendation))
        incident_id = cursor.lastrowid
        conn.commit()
        logging.info(f"📝 Incident {incident_id} created.")

        # Broadcast incident to frontend
        await broadcast_incident({
            "id": incident_id,
            "summary": analysis["summary"],
            "severity": analysis["severity"],
            "recommendation": recommendation,
            "logs": log_ids
        })

        # Create & execute actions
        await process_actions(conn, incident_id, recommendation, trigger_log["ip_address"])

        # Mark logs processed
        if log_ids:
            placeholders = ",".join(["%s"] * len(log_ids))
            cursor.execute(f"UPDATE logs SET processed = TRUE WHERE id IN ({placeholders})", tuple(log_ids))
            conn.commit()
            logging.info(f"✅ {len(log_ids)} logs marked as processed.")

    except Exception as e:
        logging.error(f"Error saving incident: {e}")
        conn.rollback()
    finally:
        cursor.close()

# --- Action Execution ---
async def process_actions(conn, incident_id, recommendation_text, ip_address):
    cursor = conn.cursor()
    for line in recommendation_text.splitlines():
        if "Action:" in line:
            action_type = line.split("Action:")[1].strip().split()[0]
            details = {"ip": ip_address, "note": "Auto-response by 1L0Gx"}
            try:
                cursor.execute("""
                    INSERT INTO actions (incident_id, action_type, details, status)
                    VALUES (%s, %s, %s, 'PENDING')
                """, (incident_id, action_type, json.dumps(details)))
                action_id = cursor.lastrowid
                conn.commit()
                logging.info(f"⚡ Action {action_type} created (ID={action_id})")

                # Simulate execution
                logging.info(f"--- Executing {action_type} ---")
                cursor.execute("UPDATE actions SET status='SUCCESS', executed_at=NOW() WHERE id=%s", (action_id,))
                conn.commit()
                logging.info(f"✅ Action {action_id} marked SUCCESS")

                # Broadcast action to frontend
                await broadcast_action({
                    "id": action_id,
                    "incident_id": incident_id,
                    "type": action_type,
                    "status": "SUCCESS",
                    "details": details
                })

            except Exception as e:
                logging.error(f"Failed to execute action {action_type}: {e}")
                conn.rollback()
    cursor.close()

# --- Main Loop ---
async def main_loop(config):
    conn = get_db_connection(config)
    if not conn:
        return
    while True:
        await process_incidents(conn, config)
        await asyncio.sleep(10)

async def start_server(config):
    ws_incidents = websockets.serve(incident_ws_handler, "0.0.0.0", 8765, ping_interval=None)
    ws_actions = websockets.serve(action_ws_handler, "0.0.0.0", 8766, ping_interval=None)

    await asyncio.gather(
        ws_incidents,
        ws_actions,
        main_loop(config)
    )

if __name__ == "__main__":
    config = load_config()
    asyncio.run(start_server(config))
