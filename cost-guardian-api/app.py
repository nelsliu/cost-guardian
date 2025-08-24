from flask import Flask, request, jsonify, render_template, g
from flask_cors import CORS
import logging, uuid, time, sqlite3, traceback, secrets
from functools import wraps
from datetime import datetime, timezone

from config import DB_PATH, SERVER_PORT, API_KEY, ENV, DEBUG, ALLOWED_ORIGINS, RATE_LIMIT_RPM, RATE_LIMIT_BURST, RATE_LIMIT_EXEMPT, INGEST_KEY, INGEST_RPM, INGEST_BURST, TRACKING_TOKEN_LENGTH
from db import migrate, insert_usage, get_tracking_token_by_token, touch_tracking_token_last_seen, check_usage_duplicate, create_tracking_token, list_tracking_tokens, set_tracking_token_active, delete_tracking_token, query_usage, list_models
from rate_limit import init_limit, init_ingest_limit, check_rate_limit, is_exempt_path
from metrics import increment_rate_limit_hits, increment_ingest_success, increment_ingest_duplicate, increment_ingest_bad_auth, increment_ingest_validation_error, observe_latency, observe_status

app = Flask(__name__)

# Security: Set maximum content length to 1MB to prevent abuse
app.config['MAX_CONTENT_LENGTH'] = 1 * 1024 * 1024  # 1MB

# CORS setup - exclude /ingest (server-to-server only)
if ALLOWED_ORIGINS:
    CORS(app, resources={
             r"/(?!ingest).*": {  # Exclude /ingest from CORS
                 "origins": ALLOWED_ORIGINS,
                 "supports_credentials": False,
                 "methods": ["GET","POST","DELETE","OPTIONS"],
                 "allow_headers": ["Content-Type","X-API-Key"]
             }
         })
else:
    # In development, still exclude /ingest from CORS
    CORS(app, resources={r"/(?!ingest).*": {}})
    logging.warning("ALLOWED_ORIGINS not set—CORS is wide open for non-ingest endpoints (dev mode)")

# --- Startup initialization (runs for both dev and Gunicorn) ---

def init_startup():
    """Initialize application startup logic for both Flask dev server and Gunicorn."""
    # Production validation - fail fast if misconfigured
    if ENV == "production" and not API_KEY:
        import sys
        logging.error("API_KEY must be set in production environment")
        raise SystemExit(1)
    
    # Database migration (idempotent, safe for multiple workers)
    migrate()
    
    # Rate limiting initialization (per-process, worker-safe)
    init_limit(RATE_LIMIT_RPM, RATE_LIMIT_BURST, RATE_LIMIT_EXEMPT)
    init_ingest_limit(INGEST_RPM, INGEST_BURST)
    
    # Safe startup logging (no secrets)
    logging.info("Dashboard auth requirement: %s", "ENFORCED" if ENV == "production" else "DISABLED (dev)")
    logging.info("Rate limiting initialized | Admin RPM=%d | BURST=%d | EXEMPT=%s", 
                 RATE_LIMIT_RPM, RATE_LIMIT_BURST, ",".join(RATE_LIMIT_EXEMPT))
    logging.info("Ingest rate limiting initialized | RPM=%d | BURST=%d", 
                 INGEST_RPM, INGEST_BURST)
    

# Initialize at import time (runs for both Flask dev server and Gunicorn workers)
init_startup()

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
    
    # Auth should precede throttling - let @require_api_key handle 401 first
    if API_KEY and not request.headers.get("X-API-Key"):
        return None  # let @require_api_key handle 401
    
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

    # Record metrics for specific endpoints
    if request.path in ['/data', '/ingest']:
        observe_latency(request.path, dt_ms)
        observe_status(request.path, resp.status_code)

    # Add rate limit headers for all non-exempt requests (including 429s)
    if not is_exempt_path(request.path, request.method):
        resp.headers["X-RateLimit-Limit"] = str(RATE_LIMIT_RPM)
        # Use 0 for blocked requests, actual remaining for others
        remaining = getattr(g, 'rate_limit_remaining', 0)
        resp.headers["X-RateLimit-Remaining"] = str(int(remaining))

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

