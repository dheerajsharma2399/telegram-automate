# Telegram Job Scraper Bot 🚀

A comprehensive Telegram automation project that monitors job postings in Telegram groups, parses job details using LLMs (OpenRouter), stores structured data in **Supabase PostgreSQL database**, and optionally syncs results to Google Sheets. It includes a web dashboard for monitoring and control, and exposes a REST API for programmatic control.

**New Feature**: Enhanced job management dashboard with application status tracking, duplicate detection, and bulk operations for efficient job application management.

## ✨ Features

### Core Functionality
- 🤖 **Telegram Bot**: Monitors multiple job groups simultaneously
- 🧠 **AI Job Parsing**: LLM-powered extraction of job details
- 📊 **Supabase PostgreSQL**: Reliable cloud database storage
- 📈 **Google Sheets Integration**: Optional sync for external analysis
- 🌐 **Web Dashboard**: Real-time monitoring and control interface
- 📋 **Job Management**: Application status tracking and duplicate detection

### New Job Management Dashboard
- **Application Status Tracking**: Track jobs through complete application lifecycle
- **Relevance Classification**: AI-powered classification for fresher-friendly roles
- **Duplicate Detection**: Automatic identification of duplicate job postings
- **Bulk Operations**: Mass updates and actions for efficiency
- **CSV Export**: Export data for external analysis
- **Real-time Notes**: Track follow-ups and application notes

## 🚀 Quick Start

### Prerequisites
- Docker and Docker Compose
- **Supabase PostgreSQL database** (free tier available)
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
   # Edit .env with your Supabase PostgreSQL credentials
   ```

3. **Configure Supabase Database**
   - Create a new Supabase project
   - Get your DATABASE_URL from Supabase settings
   - Update the DATABASE_URL in your .env file
   - Tables will be auto-created on first run

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
TELEGRAM_GROUP_USERNAMES=jobgroup1,jobgroup2
AUTHORIZED_USER_IDS=123456789
ADMIN_USER_ID=123456789

# Database Configuration (Supabase PostgreSQL)
DATABASE_URL=postgresql://postgres:your_password@db.your-project.supabase.co:5432/postgres

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
CONTAINER_TYPE=all
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
                │ LLM Processor│  │   Dashboard │
                │  (OpenRouter)│  │  Management │
                └──────┬───────┘  └─────────────┘
                       │
        ┌──────────────┴──────────────┐
        ▼                             ▼
┌──────────────┐              ┌──────────────┐
│ Google Sheets│              │  Local CSV   │
│   (Optional) │              │   (Backup)   │
└──────────────┘              └──────────────┘
```

### Database Architecture (Supabase PostgreSQL)

```
┌─────────────────────────────────────────────────────────────┐
│                    DATABASE LAYER                             │
├─────────────────────────────────────────────────────────────┤
│  RAW DATA LAYER (Original Scraping)                         │
│  ├── raw_messages      - Raw Telegram messages               │
│  ├── processed_jobs    - Extracted job data                 │
│  ├── bot_config        - System configuration               │
│  ├── commands_queue    - Dashboard-to-bot communication     │
│  └── telegram_auth     - Telegram session storage           │
├─────────────────────────────────────────────────────────────┤
│  DASHBOARD LAYER (Application Management)                   │
│  ├── dashboard_jobs    - User application tracking         │
│  └── job_duplicate_groups - Duplicate job management       │
└─────────────────────────────────────────────────────────────┘
```

## 📊 Database Schema

### Tables Overview

| Table | Purpose | Key Fields |
|-------|---------|------------|
| `raw_messages` | Store Telegram messages | message_id, message_text, status |
| `processed_jobs` | Parsed job data | job_id, company_name, job_role, email |
| `dashboard_jobs` | Application management | job_id, application_status, job_relevance |
| `job_duplicate_groups` | Duplicate handling | job_id, duplicate_of_id, confidence_score |
| `bot_config` | Configuration storage | key, value |
| `commands_queue` | Dashboard-to-bot communication | command, status, executed_at |
| `telegram_auth` | Telegram session storage | session_string, login_status |

### Database Setup

The application automatically initializes all required tables on first run. For manual setup:

```sql
-- Run in your Supabase SQL editor
-- Use the provided supabase_init.sql script
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
python comprehensive_bug_test.py
```

### Expected Test Results
```
✅ PASS: Python Syntax
✅ PASS: Database Integration
✅ PASS: Configuration
✅ PASS: Web Server
✅ PASS: Telegram API
✅ PASS: LLM Processor
✅ PASS: Job Management
✅ PASS: Duplicate Detection

Success Rate: 100.0%
```

