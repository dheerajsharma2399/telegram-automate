#!/usr/bin/env python3
"""Raw event processor worker.

Consumes raw_events through processing_queue, parses jobs with the LLM,
and persists structured jobs. This is the Phase 2 processor entrypoint.
"""

from __future__ import annotations

import asyncio
import logging
import os
import signal
from typing import Any, Dict, List, Optional

from config import (
    ADDITIONAL_SPREADSHEET_IDS,
    BATCH_SIZE,
    DATABASE_URL,
    GOOGLE_CREDENTIALS_JSON,
    LOG_LEVEL,
    OPENROUTER_API_KEYS,
    OPENROUTER_FALLBACK_MODELS,
    OPENROUTER_MODELS,
    SPREADSHEET_ID,
)
from database import Database, init_database
from llm_processor import LLMProcessor
from message_utils import log_execution
from services.processing_service import ProcessingService

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=getattr(logging, LOG_LEVEL.upper(), logging.INFO),
)
logger = logging.getLogger(__name__)

_db: Optional[Database] = None
_llm_processor: Optional[LLMProcessor] = None
_processing_service: Optional[ProcessingService] = None
_sheets_sync = None
shutdown_event = asyncio.Event()


def get_db() -> Database:
    global _db
    if _db is None:
        if not DATABASE_URL:
            raise RuntimeError("DATABASE_URL is not configured")
        _db = Database(DATABASE_URL)
        try:
            init_database(_db.pool)
        except Exception as exc:
            logger.warning(f"Runtime database initialization check failed: {exc}")
    return _db


def get_llm_processor() -> LLMProcessor:
    global _llm_processor
    if _llm_processor is None:
        _llm_processor = LLMProcessor(OPENROUTER_API_KEYS, OPENROUTER_MODELS, OPENROUTER_FALLBACK_MODELS)
    return _llm_processor



def get_sheets_sync():
    """Lazy Google Sheets sync factory for /sync_sheets compatibility."""
    global _sheets_sync
    if _sheets_sync is None and GOOGLE_CREDENTIALS_JSON and SPREADSHEET_ID:
        from sheets_sync import MultiSheetSync
        _sheets_sync = MultiSheetSync(GOOGLE_CREDENTIALS_JSON, SPREADSHEET_ID, ADDITIONAL_SPREADSHEET_IDS)
    return _sheets_sync


def get_processing_service() -> ProcessingService:
    global _processing_service
    if _processing_service is None:
        _processing_service = ProcessingService(get_db(), get_llm_processor(), get_sheets_sync=get_sheets_sync)
    return _processing_service


def request_shutdown(*_args):
    logger.info("Shutdown requested for processor_worker")
    shutdown_event.set()


async def process_queue_batch(batch_size: int = BATCH_SIZE, worker_id: str = "processor-worker") -> Dict[str, Any]:
    """Claim and process a batch of raw_events from processing_queue."""
    db = get_db()
    llm_processor = get_llm_processor()

    claimed_items = db.queue.claim_batch(limit=batch_size, worker_id=worker_id)
    if not claimed_items:
        logger.info("No pending raw events to process.")
        return {"processed_events": 0, "jobs_added": 0, "status": "empty"}

    processed_events = 0
    jobs_added = 0
    failed_events = 0

    for queue_item in claimed_items:
        queue_id = queue_item["id"]
        event_id = queue_item["event_id"]
        event = db.events.get_by_id(event_id)

        if not event:
            logger.warning(f"Queue item {queue_id} references missing event {event_id}")
            db.queue.mark_failed(queue_id, "event_not_found")
            failed_events += 1
            continue

        try:
            db.events.update_status(event_id, "processing")
            message_text = event.get("content") or ""
            event_source = (event.get("source") or "telegram").lower()
            event_metadata = event.get("metadata") or {}
            parsed_jobs = await llm_processor.parse_jobs(
                message_text,
                source=event_source,
                source_metadata=event_metadata,
            )

            if not parsed_jobs:
                db.events.update_status(event_id, "processed")
                db.queue.mark_done(queue_id)
                processed_events += 1
                continue

            for job_data in parsed_jobs:
                processed_data = llm_processor.process_job_data(
                    job_data,
                    raw_message_id=None,
                    source_event_id=event_id,
                )
                processed_data["source_event_id"] = event_id
                processed_data["raw_message_id"] = None

                from deduper import DedupAgent, make_fingerprint, simhash
                dedup_agent = DedupAgent(db)
                if not processed_data.get("job_fingerprint"):
                    processed_data["job_fingerprint"] = make_fingerprint(
                        processed_data.get("company_name"),
                        processed_data.get("job_role"),
                        processed_data.get("location"),
                    )
                if processed_data.get("jd_text"):
                    processed_data["simhash"] = simhash(processed_data["jd_text"])
                duplicate_job, dedup_method = dedup_agent.find_duplicate(processed_data)
                if duplicate_job:
                    logger.info(
                        "Duplicate job found via %s for '%s' - '%s'. Original job ID: %s. Skipping.",
                        dedup_method,
                        processed_data.get("company_name"),
                        processed_data.get("job_role"),
                        duplicate_job.get("job_id"),
                    )
                    continue

                job_id = db.jobs.add_job(processed_data, source=event.get("source") or "telegram")
                if job_id:
                    jobs_added += 1

            db.events.update_status(event_id, "processed")
            db.queue.mark_done(queue_id)
            processed_events += 1
        except Exception as exc:
            logger.error(f"Failed to process raw event {event_id}: {exc}", exc_info=True)
            db.events.update_status(event_id, "failed", str(exc))
            db.queue.mark_failed(queue_id, str(exc))
            failed_events += 1

    return {
        "processed_events": processed_events,
        "jobs_added": jobs_added,
        "failed_events": failed_events,
        "status": "success",
    }


