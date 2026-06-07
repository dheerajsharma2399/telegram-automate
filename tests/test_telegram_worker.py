import asyncio
import os

os.environ.setdefault("TELEGRAM_API_ID", "123456")
os.environ.setdefault("TELEGRAM_API_HASH", "testhash")
os.environ.setdefault("OPENROUTER_API_KEY", "testkey")

import pytest

import telegram_worker


class FakeConfig:
    def __init__(self, status="running"):
        self.status = status

    def get_config(self, key):
        if key == "monitoring_status":
            return self.status
        return None


class FakeDB:
    def __init__(self, status="running"):
        self.config = FakeConfig(status=status)


class FakeMonitor:
    client = object()


def test_scheduled_fetch_raises_on_service_error(monkeypatch):
    class FakeScrapingService:
        async def fetch_recent(self, hours_back, client=None):
            return {
                "status": "error",
                "fetched_count": 0,
                "storage_mode": "events",
                "processing_enqueued": False,
                "command_id": None,
                "error": "backend failed",
            }

    monkeypatch.setattr(telegram_worker, "get_db", lambda: FakeDB())
    monkeypatch.setattr(telegram_worker, "get_scraping_service", lambda: FakeScrapingService())
    monkeypatch.setattr(telegram_worker, "FETCH_LOOKBACK_MINUTES", 10)

    with pytest.raises(RuntimeError, match="backend failed"):
        asyncio.run(telegram_worker.scheduled_fetch(FakeMonitor()))


def test_scheduled_fetch_not_authenticated_does_not_raise(monkeypatch, caplog):
    class FakeScrapingService:
        async def fetch_recent(self, hours_back, client=None):
            return {
                "status": "not_authenticated",
                "fetched_count": 0,
                "storage_mode": "events",
                "processing_enqueued": False,
                "command_id": None,
                "error": "No active Telegram session found. Please authenticate first.",
            }

    monkeypatch.setattr(telegram_worker, "get_db", lambda: FakeDB())
    monkeypatch.setattr(telegram_worker, "get_scraping_service", lambda: FakeScrapingService())
    monkeypatch.setattr(telegram_worker, "FETCH_LOOKBACK_MINUTES", 10)

    result = asyncio.run(telegram_worker.scheduled_fetch(FakeMonitor()))

    assert result == 0
    assert "not authenticated" in caplog.text