### Manual Testing Checklist

- [ ] **Database Connection**: Supabase PostgreSQL connects successfully
- [ ] **Table Creation**: All tables initialize properly
- [ ] **Telegram Session**: Session storage works in Supabase
- [ ] **API Endpoints**: All `/api/*` endpoints respond correctly
- [ ] **Bot Commands**: `/start`, `/stop`, `/status` work
- [ ] **Job Management**: Dashboard jobs system operational
- [ ] **Duplicate Detection**: AI-powered duplicate identification
- [ ] **Google Sheets**: Sync operations function properly
- [ ] **LLM Processing**: Job parsing extracts data correctly

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
📋 Dashboard Jobs: 25
  - ✅ Applied: 8
  - ⏳ Not Applied: 12
  - 📞 Interview: 3
  - ❌ Rejected: 2
```

## 🌐 Web API

### Core API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/status` | GET | System status and statistics |
| `/api/queue` | GET | Unprocessed messages queue |
| `/api/pending_commands` | GET | Pending bot commands |
| `/api/command` | POST | Enqueue new command |
| `/api/logs` | GET | System logs |
| `/api/monitored_groups` | GET/POST/DELETE | Manage monitored groups |

### Job Management API

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/dashboard/jobs` | GET/POST | Get all jobs / Create new job |
| `/api/dashboard/jobs/{id}` | PUT/DELETE | Update/Delete specific job |
| `/api/dashboard/jobs/{id}/status` | POST | Update job application status |
| `/api/dashboard/jobs/{id}/notes` | POST | Add notes to job |
| `/api/dashboard/import` | POST | Import jobs from Google Sheets |
| `/api/dashboard/jobs/export` | GET | Export dashboard jobs to CSV |
| `/api/dashboard/detect_duplicates` | POST | Run duplicate detection |
| `/api/dashboard/jobs/relevant` | GET | Get fresher-friendly jobs |
| `/api/dashboard/jobs/irrelevant` | GET | Get experienced-level jobs |
| `/api/jobs/stats` | GET | Get job statistics breakdown |

### Example API Usage

```bash
# Get system status
curl http://localhost:9501/api/status

# Get dashboard jobs
curl http://localhost:9501/api/dashboard/jobs

# Update job status
curl -X POST http://localhost:9501/api/dashboard/jobs/123/status \
  -H "Content-Type: application/json" \
  -d '{"status": "applied"}'

# Import from Google Sheets
curl -X POST http://localhost:9501/api/dashboard/import

# Run duplicate detection
curl -X POST http://localhost:9501/api/dashboard/detect_duplicates
```

## 🌐 Web Dashboard

### Dashboard Tabs

#### **1. Dashboard Tab**
- System controls (Start/Stop/Process)
- Real-time status monitoring
- Quick action buttons
- System statistics

#### **2. Jobs Tab (NEW)**
- Complete job management interface
- Application status tracking
- Job relevance filtering
- Bulk operations
- Duplicate detection
- CSV export functionality

#### **3. Queue Tab**
- Unprocessed Telegram messages
- Message processing queue
- Batch operations

#### **4. Pending Tab**
- Command queue management
- Group configuration
- Bot command status

#### **5. Logs Tab**
- Real-time bot logs
- Monitor logs
- Webhook logs
- Error tracking

#### **6. Setup Tab**
- Telegram authentication
- Webhook configuration
- System setup tools

### Job Management Features

#### **Application Status Workflow**
- **Not Applied**: New jobs ready for application
- **Applied**: Applications sent
- **Interview**: Interview scheduled
- **Rejected**: Application rejected
- **Offer**: Job offer received
- **Archived**: Old or irrelevant jobs

#### **Relevance Classification**
- **Relevant**: Fresher-friendly (0-2 years experience)
- **Irrelevant**: Experienced positions (3+ years)

#### **Bulk Operations**
- Mark multiple jobs as applied/rejected
- Add notes to multiple jobs
- Bulk duplicate marking
- Mass status updates

## 🐳 Deployment

### Docker Compose (Recommended)

```yaml
# docker-compose.yaml
version: '3.8'

services:
  telegram-job-scraper:
    build: .
    container_name: telegram-job-scraper
    restart: unless-stopped
    ports:
      - "9501:9501"
    environment:
      - DATABASE_URL=${DATABASE_URL}
      - TELEGRAM_API_ID=${TELEGRAM_API_ID}
      - TELEGRAM_API_HASH=${TELEGRAM_API_HASH}
      - OPENROUTER_API_KEY=${OPENROUTER_API_KEY}
      # ... other environment variables
