"""
Integration tests for end-to-end workflows

Tests the complete message processing pipeline.
"""

import asyncio
import os
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, Mock, patch

os.environ.setdefault("DATABASE_URL", "postgresql://user:pass@localhost:5432/testdb")
os.environ.setdefault("ADMIN_USER_ID", "1")
os.environ.setdefault("TELEGRAM_API_ID", "123456")
os.environ.setdefault("TELEGRAM_API_HASH", "testhash")
os.environ.setdefault("TELEGRAM_PHONE", "+10000000000")
os.environ.setdefault("OPENROUTER_API_KEY", "testkey")
os.environ.setdefault("GOOGLE_CREDENTIALS_JSON", "{}")
os.environ.setdefault("SPREADSHEET_ID", "testspreadsheet")
PROJECT_ROOT = Path(__file__).resolve().parents[1]


class TestMessageProcessingPipeline(unittest.TestCase):
    """Test end-to-end message processing"""

    def test_processing_service_workflow(self):
        """Test complete job processing workflow through ProcessingService."""
        from services.processing_service import ProcessingService

        mock_db = MagicMock()
        mock_llm = MagicMock()
        mock_llm.parse_jobs = AsyncMock(return_value=[
            {
                'company_name': 'Test Corp',
                'job_role': 'Software Engineer',
                'location': 'Remote'
            }
        ])
        mock_llm.process_job_data.return_value = {
            'job_id': 'test_123',
            'company_name': 'Test Corp',
            'job_role': 'Software Engineer',
            'location': 'Remote',
            'application_method': 'link'
        }

        mock_db.messages.get_unprocessed_messages.return_value = [
            {
                'id': 1,
                'message_text': 'Job posting: Software Engineer at Test Corp'
            }
        ]
        mock_db.messages.reset_stuck_processing_messages.return_value = 0
        mock_db.messages.update_message_status.return_value = None
        mock_db.jobs.find_duplicate_processed_job.return_value = None
        mock_db.jobs.add_processed_job.return_value = 'test_123'
        mock_db.jobs.get_unsynced_jobs.return_value = []

        service = ProcessingService(mock_db, mock_llm, get_sheets_sync=lambda: None)

        async def run_test():
            result = await service.process_pending_messages(batch_size=10, sync_sheets=False)

            self.assertEqual(result['status'], 'success')
            self.assertEqual(result['processed_messages'], 1)
            self.assertEqual(result['jobs_added'], 1)
            mock_db.messages.get_unprocessed_messages.assert_called_once_with(limit=10)
            mock_db.messages.update_message_status.assert_any_call(1, 'processing')
            mock_db.messages.update_message_status.assert_any_call(1, 'processed')
            mock_llm.parse_jobs.assert_called_once()
            mock_db.jobs.add_processed_job.assert_called_once()

        asyncio.run(run_test())

    def test_processing_service_does_not_sync_by_default(self):
        """Direct ProcessingService calls should not sync sheets unless requested."""
        from services.processing_service import ProcessingService

        mock_db = MagicMock()
        mock_llm = MagicMock()
        mock_llm.parse_jobs = AsyncMock(return_value=[])

        mock_db.messages.get_unprocessed_messages.return_value = []
        mock_db.messages.reset_stuck_processing_messages.return_value = 0
        mock_db.messages.update_message_status.return_value = None

        service = ProcessingService(mock_db, mock_llm, get_sheets_sync=lambda: MagicMock(client=object()))
        sync_mock = AsyncMock()
        service.sync_sheets_automatically = sync_mock

        async def run_test():
            result = await service.process_pending_messages(batch_size=5)

            self.assertEqual(result['status'], 'empty')
            sync_mock.assert_not_awaited()

        asyncio.run(run_test())

    def test_main_process_jobs_remains_compatible(self):
        with patch('database.init_connection_pool', return_value=MagicMock()), \
             patch('database.init_database'), \
             patch('llm_processor.LLMProcessor', return_value=MagicMock()), \
             patch('services.processing_service.ProcessingService') as mock_processing_service_cls:
            mock_processing_service_cls.return_value.process_pending_messages = AsyncMock(return_value={"status": "success"})

            import importlib
            main = importlib.import_module('main')
            main._processing_service = None
            main.get_processing_service = MagicMock(return_value=mock_processing_service_cls.return_value)

            async def run_test():
                await main.process_jobs()
                mock_processing_service_cls.return_value.process_pending_messages.assert_awaited_once()

            asyncio.run(run_test())


