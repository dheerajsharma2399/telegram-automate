import os
import sys
import unittest
from unittest.mock import MagicMock, patch

# Inject environment variables to satisfy config.py
_ENV_DEFAULTS = {
    "DATABASE_URL": "postgresql://fake:fake@localhost:5432/fakedb",
    "TELEGRAM_API_ID": "12345",
    "TELEGRAM_API_HASH": "fakehash",
    "OPENROUTER_API_KEY": "fake-openrouter-key",
    "API_KEY": "test-secret-key",
}
for k, v in _ENV_DEFAULTS.items():
    os.environ.setdefault(k, v)

# Mock heavy modules so we don't need real packages
for _mod in (
    "aiohttp",
    "gspread",
    "google", "google.oauth2", "google.oauth2.service_account",
    "telethon", "telethon.sessions", "telethon.errors",
):
    if _mod not in sys.modules:
        sys.modules[_mod] = MagicMock()


class TestDatabaseAgentClassification(unittest.TestCase):
    """Test the UnifiedJobRepository additions for agent classification"""

    def setUp(self):
        from database_repositories import UnifiedJobRepository
        self.mock_pool = MagicMock()
        self.mock_conn = MagicMock()
        self.mock_cursor = MagicMock()
        
        # Setup context managers
        self.mock_conn.cursor.return_value.__enter__.return_value = self.mock_cursor
        self.mock_conn.cursor.return_value.__exit__.return_value = None
        self.mock_pool.getconn.return_value = self.mock_conn
        
        self.repo = UnifiedJobRepository(self.mock_pool)
        self.repo.get_connection = MagicMock()
        self.repo.get_connection.return_value.__enter__.return_value = self.mock_conn

    def test_get_jobs_for_agent_classification(self):
        """test retrieval of eligible jobs query execution"""
        self.mock_cursor.fetchall.return_value = [
            {"id": 1, "job_id": "job1", "company_name": "Co1", "job_role": "Role1", "email": "e1@co1.com", "salary": "$100k", "jd_text": "text1", "metadata": {}}
        ]
        
        jobs = self.repo.get_jobs_for_agent_classification(limit=5)
        
        self.assertEqual(len(jobs), 1)
        self.assertEqual(jobs[0]["id"], 1)
        
        # Verify the query and parameter
        call_args = self.mock_cursor.execute.call_args
        sql = call_args[0][0]
        params = call_args[0][1]
        
        self.assertIn("metadata->>'agent_classified'", sql)
        self.assertIn("email IS NOT NULL", sql)
        self.assertEqual(params, (5,))

    def test_update_agent_classification_int_id(self):
        """test updating by integer database ID"""
        self.repo.update_agent_classification(job_id=123, passed_filters=True, relevance="relevant")
        
        # Verify cursor execution
        call_args = self.mock_cursor.execute.call_args
        sql = call_args[0][0]
        params = call_args[0][1]
        
        self.assertIn("WHERE id = %s", sql)
        self.assertEqual(params[0], "relevant")
        self.assertEqual(params[1], True)
        self.assertEqual(params[2], 123)
        self.mock_conn.commit.assert_called_once()

    def test_update_agent_classification_str_id(self):
        """test updating by string job_id"""
        self.repo.update_agent_classification(job_id="telegram_123_456", passed_filters=False)
        
        # Verify cursor execution
        call_args = self.mock_cursor.execute.call_args
        sql = call_args[0][0]
        params = call_args[0][1]
        
        self.assertIn("WHERE job_id = %s", sql)
        self.assertEqual(params[0], "irrelevant") # Default when passed_filters=False
        self.assertEqual(params[1], False)
        self.assertEqual(params[2], "telegram_123_456")
        self.mock_conn.commit.assert_called_once()