# Date normalization helpers for filtering

def _to_iso_utc_end_of_day(date_only: str) -> str:
    """Convert YYYY-MM-DD to end-of-day UTC ISO string."""
    dt = datetime.fromisoformat(date_only).replace(tzinfo=timezone.utc)
    return dt.replace(hour=23, minute=59, second=59).isoformat().replace("+00:00", "Z")

def _normalize_time_param(v: str, is_end: bool = False) -> str:
    """Normalize time parameter to ISO UTC string.
    
    Args:
        v: Input string (YYYY-MM-DD or full ISO)
        is_end: If True and input is date-only, convert to end of day
        
    Returns:
        Normalized ISO UTC string or None if invalid
    """
    if not v:
        return None
    try:
        # Check if it's a date-only format (YYYY-MM-DD)
        if len(v) == 10 and v[4] == '-' and v[7] == '-':
            if is_end:
                return _to_iso_utc_end_of_day(v)
            else:
                dt = datetime.fromisoformat(v).replace(tzinfo=timezone.utc)
                return dt.isoformat().replace("+00:00", "Z")
        
        # Handle full ISO format (with or without Z/offset)
        iso_str = v.replace("Z", "+00:00") if v.endswith("Z") else v
        dt = datetime.fromisoformat(iso_str).astimezone(timezone.utc)
        return dt.isoformat().replace("+00:00", "Z")
    except Exception:
        return None

@app.route('/ping')
def ping():
    return jsonify({"message": "pong"})

@app.route('/health')
def health():
    return jsonify({"status": "healthy", "timestamp": time.time()})

@app.route('/metrics')
@require_api_key  
def get_system_metrics():
    """Get comprehensive system metrics and health status."""
    try:
        from datetime import datetime, timezone
        from rate_limit import get_config
        from metrics import get_metrics
        
        # Get rate limiting configuration
        rate_limit_config = get_config()
        
        # Get metrics counters
        counters = get_metrics()
        
        # Database queries
        with sqlite3.connect(DB_PATH) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            # Usage rows count
            cursor.execute("SELECT COUNT(*) as count FROM usage_log")
            usage_rows = cursor.fetchone()["count"]
            
            # Active tracking tokens count
            cursor.execute("SELECT COUNT(*) as count FROM ingest_tokens WHERE active=1")
            active_tokens = cursor.fetchone()["count"]
            
            # Last usage timestamp
            cursor.execute("SELECT MAX(timestamp) as last_timestamp FROM usage_log")
            last_usage_raw = cursor.fetchone()["last_timestamp"]
            
            # Last ingest token seen timestamp
            cursor.execute("SELECT MAX(last_seen_at) as last_seen FROM ingest_tokens WHERE last_seen_at IS NOT NULL")
            last_token_seen_raw = cursor.fetchone()["last_seen"]
            
            # Token activity health indicators (1m/5m/1h)
            cursor.execute("""
                SELECT 
                    COUNT(CASE WHEN datetime(last_seen_at) > datetime('now', '-1 minute') THEN 1 END) as seen_1m,
                    COUNT(CASE WHEN datetime(last_seen_at) > datetime('now', '-5 minute') THEN 1 END) as seen_5m,
                    COUNT(CASE WHEN datetime(last_seen_at) > datetime('now', '-1 hour') THEN 1 END) as seen_1h
                FROM ingest_tokens 
                WHERE last_seen_at IS NOT NULL
            """)
            token_activity = cursor.fetchone()
        
        # Format timestamps
        last_usage_at = last_usage_raw if last_usage_raw else None
        last_token_seen_at = last_token_seen_raw if last_token_seen_raw else None
        
        # Build response
        metrics_data = {
            "version": "1",
            "env": ENV,
            "debug": DEBUG,
            "rate_limit": rate_limit_config,
            "ingest": {
                "rpm": INGEST_RPM,
                "burst": INGEST_BURST,
                "auth_enabled": bool(INGEST_KEY),
                "tracking_token_length": TRACKING_TOKEN_LENGTH
            },
            "counters": counters,
            "db": {
                "usage_rows": usage_rows,
                "active_tokens": active_tokens,
                "last_usage_at": last_usage_at,
                "last_token_seen_at": last_token_seen_at
            },
            "ingestion_health": {
                "tokens_seen_1m": token_activity["seen_1m"],
                "tokens_seen_5m": token_activity["seen_5m"], 
                "tokens_seen_1h": token_activity["seen_1h"]
            }
        }
        
        return jsonify(metrics_data)
        
    except Exception:
        logging.exception("[%s] Error occurred in /metrics route", g.get('req_id', '-'))
        if DEBUG:
            return jsonify({"error": traceback.format_exc()}), 500
        else:
            return json_error(500, "Internal server error")


