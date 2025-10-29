# Troubleshooting Guide

## 🛠️ Comprehensive Error Documentation and Solutions

This guide covers common issues, error messages, and their solutions for the Telegram Job Scraper Bot across all deployment platforms.

## 🚨 Critical Errors and Solutions

### Database Errors

#### **Error: "table processed_jobs has no column named email_body"**

**Symptoms:**
- Database migration fails
- Missing columns in processed_jobs table
- Application crashes on startup

**Solution:**
```sql
-- Manual migration (if automatic fails)
ALTER TABLE processed_jobs ADD COLUMN email_body TEXT;
ALTER TABLE processed_jobs ADD COLUMN synced_to_sheets BOOLEAN DEFAULT 0;

-- Check column existence
.schema processed_jobs
```

**Prevention:**
- Database auto-initialization includes column checks
- Safe ALTER TABLE with try-catch blocks
- Restart application after schema updates

#### **Error: "database is locked"**

**Symptoms:**
- SQLite database locked errors
- Write operations fail
- Bot stops processing

**Solution:**
```bash
# Check for multiple instances
ps aux | grep python

# Remove stale lock files
rm -f jobs.db-journal
rm -f jobs.db-wal

# Restart services
docker-compose restart

# Check permissions
chmod 664 jobs.db
chown telegram:telegram jobs.db
```

**Prevention:**
- Single instance deployment
- Proper connection timeouts
- Connection pooling management

### Telegram API Errors

#### **Error: "Session file not found"**

**Symptoms:**
- Telethon authentication fails
- Monitor cannot connect to Telegram
- Bot shows "telegram session missing" errors

**Solution:**
1. **Web Dashboard Setup:**
   - Access http://your-server:8080
   - Go to "Telegram Setup" tab
   - Click "Send Code"
   - Enter verification code
   - Session auto-saves

2. **Manual Session Creation:**
```python
from telethon import TelegramClient
from telethon.sessions import StringSession

client = TelegramClient(StringSession(), api_id, api_hash)
await client.start(phone_number)
string_session = client.session.save()
print(string_session)  # Save this string
```

**Prevention:**
- Use web dashboard for session setup
- Backup session strings
- Monitor session validity

#### **Error: "Auth key not found"**

**Symptoms:**
- Telegram API authentication failures
- "Auth key invalid" errors
- Cannot send/receive messages

**Solution:**
```bash
# Check API credentials
echo $TELEGRAM_API_ID
echo $TELEGRAM_API_HASH

# Verify bot token
curl -X GET "https://api.telegram.org/bot$TELEGRAM_BOT_TOKEN/getMe"

# Restart monitor service
docker-compose restart telegram-bot
```

**Prevention:**
- Verify API credentials from my.telegram.org
- Check bot token validity
- Monitor API rate limits

#### **Error: "Flood control exceeded"**

**Symptoms:**
- Rate limiting errors
- Messages not sent
- API calls rejected

**Solution:**
```python
# Add delays between API calls
import asyncio
await asyncio.sleep(2)  # 2 second delay

# Use exponential backoff
import time
time.sleep(min(60, 2 ** attempt))
```

**Prevention:**
- Implement rate limiting
- Use batch processing
- Monitor API usage

### LLM Processing Errors

#### **Error: "OpenRouter API key invalid"**

**Symptoms:**
- LLM parsing fails
- Jobs not extracted
- "API key authentication failed" errors

**Solution:**
```bash
# Verify API key
curl -H "Authorization: Bearer $OPENROUTER_API_KEY" \
     https://openrouter.ai/api/v1/models

# Check billing and quotas
# Ensure sufficient credits
```

**Prevention:**
- Monitor OpenRouter billing
- Set up usage alerts
- Use fallback models

#### **Error: "JSON parsing failed"**

**Symptoms:**
- LLM returns invalid JSON
- Job parsing errors
- "Could not extract JSON" messages

