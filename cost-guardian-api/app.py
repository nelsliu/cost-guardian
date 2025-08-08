from flask import Flask, request, jsonify, render_template
from flask_cors import CORS
import sqlite3
import traceback
import os
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, 'cost_guardian.db')

app = Flask(__name__)
CORS(app)

@app.route('/ping')
def ping():
    return jsonify({"message": "pong"})

@app.route('/data', methods=['GET'])
def get_data():
    try:
        print("Connecting to DB...")
        conn = sqlite3.connect(DB_PATH, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        print("Running SELECT query...")
        cursor.execute("SELECT * FROM usage_log")
        rows = cursor.fetchall()
        print(f"Fetched {len(rows)} rows from DB.")
        conn.close()
        data_list = [dict(row) for row in rows]
        print("Returning data...")
        return jsonify({"data": data_list})
    except Exception:
        print("Error occurred in /data route:")
        print(traceback.format_exc())
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
    app.run(debug=True, port=5001)