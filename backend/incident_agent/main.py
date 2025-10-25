import os
import mysql.connector
import yaml
import time
import json
import logging
import asyncio
from typing import Any, Dict, List, Optional, Set

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

# --- Logging ---
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

# --- FastAPI App & WebSocket Hubs ---
app = FastAPI(title="1L0Gx Incident Agent")

# Allow frontend files to call the API from localhost
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

incident_ws_clients: Set[WebSocket] = set()
action_ws_clients: Set[WebSocket] = set()


@app.websocket("/ws/incidents")
async def ws_incidents(websocket: WebSocket):
    await websocket.accept()
    incident_ws_clients.add(websocket)
    try:
        while True:
            # Keep connection alive; clients usually don't send messages
            await websocket.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        incident_ws_clients.discard(websocket)


@app.websocket("/ws/actions")
async def ws_actions(websocket: WebSocket):
    await websocket.accept()
    action_ws_clients.add(websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        action_ws_clients.discard(websocket)


async def broadcast_incident(data: Dict[str, Any]):
    if not incident_ws_clients:
        return
    message = json.dumps(data, default=str)
    to_remove: List[WebSocket] = []
    for ws in list(incident_ws_clients):
        try:
            await ws.send_text(message)
        except Exception:
            to_remove.append(ws)
    for ws in to_remove:
        incident_ws_clients.discard(ws)


async def broadcast_action(data: Dict[str, Any]):
    if not action_ws_clients:
        return
    message = json.dumps(data, default=str)
    to_remove: List[WebSocket] = []
    for ws in list(action_ws_clients):
        try:
            await ws.send_text(message)
        except Exception:
            to_remove.append(ws)
    for ws in to_remove:
        action_ws_clients.discard(ws)

# --- Load Config ---
def load_config() -> Dict[str, Any]:
    """Load config from YAML and environment variables (env takes precedence)."""
    try:
        with open("../config.yaml", "r") as f:
            cfg = yaml.safe_load(f) or {}
    except FileNotFoundError:
        logging.warning("config.yaml not found; using environment variables only.")
        cfg = {}

    # Overlay with environment variables if present
    cfg.setdefault("tidb", {})
    cfg["tidb"]["host"] = os.getenv("TIDB_HOST", cfg["tidb"].get("host"))
    cfg["tidb"]["port"] = int(os.getenv("TIDB_PORT", cfg["tidb"].get("port", 4000)))
    cfg["tidb"]["user"] = os.getenv("TIDB_USER", cfg["tidb"].get("user"))
    cfg["tidb"]["password"] = os.getenv("TIDB_PASSWORD", cfg["tidb"].get("password"))
    cfg["tidb"]["database"] = os.getenv("TIDB_DATABASE", cfg["tidb"].get("database"))

    cfg.setdefault("llm", {})
    cfg["llm"]["provider"] = os.getenv("LLM_PROVIDER", cfg["llm"].get("provider"))
    cfg["llm"]["api_key"] = os.getenv("LLM_API_KEY", cfg["llm"].get("api_key"))
    cfg["llm"]["model"] = os.getenv("LLM_MODEL", cfg["llm"].get("model"))

    missing = [k for k in ("host", "port", "user", "password", "database") if not cfg["tidb"].get(k)]
    if missing:
        logging.warning(f"TiDB config incomplete or missing keys: {missing}")
    return cfg

# --- Database Connection ---
def get_db_connection(config: Dict[str, Any]):
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
            "status": "OPEN",
            "created_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            "logs": related_logs,  # send full log objects for UI rendering
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
                    "details": details,
                    "created_at": time.strftime("%Y-%m-%d %H:%M:%S"),
                })

            except Exception as e:
                logging.error(f"Failed to execute action {action_type}: {e}")
                conn.rollback()
    cursor.close()

