# Docker Deployment Guide

## 🐳 Deploy Telegram Job Scraper Bot with Docker

This comprehensive guide covers deploying the Telegram Job Scraper Bot using Docker and Docker Compose for production environments.

## 📋 Prerequisites

### System Requirements
- **Docker**: Version 20.10+ installed
- **Docker Compose**: Version 2.0+ installed
- **Server**: 2+ CPU cores, 4GB+ RAM, 20GB+ storage
- **Ports**: 8080 (web dashboard), 5000 (alternative)

### Required Files

Ensure these files exist in your project root:
```bash
Dockerfile
docker-compose.yml
.env.example
requirements.txt
```

## 🏗️ Dockerfile Configuration

### Web Dashboard Dockerfile

```dockerfile
# Multi-stage build for web dashboard
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

# Start web dashboard
CMD ["python", "web_server.py"]
```

### Bot Service Dockerfile

```dockerfile
# Multi-stage build for bot service
FROM python:3.11-slim as builder

# Install build dependencies
RUN apt-get update && apt-get install -y \
    gcc \
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

# Expose no ports (background service)

# Start bot service
CMD ["python", "main.py"]
```

## 📦 Docker Compose Configuration

### Production docker-compose.yml

```yaml
version: '3.8'

services:
  web-dashboard:
    build:
      context: .
      dockerfile: Dockerfile
      args:
        - TELEGRAM_API_ID=${TELEGRAM_API_ID}
        - TELEGRAM_API_HASH=${TELEGRAM_API_HASH}
    container_name: telegram-job-dashboard
    ports:
      - "8080:8080"
    environment:
      - FLASK_ENV=production
      - PORT=8080
      - TELEGRAM_API_ID=${TELEGRAM_API_ID}
      - TELEGRAM_API_HASH=${TELEGRAM_API_HASH}
      - TELEGRAM_BOT_TOKEN=${TELEGRAM_BOT_TOKEN}
      - AUTHORIZED_USER_IDS=${AUTHORIZED_USER_IDS}
      - ADMIN_USER_ID=${ADMIN_USER_ID}
      - DATABASE_PATH=/app/data/jobs.db
      - OPENROUTER_API_KEY=${OPENROUTER_API_KEY}
      - GOOGLE_CREDENTIALS_JSON=${GOOGLE_CREDENTIALS_JSON}
      - SPREADSHEET_ID=${SPREADSHEET_ID}
    volumes:
      - ./data:/app/data
      - ./logs:/app/logs
    working_dir: /app
    restart: unless-stopped
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8080/health"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 30s
    networks:
      - telegram-network
    depends_on:
      - database

  telegram-bot:
    build:
      context: .
      dockerfile: Dockerfile
    container_name: telegram-job-bot
    environment:
      - FLASK_ENV=production
      - TELEGRAM_API_ID=${TELEGRAM_API_ID}
      - TELEGRAM_API_HASH=${TELEGRAM_API_HASH}
      - TELEGRAM_BOT_TOKEN=${TELEGRAM_BOT_TOKEN}
      - AUTHORIZED_USER_IDS=${AUTHORIZED_USER_IDS}
      - ADMIN_USER_ID=${ADMIN_USER_ID}
      - DATABASE_PATH=/app/data/jobs.db
      - OPENROUTER_API_KEY=${OPENROUTER_API_KEY}
      - GOOGLE_CREDENTIALS_JSON=${GOOGLE_CREDENTIALS_JSON}
      - SPREADSHEET_ID=${SPREADSHEET_ID}
    volumes:
      - ./data:/app/data
      - ./logs:/app/logs
    working_dir: /app
    restart: unless-stopped
    networks:
      - telegram-network
    depends_on:
      - web-dashboard
      - database
    logging:
      driver: "json-file"
      options:
        max-size: "10m"
        max-file: "3"

  database:
    image: alpine:latest
    container_name: telegram-job-db
    command: sh -c "touch /data/jobs.db && tail -f /dev/null"
    volumes:
      - ./data:/data
    restart: unless-stopped
    networks:
      - telegram-network

volumes:
  data:
    driver: local
  logs:
    driver: local

networks:
  telegram-network:
    driver: bridge
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

### Log Aggregation

```yaml
services:
  web-dashboard:
    logging:
      driver: syslog
      options:
        syslog-address: "tcp://log-server:514"
        tag: "telegram-job-bot.web"
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

---

**Your Telegram Job Scraper Bot is ready for Docker deployment!** 🐳

For troubleshooting, see `TROUBLESHOOTING.md` and check container logs.