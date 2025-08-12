# Cost Guardian 💰

**Real-time OpenAI API cost monitoring and multi-user key management**

Cost Guardian is a Flask-based web application that helps you monitor your OpenAI API usage and costs in real-time. It features secure multi-user API key management, automatic usage tracking, and a clean web dashboard for monitoring your AI spend.

## ✨ Features

### 🔐 **Secure Multi-User API Key Management**
- **Encrypted Storage**: All API keys are encrypted at rest using Fernet symmetric encryption
- **Multi-Key Support**: Add and manage multiple OpenAI API keys with custom labels
- **Access Control**: Toggle keys on/off without deleting them
- **Real-time Testing**: Test any API key instantly from the dashboard

### 📊 **Automated Usage Tracking** 
- **Background Monitoring**: Continuously probes OpenAI API to track token usage
- **Cost Calculation**: Automatic cost estimation based on current OpenAI pricing
- **Per-Key Attribution**: Track usage and costs for each individual API key
- **Health Monitoring**: Tracks last successful connection time for each key

### 🎛️ **Web Dashboard**
- **Clean Interface**: Modern, responsive web UI for monitoring and management
- **Real-time Data**: Live usage statistics and cost tracking
- **Key Management**: Add, test, activate/deactivate, and delete API keys
- **Usage Totals**: Automatic totals row showing aggregated tokens and costs
- **Data Export**: View detailed usage logs with JSON API endpoints

### 🔒 **Enterprise Security**
- **API Key Authentication**: Secure admin access with X-API-Key headers
- **Rate Limiting**: Per-API-key token bucket rate limiting with configurable limits
- **Configurable Dashboard Access**: Public or private dashboard modes
- **Production Ready**: Environment-based configuration with security warnings
- **CORS Protection**: Configurable origin restrictions

### 🐳 **Docker Support**
- **Containerized**: Full Docker and Docker Compose support
- **Volume Persistence**: Database and configuration persistence
- **Health Checks**: Built-in container health monitoring
- **Easy Deployment**: Single command deployment

## 🚀 Quick Start

### Prerequisites
- Python 3.9+
- OpenAI API key
- Docker & Docker Compose (optional)

### 1. Clone and Setup

```bash
git clone <repository-url>
cd cost-guardian-api
pip install -r requirements.txt
```

### 2. Configuration

Copy the example environment file and configure:

```bash
cp .env.example .env
```

**Essential configuration:**
```env
# Generate with: python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
MASTER_KEY=your_32_byte_fernet_key_here

# Your admin API key for dashboard access
API_KEY=your_secret_admin_key_here

# OpenAI settings
OPENAI_MODEL=gpt-4o-mini-2024-07-18
PROBE_INTERVAL_SECS=300

# Rate limiting (optional)
RATE_LIMIT_RPM=60
RATE_LIMIT_BURST=60
RATE_LIMIT_EXEMPT=/ping,/dashboard
```

### 3. Run the Application

**Option A: Direct Python**
```bash
# Start the web server
python app.py

# In another terminal, start the worker
python worker.py
```

**Option B: Docker Compose**
```bash
docker-compose up -d
```

### 4. Access Dashboard

Visit `http://localhost:5001/dashboard` to:
- Add your OpenAI API keys
- Monitor real-time usage and costs
- Test key validity
- View detailed usage logs

## 🔧 Usage Workflow

### Initial Setup
1. **Generate Master Key**: Create a secure encryption key for API key storage
2. **Set Admin Key**: Configure admin access to the dashboard
3. **Start Services**: Launch both the web server and background worker

### Managing API Keys
1. **Add Keys**: Use the dashboard to securely add labeled OpenAI API keys
2. **Test Keys**: Instantly verify key validity with the "Test" button
3. **Monitor Health**: View last successful connection time for each key
4. **Toggle Access**: Activate/deactivate keys without deleting them

### Monitoring Usage
1. **Real-time Tracking**: Worker automatically probes active keys every 5 minutes
2. **Cost Attribution**: View usage and costs broken down by individual API key
3. **Historical Data**: Access complete usage history via dashboard or API
4. **Export Data**: Use REST endpoints for integration with other tools

