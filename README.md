Cost Guardian 💰

Ingest-first OpenAI usage and cost tracking with per-token attribution and a lightweight admin dashboard.

Cost Guardian is an ingest-first tracker: your app keeps using the OpenAI SDK as usual, and you post usage (tokens, model, cost) to `POST /ingest` with a tracking token. The dashboard (auth required in production) shows per-token usage, filters, totals, CSV export, and metrics.

—

What’s included

- Tracking tokens: Generate tokens per app/env and attribute usage server-side.
- Ingest key: Server-to-server auth for `POST /ingest` via `X-Ingest-Key`.
- Admin auth: Protects dashboard/data via `X-API-Key` (required in production).
- Rate limiting: Separate buckets for admin endpoints and ingest.
- Persistence: SQLite at `/app/data/usage_log.sqlite` (Docker volume-safe).
- Metrics: `GET /metrics` includes counters and ingest/DB health.

—

Quick start (Docker)

1) Configure environment (minimal):

API_KEY=your_admin_key            # required for production dashboard/data
INGEST_KEY=your_ingest_secret     # required for POST /ingest
ENV=development                   # or production
ALLOWED_ORIGINS=http://localhost:5001

2) Run:

docker compose up -d

3) Open dashboard:

http://localhost:5001/dashboard

—

Quick start (local)

cd cost-guardian-api
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env  # set API_KEY, INGEST_KEY, ENV, etc.
python app.py

—

Integration flow

- Create a tracking token in the dashboard.
- In your app, after each OpenAI call, post a JSON payload to `POST /ingest`:
  - Headers: `X-Ingest-Key: <INGEST_KEY>`
  - Body: `{ tracking_token, model, prompt_tokens, completion_tokens, total_tokens, cost_usd?, event_id? }`
- The server calculates cost when omitted and de-duplicates by `event_id`.

Security notes

- Never log or store customer API keys here — only identifiers (tracking tokens) are used.
- Keep `INGEST_KEY` secret; the dashboard never exposes it.
- Admin endpoints require `X-API-Key` when `ENV=production`.

—

More details

See `cost-guardian-api/README.md` for API endpoints, environment variables, and UI screenshots.


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