class TestInputValidation(unittest.TestCase):
    """Test input validation for web endpoints"""

    def test_advanced_sync_validates_days_parameter(self):
        """Test that advanced_sync validates days parameter"""
        with patch('database.init_connection_pool', return_value=MagicMock()), \
             patch('database.init_database'):
            import importlib
            web_server = importlib.import_module('web_server')
            web_server.db = MagicMock()
            web_server.get_sheets_sync = MagicMock(return_value=None)

            with web_server.app.test_client() as client:
                response = client.post('/api/sheets/advanced_sync', json={'days': 'invalid'})
                self.assertEqual(response.status_code, 400)
                self.assertIn('must be a valid integer', response.get_json()['error'])

                response = client.post('/api/sheets/advanced_sync', json={'days': 0})
                self.assertEqual(response.status_code, 400)
                self.assertIn('between 1 and 365', response.get_json()['error'])

                response = client.post('/api/sheets/advanced_sync', json={'days': 400})
                self.assertEqual(response.status_code, 400)
                self.assertIn('between 1 and 365', response.get_json()['error'])


class TestHealthCheckEndpoint(unittest.TestCase):
    """Test health check endpoint"""

    def test_health_check_returns_200(self):
        """Test that health check returns 200 ok"""
        with patch('database.init_connection_pool', return_value=MagicMock()), \
             patch('database.init_database'):
            import importlib
            web_server = importlib.import_module('web_server')
            web_server.db = MagicMock()

            with web_server.app.test_client() as client:
                response = client.get('/health')

                self.assertEqual(response.status_code, 200)
                data = response.get_json()
                self.assertEqual(data['status'], 'ok')


if __name__ == '__main__':
    unittest.main()



def test_procfile_entrypoints_exist():
    """Every Python process declared in Procfile should point at an existing file."""
    procfile = PROJECT_ROOT / "Procfile"
    missing = []
    for line in procfile.read_text().splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        if ":" not in line:
            continue
        command = line.split(":", 1)[1].strip().split()
        if len(command) >= 2 and command[0].startswith("python") and command[1].endswith(".py"):
            target = PROJECT_ROOT / command[1]
            if not target.exists():
                missing.append(command[1])
    assert missing == []


def test_processor_worker_sync_sheets_command_marks_done(monkeypatch):
    """processor_worker remains compatible with /sync_sheets dashboard/MCP commands."""
    import processor_worker

    class FakeCommands:
        def __init__(self):
            self.calls = 0
            self.results = []

        def get_pending_commands(self, limit=5):
            self.calls += 1
            if self.calls == 1:
                return [{"id": 7, "command": "/sync_sheets"}]
            raise RuntimeError("stop-loop")

        def update_command_result(self, *args, **kwargs):
            self.results.append((args, kwargs))

    class FakeDB:
        def __init__(self):
            self.commands = FakeCommands()

    class FakeService:
        def __init__(self):
            self.synced = False

        async def sync_sheets_automatically(self):
            self.synced = True

    fake_db = FakeDB()
    fake_service = FakeService()
    sleeps = []

    async def fake_sleep(_seconds):
        sleeps.append(_seconds)
        raise RuntimeError("stop-loop")

    monkeypatch.setattr(processor_worker, "get_db", lambda: fake_db)
    monkeypatch.setattr(processor_worker, "get_processing_service", lambda: fake_service)
    monkeypatch.setattr(processor_worker.asyncio, "sleep", fake_sleep)

    import pytest
    with pytest.raises(RuntimeError, match="stop-loop"):
        asyncio.run(processor_worker.poll_commands_loop())

    assert fake_service.synced is True
    assert fake_db.commands.results
    args, kwargs = fake_db.commands.results[0]
    assert args[0] == 7
    assert args[1] == "done"


