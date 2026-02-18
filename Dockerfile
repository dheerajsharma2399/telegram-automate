# Telegram Job Scraper - Fixed for Dokploy with External Database
FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Install Gunicorn for production
RUN pip install --no-cache-dir gunicorn

# Install PostgreSQL adapter for external database
RUN pip install --no-cache-dir psycopg2-binary asyncpg

# Copy application files
COPY . .

# Create necessary directories
RUN mkdir -p /app/data /app/logs

# Set environment variables for Dokploy
ENV PORT=9501
ENV FLASK_ENV=production
ENV CONTAINER_TYPE=all
ENV DATABASE_TYPE=postgresql

# Expose port
EXPOSE 9501

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=3 \
    CMD curl -f http://localhost:9501/health || exit 1

# Start command - Database will be initialized at runtime when DATABASE_URL is available
CMD python initialize_db.py && honcho start
