#!/usr/bin/env python3
"""LinkedIn Scraper Worker.

Phase 4 scraper worker. Periodically or on-demand executes the LinkedIn CDP scrapers
to pull posts and structured job cards, saving them to PostgreSQL raw_events and jobs tables.
"""

import argparse
import logging
import signal
import sys
import time
from typing import Optional

from config import DATABASE_URL, LOG_LEVEL
from database import Database, init_database
from scrapers.linkedin.cdp_client import CDPClient
from scrapers.linkedin.post_scraper import LinkedInPostScraper
from scrapers.linkedin.job_scraper import LinkedInJobScraper

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=getattr(logging, LOG_LEVEL.upper(), logging.INFO),
)
logger = logging.getLogger(__name__)

_running = True
_db: Optional[Database] = None

def get_db() -> Database:
    global _db
    if _db is None:
        if not DATABASE_URL:
            raise RuntimeError("DATABASE_URL is not configured")
        _db = Database(DATABASE_URL)
        try:
            init_database(_db.pool)
        except Exception as exc:
            logger.warning("Runtime database initialization check failed: %s", exc)
    return _db

def request_shutdown(*_args):
    global _running
    logger.info("Shutdown requested for scraper_worker")
    _running = False

def run_scraping(args) -> None:
    db = get_db()
    cdp = CDPClient()
    
    try:
        logger.info("Connecting to Chrome DevTools Protocol...")
        cdp.connect()
    except Exception as exc:
        logger.error("Could not connect to Chrome instance: %s. Skipping scraping cycle.", exc)
        return

    try:
        roles = [args.role] if args.role else None
        
        # 1. Run LinkedIn Content/Post Scraper
        if not args.jobs_only:
            logger.info("Starting LinkedIn Content/Post Scraper...")
            post_scraper = LinkedInPostScraper(cdp, db)
            res = post_scraper.scrape(roles=roles)
            logger.info("Post scraping complete: %d posts found, %d new enqueued.", res["total_scraped"], res["total_new"])

        # 2. Run LinkedIn Jobs Card Scraper
        if not args.posts_only:
            logger.info("Starting LinkedIn Jobs Card Scraper...")
            job_scraper = LinkedInJobScraper(cdp, db)
            res = job_scraper.scrape(roles=roles, limit_per_role=args.limit)
            logger.info("Job scraping complete: %d cards found, %d new saved.", res["total_scraped"], res["total_new"])

    except Exception as exc:
        logger.error("Error during LinkedIn scraping cycle: %s", exc, exc_info=True)
    finally:
        cdp.close()

def main() -> None:
    signal.signal(signal.SIGTERM, request_shutdown)
    signal.signal(signal.SIGINT, request_shutdown)

    parser = argparse.ArgumentParser(description="LinkedIn Scraper Worker")
    parser.add_argument("--posts-only", action="store_true", help="Only scrape LinkedIn posts (content search)")
    parser.add_argument("--jobs-only", action="store_true", help="Only scrape LinkedIn jobs (job cards/JDs)")
    parser.add_argument("--role", type=str, default=None, help="Limit scraping to a specific role bucket")
    parser.add_argument("--limit", type=int, default=15, help="Limit the number of jobs per role")
    parser.add_argument("--loop", action="store_true", help="Run continuously in a loop")
    parser.add_argument("--interval", type=int, default=14400, help="Interval in seconds between runs (default 4 hours)")
    args = parser.parse_args()

    logger.info("LinkedIn scraper worker started")

    if args.loop:
        logger.info("Continuous loop mode active. Scraping interval: %d seconds.", args.interval)
        while _running:
            run_scraping(args)
            logger.info("Scraping cycle complete. Sleeping for %d seconds.", args.interval)
            
            # Sleep in small segments to remain responsive to SIGTERM/SIGINT
            elapsed = 0
            while _running and elapsed < args.interval:
                time.sleep(2)
                elapsed += 2
    else:
        run_scraping(args)
        logger.info("One-shot scraping run finished.")

if __name__ == "__main__":
    main()