@app.route('/data', methods=['GET'])
@require_api_key
def get_data():
    """Get usage data with optional filtering by date range, model, and tracking token."""
    try:
        # Extract query parameters
        start_param = request.args.get('start')
        end_param = request.args.get('end')
        model_param = request.args.get('model')
        ingest_token_id_param = request.args.get('ingest_token_id')
        
        # Normalize and validate date parameters
        start_normalized = _normalize_time_param(start_param, is_end=False) if start_param else None
        end_normalized = _normalize_time_param(end_param, is_end=True) if end_param else None
        
        # Validate date parameters
        if start_param and not start_normalized:
            return json_error(400, f"Invalid start date format: {start_param}. Use YYYY-MM-DD or ISO-8601.")
        
        if end_param and not end_normalized:
            return json_error(400, f"Invalid end date format: {end_param}. Use YYYY-MM-DD or ISO-8601.")
        
        # Validate date range
        if start_normalized and end_normalized:
            start_dt = datetime.fromisoformat(start_normalized.replace("Z", "+00:00"))
            end_dt = datetime.fromisoformat(end_normalized.replace("Z", "+00:00"))
            if start_dt > end_dt:
                return json_error(400, "Start date cannot be after end date.")
        
        # Validate ingest_token_id parameter
        ingest_token_id = None
        if ingest_token_id_param:
            try:
                ingest_token_id = int(ingest_token_id_param)
                if ingest_token_id <= 0:
                    return json_error(400, "ingest_token_id must be a positive integer.")
            except (ValueError, TypeError):
                return json_error(400, "ingest_token_id must be a valid integer.")
        
        # Query with filters
        logging.info("Querying usage data with filters: start=%s, end=%s, model=%s, ingest_token_id=%s", 
                    start_normalized, end_normalized, model_param, ingest_token_id)
        
        rows = query_usage(
            start=start_normalized,
            end=end_normalized, 
            model=model_param,
            ingest_token_id=ingest_token_id
        )
        
        logging.info("Fetched %d rows from DB with filters.", len(rows))
        return jsonify({"data": rows})
        
    except Exception:
        logging.exception("[%s] Error occurred in /data route", g.get('req_id', '-'))
        if DEBUG:
            return jsonify({"error": traceback.format_exc()}), 500
        else:
            return json_error(500, "Internal server error")

@app.route('/models', methods=['GET'])
@require_api_key
def get_models():
    """Get all distinct model names from the usage data."""
    try:
        models = list_models()
        logging.info("Returning %d distinct models", len(models))
        return jsonify({"models": models})
    except Exception:
        logging.exception("[%s] Error occurred in /models route", g.get('req_id', '-'))
        if DEBUG:
            return jsonify({"error": traceback.format_exc()}), 500
        else:
            return json_error(500, "Internal server error")