async def poll_commands_loop() -> None:
    """Compatibility command poller for dashboard-triggered actions."""
    db = get_db()
    logger.info("🔧 Starting processor command poller loop...")

    while not shutdown_event.is_set():
        try:
            pending = db.commands.get_pending_commands(limit=5)
            if pending:
                for cmd in pending:
                    text = (cmd.get("command") or "").strip()
                    executed_ok = False
                    result_text = None

                    try:
                        if text.startswith("/process"):
                            await process_queue_batch()
                            executed_ok = True
                            result_text = "Processing triggered successfully"
                        elif text.startswith("/sync_sheets"):
                            await get_processing_service().sync_sheets_automatically()
                            executed_ok = True
                            result_text = "Sync triggered successfully"
                        elif text.startswith("/scrape_linkedin"):
                            def scrape_task():
                                from scrapers.linkedin.cdp_client import CDPClient
                                from scrapers.linkedin.post_scraper import LinkedInPostScraper
                                from scrapers.linkedin.job_scraper import LinkedInJobScraper
                                cdp = CDPClient()
                                cdp.connect()
                                try:
                                    post_scraper = LinkedInPostScraper(cdp, db)
                                    post_scraper.scrape()
                                    job_scraper = LinkedInJobScraper(cdp, db)
                                    job_scraper.scrape()
                                finally:
                                    cdp.close()
                            await asyncio.to_thread(scrape_task)
                            executed_ok = True
                            result_text = "LinkedIn scraping triggered successfully"
                        elif text.startswith("/fetch_telegram"):
                            from services.scraping_service import build_scraping_service
                            from config import TELEGRAM_API_ID, TELEGRAM_API_HASH, TELEGRAM_PHONE, TELEGRAM_GROUP_USERNAMES
                            scraping_service = build_scraping_service(
                                db,
                                TELEGRAM_API_ID,
                                TELEGRAM_API_HASH,
                                TELEGRAM_PHONE,
                                TELEGRAM_GROUP_USERNAMES
                            )
                            res = await scraping_service.fetch_recent(hours_back=12)
                            executed_ok = res.get("status") != "error"
                            result_text = f"Telegram fetch completed: {res.get('fetched_count', 0)} messages. Status: {res.get('status')}"
                        elif text.startswith("/export"):
                            executed_ok = True
                            result_text = "Export handled via API"
                        elif text.startswith("/backfill_sheets"):
                            executed_ok = True
                            result_text = "Backfill command acknowledged"
                        else:
                            logger.warning(f"Unknown command: {text}")
                            result_text = "Unknown command"
                    except Exception as exc:
                        logger.error(f"Error executing command {cmd.get('id')}: {exc}")
                        result_text = str(exc)

                    status = "done" if executed_ok else "failed"
                    db.commands.update_command_result(
                        cmd["id"],
                        status,
                        result_text=result_text,
                        executed_by="processor_worker",
                    )

            await asyncio.sleep(2)
        except Exception as exc:
            logger.error(f"Command poller error: {exc}")
            await asyncio.sleep(5)


@log_execution
async def main() -> None:
    """Long-running raw event processor loop."""
    logger.info("Starting raw event processor worker")
    for sig in (signal.SIGTERM, signal.SIGINT):
        signal.signal(sig, request_shutdown)
    get_db()
    command_task = asyncio.create_task(poll_commands_loop())

    try:
        while not shutdown_event.is_set():
            try:
                result = await process_queue_batch(batch_size=BATCH_SIZE)
                idle_delay = 0 if result.get("processed_events", 0) else 2
                try:
                    await asyncio.wait_for(shutdown_event.wait(), timeout=idle_delay)
                except asyncio.TimeoutError:
                    pass
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.error(f"Processor worker loop error: {exc}", exc_info=True)
                await asyncio.sleep(5)
    finally:
        command_task.cancel()
        try:
            await command_task
        except asyncio.CancelledError:
            pass
    logger.info("Processor worker shutdown complete")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Processor worker stopped.")
    except Exception as exc:
        logger.error(f"Unexpected processor worker error: {exc}", exc_info=True)
        raise
