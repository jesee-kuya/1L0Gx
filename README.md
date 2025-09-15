# 1L0Gx - Cybersecurity Incident Response Agent

**1L0Gx** is a proof-of-concept cybersecurity incident response agent built for the TiDB AgentX Hackathon. It demonstrates a multi-step agent workflow that leverages Go, Python, Large Language Models (LLMs), and TiDB Serverless with vector search to automate the detection, analysis, and response to security threats.

## 🚀 Core Features

- **Log Ingestion:** A Go-based service generates and ingests security logs into TiDB.
- **Vector-Powered Search:** Finds related security events using vector embeddings for semantic search.
- **LLM-Powered Analysis:** Uses publicly available LLMs (like OpenAI's GPT-4o mini) to analyze correlated logs, summarize incidents, and suggest actions.
- **Automated Workflow:** Creates incidents and triggers response actions in a structured, multi-step process.
- **TiDB Serverless Backend:** All data—logs, embeddings, incidents, and actions—is stored in TiDB Serverless.

## 🏛️ Architecture

1L0Gx consists of two main services:

1.  **Log Ingestor (`log_ingestor/`)**: A Go application that simulates the generation of security logs from various sources (e.g., Firewall, Auth, IDS). It connects to TiDB Serverless and writes these logs to the `logs` table. In this version, vector embeddings are mocked as random data for demonstration.

2.  **Incident Agent (`incident_agent/`)**: A Python application that acts as the "brain" of the system.
    - It polls the `logs` table for new, high-severity, unprocessed events.
    - When a trigger event is found, it (conceptually) uses vector search to find similar logs.
    - It bundles these logs and sends them to an LLM for analysis.
    - The LLM's response (summary, severity, recommendation) is used to create a new entry in the `incidents` table.
    - It then creates and "executes" automated responses (e.g., `BLOCK_IP`, `SLACK_ALERT`) by adding them to the `actions` table and printing to the console.

## 🔧 Setup and Installation

### 1. TiDB Serverless Database

1.  **Create a TiDB Serverless Cluster:** Go to [TiDB Cloud](https://tidbcloud.com/) and create a free Serverless cluster.
2.  **Get Connection String:** In your cluster dashboard, click "Connect" and get the connection string (using the "General" format). You will also need the password you set during cluster creation.
3.  **Run Schema Script:** Connect to your database using a MySQL client or the built-in SQL editor and run the contents of `db/schema.sql` to create the necessary tables.

### 2. Configuration

1.  **Copy the Example:** `cp config.yaml.example config.yaml` (if one exists) or just edit `config.yaml`.
2.  **Edit `config.yaml`:**
    - `tidb.connection_string`: Paste your full TiDB Serverless connection string. Make sure to replace the password placeholder with your actual password.
    - `llm.api_key`: Enter your API key for the chosen LLM provider (e.g., OpenAI).

### 3. Running the Services

You will need to run the two services in separate terminals.

#### Terminal 1: Log Ingestor (Go)

```bash
# Navigate to the Go application directory
cd log_ingestor

# Tidy dependencies
go mod tidy

# Run the application
# It will start generating and ingesting logs immediately.
go run main.go
```

#### Terminal 2: Incident Agent (Python)

```bash
# Navigate to the Python application directory
cd incident_agent

# Create a virtual environment (recommended)
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Run the agent
# The agent will start polling for new incidents.
python3 main.py
```

##  workflow_state

The agent will now be running. The Go application will continuously feed logs into the `logs` table. The Python agent will periodically scan these logs, process them, create incidents, and simulate actions. You can monitor the output in both terminals and query the tables in your TiDB database to see the results.
