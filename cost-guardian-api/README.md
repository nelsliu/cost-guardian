# Cost Guardian 💰

Real-time OpenAI API cost monitoring with client-push ingestion

Cost Guardian is a Flask-based web app that helps you monitor OpenAI API usage and costs in real time through client-push data ingestion. It features tracking tokens, rate limiting, and a simple web dashboard.

---

## ✨ Features

### 🏷️ Tracking Token System
- Generate unique tracking tokens for different apps/environments
- Client-push ingestion via `/ingest` endpoint
- No API key storage required - your keys stay in your applications

### 📊 Usage Analytics
- Real-time usage tracking and cost calculation
- Per-token attribution for usage analysis
- Historical data with filtering by date, model, and token
- CSV export capabilities

### 🎛️ Dashboard
- Live table of usage data with filtering
- Usage totals and cost summaries
- Tracking token management
- Admin authentication with "remember me" option

### 🔒 Production Ready
- Admin authentication via X-API-Key header
- Server-to-server authentication via X-Ingest-Key header
- Rate limiting with token bucket algorithm
- CORS controls for browser security
- Environment-aware error handling

### 🐳 Docker Support
- Single-service Docker deployment
- Health checks and persistent storage
- Production-ready with Gunicorn

---

## 🚀 Quick Start

### Prerequisites
- Python 3.9+ or Docker
- OpenAI applications you want to monitor

### 1) Clone & Install

```bash
git clone <repository-url>
cd cost-guardian-api
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 2) Configure

```bash
cp .env.example .env
```

Essential configuration:

```bash
# Required for production
API_KEY=your_secret_admin_key_here          # Admin dashboard access
INGEST_KEY=your_secret_ingest_key_here      # Server-to-server ingestion auth
ENV=production                              # production | development
ALLOWED_ORIGINS=https://your-domain.com     # Browser origins (comma-separated)

# Optional configuration
OPENAI_MODEL=gpt-4o-mini-2024-07-18        # For cost calculation reference
RATE_LIMIT_RPM=60                          # Requests per minute
RATE_LIMIT_BURST=60                        # Burst capacity
INGEST_RPM=60                              # Ingestion rate limit
TRACKING_TOKEN_LENGTH=22                   # Generated token length
```

### 3) Run the Service

**Option A - Python:**
```bash
python app.py
```

**Option B - Docker:**
```bash
docker-compose up -d
```

### 4) Create Your First Tracking Token

1. Open the dashboard: `http://localhost:5001/dashboard`
2. Sign in with your `API_KEY`
3. Create a tracking token (e.g., "Production App")
4. Copy the generated token and code snippet

### 5) Integrate with Your Application

Add the provided code snippet to your OpenAI-using application:

```python
import requests
import json

def track_openai_usage(response, tracking_token="your_token_here"):
    """Track OpenAI API usage after each request"""
    usage = response.usage
    
    usage_data = {
        "tracking_token": tracking_token,
        "model": response.model,
        "prompt_tokens": usage.prompt_tokens,
        "completion_tokens": usage.completion_tokens,
        "total_tokens": usage.total_tokens
    }
    
    try:
        requests.post(
            "http://localhost:5001/ingest",
            headers={"X-Ingest-Key": "your_ingest_key_here"},
            json=usage_data,
            timeout=5
        )
    except Exception as e:
        print(f"Usage tracking failed: {e}")

# Example usage with OpenAI client
response = openai_client.chat.completions.create(
    model="gpt-4o-mini",
    messages=[{"role": "user", "content": "Hello!"}]
)

# Track the usage
track_openai_usage(response, "your_token_here")
```

---

## 📋 API Reference

### Public Endpoints
- `GET /ping` - Health check
- `GET /health` - Detailed health status  
- `GET /dashboard` - Web dashboard (requires auth in production)

### Admin Endpoints (require X-API-Key)
- `GET /data` - Retrieve usage data with filtering
- `GET /models` - List tracked models
- `GET /ingest/tokens` - List tracking tokens
- `POST /ingest/tokens` - Create new tracking token
- `PATCH /ingest/tokens/<id>/active` - Toggle token status
- `DELETE /ingest/tokens/<id>` - Delete tracking token
- `DELETE /reset` - Clear all usage data
- `GET /metrics` - System metrics

### Ingestion Endpoints (require X-Ingest-Key)
- `POST /ingest` - Submit usage data with tracking token

### Deprecated Endpoints
- `POST /log` - Legacy endpoint (use `/ingest` instead)

### Usage Data Format

```json
{
  "tracking_token": "abc123",
  "model": "gpt-4o-mini-2024-07-18",
  "prompt_tokens": 10,
  "completion_tokens": 5,
  "total_tokens": 15,
  "timestamp": "2024-01-15T10:30:00Z"  // Optional, defaults to now
}
```

---

## 🏗️ Architecture

### Ingest-Only Design
Cost Guardian uses a pure client-push architecture:

1. **Your Applications** retain their OpenAI API keys
2. **Tracking Tokens** identify different sources/environments  
3. **Client Code** pushes usage data to `/ingest` after each OpenAI call
4. **Cost Guardian** aggregates, calculates costs, and displays analytics

### Security Model
- **Admin access**: `API_KEY` for dashboard and admin endpoints
- **Ingestion auth**: `INGEST_KEY` for server-to-server data submission  
- **Tracking tokens**: Non-secret identifiers for usage attribution
- **No key storage**: Your OpenAI keys never leave your applications

