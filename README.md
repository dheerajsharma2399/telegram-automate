# Telegram Job Scraper Bot

A production-ready Telegram automation project that monitors job postings in Telegram groups, parses job details using LLMs (OpenRouter), stores structured data in SQLite database, and provides enhanced email generation with IoT project prioritization. Features include web dashboard, Google Sheets integration, and Docker deployment support.

## 🚀 Key Features

### Core Functionality
- **Smart Job Monitoring**: Monitor multiple Telegram groups for job postings using Telethon
- **AI-Powered Parsing**: Extract structured job data using LLMs with regex fallback
- **Enhanced Email Generation**: IoT monitoring projects prioritized, GitHub links included
- **Google Sheets Integration**: Sync jobs to spreadsheets with email generation
- **Web Dashboard**: Real-time monitoring and control interface
- **Command Queue System**: Dashboard-to-bot communication bridge
- **Auto-Processing**: Scheduled and manual job processing

### Enhanced Email Generation
- **IoT Monitoring Priority**: IoT projects featured first in all email generation
- **GitHub Integration**: All 7 projects include GitHub repository links
- **Updated Contact Information**: Professional email, phone, LinkedIn, GitHub
- **Job-Specific Customization**: Personalized emails based on job requirements
- **Backend Developer Focus**: Emphasizes backend and automation expertise

## 📁 Project Structure

```
├── main.py                 # Telegram bot orchestrator with enhanced email generation
├── monitor.py              # Telethon-based group monitoring
├── database.py             # SQLite wrapper with auto-initialization
├── llm_processor.py        # LLM integration with IoT-prioritized email generation
├── sheets_sync.py          # Google Sheets bidirectional sync
├── web_server.py           # Flask dashboard with IoT-enhanced APIs
├── config.py               # Environment configuration
├── enhanced_email_generator.py  # IoT-prioritized email generation
├── user_profile.json       # User profile for personalized emails
├── requirements.txt        # Python dependencies
├── Procfile                # Process configuration
├── render.yaml            # Render deployment config
├── templates/
│   └── index.html         # Web dashboard UI
├── scripts/
│   └── push_email_body_to_sheets.py  # Email body sync script
└── deployment/
    ├── COOLIFY_DEPLOYMENT.md
    ├── DOCKER_DEPLOYMENT.md
    └── TROUBLESHOOTING.md
```

## 🔧 Configuration

### Environment Variables

Required for basic operation:
- `TELEGRAM_API_ID`, `TELEGRAM_API_HASH` - Telegram API credentials
- `TELEGRAM_PHONE` - Phone number for Telethon authentication
- `TELEGRAM_BOT_TOKEN` - Bot token from BotFather
- `AUTHORIZED_USER_IDS` - Comma-separated allowed user IDs
- `ADMIN_USER_ID` - Admin user ID for notifications

Optional for enhanced features:
- `OPENROUTER_API_KEY` - OpenRouter API key for LLM parsing
- `GOOGLE_CREDENTIALS_JSON` - Google service account JSON
- `SPREADSHEET_ID` - Google Sheets ID for sync
- `TELEGRAM_GROUP_USERNAMES` - Groups to monitor

### User Profile Configuration

Edit `user_profile.json` to customize email generation:
```json
{
  "full_name": "Your Name",
  "email": "your.email@example.com",
  "current_title": "Your Current Position",
  "current_company": "Your Company",
  "linkedin": "https://linkedin.com/in/your-profile",
  "top_projects": [
    {
      "name": "IoT Monitoring System",
      "description": "Real-time IoT sensor monitoring with alert system"
    }
  ]
}
```

## 🚀 Quick Start

### Local Development

1. **Clone and setup**:
```bash
git clone <repository>
cd telegram-job-bot
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
pip install -r requirements.txt
```

2. **Configure environment**:
```bash
cp .env.example .env
# Edit .env with your credentials
```

3. **Run components**:
```bash
# Terminal 1: Web dashboard
python web_server.py

# Terminal 2: Telegram bot
python main.py
```

4. **Setup Telegram session**:
- Open http://localhost:5000
- Go to "Telegram Setup" tab
- Complete authentication flow

## 🐳 Docker Deployment

### Using Docker Compose

1. **Create environment file**:
```bash
cp .env.example .env.docker
# Edit .env.docker with your credentials
```

2. **Build and run**:
```bash
docker-compose up --build
```

3. **Access services**:
- Web Dashboard: http://localhost:8080
- API Health: http://localhost:8080/health

