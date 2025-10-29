# Coolify Self-Hosted Deployment Guide

## 🚀 Deploying Telegram Job Scraper Bot on Coolify

This guide covers deploying the Telegram Job Scraper Bot on your self-hosted Coolify instance running on Oracle Server.

## 📋 Prerequisites

### System Requirements
- **Coolify Instance**: Self-hosted Coolify installation
- **Server Resources**: 2+ CPU cores, 4GB+ RAM, 20GB+ storage
- **Domain**: Optional subdomain for web access
- **SSL Certificate**: Recommended for production

### Required Accounts/Services
- **Telegram**: Bot token from @BotFather
- **Telegram API**: API ID and Hash from my.telegram.org
- **OpenRouter**: API key for LLM parsing
- **Google**: Service account for Sheets integration (optional)

## 🏗️ Coolify Project Setup

### 1. Create New Project

1. **Login to Coolify Dashboard**
2. **Click "New Project"**
3. **Choose "Docker Compose"**
4. **Import from Git**: Use your repository URL
5. **Project Name**: `telegram-job-bot`

### 2. Service Configuration

#### **Service 1: Web Dashboard**

```yaml
version: '3.8'
services:
  web-dashboard:
    image: python:3.11-slim
    container_name: telegram-job-dashboard
    ports:
      - "8080:8080"
    environment:
      - FLASK_ENV=production
      - PORT=8080
    volumes:
      - ./data:/app/data
      - ./logs:/app/logs
    working_dir: /app
    command: python web_server.py
    restart: unless-stopped
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8080/health"]
      interval: 30s
      timeout: 10s
      retries: 3
```

#### **Service 2: Telegram Bot**

```yaml
  telegram-bot:
    image: python:3.11-slim
    container_name: telegram-job-bot
    environment:
      - FLASK_ENV=production
    volumes:
      - ./data:/app/data
      - ./logs:/app/logs
    working_dir: /app
    command: python main.py
    restart: unless-stopped
    depends_on:
      - web-dashboard
```

### 3. Environment Variables

Add these environment variables in Coolify:

#### **Required Variables**
```bash
# Telegram Configuration
TELEGRAM_API_ID=your_api_id
TELEGRAM_API_HASH=your_api_hash
TELEGRAM_PHONE=+1234567890
TELEGRAM_BOT_TOKEN=your_bot_token
AUTHORIZED_USER_IDS=123456789
ADMIN_USER_ID=123456789

# Database Configuration
DATABASE_PATH=/app/data/jobs.db

# Processing Configuration
PROCESSING_INTERVAL_MINUTES=5
BATCH_SIZE=10
```

#### **Optional Variables**
```bash
# OpenRouter LLM (Recommended)
OPENROUTER_API_KEY=sk-xxxxx
OPENROUTER_MODEL=anthropic/claude-3.5-sonnet
OPENROUTER_FALLBACK_MODEL=openai/gpt-4o-mini

# Google Sheets Integration
GOOGLE_CREDENTIALS_JSON={"type":"service_account",...}
SPREADSHEET_ID=your_spreadsheet_id

# Flask Configuration
FLASK_SECRET_KEY=your_secret_key
FLASK_ENV=production
PORT=8080
```

## 🔧 Coolify-Specific Configuration

### 1. Build Process

```yaml
# Add to your docker-compose.yml
build:
  context: .
  dockerfile: Dockerfile
  args:
    - TELEGRAM_API_ID=${TELEGRAM_API_ID}
    - TELEGRAM_API_HASH=${TELEGRAM_API_HASH}
```

### 2. Volume Management

Create persistent volumes in Coolify:
```
/opt/coolify/projects/telegram-job-bot/data
/opt/coolify/projects/telegram-job-bot/logs
/opt/coolify/projects/telegram-job-bot/config
```

### 3. Network Configuration

```yaml
networks:
  default:
    driver: bridge
    name: telegram-job-network
```

### 4. Health Checks

Both services include health checks. Configure in Coolify:
- **Web Dashboard**: HTTP GET to `/health` (Port 8080)
- **Bot Service**: Custom script check

## 🚀 Deployment Steps

### Step 1: Prepare Repository

1. **Push clean code** to GitHub/GitLab
2. **Include .env.example** for reference
3. **Ensure Dockerfile present** (see below)

### Step 2: Create Dockerfile

```dockerfile
FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Create data directories
RUN mkdir -p /app/data /app/logs

# Set environment variables
ENV PYTHONPATH=/app
ENV FLASK_ENV=production

# Expose port
EXPOSE 8080

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8080/health || exit 1

# Command for web dashboard
CMD ["python", "web_server.py"]
```

### Step 3: Configure Coolify

1. **Import Project**:
   - Use Git URL: `https://github.com/yourusername/telegram-job-bot.git`
   - Branch: `main`
   - Auto-deploy: Enabled

2. **Environment Variables**:
   - Add all required variables from section above
   - Use Coolify's secret management for sensitive data

3. **Deploy**:
   - Click "Deploy"
   - Monitor logs during first deployment
   - Verify both services are running

### Step 4: Setup Telegram Session

1. **Access Dashboard**: `http://your-server-ip:8080`
2. **Go to "Telegram Setup" tab**
3. **Click "Send Code"**
4. **Enter verification code**
5. **Session auto-saves to database**

### Step 5: Configure Groups

