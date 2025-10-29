# Docker Deployment Guide

## 🐳 Deploy Telegram Job Scraper Bot with Docker

This comprehensive guide covers deploying the Telegram Job Scraper Bot using Docker and Docker Compose for production environments.

## 📋 Prerequisites

### System Requirements
- **Docker**: Version 20.10+ installed
- **Docker Compose**: Version 2.0+ installed
- **Server**: 2+ CPU cores, 4GB+ RAM, 20GB+ storage
- **Ports**: 8080 (web dashboard)

### Required Files

Ensure these files exist in your project root:
```bash
Dockerfile
docker-compose.yml (or docker-compose.yaml)
.env.example
requirements.txt
```

## 🏗️ Unified Dockerfile Configuration

### Single Production Dockerfile

```dockerfile
# Multi-stage build for production
FROM python:3.11-slim as builder

# Install build dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Copy and install Python dependencies
COPY requirements.txt .
RUN pip install --user --no-cache-dir -r requirements.txt

# Production stage
FROM python:3.11-slim

# Install runtime dependencies
RUN apt-get update && apt-get install -y \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Create non-root user
RUN groupadd -r telegram && useradd -r -g telegram telegram

# Set working directory
WORKDIR /app

# Copy Python packages from builder
COPY --from=builder /root/.local /home/telegram/.local

# Copy application code
COPY . .

# Create data directories
RUN mkdir -p data logs && \
    chown -R telegram:telegram /app

# Switch to non-root user
USER telegram

# Add local bin to PATH
ENV PATH=/home/telegram/.local/bin:$PATH

# Set environment variables
ENV PYTHONPATH=/app
ENV FLASK_ENV=production
ENV PORT=8080

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=3 \
    CMD curl -f http://localhost:8080/health || exit 1

# Expose port
EXPOSE 8080

# Default command starts web dashboard
# Use 'python main.py' for bot service
CMD ["python", "web_server.py"]
```

## 📦 Docker Compose Configuration

### Production docker-compose.yml

```yaml
# Docker Compose configuration for Telegram Job Scraper Bot
# Production-ready deployment with web dashboard and Telegram bot
# Compatible with Coolify, Docker, and other platforms

version: '3.8'

services:
  # Web Dashboard Service
  web-dashboard:
    build:
      context: .
      dockerfile: Dockerfile
    container_name: telegram-job-dashboard
    ports:
      - "8080:8080"
    environment:
      # Database Configuration
      - DATABASE_PATH=/app/data/jobs.db
      
      # Flask Configuration
      - FLASK_ENV=production
      - FLASK_DEBUG=0
      - PORT=8080
      
      # Security Configuration
      - FLASK_SECRET_KEY=${FLASK_SECRET_KEY:-super-secret}
      
      # Telegram Configuration (for API calls)
      - TELEGRAM_BOT_TOKEN=${TELEGRAM_BOT_TOKEN}
      - ADMIN_USER_ID=${ADMIN_USER_ID}
      
      # LLM Configuration
      - OPENROUTER_API_KEY=${OPENROUTER_API_KEY}
      - OPENROUTER_MODEL=${OPENROUTER_MODEL:-anthropic/claude-3.5-sonnet}
      - OPENROUTER_FALLBACK_MODEL=${OPENROUTER_FALLBACK_MODEL:-openai/gpt-4o-mini}
      
      # Google Sheets Configuration
      - GOOGLE_CREDENTIALS_JSON=${GOOGLE_CREDENTIALS_JSON}
      - SPREADSHEET_ID=${SPREADSHEET_ID}
      
      # Telegram API Configuration
      - TELEGRAM_API_ID=${TELEGRAM_API_ID}
      - TELEGRAM_API_HASH=${TELEGRAM_API_HASH}
    volumes:
      # Persistent data storage
      - ./data:/app/data
      - ./logs:/app/logs
      - ./user_profile.json:/app/user_profile.json:ro
    restart: unless-stopped
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8080/health"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 60s
    networks:
      - telegram-network

  # Telegram Bot Service
  telegram-bot:
    build:
      context: .
      dockerfile: Dockerfile
    container_name: telegram-job-bot
    environment:
      # Database Configuration
      - DATABASE_PATH=/app/data/jobs.db
      
      # Telegram API Configuration
      - TELEGRAM_API_ID=${TELEGRAM_API_ID}
      - TELEGRAM_API_HASH=${TELEGRAM_API_HASH}
      - TELEGRAM_PHONE=${TELEGRAM_PHONE}
      - TELEGRAM_BOT_TOKEN=${TELEGRAM_BOT_TOKEN}
      - TELEGRAM_GROUP_USERNAME=${TELEGRAM_GROUP_USERNAME}
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
    volumes:
      # Persistent data storage
      - ./data:/app/data
      - ./logs:/app/logs
      - ./user_profile.json:/app/user_profile.json:ro
    restart: unless-stopped
    networks:
      - telegram-network
    depends_on:
      - web-dashboard

# Network configuration
networks:
  telegram-network:
    driver: bridge
    internal: false
```

