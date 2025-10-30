# Telegram Job Scraper - Simple Dockerfile
FROM python:3.11-slim

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application files
COPY . .

# Create data directory
RUN mkdir -p /app/data

# Set environment variables
ENV PORT=8888
ENV FLASK_ENV=production
ENV CONTAINER_TYPE=web

# Expose port
EXPOSE 8888

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=3 \
    CMD curl -f http://localhost:8888/health || exit 1

# Start command
CMD ["python", "web_server.py"]