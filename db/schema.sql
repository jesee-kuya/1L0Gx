-- 1L0Gx: TiDB Serverless Schema
-- This script creates the necessary tables for the cybersecurity incident response agent.

-- Table for raw and structured security log entries.
CREATE TABLE IF NOT EXISTS logs (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    timestamp DATETIME NOT NULL,
    source VARCHAR(50),         -- e.g., Firewall, Auth, IDS, System
    severity VARCHAR(20),       -- e.g., INFO, WARNING, ALERT, CRITICAL
    message TEXT,               -- full log line
    ip_address VARCHAR(45),     -- IPv4 or IPv6
    embedding VECTOR(768),      -- vector embedding of message for semantic search
    processed BOOLEAN DEFAULT FALSE, -- Flag to indicate if the log has been processed by the agent
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Create an index on the timestamp and severity for faster querying of new, severe logs.
CREATE INDEX idx_log_time_severity ON logs (timestamp, severity);
CREATE INDEX idx_log_processed ON logs (processed);


-- Table for storing analyzed incidents after LLM processing.
CREATE TABLE IF NOT EXISTS incidents (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    log_ids JSON,               -- array of related log IDs
    summary TEXT,               -- human-readable incident summary
    severity VARCHAR(20),       -- LOW, MEDIUM, HIGH, CRITICAL
    recommendation TEXT,        -- recommended actions
    status VARCHAR(20) DEFAULT 'OPEN',  -- OPEN, MITIGATED, CLOSED
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Table for tracking automated responses executed by the agent.
CREATE TABLE IF NOT EXISTS actions (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    incident_id BIGINT,
    action_type VARCHAR(50),    -- e.g., BLOCK_IP, SLACK_ALERT, CREATE_TICKET
    details JSON,               -- metadata about the action
    status VARCHAR(20) DEFAULT 'PENDING', -- PENDING, SUCCESS, FAILED
    executed_at TIMESTAMP NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (incident_id) REFERENCES incidents(id)
);

-- Optional table for caching results from external IP reputation APIs.
CREATE TABLE IF NOT EXISTS ip_reputation (
    ip_address VARCHAR(45) PRIMARY KEY,
    risk_score INT,             -- 0–100
    last_checked TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Add a vector index on the embedding column for fast semantic search.
-- Note: The exact syntax for creating a vector index may vary based on TiDB version.
-- This is a representative example.
-- ALTER TABLE logs ADD INDEX embedding_index (embedding) IVFFLAT;

