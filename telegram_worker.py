#!/usr/bin/env python3
"""Telegram ingestion worker.

Fetches Telegram messages into raw_events/processing_queue only. No LLM
processing and no Google Sheets sync happen here.
"""
from __future__ import annotations

import asyncio
import logging
import signal
from typing import Optional

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from config import (
    DATABASE_URL,
    FETCH_INTERVAL_MINUTES,
    FETCH_LOOKBACK_MINUTES,
    LOG_LEVEL,
    TELEGRAM_API_HASH,
    TELEGRAM_API_ID,
    TELEGRAM_GROUP_USERNAMES,
    TELEGRAM_PHONE,
)
from database import Database, init_database
from monitor import TelegramMonitor
from services.scraping_service import ScrapingService, build_scraping_service

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=getattr(logging, LOG_LEVEL.upper(), logging.INFO),
)
logger = logging.getLogger(__name__)

shutdown_event = asyncio.Event()
db: Optional[Database] = None


def get_db() -> Database:
    global db
    if db is None:
        if not DATABASE_URL:
            raise RuntimeError("DATABASE_URL is not configured")
        db = Database(DATABASE_URL)
        try:
            init_database(db.pool)
        except Exception as exc:
            logger.warning("Runtime database initialization check failed: %s", exc)
    return db


def get_scraping_service() -> ScrapingService:
    return build_scraping_service(
        get_db(),
        TELEGRAM_API_ID,
        TELEGRAM_API_HASH,
        TELEGRAM_PHONE,
        TELEGRAM_GROUP_USERNAMES,
    )


def request_shutdown(*_args):
    logger.info("Shutdown requested for telegram_worker")
    shutdown_event.set()


async def scheduled_fetch(monitor: TelegramMonitor) -> int:
    current_db = get_db()
    status = current_db.config.get_config("monitoring_status")
    if status != "running":
        logger.info("Monitoring is paused (Status: %s). Skipping Telegram fetch.", status)
        return 0

    hours_back = FETCH_LOOKBACK_MINUTES / 60.0
    result = await get_scraping_service().fetch_recent(hours_back=hours_back, client=monitor.client)
    fetched_count = int(result.get("fetched_count") or 0)
    logger.info("Telegram fetch result: %s", result)
    if result.get("status") == "error":
        raise RuntimeError(result.get("error") or "Telegram fetch failed")
    if result.get("status") == "not_authenticated":
        logger.warning("Telegram fetch skipped: not authenticated")
    return fetched_count


async def main() -> None:
    logger.info("Starting Telegram ingestion worker")
    for sig in (signal.SIGTERM, signal.SIGINT):
        signal.signal(sig, request_shutdown)

    current_db = get_db()
    monitor = TelegramMonitor(
        TELEGRAM_API_ID, TELEGRAM_API_HASH, TELEGRAM_PHONE, TELEGRAM_GROUP_USERNAMES, current_db
    )
    if current_db.config.get_config("monitoring_status") != "running":
        current_db.config.set_config("monitoring_status", "running")

    scheduler = AsyncIOScheduler()
    scheduler.add_job(
        scheduled_fetch,
        "interval",
        minutes=FETCH_INTERVAL_MINUTES,
        id="telegram_fetch",
        args=[monitor],
        replace_existing=True,
    )
    scheduler.start()
    asyncio.create_task(scheduled_fetch(monitor))

    try:
        await shutdown_event.wait()
    finally:
        scheduler.shutdown(wait=False)
        if monitor.client and monitor.client.is_connected():
            await monitor.client.disconnect()
        logger.info("Telegram ingestion worker stopped")


if __name__ == "__main__":
    asyncio.run(main())
