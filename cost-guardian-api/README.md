Here’s a cleaned-up, production-ready README you can drop in:

Cost Guardian 💰

Real-time OpenAI API cost monitoring with secure multi-key management

Cost Guardian is a Flask-based web app that helps you monitor OpenAI API usage and costs in real time. It includes encrypted API key storage, background usage collection, rate limiting, and a simple web dashboard.

⸻

✨ Features

🔐 Secure multi-key management
	•	Encrypted at rest with Fernet (symmetric encryption)
	•	Multiple keys per deployment, each with a label
	•	Activate/disable keys without deleting
	•	Masked display—plaintext keys never returned or logged

📊 Automated usage tracking
	•	Background worker probes OpenAI regularly
	•	Cost estimates using the configured model’s pricing
	•	Per-key attribution for usage and cost
	•	Health flag: last successful probe per key

🎛️ Dashboard
	•	Live table of usage rows
	•	Totals row (tokens & $)
	•	Manage API keys (add/activate/delete)
	•	Auth UI (enter admin API key once; “remember” option)

🔒 Production hardening
	•	Admin auth via X-API-Key
	•	Rate limiting (token bucket; per API key or IP)
	•	CORS controls (allowed origins)
	•	Environment-aware errors (clean JSON in prod)

🐳 Docker support
	•	Dockerfile + docker compose
	•	Health checks
	•	Persistent volume for database

⸻

🚀 Quick Start

Prerequisites
	•	Python 3.9+
	•	(Optional) Docker & Docker Compose
	•	An OpenAI account (you add API keys in the dashboard—not in .env)

1) Clone & install (no Docker)

git clone <repository-url>
cd cost-guardian-api
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

2) Configure

Copy the example env and set required values:

cp .env.example .env

Essential configuration:

# Required
MASTER_KEY=your_32_byte_fernet_key_here           # Generate: python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
API_KEY=your_secret_admin_key_here                # For admin requests to protected endpoints
ENV=production                                    # production | development
ALLOWED_ORIGINS=https://your-domain.com           # Comma-separated list of allowed browser origins

# OpenAI + worker
OPENAI_MODEL=gpt-4o-mini-2024-07-18
PROBE_INTERVAL_SECS=300

# Rate limiting (optional; per process)
RATE_LIMIT_RPM=60
RATE_LIMIT_BURST=60
RATE_LIMIT_EXEMPT=/ping,/dashboard,/health

Notes
	•	Do not change MASTER_KEY after adding keys; previously stored keys become unrecoverable.
	•	In development you can set ENV=development and ALLOWED_ORIGINS=http://127.0.0.1:5001.

3) Run it

Option A — Python

# Terminal 1 (API)
python app.py

# Terminal 2 (worker)
python worker.py

Option B — Docker

docker compose up -d

4) Open the dashboard

Visit: http://localhost:5001/dashboard

From the dashboard you can:
	•	Add your OpenAI API keys (stored encrypted)
	•	See live usage rows & totals
	•	Activate/deactivate or delete keys

⸻

🔧 How it works
	1.	Admin auth: In production, the dashboard always requires sign-in. In development, leaving API_KEY blank disables admin auth for faster local testing.
	2.	Keys at rest: Your OpenAI keys are encrypted with MASTER_KEY and never returned in plaintext.
	3.	Background worker: Probes the OpenAI API on a schedule and logs per-key usage to SQLite.
	4.	Rate limiting: Token bucket—configurable RPM & burst. In auth mode it limits per API key; in no-auth mode it limits per IP.
Limits are per process (in-memory). Multiple API replicas mean limits apply per replica.

⸻

📡 API Endpoints

Public
	•	GET /ping — lightweight liveness
	•	GET /health — health probe
	•	GET /dashboard — dashboard HTML (data calls are protected)

Protected (require X-API-Key)
	•	GET /data — list usage rows
	•	DELETE /reset — clear usage data
	•	GET /keys — list keys (masked)
	•	POST /keys — add key {label, key, provider}
	•	PATCH /keys/<id>/active — activate/deactivate
	•	DELETE /keys/<id> — delete key
	•	GET /metrics — system metrics & health

Example /metrics