@app.route('/log', methods=['POST'])
@require_api_key
def log_data():
    """DEPRECATED: Legacy endpoint for logging usage data. Use POST /ingest with tracking tokens instead."""
    try:
        # Log deprecation warning
        logging.warning("[%s] DEPRECATED: /log endpoint used - consider migrating to POST /ingest with tracking tokens", 
                       g.get('req_id', '-'))
        
        data = request.json
        if not data:
            return json_error(400, "JSON body required")
        
        # Use the insert_usage function with source='legacy' for backward compatibility
        usage_row = {
            "timestamp": data.get('timestamp'),
            "model": data.get('model'), 
            "promptTokens": data.get('promptTokens', 0),
            "completionTokens": data.get('completionTokens', 0),
            "totalTokens": data.get('totalTokens', 0),
            "estimatedCostUSD": data.get('estimatedCostUSD', 0.0)
        }
        
        insert_usage(usage_row, source='legacy')  # Mark as legacy endpoint usage
        
        return jsonify({
            "message": "Data logged successfully",
            "warning": "DEPRECATED: This endpoint is deprecated. Please migrate to POST /ingest with tracking tokens."
        })
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


@app.route('/ingest', methods=['POST'])
def ingest_usage():
    """Server-to-server endpoint for ingesting OpenAI usage data with tracking token attribution."""
    try:
        # 1. Auth FIRST - check X-Ingest-Key before any other processing
        ingest_key = request.headers.get('X-Ingest-Key')
        if not INGEST_KEY:
            logging.warning("[%s] INGEST_KEY not configured - /ingest endpoint accessible without auth", g.get('req_id', '-'))
            increment_ingest_bad_auth()
            return json_error(500, "Ingest authentication not configured")
        
        if not ingest_key or ingest_key != INGEST_KEY:
            logging.warning("[%s] Invalid or missing X-Ingest-Key for /ingest", g.get('req_id', '-'))
            increment_ingest_bad_auth()
            return json_error(401, "Invalid or missing X-Ingest-Key")
        
        # 2. Validate JSON payload
        if not request.is_json:
            increment_ingest_validation_error()
            return json_error(400, "Content-Type must be application/json")
        
        data = request.get_json()
        if not data:
            increment_ingest_validation_error()
            return json_error(400, "JSON body required")
        
        # 3. Extract and validate tracking token
        tracking_token = data.get('tracking_token', '').strip()
        if not tracking_token:
            increment_ingest_validation_error()
            return json_error(400, "tracking_token is required")
        
        # Resolve tracking token -> token data
        token_data = get_tracking_token_by_token(tracking_token)
        if not token_data:
            increment_ingest_validation_error()
            return json_error(404, "Unknown tracking token")
        
        if not token_data['active']:
            increment_ingest_validation_error()
            return json_error(403, "Tracking token is inactive")
        
        # 4. Rate limiting with per-token buckets
        limiter_key = f"ingest:{tracking_token}"
        allowed, retry_after, remaining = check_rate_limit(limiter_key)
        
        if not allowed:
            increment_rate_limit_hits()
            logging.warning("[%s] Rate limit exceeded for tracking token %s", 
                           g.get('req_id', '-'), mask_tracking_token(tracking_token))
            resp = json_error(429, "Rate limit exceeded")
            resp[0].headers["Retry-After"] = str(retry_after)
            return resp
        
        # 5. Payload normalization and validation
        # Normalize camelCase to snake_case
        normalized_data = {}
        field_mapping = {
            'promptTokens': 'prompt_tokens',
            'completionTokens': 'completion_tokens', 
            'totalTokens': 'total_tokens',
            'costUsd': 'cost_usd'
        }
        
        for key, value in data.items():
            if key in field_mapping:
                normalized_data[field_mapping[key]] = value
            else:
                normalized_data[key] = value
        
        # Extract and validate required fields
        event_id = normalized_data.get('event_id')
        provider = normalized_data.get('provider', 'openai')
        model = normalized_data.get('model', '').strip()
        prompt_tokens = normalized_data.get('prompt_tokens', 0)
        completion_tokens = normalized_data.get('completion_tokens', 0) 
        total_tokens = normalized_data.get('total_tokens')
        cost_usd = normalized_data.get('cost_usd', 0.0)
        meta = normalized_data.get('meta', {})
        
        # Validation
        if not model:
            increment_ingest_validation_error()
            return json_error(400, "model is required")
        
        try:
            prompt_tokens = int(prompt_tokens)
            completion_tokens = int(completion_tokens) 
            if prompt_tokens < 0 or completion_tokens < 0:
                raise ValueError("Token counts cannot be negative")
        except (ValueError, TypeError):
            increment_ingest_validation_error()
            return json_error(400, "prompt_tokens and completion_tokens must be non-negative integers")
        
        # Compute total_tokens if missing
        if total_tokens is None:
            total_tokens = prompt_tokens + completion_tokens
        else:
            try:
                total_tokens = int(total_tokens)
                if total_tokens < 0:
                    raise ValueError("Total tokens cannot be negative")
            except (ValueError, TypeError):
                increment_ingest_validation_error()
                return json_error(400, "total_tokens must be a non-negative integer")
        
        # Validate cost_usd
        try:
            cost_usd = float(cost_usd)
        except (ValueError, TypeError):
            increment_ingest_validation_error()
            return json_error(400, "cost_usd must be a number")
        
        # Server-side cost calculation when cost not provided
        if cost_usd == 0.0 and (prompt_tokens > 0 or completion_tokens > 0):
            from calc import compute_cost
            usage_for_calc = {
                'prompt_tokens': prompt_tokens,
                'completion_tokens': completion_tokens
            }
            cost_usd = compute_cost(usage_for_calc)
        
        # Handle timestamp - use server time if missing
        timestamp = normalized_data.get('timestamp')
        if not timestamp:
            timestamp = datetime.now(timezone.utc).isoformat(timespec='seconds')
        
        # 6. Check for idempotency if event_id provided
        if event_id:
            if check_usage_duplicate(token_data['id'], event_id):
                increment_ingest_duplicate()
                return jsonify({"duplicate": True}), 200
        
        # 7. Insert usage data
        usage_row = {
            "timestamp": timestamp,
            "model": model,
            "promptTokens": prompt_tokens,
            "completionTokens": completion_tokens,
            "totalTokens": total_tokens,
            "estimatedCostUSD": cost_usd
        }
        
        row_id = insert_usage(usage_row, 
                             ingest_token_id=token_data['id'], 
                             source='ingest', 
                             event_id=event_id)
        
        # 8. Update last_seen_at for the tracking token
        touch_tracking_token_last_seen(token_data['id'], timestamp)
        
        # 9. Success metrics and response
        increment_ingest_success()
        logging.info("[%s] Successfully ingested usage for token %s: %s tokens, $%s", 
                    g.get('req_id', '-'), mask_tracking_token(tracking_token), 
                    total_tokens, cost_usd)
        
        return jsonify({"ok": True, "id": row_id}), 201
        
    except Exception:
        logging.exception("[%s] Error occurred in /ingest route", g.get('req_id', '-'))
        increment_ingest_validation_error()
        if DEBUG:
            return jsonify({"error": traceback.format_exc()}), 500
        else:
            return json_error(500, "Internal server error")