### Data Flow
```
Your App → OpenAI API → Usage Response → Cost Guardian /ingest → Dashboard
```

---

## 🔧 Configuration

### Environment Variables

```bash
# Server Configuration
SERVER_PORT=5001                    # Flask server port
ENV=development                     # development | production
DB_FILENAME=usage_log.sqlite        # Database filename

# Authentication  
API_KEY=                            # Admin API key (leave empty to disable auth in dev)
INGEST_KEY=your_secret_key          # Required for /ingest endpoint

# CORS Configuration
ALLOWED_ORIGINS=http://localhost:5001  # Comma-separated browser origins

# Rate Limiting
RATE_LIMIT_RPM=60                   # Admin requests per minute
RATE_LIMIT_BURST=60                 # Burst capacity
RATE_LIMIT_EXEMPT=/ping,/health,/dashboard  # Exempt paths

# Ingestion Rate Limiting  
INGEST_RPM=60                       # Ingestion requests per minute
INGEST_BURST=60                     # Ingestion burst capacity

# Model Configuration
OPENAI_MODEL=gpt-4o-mini-2024-07-18 # Reference model for cost calculation
PROVIDER=openai                     # Currently only 'openai' supported

# Tracking Configuration
TRACKING_TOKEN_LENGTH=22            # Generated token length (16-40 recommended)
```

### Production Deployment

1. **Set environment to production**: `ENV=production`
2. **Configure authentication**: Set strong `API_KEY` and `INGEST_KEY`  
3. **Set CORS origins**: Configure `ALLOWED_ORIGINS` for your domain
4. **Enable rate limiting**: Adjust `RATE_LIMIT_RPM` and `INGEST_RPM` as needed
5. **Use Docker**: `docker-compose up -d` for production deployment

---

## 🐳 Docker Deployment

The included `docker-compose.yml` provides a production-ready setup:

```yaml
services:
  api:
    build: .
    ports:
      - "5001:5001"
    env_file: .env
    volumes:
      - ./data:/app/data  # Persistent database storage
    healthcheck:
      test: ["CMD", "curl", "-fsS", "http://localhost:5001/health"]
    restart: unless-stopped
```

**Commands:**
```bash
# Build and start
docker-compose up -d

# View logs  
docker-compose logs -f

# Stop service
docker-compose down
```

---

## 📊 Monitoring & Metrics

### Health Endpoint
`GET /health` returns service status:

```json
{
  "status": "healthy",
  "timestamp": "2024-01-15T10:30:00Z",
  "version": "1.0.0"
}
```

### Metrics Endpoint  
`GET /metrics` provides operational metrics:

```json
{
  "version": "1",
  "env": "production", 
  "ingest": {
    "rpm": 60,
    "burst": 60,
    "auth_enabled": true
  },
  "counters": {
    "ingest_success": 1250,
    "ingest_duplicate": 5,
    "ingest_bad_auth": 2
  },
  "db": {
    "usage_rows": 1200,
    "active_tokens": 3,
    "last_usage_at": "2024-01-15T10:25:00Z"
  }
}
```

---

## 🔄 Migration from v0.2.x

If upgrading from the previous API key management version:

1. **Backup your data**: Copy your SQLite database
2. **Update environment**: Remove `MASTER_KEY`, `PROBE_INTERVAL_SECS`, `WORKER_HEARTBEAT_ENABLED`
3. **Add new variables**: Set `INGEST_KEY` and adjust rate limits
4. **Create tracking tokens**: Replace managed API keys with tracking tokens  
5. **Update client code**: Integrate the client-push tracking snippet
6. **Remove worker**: The background worker is no longer needed

**Breaking changes in v0.3.x:**
- `/keys/*` endpoints removed (404)
- Worker service removed from Docker Compose
- `MASTER_KEY` no longer required
- Client-side integration now required for data collection

---

## 🏗️ Development

### Project Structure
```
├── app.py              # Flask application and API routes
├── db.py               # Database operations and schema  
├── config.py           # Environment configuration
├── calc.py             # Cost calculation utilities
├── rate_limit.py       # Token bucket rate limiting
├── metrics.py          # Application metrics collection
├── templates/          # HTML dashboard template
├── data/               # SQLite database storage
├── requirements.txt    # Python dependencies
├── Dockerfile          # Container build
└── docker-compose.yml  # Multi-service orchestration
```

### Local Development
```bash
# Install dependencies
pip install -r requirements.txt

# Run with auto-reload
python app.py

# Run tests (if available)
python -m pytest
```

### Database Schema
- `usage_log`: Usage tracking with token attribution
- `ingest_tokens`: Tracking token management  
- `api_keys`: Legacy table (deprecated, kept for compatibility)

---

## 📈 Cost Calculation

Cost Guardian calculates estimates based on the configured model's pricing:

- **Current rates**: Based on `gpt-4o-mini-2024-07-18` pricing
- **Calculation**: `(prompt_tokens * input_rate + completion_tokens * output_rate) / 1M`
- **Updates**: Modify `calc.py` when OpenAI updates pricing

**Note**: Estimates are for monitoring purposes. Always verify costs in your OpenAI billing dashboard.

---

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch: `git checkout -b feature-name`
3. Make changes and test thoroughly  
4. Submit a pull request with clear description

---

## 📄 License

[Add your license here]

---

## 🛟 Support

- **Issues**: Report bugs via GitHub Issues
- **Discussions**: Feature requests and questions welcome
- **Security**: Report security issues privately

---

*Cost Guardian - Keep your OpenAI costs under control* 💰✨