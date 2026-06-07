#!/usr/bin/env python3
"""Scraper worker entrypoint placeholder.

Phase 2 separates deployment process types. Telegram ingestion runs in
telegram_worker.py and queue processing runs in processor_worker.py. This
worker remains available for future non-Telegram scraper jobs and intentionally
idles instead of duplicating Telegram ingestion.
"""
import logging
import signal
import time

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)
_running = True

def _stop(*_args):
    global _running
    logger.info("Shutdown requested for scraper_worker")
    _running = False

def main():
    signal.signal(signal.SIGTERM, _stop)
    signal.signal(signal.SIGINT, _stop)
    logger.info("Scraper worker started; no scraper jobs configured in Phase 2")
    while _running:
        time.sleep(30)
    logger.info("Scraper worker stopped")

if __name__ == "__main__":
    main()