### Development docker-compose.dev.yml

```yaml
version: '3.8'

# Development override
# Use: docker-compose -f docker-compose.yml -f docker-compose.dev.yml up

services:
  web-dashboard:
    build:
      context: .
      dockerfile: Dockerfile
    environment:
      - FLASK_ENV=development
      - FLASK_DEBUG=1
    ports:
      - "5000:8080"  # Development port mapping
    volumes:
      - ./:/app  # Mount source code for hot reload
      - ./data:/app/data
      - ./logs:/app/logs

  telegram-bot:
    build:
      context: .
      dockerfile: Dockerfile
    environment:
      - FLASK_ENV=development
    volumes:
      - ./:/app  # Mount source code for hot reload
      - ./data:/app/data
      - ./logs:/app/logs
```

## 🚀 Deployment Steps

### 1. Prepare Environment

```bash
# Clone repository
git clone <repository-url>
cd telegram-job-bot

# Copy environment template
cp .env.example .env

# Edit environment variables
nano .env
```

### 2. Environment Configuration

```bash
# .env file content
TELEGRAM_API_ID=123456
TELEGRAM_API_HASH=your_api_hash
TELEGRAM_PHONE=+1234567890
TELEGRAM_BOT_TOKEN=your_bot_token
AUTHORIZED_USER_IDS=123456789
ADMIN_USER_ID=123456789

# Optional but recommended
OPENROUTER_API_KEY=sk-xxxxx
OPENROUTER_MODEL=anthropic/claude-3.5-sonnet
GOOGLE_CREDENTIALS_JSON={"type":"service_account",...}
SPREADSHEET_ID=your_spreadsheet_id

# Database
DATABASE_PATH=/app/data/jobs.db

# Processing
PROCESSING_INTERVAL_MINUTES=5
BATCH_SIZE=10
```

### 3. Build and Deploy

```bash
# Build images
docker-compose build --no-cache

# Start services
docker-compose up -d

# View logs
docker-compose logs -f

# Check status
docker-compose ps
```

### 4. Verify Deployment

```bash
# Check web dashboard health
curl http://localhost:8080/health

# View service logs
docker-compose logs web-dashboard
docker-compose logs telegram-bot

# Check database initialization
ls -la data/
tail -f logs/web.log
```

## 🔧 Docker Commands Reference

### Basic Operations

```bash
# Start all services
docker-compose up -d

# Stop all services
docker-compose down

# Restart services
docker-compose restart

# View logs
docker-compose logs -f [service_name]

# Check status
docker-compose ps

# Scale services (if needed)
docker-compose up -d --scale telegram-bot=2
```

### Debugging

```bash
# Execute commands in running container
docker-compose exec web-dashboard bash
docker-compose exec telegram-bot python -c "from database import Database; print('DB OK')"

# Check container status
docker-compose ps

# View resource usage
docker stats

# Check networks
docker network ls
docker network inspect telegram-job-bot_telegram-network
```

### Maintenance

```bash
# Update images
docker-compose pull
docker-compose up -d

# Clean up unused resources
docker system prune -f

# Backup database
docker-compose exec web-dashboard cp /app/data/jobs.db /tmp/backup.db
docker cp telegram-job-dashboard:/tmp/backup.db ./backups/jobs_$(date +%Y%m%d).db

# Restore database
docker cp ./backups/jobs_YYYYMMDD.db telegram-job-dashboard:/app/data/jobs.db
docker-compose restart telegram-bot
```

## 🛡️ Production Configuration

### Resource Limits

```yaml
services:
  web-dashboard:
    deploy:
      resources:
        limits:
          memory: 1G
          cpus: '0.5'
        reservations:
          memory: 512M
          cpus: '0.25'
```

### Logging Configuration

```yaml
services:
  web-dashboard:
    logging:
      driver: "json-file"
      options:
        max-size: "50m"
        max-file: "5"
        labels: "service=web-dashboard"
```

### Health Checks

```yaml
services:
  web-dashboard:
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8080/health"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 60s
```

