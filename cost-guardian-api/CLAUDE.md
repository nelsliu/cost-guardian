# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

### Development Commands
- **Install dependencies**: `pip install -r requirements.txt`
- **Run Flask API server**: `python app.py` (starts on port 5001 by default)
- **Run background worker**: `python worker.py` (continuous monitoring)
- **Run single probe**: `python worker.py --once` (one-time usage check)
- **Database migration**: Automatically runs at startup; manually via `python -c "from db import migrate; migrate()"`
- **Kill orphan Flask process**: `lsof -ti :5001 | xargs kill -9` (macOS)
- **Docker development**: `docker-compose up -d` (runs both API and worker)
- **Generate master key**: `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`

### Environment Setup
Copy `.env.example` to `.env` and configure with your values:
```bash
cp .env.example .env
```

**CRITICAL**: Must configure `MASTER_KEY` for encrypted API key storage:
```
# Generate with: python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
MASTER_KEY=your_32_byte_fernet_key_here
```

Required environment variables:
```
# Encryption (CRITICAL - backup securely!)
MASTER_KEY=your_32_byte_fernet_key_here

# OpenAI settings (API keys now managed via dashboard)
OPENAI_MODEL=gpt-4o-mini-2024-07-18
PROBE_INTERVAL_SECS=300
HEARTBEAT_PROMPT=ping

# Server config
SERVER_PORT=5001
DB_FILENAME=cost_guardian.db

# Environment: development | production
ENV=development

# CORS: comma-separated origins
ALLOWED_ORIGINS=http://127.0.0.1:5001,http://localhost:5001

# Auth config (leave API_KEY empty to disable)
API_KEY=your_secret_admin_key_here
DASHBOARD_PUBLIC=true

# Rate limiting (optional)
RATE_LIMIT_RPM=60
RATE_LIMIT_BURST=60
RATE_LIMIT_EXEMPT=/ping,/dashboard,/health

# Provider (currently only 'openai' supported)
PROVIDER=openai
```

Ensure `.gitignore` includes: `.env`, `venv/`, `__pycache__/`, `*.db`, `.DS_Store`

## Authentication

### API Key Protection
- Protected endpoints: `GET /data`, `POST /log`, `DELETE /reset`
- Public endpoints: `GET /ping`, `GET /dashboard` (configurable)
- Auth header: `X-API-Key: your_api_key_here`
- If `API_KEY` is not configured, endpoints remain accessible with warnings logged

### Dashboard Access
- `DASHBOARD_PUBLIC=true` (default): Dashboard accessible without auth
- `DASHBOARD_PUBLIC=false`: Dashboard requires API key authentication

## Architecture

### Core Components
- **Flask API Server** (`app.py`): REST API with CORS enabled, serves dashboard and provides data endpoints
- **Background Worker** (`worker.py`): Periodically probes OpenAI API to track token usage and costs
- **Database Layer** (`db.py`): SQLite operations with automatic connection cleanup and migration support
- **Cost Calculator** (`calc.py`): Computes estimated costs based on token usage rates
- **Configuration** (`config.py`): Environment variable management with defaults
- **Encryption Module** (`crypto.py`): Fernet symmetric encryption for secure API key storage
- **Rate Limiter** (`rate_limit.py`): Token bucket algorithm for per-key rate limiting
- **Metrics Collection** (`metrics.py`): Simple counters and system health monitoring

### Data Flow
1. Worker sends heartbeat requests to OpenAI API at configured intervals
2. Usage data (tokens, costs) is parsed and stored in SQLite database via `insert_usage()`
3. Flask API serves this data through REST endpoints for dashboard consumption
4. HTML dashboard displays real-time usage statistics with reset functionality

### Database Schema
Single table `usage_log` with fields:
- `id` (primary key), `timestamp`, `model`, `promptTokens`, `completionTokens`, `totalTokens`, `estimatedCostUSD`

### API Endpoints

#### Public Endpoints
- `GET /ping` - Health check
- `GET /dashboard` - Web dashboard (configurable protection via DASHBOARD_PUBLIC)

#### Protected Endpoints (require X-API-Key header)
- `GET /data` - Retrieve all usage logs
- `GET /keys` - List managed API keys (encrypted values masked)
- `POST /keys` - Add new OpenAI API key with label
- `PATCH /keys/<id>/active` - Toggle API key active/inactive status  
- `DELETE /keys/<id>` - Remove API key from management
- `POST /keys/<id>/probe` - Test specific API key validity
- `POST /log` - Manually log usage data (external clients; worker uses direct DB insertion)
- `DELETE /reset` - Clear all usage logs
- `GET /metrics` - System metrics and health status

### Key Patterns
- Database connections use context managers (`with get_conn() as conn`) for automatic cleanup
- HTTP retry logic in worker for transient API failures (429, 5xx errors) with 1-second delay and max 2 attempts
- Environment-based configuration with sensible defaults via `config.py`
- Error handling with conditional full tracebacks (DEBUG mode only, clean JSON errors in production)
- Structured logging using Python logging module with request correlation IDs
- Request tracing middleware: 8-character UUIDs for correlation, response time logging in milliseconds
- Consistent JSON error responses with `json_error()` helper function
- CORS configuration: restrictive with `ALLOWED_ORIGINS` in production, wide open in development
- Cost calculation with configurable rates in `calc.py` (currently hardcoded for gpt-4o-mini pricing)

### Security & Production Notes
- **API Key Auth**: Simple header-based authentication (`X-API-Key`)
- **CORS**: Configured via `ALLOWED_ORIGINS` environment variable; falls back to wide-open in development
- **Error responses**: Full tracebacks conditional on `DEBUG` flag (auto-determined from `ENV` setting)
- **Environment**: Ensure `.env` file security and never commit API keys to version control
- **Auth bypass**: If `API_KEY` is empty, endpoints remain unprotected (logged as warnings)
- **Production checklist**: Set `ENV=production`, configure `ALLOWED_ORIGINS`, set strong `API_KEY`

### Development Patterns
- Use context managers for database operations to ensure proper connection cleanup
- All Flask routes use consistent error handling with `json_error()` helper
- Worker uses direct database insertion via `insert_usage()`, API `/log` endpoint for external clients
- Dashboard HTML template supports both authenticated and public access modes
- Cost rates in `calc.py` should be updated when OpenAI pricing changes