import mysql.connector
import yaml
import time
import json
import logging

# --- Logging ---
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

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

# --- LLM Analysis ---
def analyze_logs_with_llm(logs, config):
    provider = config["llm"]["provider"]
    api_key = config["llm"]["api_key"]
    model = config["llm"]["model"]

    if not api_key or api_key.startswith("YOUR_"):
        logging.warning("⚠️ No valid LLM API key found. Using mock response.")
        return {
            "summary": "Mock analysis due to missing LLM configuration.",
            "severity": "MEDIUM",
            "recommendation": "Action: BLOCK_IP\nAction: CREATE_TICKET"
        }

    log_str = "\n".join(
        [f"[{log['timestamp']}] [{log['source']}] [{log['severity']}] {log['message']}" for log in logs]
    )
    prompt = f"""
You are a cybersecurity analyst.

Logs:
{log_str}

Task:
1. Summarize the incident in 2 sentences.
2. Assign a severity (LOW, MEDIUM, HIGH, CRITICAL).
3. Suggest recommended actions like \"Action: BLOCK_IP\", \"Action: SLACK_ALERT\", \"Action: CREATE_TICKET\".
Return JSON only:
{{\"summary\": \"...\", \"severity\": \"...\", \"recommendation\": \"...\"}}
"""

    messages = [
        {"role": "system", "content": "You are a helpful cybersecurity analyst. Always return valid JSON."},
        {"role": "user", "content": prompt},
    ]

    try:
        if provider == "openai":
            from openai import OpenAI
            client = OpenAI(api_key=api_key)
        elif provider == "groq":
            from groq import Groq
            client = Groq(api_key=api_key)
        else:
            logging.error(f"Unsupported LLM provider: {provider}")
            return None

        response = client.chat.completions.create(
            model=model,
            messages=messages,
            response_format={"type": "json_object"},
        )
        content = response.choices[0].message.content.strip()
        if content.startswith("```"):
            content = content.strip("`").replace("json", "").strip()
        analysis = json.loads(content)
        logging.info(f"🤖 LLM ({provider}) returned: {analysis}")
        return analysis
    except Exception as e:
        logging.error(f"Error calling {provider} API: {e}")
        return None

# --- Incident Processing ---
def process_incidents(conn, config):
    cursor = conn.cursor(dictionary=True)

    # 1. Find new CRITICAL/ALERT logs
    cursor.execute("""
        SELECT id, timestamp, source, severity, message, ip_address
        FROM logs
        WHERE processed = FALSE AND severity IN ('CRITICAL','ALERT')
        ORDER BY timestamp DESC
        LIMIT 1
    """ )
    trigger_log = cursor.fetchone()

    if not trigger_log:
        logging.info("No new critical/alert logs.")
        cursor.close()
        return

    logging.info(f"🚨 Trigger log {trigger_log['id']}: {trigger_log['message']}")

    # 2. Find related logs (same IP ±5 minutes)
    cursor.execute("""
        SELECT id, timestamp, source, severity, message, ip_address
        FROM logs
        WHERE ip_address = %s
          AND timestamp BETWEEN %s - INTERVAL 5 MINUTE AND %s + INTERVAL 5 MINUTE
    """, (trigger_log["ip_address"], trigger_log["timestamp"], trigger_log["timestamp"]))
    related_logs = cursor.fetchall()
    log_ids = [log["id"] for log in related_logs]

    logging.info(f"📊 Found {len(related_logs)} related logs for IP {trigger_log['ip_address']}.")

    # 3. Analyze with LLM
    analysis = analyze_logs_with_llm(related_logs, config)
    if not analysis:
        cursor.close()
        return

    # Normalize recommendation: ensure it's always a string
    recommendation = analysis.get("recommendation", "")
    if isinstance(recommendation, list):
        recommendation = "\n".join(recommendation)

    try:
        # 4. Save new incident
        cursor.execute("""
            INSERT INTO incidents (log_ids, summary, severity, recommendation, status)
            VALUES (%s, %s, %s, %s, 'OPEN')
        """, (json.dumps(log_ids), analysis["summary"], analysis["severity"], recommendation))
        incident_id = cursor.lastrowid
        conn.commit()
        logging.info(f"📝 Incident {incident_id} created.")

        # 5. Create & execute actions
        process_actions(conn, incident_id, recommendation, trigger_log["ip_address"])

        # 6. Mark logs as processed
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
def process_actions(conn, incident_id, recommendation_text, ip_address):
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
                if action_type == "BLOCK_IP":
                    logging.info(f"   -> Blocking {ip_address} in firewall (simulated).")
                elif action_type == "SLACK_ALERT":
                    logging.info("   -> Sending alert to Slack (simulated).")
                elif action_type == "CREATE_TICKET":
                    logging.info("   -> Creating Jira ticket (simulated).")

                cursor.execute("UPDATE actions SET status='SUCCESS', executed_at=NOW() WHERE id=%s", (action_id,))
                conn.commit()
                logging.info(f"✅ Action {action_id} marked SUCCESS")
            except Exception as e:
                logging.error(f"Failed to execute action {action_type}: {e}")
                conn.rollback()
    cursor.close()

# --- Main ---
if __name__ == "__main__":
    config = load_config()
    conn = get_db_connection(config)
    if not conn:
        exit(1)

    logging.info("🚀 1L0Gx Incident Agent running. Polling every 10s...")
    try:
        while True:
            process_incidents(conn, config)
            time.sleep(10)
    except KeyboardInterrupt:
        logging.info("👋 Agent stopped by user.")
    finally:
        if conn.is_connected():
            conn.close()
            logging.info("🔒 DB connection closed.")
