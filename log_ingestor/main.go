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