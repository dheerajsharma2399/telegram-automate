
# Telegram Job Scraper Bot

A comprehensive Telegram automation project that monitors job postings in Telegram groups, parses job details using LLMs (OpenRouter), stores structured data in Supabase PostgreSQL database, and optionally syncs results to Google Sheets. It includes a web dashboard for monitoring and control, and exposes a REST API for programmatic control.

## 🚀 Quick Start

### Prerequisites
- Docker and Docker Compose
- PostgreSQL/Supabase database
- Telegram API credentials
- OpenRouter API key (for LLM processing)
- Google Sheets credentials (optional)

### Installation

1. **Clone the repository**
   ```bash
   git clone <repository-url>
   cd telegram-automate
   ```

2. **Set up environment variables**
   ```bash
   cp .env.example .env
   # Edit .env with your credentials
   ```

3. **Configure Supabase Database**
   - Use the provided SQL script: `supabase_init.sql`
   - Or let the application auto-create tables on startup

4. **Run with Docker**
   ```bash
   docker-compose up --build -d
   ```

5. **Access the application**
   - Web Dashboard: http://localhost:9501
   - Health Check: http://localhost:9501/health

## 📋 Configuration

### Required Environment Variables

```bash
# Telegram Configuration
TELEGRAM_API_ID=your_api_id
TELEGRAM_API_HASH=your_api_hash
TELEGRAM_PHONE=your_phone_number
TELEGRAM_BOT_TOKEN=your_bot_token
TELEGRAM_GROUP_USERNAMES=jobgroup1,jobgroup2
AUTHORIZED_USER_IDS=123456789
ADMIN_USER_ID=123456789

# Database Configuration
DATABASE_URL=postgresql://user:password@host:port/database

# OpenRouter Configuration
OPENROUTER_API_KEY=your_openrouter_key
OPENROUTER_MODEL=anthropic/claude-3.5-sonnet
OPENROUTER_FALLBACK_MODEL=openai/gpt-4o-mini

# Google Sheets Configuration (Optional)
GOOGLE_CREDENTIALS_JSON={"type":"service_account",...}
SPREADSHEET_ID=your_spreadsheet_id
```

### Optional Environment Variables

```bash
# Application Settings
PORT=9501
FLASK_ENV=production
BOT_RUN_MODE=webhook
BATCH_SIZE=10
PROCESSING_INTERVAL_MINUTES=5
MAX_RETRIES=3
```

## 🏗️ Architecture

### Core Components

```
┌─────────────────────────────────────────────────────────────┐
│                     TELEGRAM BOT (Controller)                │
│  Commands: /start, /stop, /status, /process, /stats         │
└───────────────────┬─────────────────────────────────────────┘
                    │
        ┌───────────┴───────────┐
        ▼                       ▼
┌───────────────┐       ┌──────────────────┐
│  Job Monitor  │       │  Message Queue   │
│   (Listener)  │──────▶│   (PostgreSQL)   │
└───────────────┘       └──────────────────┘
                                │
                        ┌───────┴────────┐
                        ▼                ▼
                ┌──────────────┐  ┌─────────────┐
                │ LLM Processor│  │   Status    │
                │  (OpenRouter)│  │   Tracker   │
                └──────┬───────┘  └─────────────┘
                       │
        ┌──────────────┴──────────────┐
        ▼                             ▼
┌──────────────┐              ┌──────────────┐
│ Google Sheets│              │  Local CSV   │
│  (Primary DB)│              │   (Backup)   │
└──────────────┘              └──────────────┘
```

## 🧪 Testing

### Basic Test Suite
```bash
# Run basic functionality tests
python basic_test.py
```

### Comprehensive Test Suite
```bash
# Run all component tests
python comprehensive_test.py
```

### Expected Test Results
```
✅ PASS: Imports
✅ PASS: Database  
✅ PASS: Configuration
✅ PASS: Web Server
✅ PASS: Telegram API
✅ PASS: LLM Processor
✅ PASS: Sheets Sync

Success Rate: 100.0%
```

### Manual Testing Checklist

