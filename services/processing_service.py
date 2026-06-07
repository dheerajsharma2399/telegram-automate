"""Processing service extracted from main.py.

This keeps queue consumption, LLM parsing, job persistence, and optional
Google Sheets synchronization in a dedicated service layer.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Callable, Dict, Optional

logger = logging.getLogger(__name__)


class ProcessingService:
    def __init__(
        self,
        db,
        llm_processor,
        get_sheets_sync: Optional[Callable[[], Any]] = None,
    ):
        self.db = db
        self.llm_processor = llm_processor
        self.get_sheets_sync = get_sheets_sync or (lambda: None)

    async def process_message(self, message: Dict[str, Any]) -> Dict[str, Any]:
        """Process a single raw message into one or more jobs."""
        message_id = message["id"]
        logger.info(
            f"Processing message ID: {message_id} (Text len: {len(message.get('message_text', ''))})"
        )

        self.db.messages.update_message_status(message_id, "processing")

        logger.info(f"Sending message {message_id} to LLM...")
        source = (message.get("source") or "telegram").lower()
        source_metadata = message.get("metadata") or {}
        parsed_jobs = await self.llm_processor.parse_jobs(
            message["message_text"],
            source=source,
            source_metadata=source_metadata,
        )

        if not parsed_jobs:
            logger.warning(f"Message {message_id} yielded NO jobs from LLM.")
            self.db.messages.update_message_status(message_id, "processed", "No jobs found")
            return {"message_id": message_id, "jobs_added": 0, "status": "no_jobs"}

        logger.info(f"LLM found {len(parsed_jobs)} jobs in message {message_id}")

        jobs_added = 0
        for job_data in parsed_jobs:
            try:
                processed_data = self.llm_processor.process_job_data(job_data, message_id)
                duplicate_job = self.db.jobs.find_duplicate_processed_job(
                    processed_data.get("company_name"),
                    processed_data.get("job_role"),
                    processed_data.get("email"),
                )
                if duplicate_job:
                    logger.info(
                        "Duplicate job found for '%s' - '%s'. Original job ID: %s. Skipping.",
                        processed_data.get("company_name"),
                        processed_data.get("job_role"),
                        duplicate_job["job_id"],
                    )
                    continue

                job_id = self.db.jobs.add_processed_job(processed_data)
                if not job_id:
                    logger.error("Failed to add job to database")
                    continue

                jobs_added += 1
                logger.info(
                    "✅ Job saved successfully: %s (ID: %s)",
                    processed_data.get("company_name"),
                    job_id,
                )
            except Exception as exc:
                logger.error(f"Failed to process individual job: {exc}")
                continue

        self.db.messages.update_message_status(message_id, "processed")
        logger.info(f"✅ Fully processed message {message_id}")
        return {"message_id": message_id, "jobs_added": jobs_added, "status": "processed"}

    async def sync_sheets_automatically(self) -> None:
        """Synchronize unsynced jobs to Google Sheets if configured."""
        sheets_sync = self.get_sheets_sync()
        if not (sheets_sync and getattr(sheets_sync, "client", None)):
            logger.info("Google Sheets not configured, skipping automatic sync.")
            return

        try:
            unsynced_jobs = self.db.jobs.get_unsynced_jobs()
            if not unsynced_jobs:
                logger.info("No new jobs to sync to Google Sheets.")
                return

            logger.info(f"Found {len(unsynced_jobs)} new jobs to sync to Google Sheets.")
            synced_count = 0
            failed_count = 0

            for job in unsynced_jobs:
                try:
                    sync_success = await asyncio.to_thread(sheets_sync.sync_job, job)
                    if sync_success:
                        self.db.jobs.mark_job_synced(job.get("job_id"))
                        synced_count += 1
                    else:
                        failed_count += 1
                        logger.warning(
                            f"Failed to sync job {job.get('job_id')}: {job.get('company_name')} - {job.get('job_role')}"
                        )
                except Exception as exc:
                    failed_count += 1
                    logger.error(
                        f"Exception syncing job {job.get('job_id')} ({job.get('company_name')}): {exc}"
                    )

            if failed_count > 0:
                logger.warning(
                    f"Google Sheets sync complete. Synced {synced_count} jobs, {failed_count} failed."
                )
            else:
                logger.info(f"Google Sheets sync complete. Successfully synced {synced_count} new jobs.")
        except Exception as exc:
            logger.error(f"Automatic Google Sheets sync failed: {exc}")

    async def process_batch(self, batch_size: int = 10, sync_sheets: bool = False) -> Dict[str, Any]:
        """Process a batch of pending raw messages from the queue.

        Sheets synchronization is opt-in so direct service callers do not
        accidentally couple extraction to sync side effects.
        """
        if not self.db or not self.llm_processor:
            logger.error("Processing service is missing DB or LLM processor.")
            return {"processed_messages": 0, "status": "error", "error": "service_unavailable"}

        logger.info("🚀 Starting job processing...")
        self.db.messages.reset_stuck_processing_messages(stuck_minutes=30)
        unprocessed_messages = self.db.messages.get_unprocessed_messages(limit=batch_size)
        if not unprocessed_messages:
            logger.info("No unprocessed messages to process.")
            return {"processed_messages": 0, "status": "empty"}

        logger.info(f"Found {len(unprocessed_messages)} unprocessed messages. Starting batch...")
        processed_messages = 0
        total_jobs_added = 0

        for message in unprocessed_messages:
            try:
                result = await self.process_message(message)
                processed_messages += 1
                total_jobs_added += int(result.get("jobs_added") or 0)
            except Exception as exc:
                logger.error(f"❌ Failed to process message {message['id']}: {exc}", exc_info=True)
                self.db.messages.update_message_status(message["id"], "failed", str(exc))

        if sync_sheets:
            logger.info("Job processing batch finished. Starting automatic Google Sheets sync.")
            await self.sync_sheets_automatically()

        return {
            "processed_messages": processed_messages,
            "jobs_added": total_jobs_added,
            "status": "success",
        }

    async def process_pending_messages(self, batch_size: int = 10, sync_sheets: bool = False) -> Dict[str, Any]:
        """Compatibility wrapper for older callers."""
        return await self.process_batch(batch_size=batch_size, sync_sheets=sync_sheets)