**Solution:**
The system automatically attempts multiple JSON extraction strategies:
1. Direct JSON parsing
2. Markdown code block extraction
3. Regex-based JSON array detection
4. Fallback to regex parsing

**Manual Fix:**
```python
# Check LLM response format
response = await llm_call()
print("Response:", response)

# Verify JSON structure
import json
try:
    data = json.loads(response)
    print("Valid JSON:", data)
except json.JSONDecodeError as e:
    print("JSON Error:", e)
```

### Web Dashboard Errors

#### **Error: "Port 8080 already in use"**

**Symptoms:**
- Web dashboard won't start
- "Address already in use" errors
- Cannot access web interface

**Solution:**
```bash
# Find process using port
sudo netstat -tulpn | grep :8080
sudo lsof -i :8080

# Kill conflicting process
sudo kill -9 <PID>

# Use different port
# Edit docker-compose.yml: "8081:8080"
```

**Prevention:**
- Avoid port conflicts
- Use environment-specific port mapping
- Check running services

#### **Error: "Health check failed"**

**Symptoms:**
- Container health checks failing
- Service restarts continuously
- Monitoring alerts triggered

**Solution:**
```bash
# Test health endpoint manually
curl http://localhost:8080/health

# Check service logs
docker-compose logs web-dashboard

# Verify dependencies
docker-compose exec web-dashboard python -c "
from database import Database
from config import *
db = Database(DATABASE_PATH)
print('DB OK')
"
```

### Google Sheets Integration Errors

#### **Error: "Spreadsheet not found"**

**Symptoms:**
- Google Sheets sync fails
- "SpreadsheetNotFound" errors
- Permission errors

**Solution:**
1. **Verify Spreadsheet ID:**
```python
# Check in Google Sheets URL
# https://docs.google.com/spreadsheets/d/SPREADSHEET_ID/edit

# Verify in code
print(f"Spreadsheet ID: {SPREADSHEET_ID}")
```

2. **Service Account Permissions:**
   - Add service account email to spreadsheet
   - Grant "Editor" permissions
   - Verify sharing settings

**Prevention:**
- Double-check spreadsheet ID format
- Monitor service account permissions
- Test API connectivity

#### **Error: "Insufficient permissions"**

**Symptoms:**
- Cannot write to Sheets
- Permission denied errors
- Read-only access

**Solution:**
```python
# Verify service account access
from google.oauth2.service_account import Credentials
from gspread import authorize

# Check credentials
creds = Credentials.from_service_account_info(
    json.loads(GOOGLE_CREDENTIALS_JSON),
    scopes=['https://www.googleapis.com/auth/spreadsheets']
)
client = authorize(creds)
print("Auth successful")
```

## 🔧 Configuration Issues

### Environment Variables

#### **Error: "TELEGRAM_API_ID not set"**

**Solution:**
```bash
# Check environment
printenv | grep TELEGRAM

# Set in .env file
echo "TELEGRAM_API_ID=123456" >> .env

# Set in Docker
docker-compose exec web-dashboard env | grep TELEGRAM
```

### File Permissions

#### **Error: "Permission denied: /app/data/jobs.db"**

**Solution:**
```bash
# Fix permissions
sudo chown -R 1000:1000 data/
chmod 664 data/jobs.db

# Check container user
docker-compose exec web-dashboard id

# Use volume mount correctly
# In docker-compose.yml:
volumes:
  - ./data:/app/data
```

## 🐳 Docker-Specific Issues

### Container Issues

#### **Error: "Container exited with code 1"**

**Solution:**
```bash
# Check container logs
docker-compose logs [service_name]

# Debug inside container
docker-compose exec [service_name] bash

# Check file system
docker-compose exec [service_name] ls -la /app

# Verify dependencies
docker-compose exec [service_name] python -c "import flask; print('OK')"
```

#### **Error: "Image build failed"**

**Solution:**
```bash
# Build with verbose output
docker-compose build --no-cache --progress=plain

# Check Dockerfile syntax
dockerfile-runner Dockerfile

# Test base image
docker run python:3.11-slim python --version
```

