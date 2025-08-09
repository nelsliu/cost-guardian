import argparse
import time
import logging
import requests
from datetime import datetime, timezone

from config import OPENAI_API_KEY, OPENAI_MODEL, PROBE_INTERVAL_SECS
from db import migrate, insert_usage
from calc import compute_cost

OPENAI_URL = "https://api.openai.com/v1/chat/completions"

def now_iso():
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()

def probe_once():
    """Hit OpenAI with a tiny prompt, parse usage, write a row into SQLite."""
    payload = {
        "model": OPENAI_MODEL,
        "messages": [
            {"role": "user", "content": "Return a one-word heartbeat: 'ping'."}
        ]
    }
    headers = {"Authorization": f"Bearer {OPENAI_API_KEY}"}

    r = requests.post(OPENAI_URL, headers=headers, json=payload, timeout=30)
    r.raise_for_status()
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
    insert_usage(row)
    logging.info("Logged usage row: %s", row)
    return row

def loop():
    logging.info("Cost Guardian worker started | interval=%ss | model=%s",
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