def mask_tracking_token(token: str) -> str:
    """Create a masked version of a tracking token showing first 4 and last 4 characters."""
    if len(token) <= 8:
        return 'tok_••••'
    return f"tok_{token[:4]}…{token[-4:]}"

def mask_ingest_key(key: str) -> str:
    """Create a masked version of an ingest key for logging."""
    if len(key) <= 8:
        return 'key_••••'
    return f"key_{key[:4]}…{key[-4:]}"

# Tracking token management endpoints

@app.route('/ingest/tokens', methods=['GET'])
@require_api_key
def get_tracking_tokens():
    """List all tracking tokens with metadata and usage counts."""
    try:
        tokens = list_tracking_tokens()
        
        # Mask the tokens for security
        for token in tokens:
            token['token_masked'] = mask_tracking_token(token['token'])
            # Keep the full token for copy functionality in the UI
            # token['token'] remains unmasked for admin UI copy buttons
        
        return jsonify({"tokens": tokens})
    except Exception:
        logging.exception("[%s] Error occurred in GET /ingest/tokens route", g.get('req_id', '-'))
        if DEBUG:
            return jsonify({"error": traceback.format_exc()}), 500
        else:
            return json_error(500, "Internal server error")

@app.route('/ingest/tokens', methods=['POST'])
@require_api_key
def create_tracking_token_endpoint():
    """Create a new tracking token."""
    try:
        data = request.json
        if not data:
            return json_error(400, "JSON body required")
        
        label = data.get('label', '').strip()
        
        # Validation
        if not label or len(label) > 64:
            return json_error(400, "Label must be 1-64 characters")
        
        # Check tracking token length bounds
        if TRACKING_TOKEN_LENGTH < 16 or TRACKING_TOKEN_LENGTH > 40:
            logging.error("[%s] Invalid TRACKING_TOKEN_LENGTH %s (must be 16-40)", 
                         g.get('req_id', '-'), TRACKING_TOKEN_LENGTH)
            return json_error(500, "Invalid tracking token length configuration")
        
        # Generate a unique token
        token = secrets.token_urlsafe(TRACKING_TOKEN_LENGTH)
        
        # Store in database
        try:
            result = create_tracking_token(label, token)
        except sqlite3.IntegrityError as e:
            if "UNIQUE constraint failed: ingest_tokens.label" in str(e):
                return json_error(400, f"Label '{label}' already exists")
            elif "UNIQUE constraint failed: ingest_tokens.token" in str(e):
                # Extremely unlikely but handle token collision
                return json_error(500, "Token generation collision, please retry")
            raise
        
        logging.info("[%s] Created new tracking token with ID %s and label '%s'", 
                    g.get('req_id', '-'), result['id'], label)
        return jsonify(result), 201
        
    except Exception:
        logging.exception("[%s] Error occurred in POST /ingest/tokens route", g.get('req_id', '-'))
        if DEBUG:
            return jsonify({"error": traceback.format_exc()}), 500
        else:
            return json_error(500, "Internal server error")

