import sqlite3
import json
from pathlib import Path

DB_PATH = "migration.db"


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with get_db() as conn:
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS jobs (
            id TEXT PRIMARY KEY,
            filename TEXT,
            source_format TEXT,
            target_format TEXT,
            status TEXT DEFAULT 'queued',
            created_at TEXT,
            updated_at TEXT,
            hitl_status TEXT DEFAULT 'pending',
            report JSON,
            output_path TEXT,
            ollama_model TEXT
        );

        CREATE TABLE IF NOT EXISTS agent_steps (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            job_id TEXT,
            agent_name TEXT,
            status TEXT DEFAULT 'pending',
            message TEXT,
            started_at TEXT,
            completed_at TEXT,
            output JSON,
            ai_log TEXT,
            FOREIGN KEY(job_id) REFERENCES jobs(id)
        );
        """)
