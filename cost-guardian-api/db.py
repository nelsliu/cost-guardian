# db.py
import sqlite3
import os
import shutil
import time
import logging
from config import DB_PATH, BASE_DIR

def _ensure_db_dir_and_migrate():
    """Ensure data directory exists and handle legacy database migration with race protection."""
    # Create directory if it doesn't exist
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    
    # Skip migration if target already exists
    if os.path.exists(DB_PATH):
        return
    
    # File lock to prevent migration races between API and worker
    lock_file = os.path.join(os.path.dirname(DB_PATH), ".migrate.lock")
    try:
        # Exclusive creation - fails if another process is migrating
        with open(lock_file, 'x') as f:
            f.write(f"Migration started by PID {os.getpid()}")
            
            # Migration candidates in order of preference:
            # 1. data/cost_guardian.db (newer location, preferred)
            # 2. root cost_guardian.db (legacy location)
            # 3. root usage_log.sqlite (legacy location)
            candidates = [
                os.path.join(os.path.dirname(DB_PATH), "cost_guardian.db"),
                os.path.join(BASE_DIR, "cost_guardian.db"),
                os.path.join(BASE_DIR, "usage_log.sqlite")
            ]
            
            for legacy in candidates:
                if os.path.exists(legacy):
                    shutil.move(legacy, DB_PATH)
                    logging.info("Migrated legacy DB from %s to %s", legacy, DB_PATH)
                    break
                    
    except FileExistsError:
        # Another process is migrating, wait briefly then continue
        logging.debug("Migration lock exists, waiting for completion...")
        time.sleep(0.1)
    except Exception as e:
        logging.warning("Migration lock handling failed: %s", e)
    finally:
        # Clean up lock file (best effort)
        try:
            os.remove(lock_file)
        except FileNotFoundError:
            pass  # Another process cleaned it up
        except Exception as e:
            logging.warning("Failed to remove migration lock: %s", e)

def get_conn():
    """Get SQLite connection with proper setup and optimizations."""
    _ensure_db_dir_and_migrate()
    
    # Connect with timeout to reduce "database is locked" errors
    conn = sqlite3.connect(
        DB_PATH,
        timeout=30.0,  # 30 second timeout for lock conflicts
        check_same_thread=True  # Keep default since we don't share connections across threads
    )
    conn.row_factory = sqlite3.Row
    
    # Set SQLite pragmas for performance and reliability (best effort)
    try:
        conn.execute("PRAGMA journal_mode=WAL;")       # Better concurrency
        conn.execute("PRAGMA synchronous=NORMAL;")     # Performance/safety balance
        conn.execute("PRAGMA foreign_keys=ON;")        # Data integrity
        conn.execute("PRAGMA busy_timeout=30000;")     # 30 second busy timeout
    except Exception as e:
        # Don't crash on unsupported pragmas, just log
        logging.debug("Failed to set SQLite pragmas: %s", e)
    
    return conn

def migrate():
    with get_conn() as conn:
        c = conn.cursor()
        
        # Create usage_log table
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
        
        # Create api_keys table
        c.execute("""
            CREATE TABLE IF NOT EXISTS api_keys (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                label TEXT NOT NULL,
                provider TEXT NOT NULL DEFAULT 'openai',
                enc_key BLOB NOT NULL,
                active INTEGER NOT NULL DEFAULT 1,
                last_ok TEXT NULL,
                created_at TEXT NOT NULL DEFAULT (DATETIME('now'))
            );
        """)
        
        # Add api_key_id column to usage_log if it doesn't exist
        try:
            c.execute("ALTER TABLE usage_log ADD COLUMN api_key_id INTEGER NULL")
        except Exception:
            # Column already exists, ignore
            pass
        
        # Create ingest_tokens table
        c.execute("""
            CREATE TABLE IF NOT EXISTS ingest_tokens (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                label TEXT NOT NULL,
                token TEXT NOT NULL UNIQUE,
                active INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL DEFAULT (DATETIME('now')),
                last_seen_at TEXT NULL
            );
        """)
        
        # Add new columns to usage_log if they don't exist
        try:
            c.execute("ALTER TABLE usage_log ADD COLUMN ingest_token_id INTEGER NULL REFERENCES ingest_tokens(id) ON DELETE SET NULL")
        except Exception:
            # Column already exists, ignore
            pass
            
        try:
            c.execute("ALTER TABLE usage_log ADD COLUMN source TEXT NOT NULL DEFAULT 'ingest'")
        except Exception:
            # Column already exists, ignore
            pass
            
        try:
            c.execute("ALTER TABLE usage_log ADD COLUMN event_id TEXT NULL")
        except Exception:
            # Column already exists, ignore
            pass
        
        # Create indexes for performance
        c.execute("CREATE INDEX IF NOT EXISTS idx_usage_key_ts ON usage_log(api_key_id, timestamp)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_usage_ingest_ts ON usage_log(ingest_token_id, timestamp)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_keys_active ON api_keys(active)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_ingest_tokens_active ON ingest_tokens(active)")
        
        # Create filtering indexes for dashboard performance  
        c.execute("CREATE INDEX IF NOT EXISTS idx_usage_ts ON usage_log(timestamp)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_usage_model_ts ON usage_log(model, timestamp)")
        
        # Create unique constraint for labels to prevent duplicates
        c.execute("CREATE UNIQUE INDEX IF NOT EXISTS ux_api_keys_label ON api_keys(label)")
        c.execute("CREATE UNIQUE INDEX IF NOT EXISTS ux_ingest_tokens_label ON ingest_tokens(label)")
        c.execute("CREATE UNIQUE INDEX IF NOT EXISTS ux_ingest_tokens_token ON ingest_tokens(token)")
        
        # Create unique idempotency index for event deduplication
        c.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_usage_event ON usage_log(ingest_token_id, event_id) WHERE event_id IS NOT NULL")
        
        conn.commit()

