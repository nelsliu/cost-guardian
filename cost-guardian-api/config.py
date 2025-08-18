import os
import logging
from dotenv import load_dotenv

load_dotenv()

# OpenAI model configuration (used for cost calculation reference)
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini-2024-07-18")
SERVER_PORT = int(os.getenv("SERVER_PORT", "5001"))

# Auth config
API_KEY = os.getenv("API_KEY", "")

# Provider config
PROVIDER = os.getenv("PROVIDER", "openai")

# Rate limiting config
RATE_LIMIT_RPM = int(os.getenv("RATE_LIMIT_RPM", "60"))
RATE_LIMIT_BURST = int(os.getenv("RATE_LIMIT_BURST", os.getenv("RATE_LIMIT_RPM", "60")))
RATE_LIMIT_EXEMPT = [path.strip() for path in os.getenv("RATE_LIMIT_EXEMPT", "/ping,/health,/dashboard").split(",") if path.strip()]

# Ingestion config
INGEST_KEY = os.getenv("INGEST_KEY", "")
INGEST_RPM = int(os.getenv("INGEST_RPM", str(RATE_LIMIT_RPM)))
INGEST_BURST = int(os.getenv("INGEST_BURST", str(RATE_LIMIT_BURST)))

# Tracking token config
TRACKING_TOKEN_LENGTH = int(os.getenv("TRACKING_TOKEN_LENGTH", "22"))

# Environment and CORS config
ENV = os.getenv("ENV", "development").lower()
ALLOWED_ORIGINS = [o.strip() for o in os.getenv("ALLOWED_ORIGINS", "").split(",") if o.strip()]
DEBUG = (ENV != "production")

# Database configuration - single source of truth
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# Data directory configuration - environment aware
DATA_DIR = os.getenv(
    "DATA_DIR",
    "/app/data" if ENV == "production" else os.path.join(BASE_DIR, "data")
)

# Database file configuration - overridable for flexibility
DB_FILENAME = os.getenv("DB_FILENAME", "usage_log.sqlite")
DB_PATH = os.getenv("DB_PATH", os.path.join(DATA_DIR, DB_FILENAME))

# Log resolved database path on startup
logging.basicConfig(level=logging.INFO)
logging.info("Database path resolved to: %s", DB_PATH)