@app.route('/ingest/tokens/<int:token_id>/active', methods=['PATCH'])
@require_api_key
def toggle_tracking_token_active(token_id):
    """Toggle the active status of a tracking token."""
    try:
        data = request.json
        if not data or 'active' not in data:
            return json_error(400, "JSON body with 'active' field required")
        
        active = bool(data['active'])
        set_tracking_token_active(token_id, active)
        
        logging.info("[%s] Set tracking token %s active status to %s", 
                    g.get('req_id', '-'), token_id, active)
        return jsonify({"ok": True})
        
    except Exception:
        logging.exception("[%s] Error occurred in PATCH /ingest/tokens/%s/active route", 
                         g.get('req_id', '-'), token_id)
        if DEBUG:
            return jsonify({"error": traceback.format_exc()}), 500
        else:
            return json_error(500, "Internal server error")

@app.route('/ingest/tokens/<int:token_id>', methods=['DELETE'])
@require_api_key
def remove_tracking_token(token_id):
    """Delete a tracking token."""
    try:
        delete_tracking_token(token_id)
        logging.info("[%s] Deleted tracking token %s", g.get('req_id', '-'), token_id)
        return jsonify({"ok": True})
        
    except Exception:
        logging.exception("[%s] Error occurred in DELETE /ingest/tokens/%s route", 
                         g.get('req_id', '-'), token_id)
        if DEBUG:
            return jsonify({"error": traceback.format_exc()}), 500
        else:
            return json_error(500, "Internal server error")

@app.route('/dashboard')
def dashboard():
    return render_template('dashboard.html', require_signin=(ENV == "production"))


if __name__ == '__main__':
    # DEV ONLY - Gunicorn handles logging in production
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")
    
    # Verbose development-only startup logging
    origins_count = len(ALLOWED_ORIGINS) if ALLOWED_ORIGINS else 0
    logging.info("Starting Cost Guardian API | ENV=%s | DEBUG=%s | ALLOWED_ORIGINS=%d origins | PORT=%d", 
                 ENV, DEBUG, origins_count, SERVER_PORT)
    if ALLOWED_ORIGINS:
        logging.info("Allowed origins: %s", ", ".join(ALLOWED_ORIGINS))
    
    # Start Flask development server
    app.run(host="0.0.0.0", debug=DEBUG, port=SERVER_PORT)