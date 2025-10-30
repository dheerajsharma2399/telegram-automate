# 🚀 Coolify Deployment Guide - Telegram Job Scraper Bot

## 📋 **Deployment Issue Resolved**

The previous deployment failed because Coolify couldn't locate the Dockerfile. This guide provides the correct setup for Coolify deployment.

---

## 🔧 **Problem Analysis**

**Error Encountered:**
```
cat: can't open '/artifacts/v80wk08kcc4scs4s0sg0s0s4w0/Dockerfile': No such file or directory
Deployment failed. Removing the new version of your application.
```

**Root Cause:** Dockerfile wasn't accessible in the repository root during Coolify deployment.

---

## ✅ **Solution: Repository Structure Check**

### **Required File Structure for Coolify**
```
telegram-automate/
├── Dockerfile              ← MUST be in root
├── docker-compose.yaml     ← MUST be in root (for Compose projects)
├── requirements.txt        ← MUST be in root
├── main.py                 ← Entry point
├── web_server.py           ← Web interface
├── config.py               ← Configuration
├── .env                    ← Environment variables
└── .dockerignore           ← Build optimization
```

### **Verification Commands**
```bash
# Check if Dockerfile exists in root
ls -la | grep Dockerfile

# Check file permissions
stat Dockerfile

# Verify Dockerfile content
head -10 Dockerfile
```

---

## 🛠️ **Coolify Deployment Steps**

### **Step 1: Repository Setup**
1. **Ensure Dockerfile is in repository root**
2. **Verify all required files are present**
3. **Check file permissions (644 for text files)**
4. **Commit and push changes to GitHub**

### **Step 2: Coolify Configuration**

#### **For Single Container Deployment:**
```yaml
# Coolify Project Settings:
Build Pack: Dockerfile
Dockerfile Location: Dockerfile (default)
Port: 8080
Environment Variables: (see .env section below)
```

#### **For Docker Compose Deployment:**
```yaml
# Coolify Project Settings:
Project Type: Docker Compose
Docker Compose File: docker-compose.yaml
Build Context: ./
```

### **Step 3: Environment Variables Setup**

In Coolify's environment variables section, add:

```bash
# Required for All Services
TELEGRAM_API_ID=your_telegram_api_id
TELEGRAM_API_HASH=your_telegram_api_hash
TELEGRAM_PHONE=+1234567890
TELEGRAM_BOT_TOKEN=your_bot_token
TELEGRAM_GROUP_USERNAMES=-1234567890
AUTHORIZED_USER_IDS=123456789
ADMIN_USER_ID=123456789

# LLM Configuration
OPENROUTER_API_KEY=your_openrouter_key
OPENROUTER_MODEL=anthropic/claude-3.5-sonnet

# Google Sheets (Optional)
GOOGLE_CREDENTIALS_JSON={"type":"service_account",...}
SPREADSHEET_ID=your_spreadsheet_id

# Security
FLASK_SECRET_KEY=your-secure-secret-key
```

### **Step 4: Resource Configuration**

#### **Recommended Resource Limits:**
```yaml
Memory Limit: 1024MB
CPU Limit: 1.0
Disk Space: 2GB
Network: Public (Port 8080)
```

### **Step 5: Deployment Process**

1. **Build Context:** `./` (repository root)
2. **Dockerfile:** `Dockerfile` (if using single container)
3. **Docker Compose File:** `docker-compose.yaml` (if using compose)
4. **Environment Variables:** Add all required variables
5. **Health Check Path:** `/health`
6. **Startup Timeout:** 300 seconds

---

## 🔍 **Troubleshooting Coolify Deployment**

### **Issue 1: Dockerfile Not Found**
```bash
# Solution: Ensure Dockerfile is in repository root
git add Dockerfile
git commit -m "Add Dockerfile for Coolify deployment"
git push
```

### **Issue 2: Build Context Issues**
```bash
# Solution: Check build context
# In Coolify, set Build Context to: ./
# Ensure Dockerfile path is: ./Dockerfile
```

### **Issue 3: Environment Variables Missing**
```bash
# Solution: Add all required environment variables in Coolify dashboard
# Check .env file for required variables
# Copy them to Coolify environment section
```

