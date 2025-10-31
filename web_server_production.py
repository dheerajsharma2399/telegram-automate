#!/usr/bin/env python3
"""
Production-ready web server for Telegram Job Scraper
Ensures proper Gunicorn configuration and external accessibility
"""
import os
import logging
import sys

# Set production environment
os.environ['FLASK_ENV'] = 'production'

# Import after setting environment
from web_server import app, application

if __name__ == "__main__":
    # Production configuration
    port = int(os.environ.get('PORT', 9501))
    host = os.environ.get('HOST', '0.0.0.0')
    workers = int(os.environ.get('WORKERS', 2))
    
    # Configure logging for production
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.StreamHandler(sys.stdout),
            logging.FileHandler('/app/logs/web_server.log')
        ]
    )
    
    logging.info(f"Starting production web server on {host}:{port}")
    logging.info(f"Using {workers} workers")
    
    # This will be called by Gunicorn
    application.run(
        host=host,
        port=port,
        debug=False,
        threaded=True
    )