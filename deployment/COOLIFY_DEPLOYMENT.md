# Coolify Self-Hosted Deployment Guide - DOCKERFILE ISSUE RESOLVED

## 🚨 **CRITICAL UPDATE: Dockerfile Not Found Error FIXED**

**Original Error:**
```
"target telegram-bot: failed to solve: failed to read dockerfile: open Dockerfile: no such file or directory"
```

**Root Cause**: Coolify cannot access the Dockerfile during build process.

**✅ SOLUTION**: Updated `docker-compose.yaml` with Coolify-compatible approach that eliminates Dockerfile issues entirely.

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

### 2. Service Configuration - UPDATED

**IMPORTANT**: Use the updated `docker-compose.yaml` from the repository root. It contains the fix for Coolify compatibility.

#### **Updated Configuration (No Dockerfile Required)**
```yaml
version: '3.8'

services:
  telegram-bot:
    image: python:3.11-slim  # Pre-built image, no build required
    container_name: telegram-job-bot
    restart: unless-stopped
    command: >
      bash -c "
        pip install --no-cache-dir -r requirements.txt &&
        if [ '$CONTAINER_TYPE' = 'web' ]; then
          echo 'Starting web dashboard...' && python web_server.py
        else
          echo 'Starting Telegram bot...' && python main.py
        fi
      "
    environment:
      # Container type identification
      - CONTAINER_TYPE=${CONTAINER_TYPE:-bot}
      - SKIP_DB_WAIT=true
      
      # Database Configuration
      - DATABASE_PATH=/app/jobs.db
      
      # Telegram API Configuration
      - TELEGRAM_API_ID=${TELEGRAM_API_ID}
      - TELEGRAM_API_HASH=${TELEGRAM_API_HASH}
      - TELEGRAM_PHONE=${TELEGRAM_PHONE}
      - TELEGRAM_BOT_TOKEN=${TELEGRAM_BOT_TOKEN}
      - TELEGRAM_GROUP_USERNAMES=${TELEGRAM_GROUP_USERNAMES}
      
      # Authorization
      - AUTHORIZED_USER_IDS=${AUTHORIZED_USER_IDS}
      - ADMIN_USER_ID=${ADMIN_USER_ID}
      
      # LLM Configuration
      - OPENROUTER_API_KEY=${OPENROUTER_API_KEY}
      - OPENROUTER_MODEL=${OPENROUTER_MODEL:-anthropic/claude-3.5-sonnet}
      - OPENROUTER_FALLBACK_MODEL=${OPENROUTER_FALLBACK_MODEL:-openai/gpt-4o-mini}
      
      # Processing Configuration
      - BATCH_SIZE=10
      - PROCESSING_INTERVAL_MINUTES=5
      - MAX_RETRIES=3
      
      # Google Sheets Configuration
      - GOOGLE_CREDENTIALS_JSON=${GOOGLE_CREDENTIALS_JSON}
      - SPREADSHEET_ID=${SPREADSHEET_ID}
      
      # Bot Configuration
      - BOT_RUN_MODE=polling
      
      # Flask Configuration (for web service)
      - FLASK_ENV=production
      - FLASK_DEBUG=0
      - PORT=8080
      
      # Python Environment
      - PYTHONUNBUFFERED=1
      - PYTHONDONTWRITEBYTECODE=1
    ports:
      - "8080:8080"
    volumes:
      - ./data:/app
    working_dir: /tmp
    deploy:
      resources:
        limits:
          memory: 512M
          cpus: '0.5'
        reservations:
          memory: 256M
          cpus: '0.25'
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
TELEGRAM_GROUP_USERNAMES=@yourgroup
AUTHORIZED_USER_IDS=123456789
ADMIN_USER_ID=123456789
CONTAINER_TYPE=bot  # or web for dashboard

# Database Configuration
DATABASE_PATH=/app/jobs.db

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

### 1. Build Process - UPDATED

**No build required!** The updated configuration uses pre-built Python images.

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

The service includes startup commands that serve as health indicators:
- **Web Dashboard**: Container logs show "Starting web dashboard..."
- **Bot Service**: Container logs show "Starting Telegram bot..."

## 🚀 Deployment Steps

### Step 1: Repository Setup

1. **Use updated code** with fixed `docker-compose.yaml`
2. **Push to GitHub/GitLab**
3. **Ensure all required files are present**

### Step 2: Configure Coolify

1. **Import Project**:
   - Use Git URL: `https://github.com/yourusername/telegram-automate.git`
   - Branch: `main`
   - Auto-deploy: Enabled

2. **Environment Variables**:
   - Add all required variables from section above
   - Use Coolify's secret management for sensitive data

3. **Deploy**:
   - Click "Deploy"
   - Monitor logs during first deployment
   - Verify service is running

