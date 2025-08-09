# db.py
import os
import sqlite3

DB_FILENAME = os.environ.get("DB_FILENAME", "cost_guardian.db")

def get_conn():
    conn = sqlite3.connect(DB_FILENAME)
    conn.row_factory = sqlite3.Row
    return conn

def migrate():
    with get_conn() as conn:
        c = conn.cursor()
        c.execute("""
            CREATE TABLE IF NOT EXISTS usage_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT,
                model TEXT,
                promptTokens INTEGER,
                completionTokens INTEGER,
                totalTokens INTEGER,
                estimatedCostUSD REAL
            );
        """)
        conn.commit()

def insert_usage(row: dict):
    with get_conn() as conn:
        c = conn.cursor()
        c.execute("""
            INSERT INTO usage_log (
                timestamp, model, promptTokens, completionTokens, totalTokens, estimatedCostUSD
            ) VALUES (?, ?, ?, ?, ?, ?)
        """, (
            row.get("timestamp"),
            row.get("model"),
            int(row.get("promptTokens", 0)),
            int(row.get("completionTokens", 0)),
            int(row.get("totalTokens", 0)),
            float(row.get("estimatedCostUSD", 0.0)),
        ))
        conn.commit()