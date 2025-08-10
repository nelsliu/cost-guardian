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

### Environment Setup
Create a `.env` file with required variables:
```
OPENAI_API_KEY=your_api_key_here
OPENAI_MODEL=gpt-4o-mini-2024-07-18
PROBE_INTERVAL_SECS=300
SERVER_PORT=5001
DB_FILENAME=cost_guardian.db
HEARTBEAT_PROMPT=ping

# Auth config
API_KEY=your_secret_api_key_here
DASHBOARD_PUBLIC=true
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
- **Database Layer** (`db.py`): SQLite operations with automatic connection cleanup
- **Cost Calculator** (`calc.py`): Computes estimated costs based on token usage rates
- **Configuration** (`config.py`): Environment variable management with defaults

### Data Flow
1. Worker sends heartbeat requests to OpenAI API at configured intervals
2. Usage data (tokens, costs) is parsed and stored in SQLite database via `insert_usage()`
3. Flask API serves this data through REST endpoints for dashboard consumption
4. HTML dashboard displays real-time usage statistics with reset functionality

### Database Schema
Single table `usage_log` with fields:
- `id` (primary key), `timestamp`, `model`, `promptTokens`, `completionTokens`, `totalTokens`, `estimatedCostUSD`

### API Endpoints
- `GET /ping` - Health check (public)
- `GET /data` - Retrieve all usage logs (protected)
- `POST /log` - Manually log usage data (protected, for external clients; worker uses direct DB insertion)
- `DELETE /reset` - Clear all usage logs (protected)
- `GET /dashboard` - Serve HTML dashboard (configurable protection)

### Key Patterns
- Database connections are closed after each operation for automatic cleanup
- HTTP retry logic in worker for transient API failures (429, 5xx errors) with 1-second delay
- Environment-based configuration with sensible defaults
- Error handling with full tracebacks in API responses (development only - restrict in production)
- Structured logging using Python logging module (avoid logging sensitive data like API keys)
- Request tracing with unique IDs and response time logging
- Consistent JSON error responses with request correlation

### Security & Production Notes
- **API Key Auth**: Simple header-based authentication (`X-API-Key`)
- **CORS**: Currently wide open for development; restrict origins in production
- **Error responses**: Full tracebacks shown in development; should be conditional on DEBUG mode in production
- **Environment**: Ensure `.env` file security and never commit API keys to version control
- **Auth bypass**: If `API_KEY` is empty, endpoints remain unprotected (logged as warnings)