class TestAgentExportEndpoint(unittest.TestCase):
    """Test the POST /api/ai-agent/export Flask endpoint"""

    @classmethod
    def setUpClass(cls):
        cls.mock_db = MagicMock()
        
        # Patch Database module during import of web_server
        with patch("database.Database", return_value=cls.mock_db):
            import web_server
            cls.web_server = web_server
            cls.web_server.db = cls.mock_db
            cls.web_server.app.config["TESTING"] = True
            cls.client = cls.web_server.app.test_client()

    def setUp(self):
        self.mock_db.reset_mock()

    def test_export_unauthorized(self):
        """Return 401 when API Key is missing or invalid"""
        resp = self.client.post("/api/ai-agent/export", json={})
        self.assertEqual(resp.status_code, 401)
        
        resp = self.client.post(
            "/api/ai-agent/export",
            headers={"X-API-Key": "wrong-key"},
            json={}
        )
        self.assertEqual(resp.status_code, 401)

    def test_export_missing_webhook(self):
        """Return 400 when no webhook URL is configured/provided"""
        with patch.dict(os.environ, {"AI_AGENT_WEBHOOK_URL": ""}):
            resp = self.client.post(
                "/api/ai-agent/export",
                headers={"X-API-Key": "test-secret-key"},
                json={}
            )
            self.assertEqual(resp.status_code, 400)
            self.assertIn("AI_AGENT_WEBHOOK_URL is not configured", resp.get_json()["error"])

    def test_export_no_pending_jobs(self):
        """Return 200 with success status and 0 jobs processed when no jobs match"""
        self.mock_db.jobs.get_jobs_for_agent_classification.return_value = []
        
        resp = self.client.post(
            "/api/ai-agent/export",
            headers={"X-API-Key": "test-secret-key"},
            json={"webhook_url": "https://example.com/webhook"}
        )
        self.assertEqual(resp.status_code, 200)
        res_data = resp.get_json()
        self.assertEqual(res_data["status"], "success")
        self.assertEqual(res_data["total_processed"], 0)
        self.assertEqual(res_data["batches_sent"], 0)

    @patch("web_server.requests.post")
    def test_export_success_flow(self, mock_post):
        """Test successful fetch, batching, push to webhook, and DB update"""
        # 1. Setup mock jobs
        mock_jobs = [
            {
                "id": idx,
                "job_id": f"job_{idx}",
                "company_name": f"Company {idx}",
                "job_role": f"Role {idx}",
                "email": f"email_{idx}@test.com",
                "salary": "$100k",
                "jd_text": "Sample description",
                "metadata": {}
            }
            for idx in range(1, 13) # 12 jobs (creates 2 batches of size 10)
        ]
        self.mock_db.jobs.get_jobs_for_agent_classification.return_value = mock_jobs
        
        # 2. Setup mock response for requests.post
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        # Simulated agent result payload: returns classification results
        mock_resp.json.side_effect = [
            {
                "results": [
                    {"id": idx, "passed_filters": True, "relevance": "relevant"}
                    for idx in range(1, 11)
                ]
            },
            {
                "results": [
                    {"id": idx, "passed_filters": False, "relevance": "irrelevant"}
                    for idx in range(11, 13)
                ]
            }
        ]
        mock_post.return_value = mock_resp
        
        # 3. Call endpoint
        resp = self.client.post(
            "/api/ai-agent/export",
            headers={"X-API-Key": "test-secret-key"},
            json={
                "webhook_url": "https://example.com/webhook",
                "limit": 20,
                "batch_size": 10
            }
        )
        
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertEqual(data["status"], "success")
        self.assertEqual(data["total_processed"], 12)
        self.assertEqual(data["batches_sent"], 2)
        
        # 4. Verify post mock was called twice (two batches)
        self.assertEqual(mock_post.call_count, 2)
        
        # Verify first batch had 10 jobs
        first_call_args = mock_post.call_args_list[0]
        self.assertEqual(len(first_call_args[1]["json"]["jobs"]), 10)
        
        # Verify second batch had 2 jobs
        second_call_args = mock_post.call_args_list[1]
        self.assertEqual(len(second_call_args[1]["json"]["jobs"]), 2)
        
        # 5. Verify database update calls
        self.assertEqual(self.mock_db.jobs.update_agent_classification.call_count, 12)
        # Verify arguments of one of the update calls
        self.mock_db.jobs.update_agent_classification.assert_any_call(1, True, "relevant")
        self.mock_db.jobs.update_agent_classification.assert_any_call(12, False, "irrelevant")

    @patch("web_server.requests.post")
    def test_export_webhook_failure(self, mock_post):
        """Ensure endpoint gracefully logs and reports webhook HTTP/network errors"""
        mock_jobs = [
            {"id": 1, "job_id": "j1", "company_name": "C1", "job_role": "R1", "email": "e1@c1.com", "salary": "", "jd_text": "jd", "metadata": {}}
        ]
        self.mock_db.jobs.get_jobs_for_agent_classification.return_value = mock_jobs
        
        # Simulate network error
        import requests
        mock_post.side_effect = requests.RequestException("Connection refused")
        
        resp = self.client.post(
            "/api/ai-agent/export",
            headers={"X-API-Key": "test-secret-key"},
            json={"webhook_url": "https://example.com/webhook"}
        )
        
        self.assertEqual(resp.status_code, 200) # Returns 200 but details trace the error
        data = resp.get_json()
        self.assertEqual(data["status"], "success")
        self.assertEqual(data["batches_sent"], 0)
        self.assertEqual(len(data["details"]), 1)
        self.assertEqual(data["details"][0]["status"], "error")
        self.assertIn("Webhook request failed", data["details"][0]["message"])


if __name__ == "__main__":
    unittest.main()
