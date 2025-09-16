package main

import (
	"database/sql"
	"encoding/json"
	"fmt"
	"log"
	"math/rand"
	"net/http"
	"os"
	"sync"
	"time"

	_ "github.com/go-sql-driver/mysql"
	"github.com/gorilla/websocket"
	"gopkg.in/yaml.v3"
)

// Config struct for database credentials
type Config struct {
	TiDB struct {
		Host     string `yaml:"host"`
		Port     int    `yaml:"port"`
		User     string `yaml:"user"`
		Password string `yaml:"password"`
		Database string `yaml:"database"`
	} `yaml:"tidb"`
}

// LogEntry represents a single security log.
type LogEntry struct {
	ID        int64     `json:"id,omitempty"`
	Timestamp time.Time `json:"timestamp"`
	Source    string    `json:"source"`
	Severity  string    `json:"severity"`
	Message   string    `json:"message"`
	IPAddress string    `json:"ip_address"`
}

// WebSocket hub for broadcasting logs
var (
	clients   = make(map[*websocket.Conn]bool)
	clientsMu sync.Mutex
	upgrader  = websocket.Upgrader{
		CheckOrigin: func(r *http.Request) bool { return true }, // allow all origins for hackathon
	}
)

// Generates a random vector embedding (mock).
func generateMockEmbedding(dims int) string {
	vec := make([]float32, dims)
	for i := range vec {
		vec[i] = rand.Float32()
	}
	return fmt.Sprintf("[%s]", joinFloat32(vec, ", "))
}

func joinFloat32(slice []float32, sep string) string {
	str := ""
	for i, v := range slice {
		if i > 0 {
			str += sep
		}
		str += fmt.Sprintf("%.6f", v)
	}
	return str
}

// generateRandomLog creates a new LogEntry with randomized data.
func generateRandomLog() LogEntry {
	sources := []string{"Firewall", "Auth", "IDS", "System", "WebApp"}
	severities := []string{"INFO", "WARNING", "ALERT", "CRITICAL"}
	messages := map[string]string{
		"Firewall": "Blocked suspicious traffic",
		"Auth":     "Failed login attempt",
		"IDS":      "Potential SQL injection detected",
		"System":   "Service unexpectedly stopped",
		"WebApp":   "Cross-site scripting attempt",
		"CRITICAL": "Multiple brute-force attempts detected on account 'admin'",
	}
	ips := []string{"203.0.113.45", "198.51.100.2", "192.0.2.88", "203.0.113.101", "198.51.100.14"}

	source := sources[rand.Intn(len(sources))]
	severity := severities[rand.Intn(len(severities))]

	var message string
	if severity == "CRITICAL" && rand.Float32() > 0.5 {
		message = messages["CRITICAL"]
	} else {
		message = messages[source]
	}

	return LogEntry{
		Timestamp: time.Now(),
		Source:    source,
		Severity:  severity,
		Message:   fmt.Sprintf("%s for user 'testuser'.", message),
		IPAddress: ips[rand.Intn(len(ips))],
	}
}

// --- WebSocket Handlers ---
func wsHandler(w http.ResponseWriter, r *http.Request) {
	conn, err := upgrader.Upgrade(w, r, nil)
	if err != nil {
		log.Println("⚠️ WebSocket upgrade failed:", err)
		return
	}
	defer conn.Close()

	clientsMu.Lock()
	clients[conn] = true
	clientsMu.Unlock()

	log.Println("🔌 Client connected via WebSocket")

	// Keep connection alive
	for {
		if _, _, err := conn.NextReader(); err != nil {
			break
		}
	}

	clientsMu.Lock()
	delete(clients, conn)
	clientsMu.Unlock()
	log.Println("❌ Client disconnected")
}

func broadcastLog(entry LogEntry) {
	clientsMu.Lock()
	defer clientsMu.Unlock()

	data, _ := json.Marshal(entry)
	for conn := range clients {
		if err := conn.WriteMessage(websocket.TextMessage, data); err != nil {
			log.Println("⚠️ Failed to send log to client:", err)
			conn.Close()
			delete(clients, conn)
		}
	}
}

// --- Main ---
func main() {
	log.Println("🚀 Starting 1L0Gx Log Ingestor...")

	// Load config
	configFile, err := os.ReadFile("../config.yaml")
	if err != nil {
		log.Fatalf("Failed to read config file: %v", err)
	}
	var config Config
	if err := yaml.Unmarshal(configFile, &config); err != nil {
		log.Fatalf("Failed to parse config: %v", err)
	}

	// Build DSN
	dsn := fmt.Sprintf("%s:%s@tcp(%s:%d)/%s?tls=true",
		config.TiDB.User,
		config.TiDB.Password,
		config.TiDB.Host,
		config.TiDB.Port,
		config.TiDB.Database,
	)

	// Connect to TiDB
	db, err := sql.Open("mysql", dsn)
	if err != nil {
		log.Fatalf("Failed to connect to TiDB: %v", err)
	}
	defer db.Close()

	db.SetConnMaxLifetime(time.Minute * 3)
	db.SetMaxOpenConns(10)
	db.SetMaxIdleConns(10)

	if err := db.Ping(); err != nil {
		log.Fatalf("Ping to TiDB failed: %v", err)
	}
	log.Println("✅ Connected to TiDB Serverless.")

	// Start WebSocket server
	http.HandleFunc("/ws", wsHandler)
	go func() {
		log.Println("🌐 WebSocket server running on :8080/ws")
		if err := http.ListenAndServe(":8080", nil); err != nil {
			log.Fatalf("WebSocket server failed: %v", err)
		}
	}()

	// Log generation loop
	ticker := time.NewTicker(2 * time.Second)
	defer ticker.Stop()

	for range ticker.C {
		entry := generateRandomLog()
		embedding := generateMockEmbedding(768)

		res, err := db.Exec(`
			INSERT INTO logs (timestamp, source, severity, message, ip_address, embedding)
			VALUES (?, ?, ?, ?, ?, ?)`,
			entry.Timestamp, entry.Source, entry.Severity, entry.Message, entry.IPAddress, embedding,
		)
		if err != nil {
			log.Printf("❌ Failed to insert log: %v", err)
			continue
		}
		id, _ := res.LastInsertId()
		entry.ID = id

		log.Printf("📥 Ingested log: [%s] %s - %s", entry.Severity, entry.Source, entry.Message)

		// Broadcast to WebSocket clients
		broadcastLog(entry)
	}
}
