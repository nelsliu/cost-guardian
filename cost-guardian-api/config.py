import os
from dotenv import load_dotenv

load_dotenv()

# OPENAI_API_KEY no longer used - keys managed via encrypted dashboard storage
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini-2024-07-18")
PROBE_INTERVAL_SECS = int(os.getenv("PROBE_INTERVAL_SECS", "300"))
DB_FILENAME = os.getenv("DB_FILENAME", "cost_guardian.db")
SERVER_PORT = int(os.getenv("SERVER_PORT", "5001"))
HEARTBEAT_PROMPT = os.getenv("HEARTBEAT_PROMPT", "ping")

# Auth config
API_KEY = os.getenv("API_KEY", "")

# Encryption config
MASTER_KEY = os.getenv("MASTER_KEY", "")

# Provider config
PROVIDER = os.getenv("PROVIDER", "openai")

# Rate limiting config
RATE_LIMIT_RPM = int(os.getenv("RATE_LIMIT_RPM", "60"))
RATE_LIMIT_BURST = int(os.getenv("RATE_LIMIT_BURST", os.getenv("RATE_LIMIT_RPM", "60")))
RATE_LIMIT_EXEMPT = [path.strip() for path in os.getenv("RATE_LIMIT_EXEMPT", "/ping,/dashboard").split(",") if path.strip()]

# Ingestion config
INGEST_KEY = os.getenv("INGEST_KEY", "")
INGEST_RPM = int(os.getenv("INGEST_RPM", str(RATE_LIMIT_RPM)))
INGEST_BURST = int(os.getenv("INGEST_BURST", str(RATE_LIMIT_BURST)))

# Worker config
WORKER_HEARTBEAT_ENABLED = os.getenv("WORKER_HEARTBEAT_ENABLED", "false").lower() == "true"

# Tracking token config
TRACKING_TOKEN_LENGTH = int(os.getenv("TRACKING_TOKEN_LENGTH", "22"))

# Environment and CORS config
ENV = os.getenv("ENV", "development").lower()
ALLOWED_ORIGINS = [o.strip() for o in os.getenv("ALLOWED_ORIGINS", "").split(",") if o.strip()]
DEBUG = (ENV != "production")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, DB_FILENAME)