### Network Issues

#### **Error: "Network driver not found"**

**Solution:**
```bash
# Check Docker networks
docker network ls

# Recreate network
docker-compose down
docker network prune
docker-compose up -d

# Check network configuration
docker network inspect telegram-job-bot_telegram-network
```

## 🌐 Deployment Platform Issues

### Render.com Issues

#### **Error: "Build failed"**

**Solution:**
1. **Check build logs** in Render dashboard
2. **Verify requirements.txt** syntax
3. **Check environment variables**
4. **Ensure repository accessibility**

```bash
# Test locally
pip install -r requirements.txt
python main.py --version
```

#### **Error: "Service not responding"**

**Solution:**
1. **Check health endpoint** in logs
2. **Verify environment variables**
3. **Check resource limits**
4. **Review deployment logs**

### Coolify Issues

#### **Error: "Project deployment failed"**

**Solution:**
```bash
# Check Coolify logs
# Review environment variables
# Verify Docker Compose syntax
# Check server resources

# Manual deployment test
cd /opt/coolify/projects/telegram-job-bot
docker-compose up -d
```

## 📊 Performance Issues

### High Memory Usage

**Symptoms:**
- Container memory alerts
- OOM (Out of Memory) errors
- Slow processing

**Solution:**
```yaml
# Add memory limits
services:
  web-dashboard:
    deploy:
      resources:
        limits:
          memory: 1G
```

### Slow Processing

**Symptoms:**
- Queue buildup
- Long processing times
- API rate limiting

**Solution:**
```python
# Optimize batch size
BATCH_SIZE = 5  # Reduce from 10

# Add processing delays
await asyncio.sleep(1)  # 1 second between batches

# Monitor queue length
queue_length = db.get_unprocessed_count()
if queue_length > 100:
    print("High queue length, consider scaling")
```

## 🔍 Debug Commands

### Database Debugging

```bash
# Check database content
sqlite3 data/jobs.db ".tables"
sqlite3 data/jobs.db "SELECT COUNT(*) FROM raw_messages;"
sqlite3 data/jobs.db "SELECT status, COUNT(*) FROM raw_messages GROUP BY status;"

# Verify schema
sqlite3 data/jobs.db ".schema processed_jobs"
```

### API Debugging

```bash
# Test Telegram API
curl -X GET "https://api.telegram.org/bot$TELEGRAM_BOT_TOKEN/getMe"

# Test OpenRouter API
curl -H "Authorization: Bearer $OPENROUTER_API_KEY" \
     -H "Content-Type: application/json" \
     -d '{"model": "anthropic/claude-3.5-sonnet", "messages": [{"role": "user", "content": "test"}]}' \
     https://openrouter.ai/api/v1/chat/completions

# Test Google Sheets API
gcloud auth activate-service-account --key-file=key.json
gsutil ls gs://[bucket-name]
```

### Log Analysis

```bash
# Real-time logs
tail -f logs/bot.log
tail -f logs/monitor.log
tail -f logs/web.log

# Search errors
grep -i error logs/*.log
grep -i exception logs/*.log

# Count occurrences
grep -c "ERROR" logs/bot.log
```

## 🚨 Emergency Procedures

### Complete System Reset

```bash
# Stop all services
docker-compose down

# Clear data
rm -rf data/*
rm -rf logs/*

# Fresh start
docker-compose up -d

# Wait for initialization
sleep 30
curl http://localhost:8080/health
```

### Database Recovery

```bash
# Backup current database
cp data/jobs.db data/jobs.db.backup

# Check database integrity
sqlite3 data/jobs.db "PRAGMA integrity_check;"

# Repair if needed
sqlite3 data/jobs.db "REINDEX;"
```

### Quick Diagnostics