# --- Main Loop ---
async def main_loop(config):
    conn = get_db_connection(config)
    if not conn:
        logging.error("Incident processor not started; DB connection unavailable.")
        return
    while True:
        try:
            await process_incidents(conn, config)
        except Exception as e:
            logging.error(f"Error in incident loop: {e}")
            # Attempt to reconnect on failure
            try:
                conn.close()
            except Exception:
                pass
            await asyncio.sleep(2)
            conn = get_db_connection(config)
        await asyncio.sleep(10)


# --- REST API Endpoints ---
@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/api/incidents/all")
def list_incidents():
    config = app.state.config
    conn = get_db_connection(config)
    if not conn:
        return []
    try:
        cursor = conn.cursor(dictionary=True)
        cursor.execute("""
            SELECT id, severity, status, created_at
            FROM incidents
            ORDER BY created_at DESC
            LIMIT 200
        """)
        rows = cursor.fetchall()
        return rows
    finally:
        try:
            cursor.close()
            conn.close()
        except Exception:
            pass


@app.get("/api/incidents/{incident_id}")
def get_incident(incident_id: int):
    config = app.state.config
    conn = get_db_connection(config)
    if not conn:
        return {"error": "db_unavailable"}
    try:
        cursor = conn.cursor(dictionary=True)
        cursor.execute(
            "SELECT id, log_ids, summary, severity, recommendation, status, created_at FROM incidents WHERE id=%s",
            (incident_id,),
        )
        inc = cursor.fetchone()
        if not inc:
            return {"error": "not_found"}

        log_ids = []
        try:
            if inc.get("log_ids"):
                log_ids = json.loads(inc["log_ids"]) if isinstance(inc["log_ids"], str) else inc["log_ids"]
        except Exception:
            log_ids = []

        logs: List[Dict[str, Any]] = []
        if log_ids:
            placeholders = ",".join(["%s"] * len(log_ids))
            cursor.execute(
                f"SELECT id, timestamp, source, severity, message, ip_address FROM logs WHERE id IN ({placeholders}) ORDER BY timestamp DESC",
                tuple(log_ids),
            )
            logs = cursor.fetchall()

        return {
            "id": inc["id"],
            "summary": inc["summary"],
            "severity": inc["severity"],
            "recommendation": inc["recommendation"],
            "status": inc["status"],
            "created_at": inc["created_at"],
            "logs": logs,
        }
    finally:
        try:
            cursor.close()
            conn.close()
        except Exception:
            pass


@app.get("/api/logs")
def list_logs(limit: int = 100):
    config = app.state.config
    conn = get_db_connection(config)
    if not conn:
        return []
    try:
        cursor = conn.cursor(dictionary=True)
        cursor.execute(
            "SELECT id, timestamp, source, severity, message, ip_address FROM logs ORDER BY timestamp DESC LIMIT %s",
            (limit,),
        )
        return cursor.fetchall()
    finally:
        try:
            cursor.close()
            conn.close()
        except Exception:
            pass


@app.get("/api/actions")
def list_actions(limit: int = 200):
    config = app.state.config
    conn = get_db_connection(config)
    if not conn:
        return []
    try:
        cursor = conn.cursor(dictionary=True)
        cursor.execute(
            "SELECT id, incident_id, action_type, details, status, created_at, executed_at FROM actions ORDER BY created_at DESC LIMIT %s",
            (limit,),
        )
        rows = cursor.fetchall()
        # Ensure details is JSON object, not string
        for r in rows:
            try:
                if isinstance(r.get("details"), str):
                    r["details"] = json.loads(r["details"])  # may raise
            except Exception:
                pass
        return rows
    finally:
        try:
            cursor.close()
            conn.close()
        except Exception:
            pass


@app.on_event("startup")
async def on_startup():
    # Load configuration and start background processor
    app.state.config = load_config()
    asyncio.create_task(main_loop(app.state.config))


def run():
    port_str = os.getenv("PORT") or os.getenv("API_PORT") or "5001"
    try:
        port = int(port_str)
    except ValueError:
        port = 5001
    uvicorn.run(app, host="0.0.0.0", port=port, log_level="info")


if __name__ == "__main__":
    run()