### Rate Limiting (Optional)
1. **Per-Key Limiting**: Each API key gets separate rate limit buckets
2. **Token Bucket Algorithm**: Configurable requests per minute with burst capacity
3. **Automatic Fallback**: IP-based limiting when authentication is disabled
4. **Exempt Endpoints**: Health checks and dashboard always accessible
5. **In-Memory Buckets**: Rate limits are per-process; with multiple workers/replicas, limits apply per worker

## 📡 API Endpoints

### Public Endpoints
- `GET /ping` - Health check
- `GET /dashboard` - Web dashboard (configurable)

### Protected Endpoints (require X-API-Key header)
- `GET /data` - Retrieve usage logs
- `GET /keys` - List API keys (masked)
- `POST /keys` - Add new API key
- `PATCH /keys/<id>/active` - Toggle key status
- `DELETE /keys/<id>` - Remove API key
- `POST /keys/<id>/probe` - Test specific key
- `DELETE /reset` - Clear all usage data
- `GET /metrics` - System metrics and health status

#### Example /metrics Response
```json
{
  "version": "1",
  "env": "development", 
  "debug": true,
  "rate_limit": { "rpm": 60, "burst": 60, "exempt_paths": ["/ping", "/dashboard"] },
  "counters": { "rate_limit_hits": 42 },
  "db": {
    "usage_rows": 1250,
    "active_keys": 3,
    "last_usage_at": "2024-01-15T10:30:45.123456+00:00",
    "last_key_ok_at": "2024-01-15T10:30:12.987654+00:00"
  },
  "worker": { "probe_interval_secs": 300, "healthy": true }
}
```

## 🐳 Docker Deployment

### Development
```bash
docker-compose up -d
```

### Production
```bash
# Set production environment
export ENV=production
export MASTER_KEY="your_secure_master_key"
export API_KEY="your_admin_key"

docker-compose up -d
```

### Docker Security Notes
- Use environment variables or Docker secrets for sensitive keys
- Never bake MASTER_KEY into Docker images
- Restrict ALLOWED_ORIGINS in production
- Use HTTPS in production deployments

## 🔐 Security Considerations

### Encryption
- **Master Key**: All API keys encrypted with Fernet symmetric encryption
- **Key Storage**: Only encrypted blobs stored in database
- **No Key Leakage**: Plaintext keys never logged or exposed via API

### Access Control
- **Admin Authentication**: X-API-Key header required for management endpoints
- **Dashboard Security**: Configurable public/private access
- **CORS Protection**: Configurable origin restrictions

### Production Checklist
- [ ] Set `ENV=production`
- [ ] Configure strong `API_KEY` 
- [ ] Set `ALLOWED_ORIGINS` to specific domains
- [ ] Backup `MASTER_KEY` securely
- [ ] Use HTTPS
- [ ] Regular security updates

## 📂 Project Structure

```
cost-guardian-api/
├── app.py              # Flask web server & API endpoints
├── worker.py           # Background usage monitoring
├── crypto.py           # Encryption/decryption utilities
├── db.py              # Database operations & schema
├── calc.py            # Cost calculation logic
├── config.py          # Configuration management
├── templates/
│   └── dashboard.html # Web dashboard UI
├── requirements.txt   # Python dependencies
├── Dockerfile        # Container definition
├── docker-compose.yml # Multi-service orchestration
└── README.md         # This file
```

## 🛠️ Development

### Running Tests
```bash
# Test single probe
python worker.py --once

# Manual API testing
curl -H "X-API-Key: your_key" http://localhost:5001/keys
```

### Database Management
```bash
# Manual migration
python -c "from db import migrate; migrate()"

# Reset all data
curl -X DELETE -H "X-API-Key: your_key" http://localhost:5001/reset
```

## ⚠️ Important Warnings

### Master Key Security
- **BACKUP YOUR MASTER KEY**: If lost, all stored API keys become permanently unrecoverable
- **Store Securely**: Use a password manager or encrypted vault
- **Never Commit**: Ensure `.env` is in `.gitignore`

### Production Deployment
- **Use HTTPS**: Encrypt traffic in production
- **Restrict Origins**: Configure `ALLOWED_ORIGINS` appropriately
- **Monitor Logs**: Watch for unauthorized access attempts
- **Regular Updates**: Keep dependencies current

## 📄 License

[Add your license here]

## 🤝 Contributing

[Add contribution guidelines here]

---

**Cost Guardian** - Keep your AI costs under control! 🎯