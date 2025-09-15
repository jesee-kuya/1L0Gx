package main

import (
	"database/sql"
	"fmt"
	"log"
	"math/rand"
	"os"
	"time"

	_ "github.com/go-sql-driver/mysql"
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
	Timestamp time.Time
	Source    string
	Severity  string
	Message   string
	IPAddress string
}

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
