"""Scraping service extracted from main.py and web_server.py."""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional, List

from historical_message_fetcher import HistoricalMessageFetcher
from services.telegram_session import TelegramSessionService

logger = logging.getLogger(__name__)


class ScrapingService:
    def __init__(self, db, session_service: TelegramSessionService):
        self.db = db
        self.session_service = session_service

    @staticmethod
    def _base_result(
        status: str,
        fetched_count: int = 0,
        processing_enqueued: bool = False,
        command_id: Optional[int] = None,
        error: Optional[str] = None,
    ) -> Dict[str, Any]:
        return {
            "status": status,
            "fetched_count": fetched_count,
            "storage_mode": "events",
            "processing_enqueued": processing_enqueued,
            "command_id": command_id,
            "error": error,
        }

    async def fetch_recent(self, hours_back: float = 12, client: Any = None) -> Dict[str, Any]:
        """Fetch Telegram messages into raw_events only."""
        if hours_back < 0.1 or hours_back > 168:
            raise ValueError("hours_back must be between 0.1 and 168")
        if not all([self.session_service.api_id, self.session_service.api_hash]):
            raise ValueError("Telegram API credentials not configured")

        resolved_client = client
        owns_client = False
        try:
            try:
                resolved_client, owns_client = await self.session_service.ensure_authorized_client(resolved_client)
            except ConnectionError as exc:
                return self._base_result("not_authenticated", error=str(exc))

            fetcher = HistoricalMessageFetcher(self.db, resolved_client, storage_mode="events")
            result = await fetcher.fetch_only_result(hours_back)
            fetched_count = int(result.get("fetched_count") or 0)
            fetcher_status = result.get("status")
            status = "error" if fetcher_status == "error" else ("success" if fetched_count > 0 else "no_new_messages")
            normalized = self._base_result(
                status,
                fetched_count=fetched_count,
                error=result.get("error") if status == "error" else None,
            )
            normalized.update(result)
            normalized["status"] = status
            normalized["fetched_count"] = fetched_count
            normalized["storage_mode"] = "events"
            normalized["processing_enqueued"] = False
            normalized["command_id"] = None
            normalized["error"] = result.get("error") if status == "error" else None
            return normalized
        except Exception as exc:
            logger.error("Telegram scrape failed: %s", exc, exc_info=True)
            return self._base_result("error", error=str(exc))
        finally:
            if owns_client and resolved_client and resolved_client.is_connected():
                await self.session_service.disconnect_client(resolved_client)

    async def fetch_and_enqueue(self, hours_back: float = 12, client: Any = None) -> Dict[str, Any]:
        """Fetch Telegram messages into raw_events and enqueue /process if new rows exist."""
        result = await self.fetch_recent(hours_back=hours_back, client=client)
        if result.get("status") not in {"success", "no_new_messages"}:
            return result

        fetched_count = int(result.get("fetched_count") or 0)
        if fetched_count > 0:
            command_id = self.db.commands.enqueue_command("/process")
            result["processing_enqueued"] = True
            result["command_id"] = command_id
            result["message"] = f"Successfully fetched {fetched_count} new messages. Processing command enqueued."
        return result

    async def fetch_historical_messages(
        self,
        hours_back: float = 12,
        enqueue_process: bool = False,
        client: Any = None,
    ) -> Dict[str, Any]:
        """Compatibility wrapper for old callers."""
        if enqueue_process:
            return await self.fetch_and_enqueue(hours_back=hours_back, client=client)
        return await self.fetch_recent(hours_back=hours_back, client=client)

    async def fetch_only(self, hours_back: float = 12, client: Any = None) -> Dict[str, Any]:
        return await self.fetch_recent(hours_back=hours_back, client=client)

    def run_historical_fetch_sync(
        self,
        hours_back: float,
        enqueue_process: bool = False,
    ) -> Dict[str, Any]:
        """Synchronously execute the historical message fetch, managing its own event loop."""
        import asyncio
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            return loop.run_until_complete(
                self.fetch_historical_messages(
                    hours_back=hours_back,
                    enqueue_process=enqueue_process,
                )
            )
        finally:
            loop.close()


def build_scraping_service(
    db,
    api_id: Any,
    api_hash: str,
    phone: Optional[str] = None,
    group_usernames: Optional[List[str]] = None,
) -> ScrapingService:
    """Factory helper to build ScrapingService with its TelegramSessionService dependency."""
    session_service = TelegramSessionService(
        db,
        api_id,
        api_hash,
        phone,
        group_usernames,
    )
    return ScrapingService(db, session_service)

