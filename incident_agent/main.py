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