def test_fetch_historical_messages_accepts_string_hours_back(monkeypatch):
    """API accepts JSON numeric strings for hours_back and reports coerced value."""
    import database
    monkeypatch.setattr(database, "Database", lambda *args, **kwargs: None)
    import importlib, web_server
    web_server = importlib.reload(web_server)

    monkeypatch.setattr(web_server, "TELEGRAM_API_ID", "123")
    monkeypatch.setattr(web_server, "TELEGRAM_API_HASH", "hash")
    monkeypatch.setattr(web_server, "TELEGRAM_PHONE", "+1000")

    class FakeScrapingService:
        async def fetch_historical_messages(self, hours_back=12, enqueue_process=False):
            return {
                "status": "no_new_messages",
                "fetched_count": 0,
                "storage_mode": "events",
                "processing_enqueued": False,
                "command_id": None,
                "error": None,
            }

    monkeypatch.setattr(web_server, "db", object())
    monkeypatch.setattr(web_server, "get_scraping_service", lambda: FakeScrapingService())

    client = web_server.app.test_client()
    resp = client.post("/api/fetch_historical_messages", json={"hours_back": "6", "enqueue_process": False}, headers={"X-API-Key": "test"})
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["hours_back"] == 6.0
    assert data["status"] == "no_new_messages"


def test_fetch_historical_messages_rejects_invalid_hours_back(monkeypatch):
    import database
    monkeypatch.setattr(database, "Database", lambda *args, **kwargs: None)
    import importlib, web_server
    web_server = importlib.reload(web_server)
    client = web_server.app.test_client()
    resp = client.post("/api/fetch_historical_messages", json={"hours_back": "abc"}, headers={"X-API-Key": "test"})
    assert resp.status_code == 400
    assert "hours_back" in resp.get_json()["error"]


def test_llm_processor_single_object_json_is_normalized(monkeypatch):
    """A valid single-job JSON object should be treated as a one-item job list."""
    from llm_processor import LLMProcessor

    async def fake_try_pool(self, model_pool, message_text, max_retries, pool_name):
        return {"company_name": "Acme", "job_role": "Python Developer", "email": "hr@example.com", "jd_text": "Acme needs Python Developer hr@example.com"}

    monkeypatch.setattr(LLMProcessor, "_try_pool", fake_try_pool)
    processor = LLMProcessor(["key"], ["model"], [])
    jobs = asyncio.run(processor.parse_jobs("Acme needs Python Developer hr@example.com"))
    assert isinstance(jobs, list)
    assert len(jobs) == 1
    assert jobs[0]["company_name"] == "Acme"


def test_fetch_historical_messages_returns_500_on_service_error(monkeypatch):
    import database
    monkeypatch.setattr(database, "Database", lambda *args, **kwargs: None)
    import importlib, web_server
    web_server = importlib.reload(web_server)

    monkeypatch.setattr(web_server, "TELEGRAM_API_ID", "123")
    monkeypatch.setattr(web_server, "TELEGRAM_API_HASH", "hash")
    monkeypatch.setattr(web_server, "TELEGRAM_PHONE", "+1000")

    class FakeDB:
        pass

    class FakeScrapingService:
        async def fetch_historical_messages(self, hours_back=12, enqueue_process=False):
            return {
                "status": "error",
                "fetched_count": 0,
                "storage_mode": "events",
                "processing_enqueued": False,
                "command_id": None,
                "error": "backend failed",
            }

    monkeypatch.setattr(web_server, "db", FakeDB())
    monkeypatch.setattr(web_server, "get_scraping_service", lambda: FakeScrapingService())

    client = web_server.app.test_client()
    resp = client.post("/api/fetch_historical_messages", json={"hours_back": "6"}, headers={"X-API-Key": "test"})

    assert resp.status_code == 500
    assert resp.get_json()["status"] == "error"
