# Telegram Job Scraper - Single Container with External Database
FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN pip install --no-cache-dir curl requests

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Install PostgreSQL adapter for external database
RUN pip install --no-cache-dir psycopg2-binary asyncpg

# Copy application files
COPY . .

# Create necessary directories
RUN mkdir -p /app/data /app/logs

# Set environment variables
ENV PORT=8888
ENV FLASK_ENV=production
ENV CONTAINER_TYPE=all
ENV BOT_RUN_MODE=webhook
ENV DATABASE_TYPE=sqlite

# Expose port
EXPOSE 8888

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=3 \
    CMD python -c "import requests; requests.get('http://localhost:8888/health', timeout=5)" || exit 1

# Start command - Run both web server and Telegram bot
CMD ["bash", "-c", "python web_server.py & python main.py & wait"]