## 🌐 Deployment Platforms

### Render.com (Recommended)

Two separate services required:

1. **Job Dashboard (Web Service)**:
   - Build: `pip install -r requirements.txt`
   - Start: `python web_server.py`
   - Health: `/health`

2. **Telegram Job Bot (Worker)**:
   - Build: `pip install -r requirements.txt`
   - Start: `python main.py`

See `render.yaml` for complete configuration.

### Coolify Self-Hosted

See `deployment/COOLIFY_DEPLOYMENT.md` for detailed Coolify deployment instructions.

### Docker Deployment

See `deployment/DOCKER_DEPLOYMENT.md` for comprehensive Docker deployment guide.

## 📱 Telegram Bot Commands

- `/start` - Start job processing and monitoring
- `/stop` - Stop automated processing
- `/status` - View current system status
- `/process` - Manually trigger job processing
- `/generate_emails` - Generate personalized email bodies
- `/sync_sheets` - Sync jobs to Google Sheets
- `/export` - Export jobs as CSV files
- `/stats` - View job statistics

## 🌐 Web Dashboard

Access at `http://your-domain:8080`

### Dashboard Features
- **Status Overview**: Real-time system monitoring
- **Queue Management**: View and manage job processing queue
- **Telegram Setup**: Initialize Telegram authentication
- **Logs Viewer**: Real-time bot and monitor logs
- **Command Queue**: View pending commands
- **Group Management**: Add/remove monitored Telegram groups

## 📊 Database Schema

Automatically initialized on first run:

- **raw_messages**: Telegram message storage
- **processed_jobs**: Structured job data with IoT-enhanced email fields
- **bot_config**: System configuration and state
- **commands_queue**: Dashboard-to-bot communication

## 🔍 API Endpoints

### Status and Monitoring
- `GET /api/status` - System status and statistics
- `GET /api/queue` - Unprocessed messages queue
- `GET /api/logs` - Bot and monitor logs
- `GET /api/pending_commands` - Pending commands queue

### Bot Control
- `POST /api/command` - Enqueue bot commands
- `POST /api/generate_emails` - Trigger email generation
- `POST /api/sheets/generate_email_bodies` - Generate email bodies from sheets

### Configuration
- `GET/POST/DELETE /api/monitored_groups` - Manage monitored groups
- `POST /api/telegram/setup` - Initialize Telegram session

## 🔧 Enhanced Email Generation

The system now includes sophisticated email generation with:

### IoT Project Prioritization
- IoT Monitoring System always featured first
- Backend Developer position emphasis
- Technical expertise showcase

### GitHub Integration
- All 7 projects include GitHub repository links
- Code examples and live demos referenced
- Professional portfolio showcase

### Professional Contact Information
- Email: dheerajsharma2930@gmail.com
- Phone: +91-9829197483
- LinkedIn: linkedin.com/in/dheeraj-sharma-2a8367259
- GitHub: github.com/DheerajSharma2930

## 📈 Google Sheets Integration

- **Email Jobs Sheet**: Jobs with email applications
- **Non-Email Jobs Sheet**: Jobs without email applications
- **Auto-Header Setup**: 17-column headers with relevance fields
- **Email Body Sync**: Automatically generate email bodies
- **Bidirectional Sync**: Update both database and sheets

## 🛡️ Security

- **Environment Variables**: All secrets managed via environment variables
- **User Authorization**: Whitelist-based access control
- **API Rate Limiting**: Built-in rate limiting for API calls
- **Session Management**: Secure Telegram session handling

## 🐛 Troubleshooting

See `deployment/TROUBLESHOOTING.md` for comprehensive troubleshooting guide.

### Common Issues

1. **Database errors**: Check file permissions and disk space
2. **Telegram authentication**: Use web dashboard setup flow
3. **LLM parsing failures**: Verify OpenRouter API key and quotas
4. **Google Sheets sync**: Check service account permissions

## 📋 Development

### Local Testing
```bash
# Run both services
honcho start

# Test individual components
python -m pytest tests/

# Check code quality
flake8 .
```

### Contributing
1. Fork the repository
2. Create feature branch
3. Add tests for new functionality
4. Submit pull request

## 📄 License

This project is licensed under the MIT License - see LICENSE file.

## 🤝 Support

- **Issues**: Create GitHub issues for bugs and feature requests
- **Documentation**: See `deployment/` folder for detailed deployment guides
- **Deployment**: Follow platform-specific deployment guides

---

**Ready for production deployment with Docker, Render, and Coolify support!** 🚀
