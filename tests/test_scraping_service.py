import asyncio
import os

os.environ.setdefault("TELEGRAM_API_ID", "123456")
os.environ.setdefault("TELEGRAM_API_HASH", "testhash")
os.environ.setdefault("OPENROUTER_API_KEY", "testkey")

from services.scraping_service import ScrapingService
from services.telegram_session import TelegramSessionService


class FakeAuth:
    def __init__(self, session="session"):
        self.session = session
        self.login_status = None

    def get_telegram_session(self):
        return self.session

    def set_telegram_login_status(self, status):
        self.login_status = status

    def set_telegram_session(self, session):
        self.session = session


class FakeConfig:
    def __init__(self):
        self.values = {}

    def set_config(self, key, value):
        self.values[key] = value


class FakeCommands:
    def __init__(self):
        self.enqueued = []

    def enqueue_command(self, command):
        self.enqueued.append(command)
        return 42


class FakeDB:
    def __init__(self, session="session"):
        self.auth = FakeAuth(session=session)
        self.config = FakeConfig()
        self.commands = FakeCommands()


class FakeClient:
    def __init__(self, authorized=True):
        self.authorized = authorized
        self.disconnected = False

    def is_connected(self):
        return not self.disconnected

    async def is_user_authorized(self):
        return self.authorized

    async def disconnect(self):
        self.disconnected = True


def test_missing_telegram_session_returns_not_authenticated():
    db = FakeDB(session="")
    service = ScrapingService(db, TelegramSessionService(db, 123, "hash"))

    result = asyncio.run(service.fetch_recent(hours_back=1))

    assert result["status"] == "not_authenticated"
    assert result["fetched_count"] == 0
    assert result["storage_mode"] == "events"
    assert result["processing_enqueued"] is False
    assert db.config.values["monitoring_status"] == "stopped"
    assert db.auth.login_status == "not_authenticated"


def test_fetch_recent_uses_events_storage_mode(monkeypatch):
    db = FakeDB()
    client = FakeClient()
    captured = {}

    class FakeFetcher:
        def __init__(self, db_arg, client_arg, storage_mode="messages"):
            captured["db"] = db_arg
            captured["client"] = client_arg
            captured["storage_mode"] = storage_mode

        async def fetch_only_result(self, hours_back):
            captured["hours_back"] = hours_back
            return {"status": "success", "fetched_count": 3, "processing_enqueued": False}

    monkeypatch.setattr("services.scraping_service.HistoricalMessageFetcher", FakeFetcher)
    service = ScrapingService(db, TelegramSessionService(db, 123, "hash"))

    result = asyncio.run(service.fetch_recent(hours_back=2, client=client))

    assert captured["db"] is db
    assert captured["client"] is client
    assert captured["storage_mode"] == "events"
    assert captured["hours_back"] == 2
    assert result["status"] == "success"
    assert result["fetched_count"] == 3
    assert result["storage_mode"] == "events"
    assert result["processing_enqueued"] is False


def test_fetch_and_enqueue_enqueues_process_when_new_messages(monkeypatch):
    db = FakeDB()
    client = FakeClient()

    class FakeFetcher:
        def __init__(self, *_args, **_kwargs):
            pass

        async def fetch_only_result(self, _hours_back):
            return {"status": "success", "fetched_count": 2, "processing_enqueued": False}

    monkeypatch.setattr("services.scraping_service.HistoricalMessageFetcher", FakeFetcher)
    service = ScrapingService(db, TelegramSessionService(db, 123, "hash"))

    result = asyncio.run(service.fetch_and_enqueue(hours_back=1, client=client))

    assert db.commands.enqueued == ["/process"]
    assert result["processing_enqueued"] is True
    assert result["command_id"] == 42


def test_fetch_and_enqueue_does_not_enqueue_when_no_new_messages(monkeypatch):
    db = FakeDB()
    client = FakeClient()

    class FakeFetcher:
        def __init__(self, *_args, **_kwargs):
            pass

        async def fetch_only_result(self, _hours_back):
            return {"status": "no_new_messages", "fetched_count": 0, "processing_enqueued": False}

    monkeypatch.setattr("services.scraping_service.HistoricalMessageFetcher", FakeFetcher)
    service = ScrapingService(db, TelegramSessionService(db, 123, "hash"))

    result = asyncio.run(service.fetch_and_enqueue(hours_back=1, client=client))

    assert db.commands.enqueued == []
    assert result["processing_enqueued"] is False
    assert result["command_id"] is None
    assert result["status"] == "no_new_messages"


def test_fetch_recent_preserves_fetcher_error_status(monkeypatch):
    db = FakeDB()
    client = FakeClient()

    class FakeFetcher:
        def __init__(self, *_args, **_kwargs):
            pass

        async def fetch_only_result(self, _hours_back):
            return {
                "status": "error",
                "fetched_count": 0,
                "processing_enqueued": False,
                "error": "storage unavailable",
            }

    monkeypatch.setattr("services.scraping_service.HistoricalMessageFetcher", FakeFetcher)
    service = ScrapingService(db, TelegramSessionService(db, 123, "hash"))

    result = asyncio.run(service.fetch_recent(hours_back=1, client=client))

    assert result["status"] == "error"
    assert result["error"] == "storage unavailable"
    assert result["processing_enqueued"] is False
    assert result["command_id"] is None