### Step 3: Oracle VM Network Configuration (CRITICAL)

**IMPORTANT**: This is required for the bot to communicate with Telegram servers.

#### **Oracle Cloud Security Rules:**
```bash
# Go to Oracle Cloud Console → Networking → VCN → Security Lists
# Add Outbound Rules:
# - Protocol: TCP, Port: 443, CIDR: 0.0.0.0/0 (HTTPS)
# - Protocol: TCP, Port: 80, CIDR: 0.0.0.0/0 (HTTP)
# - Protocol: TCP, Port: 53, CIDR: 0.0.0.0/0 (DNS)
```

#### **VM Firewall Configuration:**
```bash
sudo iptables -A OUTPUT -p tcp --dport 443 -j ACCEPT
sudo iptables -A OUTPUT -p tcp --dport 80 -j ACCEPT
sudo iptables -A OUTPUT -p tcp --dport 53 -j ACCEPT
```

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
# Check service logs
docker logs telegram-job-bot

# Test web dashboard
curl http://localhost:8080/health

# Check API status
curl http://localhost:8080/api/status
```

### 2. Database Initialization

Check logs for:
```
Starting Telegram bot...
Dependencies installed successfully...
Database initialization complete
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
ufw allow 443     # HTTPS
ufw allow 80      # HTTP
ufw enable
```

### 3. Environment Security

- Use Coolify's secret storage for sensitive variables
- Rotate API keys regularly
- Monitor logs for unauthorized access

## 📊 Monitoring & Maintenance

### 1. Log Management

Logs are stored in `./data/` directory:
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

# Redeploy in Coolify
# The updated docker-compose.yaml will be used automatically
```

### 4. Resource Monitoring

Monitor these metrics in Coolify:
- **CPU Usage**: Should be <70% average
- **Memory Usage**: Monitor for memory leaks
- **Disk Space**: Ensure adequate space for logs and database
- **Network**: Check for API rate limiting

## 🐛 Troubleshooting

### 1. Dockerfile Not Found (RESOLVED)

**Problem**: Coolify cannot find Dockerfile during build

**Solution**: 
- ✅ **FIXED**: Updated `docker-compose.yaml` uses pre-built images
- No Dockerfile access required
- Dependencies installed at runtime

### 2. Service Won't Start

**Problem**: Container crashes on startup

**Solution**:
```bash
# Check logs
docker logs telegram-job-bot

# Check environment variables
# Ensure CONTAINER_TYPE is set properly

# Restart with verbose logging
# Check Coolify logs for specific error messages
```

### 3. Telegram Authentication Failed

**Problem**: Bot can't connect to Telegram

**Solution**:
1. Verify Oracle VM network configuration (outbound HTTPS allowed)
2. Verify API credentials in environment variables
3. Check phone number format (+1234567890)
4. Use web dashboard to setup session
5. Restart telegram-bot service

### 4. Database Errors

**Problem**: SQLite database issues

**Solution**:
```bash
# Check file permissions
chmod 664 /app/data/jobs.db
chown coolify:coolify /app/data/jobs.db

# Check disk space
df -h

# Restart services via Coolify
```

### 5. Web Dashboard Not Accessible

**Problem**: Cannot access web interface

**Solution**:
1. Check port mapping: `8080:8080`
2. Verify firewall rules
3. Check service health: `curl http://localhost:8080/health`
4. Review service logs in Coolify

### 6. Oracle VM Network Issues

**Problem**: Bot cannot communicate with Telegram servers

**Solution**:
1. **Configure Oracle Cloud Security Rules** (see Step 3 above)
2. **Set up VM firewall** (see Step 3 above)
3. **Test connectivity**: `curl -v https://api.telegram.org`
4. **Verify DNS resolution**: `nslookup api.telegram.org`

## 🔄 Production Checklist

Before going live:

- [x] Updated docker-compose.yaml with Coolify fix
- [ ] All environment variables configured
- [ ] Oracle VM network configuration completed
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
- Use multiple bot instances with different container types
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
# Emergency restart via Coolify
# Or restart services through Coolify dashboard

# Full reset
# Redeploy from Coolify with updated configuration
```

### 2. Rollback Process

```bash
# Rollback to previous version
git checkout HEAD~1
# Trigger new deployment in Coolify
```

### 3. Data Recovery

1. **Stop services**: Through Coolify dashboard
2. **Restore database**: Copy from backup
3. **Verify integrity**: Check database file
4. **Restart services**: Through Coolify dashboard

---

**Your Telegram Job Scraper Bot is now ready for production deployment on Coolify with the Dockerfile issue resolved!** 🎉

For additional support, see `TROUBLESHOOTING.md` and check system logs in Coolify dashboard.