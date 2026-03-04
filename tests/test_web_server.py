"""
Unit tests for web_server.py

Covers:
- POST /api/dashboard/jobs/<id>/notes returns 404 (route removed)
- GET  /api/dashboard/jobs/<id>/notes returns 404
- _signal_handler uses port 9501 when PORT env var is absent
- _signal_handler uses the value of PORT env var when set
"""

import os
import sys
import importlib
import unittest
from unittest.mock import MagicMock, patch

# ---------------------------------------------------------------------------
# Inject required environment variables so config.py doesn't raise ValueError
# ---------------------------------------------------------------------------
_ENV_DEFAULTS = {
    "DATABASE_URL": "postgresql://fake:fake@localhost:5432/fakedb",
    "TELEGRAM_API_ID": "12345",
    "TELEGRAM_API_HASH": "fakehash",
    "OPENROUTER_API_KEY": "fake-openrouter-key",
}
for k, v in _ENV_DEFAULTS.items():
    os.environ.setdefault(k, v)

# ---------------------------------------------------------------------------
# Mock missing optional packages before any import of web_server
# ---------------------------------------------------------------------------
for _mod in (
    "aiohttp",
    "gspread",
    "google", "google.oauth2", "google.oauth2.service_account",
    "telethon", "telethon.sessions", "telethon.errors",
):
    if _mod not in sys.modules:
        sys.modules[_mod] = MagicMock()


def _make_flask_test_client():
    """
    Return a Flask test client for web_server.app with all heavy
    dependencies (DB, LLMProcessor, sheets) mocked out.
    """
    mock_db = MagicMock()
    mock_db.config.get_config.return_value = "running"
    mock_db.jobs.get_dashboard_jobs.return_value = {"jobs": [], "total_count": 0}
    mock_db.jobs.get_stats.return_value = {"total_jobs": 0, "by_status": {}, "by_relevance": {}}
    mock_db.commands.list_all_pending_commands.return_value = []

    with patch("database.Database", return_value=mock_db):
        import web_server
        web_server.db = mock_db
        web_server.llm_processor = MagicMock()
        web_server.app.config["TESTING"] = True
        client = web_server.app.test_client()

    return client, web_server


class TestNotesEndpointGone(unittest.TestCase):
    """The POST /api/dashboard/jobs/<id>/notes route was deleted; expect 404."""

    @classmethod
    def setUpClass(cls):
        cls.client, cls.ws_module = _make_flask_test_client()

    def test_post_notes_returns_404(self):
        """POST /api/dashboard/jobs/1/notes should return 404."""
        resp = self.client.post(
            "/api/dashboard/jobs/1/notes",
            json={"notes": "some note"},
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 404, (
            f"Expected 404 for POST /api/dashboard/jobs/1/notes, got {resp.status_code}"
        ))

    def test_get_notes_returns_404(self):
        """GET /api/dashboard/jobs/1/notes should also return 404 (route doesn't exist)."""
        resp = self.client.get("/api/dashboard/jobs/1/notes")
        self.assertEqual(resp.status_code, 404, (
            f"Expected 404 for GET /api/dashboard/jobs/1/notes, got {resp.status_code}"
        ))


class TestSignalHandlerPort(unittest.TestCase):
    """_signal_handler must derive the shutdown URL from the right port."""

    def _captured_url(self, env_overrides=None):
        """
        Call _signal_handler with the given os.environ overrides and return
        the URL that was passed to requests.post().
        """
        import web_server

        env_overrides = env_overrides or {}
        base_env = {k: v for k, v in os.environ.items()}
        # Remove PORT / FLASK_RUN_PORT so we start from a clean state
        base_env.pop("PORT", None)
        base_env.pop("FLASK_RUN_PORT", None)
        base_env.update(env_overrides)

        captured = {}

        def fake_post(url, **kwargs):
            captured["url"] = url
            raise RuntimeError("stop here")  # prevent actual HTTP call

        with patch.dict("os.environ", base_env, clear=True), \
             patch("web_server.requests.post", side_effect=fake_post), \
             patch("web_server.os._exit"):
            try:
                web_server._signal_handler(15, None)
            except Exception:
                pass

        return captured.get("url", "")

    def test_default_port_is_9501(self):
        """When PORT is not set, _signal_handler must use port 9501."""
        url = self._captured_url()
        self.assertIn(":9501/", url, (
            f"Expected port 9501 in shutdown URL, got: {url}"
        ))

    def test_custom_port_from_env(self):
        """When PORT=8080, _signal_handler must use port 8080."""
        url = self._captured_url(env_overrides={"PORT": "8080"})
        self.assertIn(":8080/", url, (
            f"Expected port 8080 in shutdown URL, got: {url}"
        ))


if __name__ == "__main__":
    unittest.main()
