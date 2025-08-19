import sqlite3
import json

DB_PATH = "analyses.db"

def init_db():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS analyses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source TEXT NOT NULL,
            analysis_summary TEXT NOT NULL,
            status TEXT NOT NULL, -- 'approved', 'flagged'
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()
    conn.close()

def save_analysis(source, analysis_summary, status):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO analyses (source, analysis_summary, status) VALUES (?, ?, ?)",
        (source, analysis_summary, status)
    )
    conn.commit()
    conn.close()

def get_all_analyses():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT id, source, analysis_summary, status, timestamp FROM analyses ORDER BY timestamp DESC")
    rows = cursor.fetchall()
    conn.close()
    return rows