```

### Render.com Deployment

1. **Web Service**: Main dashboard and API
2. **Worker Service**: Telegram bot processing

### Coolify Self-Hosted

1. Import `docker-compose.yaml`
2. Configure environment variables
3. Deploy with auto-scaling

### Manual Deployment

```bash
# Install dependencies
pip install -r requirements.txt

# Set environment variables
export DATABASE_URL="postgresql://..."

# Run migrations
python -c "from database import Database; db = Database('$DATABASE_URL'); db.init_database()"

# Start web server
python web_server.py

# Start bot (separate process)
python main.py
```

## 🛠️ Troubleshooting

### Common Issues and Solutions

#### 1. Database Connection Issues

**Problem**: `psycopg2.OperationalError: connection refused`

**Solution**:
- Verify DATABASE_URL format: `postgresql://postgres:password@db.project.supabase.co:5432/postgres`
- Check Supabase project is active
- Verify network connectivity
- Test connection: `python -c "from database import Database; db = Database('$DATABASE_URL'); print('OK')"`

#### 2. Port Conflicts

**Problem**: `Address already in use` on port 9501

**Solution**:
```bash
# Find process using port 9501
netstat -tulpn | grep :9501
# Change PORT in .env file to use different port
```

#### 3. Telegram API Issues

**Problem**: `Telegram API returned error`

**Solutions**:
- Check TELEGRAM_API_ID and TELEGRAM_API_HASH
- Use web dashboard to set up Telegram session
- Verify authorized users are configured

#### 4. Job Management Issues

**Problem**: Dashboard jobs not displaying

**Solution**:
- Check database connection
- Run import from processed_jobs: `/api/dashboard/import`
- Verify user has proper permissions

### Debug Commands

```bash
# Test database connection
python -c "from database import Database; db = Database('$DATABASE_URL'); print('DB OK')"

# Check web server health
curl http://localhost:9501/health

# Test API endpoints
curl http://localhost:9501/api/status

# Check logs
tail -f logs/bot.log
tail -f logs/web.log
```

## 📈 Monitoring & Maintenance

### Health Monitoring
- **Web Dashboard**: http://localhost:9501/health
- **API Status**: http://localhost:9501/api/status
- **Database**: Connection and table health

### Performance Optimization
- **Batch Size**: Adjust `BATCH_SIZE` for processing speed
- **Database**: Monitor Supabase usage and optimize queries
- **API Calls**: Monitor OpenRouter usage and costs

### Backup Strategy
- **Database**: Supabase provides automatic backups
- **Configuration**: Export environment variables
- **Logs**: Implement log rotation for large deployments

## 🔒 Security

### Environment Variables
- Store sensitive data in environment variables
- Use Supabase secrets management
- Rotate API keys regularly

### Access Control
- Configure authorized user IDs
- Use secure Telegram bot tokens
- Implement proper authentication for web dashboard

### Database Security
- Supabase provides built-in security
- Use connection pooling
- Implement proper query validation

## 📄 File Structure

```
telegram-automate/
├── README.md                 # Main documentation
├── requirements.txt          # Python dependencies
├── .env.example             # Environment template
├── .gitignore              # Git ignore rules
├── LICENSE                 # License
├── config.py               # Configuration
├── database.py             # Database operations
├── main.py                 # Telegram bot
├── web_server.py           # Web dashboard
├── monitor.py              # Message monitor
├── llm_processor.py        # LLM processing
├── sheets_sync.py          # Google Sheets sync
├── supabase_init.sql       # Database schema
├── gunicorn_config.py      # Gunicorn config
├── wsgi.py                 # WSGI entry point
├── Procfile                # Heroku/Render deployment
├── render.yaml             # Render.com config
├── docker-compose.yaml     # Docker deployment
├── Dockerfile              # Docker image
├── templates/                # HTML templates
│   ├── index.html            # Main Dashboard (Modern UI)
│   ├── old.html              # Legacy Dashboard (Backup)
│   └── logs.html             # System Logs View
├── deployment/             # Deployment guides
├── docker/                 # Docker configurations
├── scripts/                # Deployment scripts
└── logs/                   # Log files directory
```

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch
3. Make changes with proper testing
4. Submit a pull request
5. Ensure all tests pass

## 📄 License

This project is licensed under the MIT License.

## 🆘 Support

- **Documentation**: Check this README and deployment guides
- **Troubleshooting**: See `deployment/TROUBLESHOOTING.md`
- **Logs**: Check application logs for detailed error information
- **Issues**: Report bugs with full logs and configuration

---

**Happy job hunting! 🎯**

This enhanced Telegram Job Scraper Bot with integrated job management dashboard streamlines your job application process from discovery to submission.
