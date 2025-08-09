import os
from dotenv import load_dotenv

load_dotenv()

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini-2024-07-18")
PROBE_INTERVAL_SECS = int(os.getenv("PROBE_INTERVAL_SECS", "300"))
DB_FILENAME = os.getenv("DB_FILENAME", "cost_guardian.db")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, DB_FILENAME)