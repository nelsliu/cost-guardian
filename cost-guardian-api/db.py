# db.py
import sqlite3
from config import DB_PATH

def get_conn():
    conn = sqlite3.connect(DB_PATH)
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
            int(row.get("promptTokens") or 0),
            int(row.get("completionTokens") or 0),
            int(row.get("totalTokens") or 0),
            float(row.get("estimatedCostUSD") or 0.0),
        ))
        conn.commit()