```bash
# Full system check
#!/bin/bash
echo "=== SYSTEM DIAGNOSIS ==="
echo "Date: $(date)"
echo "Uptime: $(uptime)"
echo "Disk: $(df -h)"
echo "Memory: $(free -h)"
echo "Docker: $(docker --version)"
echo "Services: $(docker-compose ps)"

echo "=== DATABASE CHECK ==="
sqlite3 data/jobs.db "SELECT COUNT(*) as messages FROM raw_messages;"
sqlite3 data/jobs.db "SELECT COUNT(*) as jobs FROM processed_jobs;"

echo "=== API CHECK ==="
curl -s "http://localhost:8080/health" | jq .

echo "=== LOG ERRORS ==="
tail -20 logs/*.log | grep -i error
```

## 📞 Getting Help

### Self-Diagnosis Checklist

Before seeking help, verify:

- [ ] All environment variables set correctly
- [ ] Dependencies installed successfully
- [ ] Services running without errors
- [ ] Database accessible and initialized
- [ ] API credentials valid and working
- [ ] Network connectivity confirmed
- [ ] Resources sufficient (CPU, RAM, disk)
- [ ] Logs reviewed for specific errors

### Information to Provide

When reporting issues:

1. **System Information:**
   - Operating system
   - Python version
   - Docker version
   - Deployment platform

2. **Error Details:**
   - Complete error message
   - Relevant log excerpts
   - Steps to reproduce
   - Expected vs actual behavior

3. **Configuration:**
   - Environment variables (without secrets)
   - docker-compose.yml content
   - Database status
   - API connectivity test results

### Common Log Patterns

**Healthy Operation:**
```
Database initialization complete
Bot started successfully
Monitor connected to Telegram
Health check: OK
```

**Warning Signs:**
```
High memory usage detected
Queue length: 150 messages
API rate limit approaching
Database connection timeout
```

**Critical Errors:**
```
Authentication failed
Database locked
Port 8080 already in use
Service not responding
```

## 🛠️ Enhanced Email Generation Issues

### **Error: "Enhanced email generator not found"**

**Symptoms:**
- Email generation falls back to basic templates
- IoT projects not prioritized
- GitHub links missing

**Solution:**
1. **Verify File Exists:**
```bash
ls -la enhanced_email_generator.py
```

2. **Check Import in Main Code:**
```python
# In main.py or llm_processor.py
try:
    from enhanced_email_generator import EnhancedEmailGenerator
    print("Enhanced email generator loaded successfully")
except ImportError as e:
    print(f"Enhanced email generator not found: {e}")
```

3. **Regenerate if Missing:**
   - Copy enhanced_email_generator.py from deployment backup
   - Or recreate from source

### **Error: "User profile not found"**

**Symptoms:**
- Default profile used for emails
- Personalized information missing

**Solution:**
1. **Check Profile File:**
```bash
ls -la user_profile.json
cat user_profile.json
```

2. **Update Profile:**
```json
{
  "full_name": "Your Name",
  "email": "your.email@example.com",
  "current_title": "Your Position",
  "current_company": "Your Company",
  "linkedin": "https://linkedin.com/in/your-profile",
  "github": "https://github.com/yourusername",
  "phone": "+1234567890",
  "top_projects": [
    {
      "name": "Your IoT Project",
      "description": "Project description",
      "github": "https://github.com/yourusername/project"
    }
  ]
}
```

### **Error: "Email generation timeout"**

**Symptoms:**
- Long email generation times
- Processing timeouts

**Solution:**
1. **Optimize Email Length:**
   - Check job data size
   - Limit project descriptions
   - Reduce email complexity

2. **Add Timeout Handling:**
```python
import signal

def timeout_handler(signum, frame):
    raise TimeoutError("Email generation timeout")

signal.signal(signal.SIGALRM, timeout_handler)
signal.alarm(30)  # 30 second timeout

try:
    email_body = generator.generate_enhanced_email(job_data)
finally:
    signal.alarm(0)
```

---

**This troubleshooting guide covers most common issues. For additional support, check deployment-specific guides and system logs.** 🛠️

Remember to always check logs first and use the systematic debugging approach outlined above.