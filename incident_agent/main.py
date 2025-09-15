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
3. Suggest recommended actions like "Action: BLOCK_IP", "Action: SLACK_ALERT", "Action: CREATE_TICKET".
Return JSON only:
{{"summary": "...", "severity": "...", "recommendation": "..."}}
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