def insert_usage(row: dict, api_key_id: int = None, ingest_token_id: int = None, source: str = "ingest", event_id: str = None):
    with get_conn() as conn:
        c = conn.cursor()
        c.execute("""
            INSERT INTO usage_log (
                timestamp, model, promptTokens, completionTokens, totalTokens, estimatedCostUSD, 
                api_key_id, ingest_token_id, source, event_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            row.get("timestamp"),
            row.get("model"),
            int(row.get("promptTokens") or 0),
            int(row.get("completionTokens") or 0),
            int(row.get("totalTokens") or 0),
            float(row.get("estimatedCostUSD") or 0.0),
            api_key_id,
            ingest_token_id,
            source,
            event_id,
        ))
        conn.commit()
        return c.lastrowid

def add_api_key(label: str, provider: str, enc_key: bytes) -> int:
    """Add a new encrypted API key to the database.
    
    Args:
        label: User-friendly label for the key
        provider: The AI provider (e.g., 'openai')
        enc_key: The encrypted API key as bytes
        
    Returns:
        int: The ID of the newly created key
    """
    with get_conn() as conn:
        c = conn.cursor()
        c.execute("""
            INSERT INTO api_keys (label, provider, enc_key)
            VALUES (?, ?, ?)
        """, (label, provider, enc_key))
        conn.commit()
        return c.lastrowid

def list_api_keys() -> list:
    """List all API keys with metadata (excluding the encrypted key).
    
    Returns:
        list: List of dictionaries containing key metadata
    """
    with get_conn() as conn:
        c = conn.cursor()
        c.execute("""
            SELECT id, label, provider, active, last_ok, created_at
            FROM api_keys
            ORDER BY created_at DESC
        """)
        return [dict(row) for row in c.fetchall()]

def list_active_keys(include_secret: bool = False) -> list:
    """List active API keys, optionally including encrypted keys for worker use.
    
    Args:
        include_secret: If True, include enc_key in results (for worker)
        
    Returns:
        list: List of dictionaries containing key data
    """
    with get_conn() as conn:
        c = conn.cursor()
        if include_secret:
            c.execute("""
                SELECT id, label, provider, enc_key, last_ok, created_at
                FROM api_keys
                WHERE active = 1
                ORDER BY created_at DESC
            """)
        else:
            c.execute("""
                SELECT id, label, provider, active, last_ok, created_at
                FROM api_keys
                WHERE active = 1
                ORDER BY created_at DESC
            """)
        return [dict(row) for row in c.fetchall()]

def set_api_key_active(key_id: int, active: bool) -> None:
    """Set the active status of an API key.
    
    Args:
        key_id: The ID of the key to update
        active: True to activate, False to deactivate
    """
    with get_conn() as conn:
        c = conn.cursor()
        c.execute("UPDATE api_keys SET active = ? WHERE id = ?", (1 if active else 0, key_id))
        conn.commit()

def delete_api_key(key_id: int) -> None:
    """Delete an API key from the database.
    
    Args:
        key_id: The ID of the key to delete
    """
    with get_conn() as conn:
        c = conn.cursor()
        c.execute("DELETE FROM api_keys WHERE id = ?", (key_id,))
        conn.commit()

def update_key_last_ok(key_id: int, timestamp: str) -> None:
    """Update the last successful probe timestamp for an API key.
    
    Args:
        key_id: The ID of the key to update
        timestamp: ISO timestamp of the successful probe
    """
    with get_conn() as conn:
        c = conn.cursor()
        c.execute("UPDATE api_keys SET last_ok = ? WHERE id = ?", (timestamp, key_id))
        conn.commit()

# Tracking token CRUD functions

def create_tracking_token(label: str, token: str) -> dict:
    """Create a new tracking token.
    
    Args:
        label: User-friendly label for the token
        token: The generated token string
        
    Returns:
        dict: Created token data with id and token
        
    Raises:
        sqlite3.IntegrityError: If label or token already exists
    """
    with get_conn() as conn:
        c = conn.cursor()
        c.execute("""
            INSERT INTO ingest_tokens (label, token)
            VALUES (?, ?)
        """, (label, token))
        conn.commit()
        token_id = c.lastrowid
        return {"id": token_id, "token": token}

def list_tracking_tokens() -> list:
    """List all tracking tokens with metadata and usage counts.
    
    Returns:
        list: List of tracking token dictionaries
    """
    with get_conn() as conn:
        c = conn.cursor()
        c.execute("""
            SELECT 
                t.id,
                t.label,
                t.token,
                t.active,
                t.created_at,
                t.last_seen_at,
                COUNT(u.id) as usage_count
            FROM ingest_tokens t
            LEFT JOIN usage_log u ON t.id = u.ingest_token_id
            GROUP BY t.id, t.label, t.token, t.active, t.created_at, t.last_seen_at
            ORDER BY t.created_at DESC
        """)
        return [dict(row) for row in c.fetchall()]

def get_tracking_token_by_token(token: str) -> dict:
    """Get tracking token by token string.
    
    Args:
        token: The token string to look up
        
    Returns:
        dict: Token data or None if not found
    """
    with get_conn() as conn:
        c = conn.cursor()
        c.execute("""
            SELECT id, label, token, active, created_at, last_seen_at
            FROM ingest_tokens
            WHERE token = ?
        """, (token,))
        row = c.fetchone()
        return dict(row) if row else None

def set_tracking_token_active(token_id: int, active: bool) -> None:
    """Set the active status of a tracking token.
    
    Args:
        token_id: The ID of the token to update
        active: True to activate, False to deactivate
    """
    with get_conn() as conn:
        c = conn.cursor()
        c.execute("UPDATE ingest_tokens SET active = ? WHERE id = ?", (1 if active else 0, token_id))
        conn.commit()

def delete_tracking_token(token_id: int) -> None:
    """Delete a tracking token from the database.
    
    Args:
        token_id: The ID of the token to delete
    """
    with get_conn() as conn:
        c = conn.cursor()
        c.execute("DELETE FROM ingest_tokens WHERE id = ?", (token_id,))
        conn.commit()

def touch_tracking_token_last_seen(token_id: int, timestamp: str) -> None:
    """Update the last seen timestamp for a tracking token.
    
    Args:
        token_id: The ID of the token to update
        timestamp: ISO timestamp of when the token was last used
    """
    with get_conn() as conn:
        c = conn.cursor()
        c.execute("UPDATE ingest_tokens SET last_seen_at = ? WHERE id = ?", (timestamp, token_id))
        conn.commit()

def check_usage_duplicate(ingest_token_id: int, event_id: str) -> bool:
    """Check if a usage entry with the same token and event_id already exists.
    
    Args:
        ingest_token_id: The tracking token ID
        event_id: The event ID to check
        
    Returns:
        bool: True if duplicate exists, False otherwise
    """
    with get_conn() as conn:
        c = conn.cursor()
        c.execute("""
            SELECT COUNT(*) as count 
            FROM usage_log 
            WHERE ingest_token_id = ? AND event_id = ?
        """, (ingest_token_id, event_id))
        return c.fetchone()["count"] > 0

def query_usage(start: str = None, end: str = None, model: str = None, ingest_token_id: int = None, limit: int = 5000, offset: int = 0) -> list:
    """Query usage_log with optional filters and pagination.
    
    Args:
        start: Start timestamp (ISO-8601 UTC) for filtering (inclusive)
        end: End timestamp (ISO-8601 UTC) for filtering (inclusive)  
        model: Exact model name to filter by
        ingest_token_id: Filter by specific tracking token ID
        limit: Maximum number of rows to return (default: 5000)
        offset: Number of rows to skip (default: 0)
        
    Returns:
        list: List of usage dictionaries matching the filters
    """
    sql = """
        SELECT id, timestamp, model, promptTokens, completionTokens, totalTokens, estimatedCostUSD
        FROM usage_log WHERE 1=1
    """
    params = []
    
    if start:
        sql += " AND timestamp >= ?"
        params.append(start)
    if end:
        sql += " AND timestamp <= ?"
        params.append(end)
    if model:
        sql += " AND model = ?"
        params.append(model)
    if ingest_token_id is not None:
        sql += " AND ingest_token_id = ?"
        params.append(ingest_token_id)
        
    sql += " ORDER BY timestamp DESC LIMIT ? OFFSET ?"
    params.extend([int(limit), int(offset)])
    
    with get_conn() as conn:
        c = conn.cursor()
        c.execute(sql, params)
        return [dict(row) for row in c.fetchall()]

def list_models() -> list:
    """Get all distinct model names from usage_log.
    
    Returns:
        list: Sorted list of model names
    """
    with get_conn() as conn:
        c = conn.cursor()
        c.execute("""
            SELECT DISTINCT model 
            FROM usage_log 
            WHERE model IS NOT NULL 
            ORDER BY model ASC
        """)
        return [row[0] for row in c.fetchall()]