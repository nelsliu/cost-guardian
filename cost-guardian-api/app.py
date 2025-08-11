from flask import Flask, request, jsonify, render_template, g
from flask_cors import CORS
import logging, uuid, time, sqlite3, traceback
from functools import wraps

from config import DB_PATH, SERVER_PORT, API_KEY, DASHBOARD_PUBLIC, ENV, DEBUG, ALLOWED_ORIGINS, MASTER_KEY, RATE_LIMIT_RPM, RATE_LIMIT_BURST, RATE_LIMIT_EXEMPT
from db import migrate, add_api_key, list_api_keys, set_api_key_active, delete_api_key
from crypto import encrypt_key, decrypt_key
from worker import probe_single_key
from rate_limit import init_limit, check_rate_limit, is_exempt_path
from metrics import increment_rate_limit_hits

app = Flask(__name__)

# CORS setup
if ALLOWED_ORIGINS:
    CORS(app, resources={r"/*": {"origins": ALLOWED_ORIGINS}},
         supports_credentials=False,
         methods=["GET","POST","DELETE","OPTIONS"],
         allow_headers=["Content-Type","X-API-Key"])
else:
    CORS(app)
    logging.warning("ALLOWED_ORIGINS not set—CORS is wide open (dev mode)")

# --- Auth middleware ---

