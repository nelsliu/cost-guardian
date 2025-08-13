import argparse
import time
import logging
import requests # pyright: ignore[reportMissingModuleSource]
from datetime import datetime, timezone

from config import OPENAI_MODEL, PROBE_INTERVAL_SECS, HEARTBEAT_PROMPT, MASTER_KEY, WORKER_HEARTBEAT_ENABLED, ENV
from db import migrate, insert_usage, list_active_keys, update_key_last_ok
from calc import compute_cost
from crypto import decrypt_key

OPENAI_URL = "https://api.openai.com/v1/chat/completions"

def now_iso():
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()

def probe_single_key(api_key: str, key_id: int, label: str) -> dict:
    """Hit OpenAI with a tiny prompt using a specific API key, parse usage, write to SQLite.
    
    Args:
        api_key: The decrypted OpenAI API key
        key_id: The database ID of the key
        label: User-friendly label for the key
        
    Returns:
        dict: The usage row that was inserted
    """
    payload = {
        "model": OPENAI_MODEL,
        "messages": [
            {"role": "user", "content": f"Return a one-word heartbeat: '{HEARTBEAT_PROMPT}'."}
        ]
    }
    headers = {"Authorization": f"Bearer {api_key}"}

    start_time = time.perf_counter()
    
    # Retry logic for transient HTTP errors
    for attempt in range(2):
        try:
            r = requests.post(OPENAI_URL, headers=headers, json=payload, timeout=30)
            r.raise_for_status()
            break
        except requests.HTTPError as e:
            if attempt == 0 and r.status_code in [429] or (500 <= r.status_code < 600):
                logging.warning("HTTP error %s (attempt %d/2) for key %s (%s), retrying in 1s...", 
                              r.status_code, attempt + 1, key_id, label)
                time.sleep(1)
                continue
            raise
    
    end_time = time.perf_counter()
    response_time_ms = round((end_time - start_time) * 1000, 2)
    logging.info("Response time: %sms for key %s (%s)", response_time_ms, key_id, label)
    
    data = r.json()

    usage = data.get("usage", {}) or {}
    row = {
        "timestamp": now_iso(),
        "model": data.get("model", OPENAI_MODEL),
        "promptTokens": int(usage.get("prompt_tokens", 0) or 0),
        "completionTokens": int(usage.get("completion_tokens", 0) or 0),
        "totalTokens": int(usage.get("total_tokens", 0) or 0),
        "estimatedCostUSD": float(compute_cost(usage)),
    }
    insert_usage(row, api_key_id=key_id, source='probe')
    
    # Update last successful probe time
    update_key_last_ok(key_id, row["timestamp"])
    
    logging.info("Logged usage row for key %s (%s): %s", key_id, label, row)
    return row

def probe_once():
    """Probe OpenAI using all active API keys and log usage for each."""
    if not WORKER_HEARTBEAT_ENABLED:
        logging.info("Worker heartbeat disabled (WORKER_HEARTBEAT_ENABLED=false) - skipping probe")
        return []
    
    # Production warning
    if ENV == "production":
        logging.warning("🚨 WORKER HEARTBEAT ENABLED IN PRODUCTION 🚨 - Consider using client-push ingestion instead")
        logging.warning("Set WORKER_HEARTBEAT_ENABLED=false to disable background probing in production")
    
    if not MASTER_KEY:
        logging.warning("MASTER_KEY not configured - skipping all key probes")
        return []
    
    # Get all active keys with encrypted data
    active_keys = list_active_keys(include_secret=True)
    
    if not active_keys:
        logging.info("No active API keys found - nothing to probe")
        return []
    
    logging.info("Probing %d active API key(s) (heartbeat mode)", len(active_keys))
    results = []
    
    for key_data in active_keys:
        try:
            # Decrypt the API key
            decrypted_key = decrypt_key(key_data['enc_key'])
            
            # Probe OpenAI with this key
            result = probe_single_key(decrypted_key, key_data['id'], key_data['label'])
            results.append(result)
            
        except ValueError as e:
            logging.warning("Failed to decrypt key %s (%s): %s", 
                          key_data['id'], key_data['label'], e)
            continue
        except requests.HTTPError as e:
            logging.warning("HTTP error for key %s (%s): %s | body=%s", 
                          key_data['id'], key_data['label'], e, 
                          getattr(e.response, "text", ""))
            continue
        except Exception as e:
            logging.exception("Probe failed for key %s (%s)", key_data['id'], key_data['label'])
            continue
    
    logging.info("Completed probing %d keys, %d successful (heartbeat mode)", len(active_keys), len(results))
    return results

def loop():
    if not WORKER_HEARTBEAT_ENABLED:
        logging.info("Cost Guardian worker: heartbeat disabled (WORKER_HEARTBEAT_ENABLED=false)")
        logging.info("Worker will exit. Use client-push ingestion via POST /ingest instead")
        return
    
    # Production warning for loop mode
    if ENV == "production":
        logging.warning("🚨 WORKER HEARTBEAT LOOP ENABLED IN PRODUCTION 🚨")
        logging.warning("This should typically be disabled in production environments")
        logging.warning("Consider using client-push ingestion instead of background probing")
    
    logging.info("Cost Guardian worker started | heartbeat=enabled | interval=%ss | model=%s | multi-key=enabled",
                 PROBE_INTERVAL_SECS, OPENAI_MODEL)
    while True:
        try:
            probe_once()
        except requests.HTTPError as e:
            logging.warning("HTTP error: %s | body=%s", e, getattr(e.response, "text", ""))
        except Exception as e:
            logging.exception("Probe failed")
        time.sleep(PROBE_INTERVAL_SECS)

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")

    # ensure table exists
    migrate()

    parser = argparse.ArgumentParser()
    parser.add_argument("--once", action="store_true", help="Run a single probe then exit.")
    args = parser.parse_args()

    if args.once:
        probe_once()
    else:
        loop()