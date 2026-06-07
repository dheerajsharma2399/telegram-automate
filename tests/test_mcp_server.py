import importlib
import sys
import types
import unittest
from unittest.mock import patch


class FakeFastMCP:
    def __init__(self, name=None, **kwargs):
        self.name = name
        self.kwargs = kwargs
        self.registered_tools = []

    def tool(self, *decorator_args, **decorator_kwargs):
        def register(func):
            self.registered_tools.append({
                "name": func.__name__,
                "func": func,
                "kwargs": decorator_kwargs,
            })
            return func

        if decorator_args and callable(decorator_args[0]) and len(decorator_args) == 1 and not decorator_kwargs:
            return register(decorator_args[0])
        return register

    def run(self, *args, **kwargs):
        self.run_args = args
        self.run_kwargs = kwargs


def import_mcp_server_with_fake_fastmcp():
    fake_module = types.ModuleType("fastmcp")
    fake_module.FastMCP = FakeFastMCP
    sys.modules["fastmcp"] = fake_module
    sys.modules.pop("mcp_server", None)
    return importlib.import_module("mcp_server")


class TestFastMcpServerRegistration(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.mcp_server = import_mcp_server_with_fake_fastmcp()

    def test_server_is_named_for_project(self):
        self.assertEqual(self.mcp_server.mcp.name, "telegram-automate")

    def test_expected_tools_are_registered(self):
        tool_names = {tool["name"] for tool in self.mcp_server.mcp.registered_tools}

        self.assertIn("get_new_jobs", tool_names)
        self.assertIn("list_jobs", tool_names)
        self.assertIn("fetch_historical_messages", tool_names)
        self.assertIn("process_queue", tool_names)
        self.assertIn("sync_sheets", tool_names)
        self.assertIn("get_status", tool_names)

    def test_read_tools_have_read_only_annotations(self):
        tools = {tool["name"]: tool for tool in self.mcp_server.mcp.registered_tools}

        self.assertTrue(tools["get_new_jobs"]["kwargs"]["annotations"]["readOnlyHint"])
        self.assertTrue(tools["list_jobs"]["kwargs"]["annotations"]["readOnlyHint"])
        self.assertFalse(tools["fetch_historical_messages"]["kwargs"]["annotations"]["readOnlyHint"])


class TestMcpToolRouting(unittest.TestCase):
    def setUp(self):
        self.mcp_server = import_mcp_server_with_fake_fastmcp()

    @patch("mcp_server.api_request")
    def test_get_new_jobs_routes_to_dashboard_jobs_sorted_by_updated_at(self, mock_api_request):
        mock_api_request.return_value = {"jobs": []}

        result = self.mcp_server.get_new_jobs(limit=25, has_email=False)

        self.assertEqual(result, {"jobs": []})
        mock_api_request.assert_called_once_with(
            "GET",
            "/api/dashboard/jobs",
            {
                "page": 1,
                "page_size": 25,
                "status": None,
                "relevance": None,
                "has_email": "false",
                "sort_by": "updated_at",
                "sort_order": "DESC",
            },
        )

    @patch("mcp_server.api_request")
    def test_list_jobs_passes_filters_to_dashboard_jobs_endpoint(self, mock_api_request):
        mock_api_request.return_value = {"jobs": []}

        self.mcp_server.list_jobs(
            page=2,
            page_size=10,
            status="pending",
            relevance="relevant",
            job_role="python",
            has_email=True,
            include_archived=True,
            sort_by="company_name",
            sort_order="ASC",
        )

        mock_api_request.assert_called_once_with(
            "GET",
            "/api/dashboard/jobs",
            {
                "page": 2,
                "page_size": 10,
                "status": "pending",
                "relevance": "relevant",
                "job_role": "python",
                "has_email": "true",
                "include_archived": "true",
                "sort_by": "company_name",
                "sort_order": "ASC",
            },
        )

    @patch("mcp_server.api_request")
    def test_fetch_historical_messages_routes_to_existing_control_endpoint(self, mock_api_request):
        mock_api_request.return_value = {"status": "ok"}

        result = self.mcp_server.fetch_historical_messages(hours_back=6)

        self.assertEqual(result, {"status": "ok"})
        mock_api_request.assert_called_once_with(
            "POST",
            "/api/fetch_historical_messages",
            body={"hours_back": 6, "enqueue_process": True},
        )

    @patch("mcp_server.api_request")
    def test_process_queue_enqueues_worker_command_with_slash(self, mock_api_request):
        mock_api_request.return_value = {"command_id": 10}

        result = self.mcp_server.process_queue()

        self.assertEqual(result, {"command_id": 10})
        mock_api_request.assert_called_once_with("POST", "/api/command", body={"command": "/process"})


if __name__ == "__main__":
    unittest.main()