- [ ] **Database Connection**: PostgreSQL connects successfully
- [ ] **Table Creation**: All tables initialize in Supabase
- [ ] **Telegram Session**: Session storage works in Supabase
- [ ] **API Endpoints**: All `/api/*` endpoints respond correctly
- [ ] **Bot Commands**: `/start`, `/stop`, `/status` work
- [ ] **Google Sheets**: Sync operations function properly
- [ ] **LLM Processing**: Job parsing extracts data correctly

## 📊 Database Schema

### Tables Overview

| Table | Purpose | Key Fields |
|-------|---------|------------|
| `raw_messages` | Store Telegram messages | message_id, message_text, status |
| `processed_jobs` | Parsed job data | job_id, company_name, job_role, email |
| `bot_config` | Configuration storage | key, value |
| `commands_queue` | Dashboard-to-bot communication | command, status, executed_at |
| `telegram_auth` | Telegram session storage | session_string, login_status |

### Manual Database Setup

If you prefer manual setup, use the provided SQL script:

```sql
-- Run in your PostgreSQL/Supabase database
psql -d your_database -f supabase_init.sql
```

The script creates all required tables with proper indexes and default data.

## 🤖 Bot Commands

### Primary Commands

- `/start` — Start job monitoring and processing
- `/stop` — Stop job processing
- `/status` — Show current system status
- `/process` — Manually trigger processing cycle
- `/generate_emails` — Generate email bodies for jobs
- `/sync_sheets` — Sync jobs to Google Sheets
- `/export` — Create CSV exports
- `/stats [days]` — Show statistics for last N days

### Status Display Format
```
📊 Job Scraper Status

🔄 Monitoring: Running
🟢 Job Processing: Running
📨 Unprocessed Messages: 5
✅ Processed Jobs (Today): 12
  - 📧 With Email: 8
  - 🔗 Without Email: 4
```

## 🌐 Web API

### API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/status` | GET | System status and statistics |
| `/api/queue` | GET | Unprocessed messages queue |
| `/api/pending_commands` | GET | Pending bot commands |
| `/api/command` | POST | Enqueue new command |
| `/api/generate_emails` | POST | Generate email bodies |
| `/api/logs` | GET | System logs |
| `/api/monitored_groups` | GET/POST/DELETE | Manage monitored groups |

### Example API Usage

```bash
# Get system status
curl http://localhost:9501/api/status

# Enqueue a command
curl -X POST http://localhost:9501/api/command \
  -H "Content-Type: application/json" \
  -d '{"command": "/process"}'
```

## 🔧 Docker Deployment

### Docker Compose Configuration

The application uses a unified port configuration (9501):

```yaml
services:
  telegram-job-scraper:
    build: .
    ports:
      - "9501:9501"
    environment:
      - PORT=9501
      - DATABASE_URL=${DATABASE_URL}
      # ... other environment variables
```

### Dockerfile Features

- Python 3.11-slim base image
- Gunicorn for production WSGI server
- PostgreSQL adapters included
- Health check endpoint
- Automatic table initialization

### Deployment Commands

```bash
# Build and run
docker-compose up --build -d

# View logs
docker-compose logs -f

# Stop services
docker-compose down

# Restart services
docker-compose restart
```

## 🛠️ Troubleshooting

### Common Issues and Solutions

#### 1. Database Connection Issues

**Problem**: `psycopg2.OperationalError: connection refused`

**Solution**:
- Verify DATABASE_URL format: `postgresql://user:password@host:port/database`
- Check Supabase server is running
- Verify network connectivity
- Test connection manually: `psql "$DATABASE_URL"`

**Debug Steps**:
```bash
# Test database connection
python -c "
from database import Database
from config import DATABASE_URL
db = Database(DATABASE_URL)
print('Database connected successfully')
"
```

#### 2. Port Conflicts

**Problem**: `Address already in use` on port 9501

**Solution**:
```bash
# Find process using port 9501
netstat -tulpn | grep :9501
# Kill process if needed
kill -9 <PID>
# Or change PORT in .env file
```

#### 3. Telegram API Issues

**Problem**: `Telegram API returned error`

**Solutions**:
- Verify TELEGRAM_BOT_TOKEN is correct
- Check TELEGRAM_API_ID and TELEGRAM_API_HASH
- Ensure authorized users are configured
- Verify Telegram bot permissions

**Debug Steps**: