from flask import Flask, request, jsonify, render_template, g
from flask_cors import CORS
import logging, uuid, time, sqlite3, traceback
from functools import wraps

from config import DB_PATH, SERVER_PORT, API_KEY, DASHBOARD_PUBLIC
from db import migrate

app = Flask(__name__)
CORS(app)

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

@app.after_request
def _log_request(resp):
    # Duration in ms, even if g.t0 is missing for any reason
    dt_ms = int((time.perf_counter() - g.get('t0', time.perf_counter())) * 1000)
    logging.info("[%s] %s %s -> %s (%sms)",
                 g.get('req_id', '-'), request.method, request.path, resp.status_code, dt_ms)

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

@app.route('/ping')
def ping():
    return jsonify({"message": "pong"})

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
        logging.exception("Error occurred in /data route")
        return jsonify({"error": traceback.format_exc()}), 500

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
        return jsonify({"error": traceback.format_exc()}), 500

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
        return jsonify({"error": traceback.format_exc()}), 500

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
    
    # Ensure database table exists
    migrate()
    
    app.run(debug=True, port=SERVER_PORT)