curl -s -H "X-API-Key: $API_KEY" http://localhost:5001/metrics | jq

Example response (fields abbreviated):

{
  "version": "1",
  "env": "production",
  "debug": false,
  "rate_limit": {"rpm": 60, "burst": 60, "exempt_paths": ["/ping","/dashboard","/health"]},
  "counters": {"rate_limit_hits": 2},
  "db": {
    "usage_rows": 1250,
    "active_keys": 3,
    "last_usage_at": "2025-08-11T10:30:45+00:00",
    "last_key_ok_at": "2025-08-11T10:30:12+00:00"
  },
  "worker": {"probe_interval_secs": 300, "healthy": true}
}


⸻

🐳 Docker deployment

Development

docker compose up -d

Production (example)

export ENV=production
export MASTER_KEY="your_master_key"
export API_KEY="your_admin_key"
export ALLOWED_ORIGINS="https://your-domain.com"

docker compose up -d

Security tips
	•	Provide secrets via env vars or Docker secrets (not baked into images)
	•	Restrict ALLOWED_ORIGINS
	•	Terminate TLS (HTTPS) at a reverse proxy (nginx/Traefik) in front

⸻

🔐 Security considerations
	•	MASTER_KEY: Back it up securely (password manager / vault). If lost, encrypted keys are unrecoverable.
	•	No plaintext key exposure: The server never returns stored API keys.
	•	Auth vs. rate limiting:
	•	Missing/invalid admin key → 401
	•	Over the limit → 429 with Retry-After
	•	Prod error handling: In ENV=production, clients get clean JSON; full tracebacks stay in server logs.

⸻

💾 Persistence

### Database Storage
- **Container Location**: `/app/data/usage_log.sqlite`
- **Host Mapping**: `./data` directory (created automatically)
- **Volume Mount**: `./data:/app/data` in both API and worker containers

### Data Backup
```bash
# Backup your data
tar -czf cost-guardian-backup-$(date +%Y%m%d).tgz ./data

# Restore data
tar -xzf cost-guardian-backup-YYYYMMDD.tgz
```

### Legacy Migration
On first startup, Cost Guardian automatically migrates existing databases:
1. Checks `./data/cost_guardian.db` (preferred if exists)  
2. Falls back to `./cost_guardian.db` (root directory)
3. Falls back to `./usage_log.sqlite` (root directory)

**Upgrade Note**: If you have an existing database in the app root, it will be automatically moved to `./data/usage_log.sqlite` on first run. Look for the migration log message to confirm.

Migration precedence ensures newer data isn't overwritten - check logs for "Migrated legacy DB from X to Y" confirmation.

⸻

🧭 Troubleshooting
	•	Port already in use: Stop previous server. macOS:

lsof -ti :5001 | xargs kill -9


	•	CORS blocked: Set ALLOWED_ORIGINS to match the URL you load the dashboard from.
	•	Cannot fetch data (401): Ensure requests include X-API-Key equal to your admin key.
	•	Rate limited (429): The dashboard auto-retries; or respect Retry-After header.

⸻

📂 Project structure

cost-guardian-api/
├─ app.py               # Flask API & routes
├─ worker.py            # Background probing loop
├─ crypto.py            # Fernet encrypt/decrypt helpers
├─ db.py                # SQLite schema & ops
├─ calc.py              # Cost calculation
├─ rate_limit.py        # Token bucket limiter
├─ metrics.py           # Counters & metrics snapshot
├─ config.py            # Env-driven configuration
├─ templates/
│  └─ dashboard.html    # Dashboard UI
├─ requirements.txt
├─ Dockerfile
├─ docker-compose.yml
└─ README.md


⸻

🛠️ Development tips

Run tests / manual probes

# Ensure DB schema is up to date
python -c "from db import migrate; migrate()"

# One-off probe (uses active keys)
python worker.py --once

# Manual API check (requires admin key)
curl -H "X-API-Key: $API_KEY" http://localhost:5001/keys


⸻

📄 License

Add your license text here.

🤝 Contributing

PRs and issues welcome—please open a discussion with proposed changes and rationale.

⸻

Cost Guardian — keep your AI costs under control. 🎯