def require_api_key(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        # Skip auth if no API key is configured
        if not API_KEY:
            logging.warning("API_KEY not configured - endpoint accessible without auth")
            return f(*args, **kwargs)
        
        auth_header = request.headers.get('X-API-Key')
        if not auth_header or auth_header != API_KEY:
            logging.warning("[%s] Unauthorized access attempt to %s", g.get('req_id', '-'), request.path)
            return json_error(401, "Unauthorized")
        
        return f(*args, **kwargs)
    return decorated_function

# --- Request tracing & JSON error middleware ---


@app.before_request
def _start_timer():
    # Short request ID for log correlation
    g.req_id = uuid.uuid4().hex[:8]
    # High-resolution start time
    g.t0 = time.perf_counter()

@app.before_request
def _check_rate_limit():
    # Skip rate limiting for exempt paths and methods
    if is_exempt_path(request.path, request.method):
        return None
    
    # Determine the rate limiting key
    if API_KEY:
        # Auth enabled - use API key from header
        limiter_key = request.headers.get("X-API-Key", "anonymous")
    else:
        # Dev/no-auth mode - use IP address
        limiter_key = request.remote_addr or "unknown"
    
    # Check rate limit
    allowed, retry_after, remaining = check_rate_limit(limiter_key)
    
    if not allowed:
        # Rate limited - increment metrics and log
        increment_rate_limit_hits()
        
        display_key = limiter_key
        if API_KEY and limiter_key != "anonymous":
            display_key = mask_api_key(limiter_key)
        
        logging.warning("[%s] Rate limit exceeded for key %s (%s %s)", 
                       g.get('req_id', '-'), display_key, request.method, request.path)
        
        resp = json_error(429, "Rate limit exceeded")
        resp[0].headers["Retry-After"] = str(retry_after)
        return resp
    
    # Store remaining tokens for response headers
    g.rate_limit_remaining = remaining

@app.after_request
def _log_request(resp):
    # Duration in ms, even if g.t0 is missing for any reason
    dt_ms = int((time.perf_counter() - g.get('t0', time.perf_counter())) * 1000)
    logging.info("[%s] %s %s -> %s (%sms)",
                 g.get('req_id', '-'), request.method, request.path, resp.status_code, dt_ms)

    # Add rate limit headers for successful requests
    if resp.status_code < 400 and not is_exempt_path(request.path, request.method):
        resp.headers["X-RateLimit-Limit"] = str(RATE_LIMIT_RPM)
        if hasattr(g, 'rate_limit_remaining'):
            resp.headers["X-RateLimit-Remaining"] = str(int(g.rate_limit_remaining))

    # Avoid caching JSON responses
    if resp.content_type and "application/json" in resp.content_type:
        resp.headers["Cache-Control"] = "no-store"
    return resp

def json_error(status_code: int, message: str):
    payload = {
        "status": "error",
        "message": message,
        "requestId": g.get("req_id", None),
    }
    return jsonify(payload), status_code

# Consistent JSON errors for common cases
@app.errorhandler(400)
def _400(e): return json_error(400, "Bad request")

@app.errorhandler(401)
def _401(e): return json_error(401, "Unauthorized")

@app.errorhandler(403)
def _403(e): return json_error(403, "Forbidden")

@app.errorhandler(404)
def _404(e): return json_error(404, "Not found")

@app.errorhandler(405)
def _405(e): return json_error(405, "Method not allowed")

@app.errorhandler(500)
def _500(e): return json_error(500, "Internal server error")

# Global exception handler for consistent production error responses
@app.errorhandler(Exception)
def handle_exception(e):
    # Pass through HTTP errors to their specific handlers
    if hasattr(e, 'code'):
        return e
    
    if DEBUG:
        # In development, let Flask handle the exception normally (shows traceback)
        raise e
    else:
        # In production, log the full traceback but return clean JSON
        logging.exception("[%s] Unhandled exception", g.get('req_id', '-'))
        return json_error(500, "Internal server error")

@app.route('/ping')
def ping():
    return jsonify({"message": "pong"})

@app.route('/health')
def health():
    return jsonify({"status": "healthy", "timestamp": time.time()})

@app.route('/data', methods=['GET'])
@require_api_key
def get_data():
    try:
        logging.info("Connecting to DB...")
        conn = sqlite3.connect(DB_PATH, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        logging.info("Running SELECT query...")
        cursor.execute("SELECT * FROM usage_log")
        rows = cursor.fetchall()
        logging.info("Fetched %d rows from DB.", len(rows))
        conn.close()
        data_list = [dict(row) for row in rows]
        logging.info("Returning data...")
        return jsonify({"data": data_list})
    except Exception:
        logging.exception("[%s] Error occurred in /data route", g.get('req_id', '-'))
        if DEBUG:
            return jsonify({"error": traceback.format_exc()}), 500
        else:
            return json_error(500, "Internal server error")

@app.route('/log', methods=['POST'])
@require_api_key
def log_data():
    try:
        data = request.json
        conn = sqlite3.connect(DB_PATH, check_same_thread=False)
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO usage_log (timestamp, model, promptTokens, completionTokens, totalTokens, estimatedCostUSD)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (
            data.get('timestamp'),
            data.get('model'),
            data.get('promptTokens'),
            data.get('completionTokens'),
            data.get('totalTokens'),
            data.get('estimatedCostUSD')
        ))
        conn.commit()
        conn.close()
        return jsonify({"message": "Data logged successfully"})
    except Exception:
        logging.exception("[%s] Error occurred in /log route", g.get('req_id', '-'))
        if DEBUG:
            return jsonify({"error": traceback.format_exc()}), 500
        else:
            return json_error(500, "Internal server error")

@app.route('/reset', methods=['DELETE'])
@require_api_key
def reset_db():
    try:
        conn = sqlite3.connect(DB_PATH, check_same_thread=False)
        cursor = conn.cursor()
        cursor.execute("DELETE FROM usage_log")
        conn.commit()
        conn.close()
        return jsonify({"message": "Database reset successfully"})
    except Exception:
        logging.exception("[%s] Error occurred in /reset route", g.get('req_id', '-'))
        if DEBUG:
            return jsonify({"error": traceback.format_exc()}), 500
        else:
            return json_error(500, "Internal server error")

def mask_api_key(key: str) -> str:
    """Create a masked version of an API key showing only the last 4 characters."""
    if len(key) <= 4:
        return '••••'
    return '•' * (len(key) - 4) + key[-4:]

@app.route('/keys', methods=['GET'])
@require_api_key
def get_keys():
    """List all API keys with masked values and metadata."""
    try:
        # Fetch all keys with their enc_key once
        with sqlite3.connect(DB_PATH) as conn:
            conn.row_factory = sqlite3.Row
            cur = conn.cursor()
            cur.execute("""
                SELECT id, label, provider, active, last_ok, created_at, enc_key
                FROM api_keys
                ORDER BY created_at DESC
            """)
            rows = cur.fetchall()

        keys = []
        for row in rows:
            item = {
                "id": row["id"],
                "label": row["label"],
                "provider": row["provider"],
                "active": row["active"],
                "last_ok": row["last_ok"],
                "created_at": row["created_at"],
            }
            try:
                decrypted = decrypt_key(row["enc_key"])
                item["mask"] = mask_api_key(decrypted)
            except Exception as e:
                logging.warning("[%s] Failed to decrypt key %s for masking: %s",
                                g.get('req_id', '-'), row["id"], e)
                item["mask"] = "••••"
            keys.append(item)

        return jsonify({"keys": keys})
    except Exception:
        logging.exception("[%s] Error occurred in /keys route", g.get('req_id', '-'))
        if DEBUG:
            return jsonify({"error": traceback.format_exc()}), 500
        else:
            return json_error(500, "Internal server error")

@app.route('/keys', methods=['POST'])
@require_api_key
def add_key():
    """Add a new API key with encryption."""
    try:
        if not MASTER_KEY:
            if ENV == "production":
                logging.error("[%s] MASTER_KEY not configured in production environment", g.get('req_id', '-'))
                return json_error(500, "Encryption key not configured - cannot store API keys securely")
            else:
                logging.warning("[%s] MASTER_KEY not configured", g.get('req_id', '-'))
                return json_error(500, "Encryption not configured")
        
        data = request.json
        if not data:
            return json_error(400, "JSON body required")
        
        label = data.get('label', '').strip()
        key = data.get('key', '').strip()
        provider = data.get('provider', 'openai').strip()
        
        # Validation
        if not label or len(label) > 64:
            return json_error(400, "Label must be 1-64 characters")
        
        if not key or len(key) > 256:
            return json_error(400, "Key must be 1-256 characters")
        
        if provider not in ['openai']:
            return json_error(400, "Provider must be 'openai'")
        
        # Encrypt the key
        enc_key = encrypt_key(key)
        
        # Store in database
        try:
            key_id = add_api_key(label, provider, enc_key)
        except sqlite3.IntegrityError as e:
            if "UNIQUE constraint failed: api_keys.label" in str(e):
                return json_error(400, f"Label '{label}' already exists")
            raise
        
        logging.info("[%s] Added new API key with ID %s", g.get('req_id', '-'), key_id)
        return jsonify({"id": key_id}), 201
        
    except ValueError as e:
        logging.warning("[%s] Validation error: %s", g.get('req_id', '-'), e)
        return json_error(500, "Encryption not configured")
    except Exception:
        logging.exception("[%s] Error occurred in POST /keys route", g.get('req_id', '-'))
        if DEBUG:
            return jsonify({"error": traceback.format_exc()}), 500
        else:
            return json_error(500, "Internal server error")

@app.route('/keys/<int:key_id>/active', methods=['PATCH'])
@require_api_key
def toggle_key_active(key_id):
    """Toggle the active status of an API key."""
    try:
        data = request.json
        if not data or 'active' not in data:
            return json_error(400, "JSON body with 'active' field required")
        
        active = bool(data['active'])
        set_api_key_active(key_id, active)
        
        logging.info("[%s] Set key %s active status to %s", g.get('req_id', '-'), key_id, active)
        return jsonify({"ok": True})
        
    except Exception:
        logging.exception("[%s] Error occurred in PATCH /keys/%s/active route", g.get('req_id', '-'), key_id)
        if DEBUG:
            return jsonify({"error": traceback.format_exc()}), 500
        else:
            return json_error(500, "Internal server error")

@app.route('/keys/<int:key_id>', methods=['DELETE'])
@require_api_key
def remove_key(key_id):
    """Delete an API key."""
    try:
        delete_api_key(key_id)
        logging.info("[%s] Deleted key %s", g.get('req_id', '-'), key_id)
        return jsonify({"ok": True})
        
    except Exception:
        logging.exception("[%s] Error occurred in DELETE /keys/%s route", g.get('req_id', '-'), key_id)
        if DEBUG:
            return jsonify({"error": traceback.format_exc()}), 500
        else:
            return json_error(500, "Internal server error")

@app.route('/keys/<int:key_id>/probe', methods=['POST'])
@require_api_key
def probe_key_now(key_id):
    """Immediately probe a specific API key to test its validity."""
    try:
        if not MASTER_KEY:
            logging.warning("[%s] MASTER_KEY not configured - cannot probe key %s", g.get('req_id', '-'), key_id)
            return json_error(500, "Encryption not configured")
        
        # Get the specific key
        with sqlite3.connect(DB_PATH) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("SELECT id, label, provider, enc_key, active FROM api_keys WHERE id = ?", (key_id,))
            row = cursor.fetchone()
        
        if not row:
            return json_error(404, "API key not found")
        
        # Decrypt and probe the key
        try:
            decrypted_key = decrypt_key(row['enc_key'])
            result = probe_single_key(decrypted_key, row['id'], row['label'])
            
            return jsonify({
                "success": True,
                "message": f"Key '{row['label']}' tested successfully",
                "usage": result
            })
            
        except Exception as e:
            logging.warning("[%s] Probe failed for key %s (%s): %s", 
                          g.get('req_id', '-'), key_id, row['label'], str(e))
            return jsonify({
                "success": False,
                "message": f"Key '{row['label']}' test failed: {str(e)}",
                "error": str(e)
            }), 400
            
    except Exception:
        logging.exception("[%s] Error occurred in POST /keys/%s/probe route", g.get('req_id', '-'), key_id)
        if DEBUG:
            return jsonify({"error": traceback.format_exc()}), 500
        else:
            return json_error(500, "Internal server error")

@app.route('/dashboard')
def dashboard():
    # Apply auth if dashboard is not public
    if not DASHBOARD_PUBLIC:
        if not API_KEY:
            logging.warning("API_KEY not configured - dashboard accessible without auth")
        else:
            auth_header = request.headers.get('X-API-Key')
            if not auth_header or auth_header != API_KEY:
                logging.warning("[%s] Unauthorized access attempt to %s", g.get('req_id', '-'), request.path)
                return json_error(401, "Unauthorized")
    
    return render_template('dashboard.html')


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")
    
    # Startup configuration logging
    origins_count = len(ALLOWED_ORIGINS) if ALLOWED_ORIGINS else 0
    logging.info("Starting Cost Guardian API | ENV=%s | DEBUG=%s | ALLOWED_ORIGINS=%d origins | PORT=%d", 
                 ENV, DEBUG, origins_count, SERVER_PORT)
    if ALLOWED_ORIGINS:
        logging.info("Allowed origins: %s", ", ".join(ALLOWED_ORIGINS))
    
    # Initialize rate limiting
    init_limit(RATE_LIMIT_RPM, RATE_LIMIT_BURST, RATE_LIMIT_EXEMPT)
    logging.info("Rate limiting initialized | RPM=%d | BURST=%d | EXEMPT=%s", 
                 RATE_LIMIT_RPM, RATE_LIMIT_BURST, ",".join(RATE_LIMIT_EXEMPT))
    
    # Warn if MASTER_KEY is not configured
    if not MASTER_KEY:
        logging.warning("MASTER_KEY not configured - API key encryption/decryption will fail")
    
    # Ensure database table exists
    migrate()
    
    app.run(host="0.0.0.0", debug=DEBUG, port=SERVER_PORT)