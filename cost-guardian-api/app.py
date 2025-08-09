from flask import Flask, request, jsonify, render_template
from flask_cors import CORS
import sqlite3
import traceback
import logging

from config import DB_PATH, SERVER_PORT
from db import migrate

app = Flask(__name__)
CORS(app)

@app.route('/ping')
def ping():
    return jsonify({"message": "pong"})

@app.route('/data', methods=['GET'])
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
    return render_template('dashboard.html')


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")
    
    # Ensure database table exists
    migrate()
    
    app.run(debug=True, port=SERVER_PORT)