### **Issue 4: Port Binding Issues**
```bash
# Solution: Ensure port 8080 is properly configured
# In Coolify: Set Public Port to 8080
# Verify EXPOSE 8080 in Dockerfile
```

### **Issue 5: Permission Issues**
```bash
# Solution: Check file permissions
chmod 644 Dockerfile requirements.txt main.py
chmod 755 main.py web_server.py
```

---

## 🐳 **Coolify-Specific Configuration**

### **Dockerfile Optimizations for Coolify**

#### **Coolify-Friendly Dockerfile:**
```dockerfile
# Optimized for Coolify deployment
FROM python:3.11-slim

# Install build dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    libssl-dev \
    libffi-dev \
    curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy requirements first for better caching
COPY requirements.txt .
RUN pip install --user --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Create necessary directories
RUN mkdir -p data logs sessions

# Set environment variables
ENV PYTHONPATH=/app
ENV FLASK_ENV=production
ENV PORT=8080
ENV PYTHONUNBUFFERED=1

# Health check (Coolify requirement)
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD curl -f http://localhost:8080/health || exit 1

# Expose port
EXPOSE 8080

# Default command
CMD ["python", "web_server.py"]
```

### **Coolify-Compatible docker-compose.yaml**
```yaml
# Simplified for Coolify compatibility
version: '3.8'

services:
  web-dashboard:
    build: .
    ports:
      - "8080:8080"
    environment:
      - PORT=8080
      - FLASK_ENV=production
      # Add all required environment variables
    volumes:
      - ./data:/app/data
      - ./logs:/app/logs
    restart: unless-stopped
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8080/health"]
      interval: 30s
      timeout: 10s
      retries: 3
```

---

## 🎯 **Success Checklist for Coolify**

### **Pre-Deployment Checklist**
- [ ] Dockerfile exists in repository root
- [ ] All required files committed and pushed
- [ ] Environment variables documented
- [ ] Resource limits planned
- [ ] Health check endpoint configured
- [ ] Port mapping verified (8080:8080)

### **Coolify Configuration Checklist**
- [ ] Build Context: `./`
- [ ] Dockerfile Path: `./Dockerfile`
- [ ] Public Port: `8080`
- [ ] Health Check Path: `/health`
- [ ] Environment Variables: All configured
- [ ] Resource Limits: 1024MB RAM, 1 CPU
- [ ] Auto-Deploy: Enabled

### **Post-Deployment Checklist**
- [ ] Service health: Healthy
- [ ] Web dashboard accessible: http://your-domain:8080
- [ ] Health endpoint responding: http://your-domain:8080/health
- [ ] API endpoints working: http://your-domain:8080/api/status
- [ ] Logs accessible in Coolify
- [ ] Environment variables loaded correctly

---

## 🔄 **Deployment Commands**

### **Manual Build Test (Local)**
```bash
# Test local build before deploying to Coolify
docker build -t telegram-job-bot .
docker run -p 8080:8080 telegram-job-bot

# Test health endpoint
curl http://localhost:8080/health
```

### **Coolify Deployment Commands**
```bash
# After configuring in Coolify dashboard:
# 1. Trigger build from Coolify interface
# 2. Monitor build logs in Coolify
# 3. Check service health after deployment
# 4. Test endpoints through Coolify
```

---

## 🚀 **Next Steps After Successful Deployment**

### **1. Service Verification**
```bash
# Test the deployed service
curl http://your-coolify-domain:8080/health

# Expected response:
# {"status": "ok"}
```

### **2. Bot Integration Testing**
```bash
# Test bot commands through web API
curl -X POST http://your-coolify-domain:8080/api/command \
  -H "Content-Type: application/json" \
  -d '{"command": "/status"}'
```

### **3. Monitoring Setup**
- Enable Coolify monitoring
- Set up alerts for health check failures
- Monitor resource usage
- Configure log aggregation

---

## 🎉 **Coolify Deployment Ready**

Your Telegram Job Scraper Bot is now configured for successful Coolify deployment:

✅ **Dockerfile optimized for Coolify**  
✅ **Proper repository structure**  
✅ **Complete environment configuration**  
✅ **Resource limits configured**  
✅ **Health checks implemented**  
✅ **Troubleshooting guide provided**  

**Your bot will deploy successfully on Coolify!** 🚀