1. **Go to "Pending Commands" tab**
2. **Add Telegram group usernames**:
   - Example: `myjobgroup` or `@myjobgroup`
3. **Save configuration**

## 🔍 Verification Steps

### 1. Service Health

```bash
# Check web dashboard
curl http://localhost:8080/health

# Check bot logs
docker logs telegram-job-bot

# Check web dashboard logs
docker logs telegram-job-dashboard
```

### 2. Database Initialization

Check logs for:
```
Database initialization complete
Added missing column: phone
Added missing column: application_link
Added missing column: recruiter_name
```

### 3. Test Bot Commands

Send to your Telegram bot:
- `/status` - Check system status
- `/start` - Start monitoring

### 4. Web Dashboard Access

- **URL**: `http://your-server-ip:8080`
- **Health Check**: `http://your-server-ip:8080/health`
- **API Test**: `http://your-server-ip:8080/api/status`

## 🛡️ Security Configuration

### 1. SSL/TLS Setup

```nginx
# Add to Coolify reverse proxy configuration
location / {
    proxy_pass http://localhost:8080;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
}

# SSL redirect
server {
    listen 80;
    server_name your-domain.com;
    return 301 https://$server_name$request_uri;
}
```

### 2. Firewall Configuration

```bash
# Allow Coolify and bot ports
ufw allow 3000    # Coolify
ufw allow 8080    # Web dashboard
ufw allow 22      # SSH
ufw enable
```

### 3. Environment Security

- Use Coolify's secret storage for sensitive variables
- Rotate API keys regularly
- Monitor logs for unauthorized access

## 📊 Monitoring & Maintenance

### 1. Log Management

Logs are stored in `./logs/` directory:
- `bot.log` - Bot processing logs
- `monitor.log` - Telegram monitor logs
- `web.log` - Web server logs

### 2. Database Backup

```bash
# Backup database
cp /app/data/jobs.db /backups/jobs_$(date +%Y%m%d_%H%M%S).db

# Restore database
cp /backups/jobs_YYYYMMDD_HHMMSS.db /app/data/jobs.db
```

### 3. Update Process

```bash
# Pull latest code
git pull origin main

# Rebuild services
docker-compose down
docker-compose build --no-cache
docker-compose up -d
```

### 4. Resource Monitoring

Monitor these metrics in Coolify:
- **CPU Usage**: Should be <70% average
- **Memory Usage**: Monitor for memory leaks
- **Disk Space**: Ensure adequate space for logs and database
- **Network**: Check for API rate limiting

## 🐛 Troubleshooting

### 1. Service Won't Start

**Problem**: Container crashes on startup

**Solution**:
```bash
# Check logs
docker logs telegram-job-dashboard
docker logs telegram-job-bot

# Check environment variables
docker-compose config

# Restart with verbose logging
docker-compose up --no-cache
```

### 2. Telegram Authentication Failed

**Problem**: Bot can't connect to Telegram

**Solution**:
1. Verify API credentials in environment variables
2. Check phone number format (+1234567890)
3. Use web dashboard to setup session
4. Restart telegram-bot service

### 3. Database Errors

**Problem**: SQLite database issues

**Solution**:
```bash
# Check file permissions
chmod 664 /app/data/jobs.db
chown coolify:coolify /app/data/jobs.db

# Check disk space
df -h

# Restart services
docker-compose restart
```

### 4. Web Dashboard Not Accessible

**Problem**: Cannot access web interface

**Solution**:
1. Check port mapping: `8080:8080`
2. Verify firewall rules
3. Check service health: `curl http://localhost:8080/health`
4. Review web logs

### 5. LLM Parsing Failures

**Problem**: Jobs not being parsed correctly

**Solution**:
1. Verify OpenRouter API key
2. Check API quotas and billing
3. Review bot logs for error messages
4. Consider fallback model configuration

## 🔄 Production Checklist

Before going live:

- [ ] All environment variables configured
- [ ] Telegram session setup completed
- [ ] Monitored groups configured
- [ ] SSL certificate installed
- [ ] Firewall rules configured
- [ ] Backup strategy implemented
- [ ] Monitoring alerts configured
- [ ] Log rotation setup
- [ ] Resource limits set
- [ ] Security scan completed

## 📈 Scaling Considerations

### 1. Horizontal Scaling

For high traffic:
- Use multiple bot instances
- Implement Redis for session storage
- Add load balancer for web dashboard
- Consider PostgreSQL for database

### 2. Resource Optimization

- Set memory limits for containers
- Configure log rotation
- Use external database for persistence
- Implement caching for LLM responses

## 🆘 Emergency Procedures

### 1. Service Recovery

```bash
# Emergency restart
docker-compose restart

# Full reset
docker-compose down -v
docker-compose up -d

# Manual backup restore
cp /backups/latest/jobs.db /app/data/jobs.db
docker-compose restart
```

### 2. Rollback Process

```bash
# Rollback to previous version
git checkout HEAD~1
docker-compose down
docker-compose build --no-cache
docker-compose up -d
```

### 3. Data Recovery

1. **Stop services**: `docker-compose down`
2. **Restore database**: Copy from backup
3. **Verify integrity**: Check database file
4. **Restart services**: `docker-compose up -d`

---

**Your Telegram Job Scraper Bot is now ready for production deployment on Coolify!** 🎉

For additional support, see `TROUBLESHOOTING.md` and check system logs in Coolify dashboard.