### Security Configuration

```yaml
services:
  web-dashboard:
    security_opt:
      - no-new-privileges:true
    read_only: true
    tmpfs:
      - /tmp:noexec,nosuid,size=100m
```

## 📊 Monitoring & Alerts

### Log Rotation

```yaml
services:
  web-dashboard:
    logging:
      driver: "json-file"
      options:
        max-size: "10m"
        max-file: "3"
```

### Resource Monitoring

```bash
# Monitor resource usage
docker stats

# Monitor disk usage
docker system df

# Monitor container health
docker-compose ps
```

## 🔄 CI/CD Integration

### GitHub Actions

```yaml
# .github/workflows/docker.yml
name: Docker Build and Push

on:
  push:
    branches: [ main ]

jobs:
  build:
    runs-on: ubuntu-latest
    steps:
    - uses: actions/checkout@v2
    
    - name: Build Docker Image
      run: docker-compose build
    
    - name: Run Tests
      run: docker-compose run --rm web-dashboard python -m pytest
      
    - name: Push to Registry
      run: |
        docker tag telegram-job-bot_web your-registry/telegram-job-bot:latest
        docker push your-registry/telegram-job-bot:latest
```

## 🐛 Troubleshooting

### Common Issues

#### 1. Container Won't Start

```bash
# Check logs
docker-compose logs [service_name]

# Check configuration
docker-compose config

# Rebuild without cache
docker-compose build --no-cache
```

#### 2. Database Permission Errors

```bash
# Fix permissions
sudo chown -R 1000:1000 data/
docker-compose restart
```

#### 3. Port Conflicts

```bash
# Check port usage
netstat -tulpn | grep :8080

# Change port in docker-compose.yml
ports:
  - "8081:8080"  # Use different host port
```

#### 4. Memory Issues

```bash
# Check memory usage
docker stats --no-stream

# Add memory limits
# See resource limits section above
```

### Performance Optimization

#### 1. Image Optimization

```dockerfile
# Use multi-stage builds (already implemented)
# Remove unnecessary packages
# Use .dockerignore for smaller context
```

#### 2. Container Optimization

```yaml
# Use non-root users
# Set resource limits
# Implement health checks
# Use appropriate restart policies
```

#### 3. Network Optimization

```yaml
# Use custom networks
# Avoid unnecessary port mappings
# Use internal networks for inter-container communication
```

## 📈 Scaling

### Horizontal Scaling

```bash
# Scale bot instances
docker-compose up -d --scale telegram-bot=3

# Use load balancer
# Implement Redis for session sharing
```

### Vertical Scaling

```yaml
# Increase resource limits
# Add more CPU and memory
# Optimize database performance
```

## 🔒 Security Best Practices

### 1. Container Security

- Use non-root users
- Read-only root filesystem
- Minimal base images
- Security scanning

### 2. Network Security

- Custom networks
- No unnecessary port exposure
- Internal service communication
- TLS for external connections

### 3. Secrets Management

- Environment variables for secrets
- Docker secrets in swarm mode
- External secret management
- Regular secret rotation

## 📋 Deployment Checklist

Before production deployment:

- [ ] Environment variables configured
- [ ] SSL certificates installed
- [ ] Firewall rules configured
- [ ] Backup strategy implemented
- [ ] Monitoring alerts configured
- [ ] Log rotation setup
- [ ] Resource limits configured
- [ ] Health checks implemented
- [ ] Security scan completed
- [ ] Documentation updated

## 🏗️ Coolify-Specific Configuration

### 1. Docker Compose Import

Coolify can automatically detect and import the `docker-compose.yml` file:

1. **Create New Project**
2. **Choose "Docker Compose"**
3. **Import from repository**
4. **Select `docker-compose.yml`**
5. **Configure environment variables**

### 2. Service Configuration

The unified Docker Compose configuration works perfectly with Coolify:

- **Web Dashboard**: Port 8080 exposed
- **Bot Service**: Background service
- **Health Checks**: Built-in monitoring
- **Resource Limits**: Configurable in Coolify

### 3. Environment Variables

Set all required environment variables in Coolify's project settings:

- **Telegram Credentials**: API ID, Hash, Bot Token
- **Authorization**: User IDs for access control
- **LLM Configuration**: OpenRouter API key
- **Google Sheets**: Credentials and spreadsheet ID

---

**Your Telegram Job Scraper Bot is ready for Docker deployment!** 🐳

For troubleshooting, see `TROUBLESHOOTING.md` and check container logs.