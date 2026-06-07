#!/usr/bin/env python3
"""
FastMCP server for the Telegram Automate HTTP API.

The MCP layer intentionally stays thin: every tool calls the existing Flask API
so authorization, validation, and business rules remain centralized there.
"""
import json
import os
from typing import Any, Dict, Literal, Optional
from urllib import error, parse, request

from fastmcp import FastMCP


API_BASE_URL = os.getenv("TELEGRAM_AUTOMATE_API_BASE_URL", "http://127.0.0.1:9501").rstrip("/")
API_KEY = os.getenv("API_KEY") or os.getenv("TELEGRAM_AUTOMATE_API_KEY")

mcp = FastMCP(name="telegram-automate")

JobRelevance = Literal["relevant", "irrelevant", "unclassified"]
SortBy = Literal["created_at", "updated_at", "job_role", "company_name", "status", "job_relevance", "id"]
SortOrder = Literal["ASC", "DESC"]


class ApiError(Exception):
    """Raised when the wrapped HTTP API returns an error."""

    def __init__(self, message: str, status: Optional[int] = None, payload: Any = None):
        super().__init__(message)
        self.status = status
        self.payload = payload


def _headers() -> Dict[str, str]:
    headers = {"Accept": "application/json"}
    if API_KEY:
        headers["X-API-Key"] = API_KEY
    return headers


def _decode_response(raw: bytes, content_type: str) -> Any:
    text = raw.decode("utf-8", errors="replace")
    if "application/json" in content_type:
        return json.loads(text) if text else None
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return text


def api_request(method: str, path: str, params: Optional[Dict[str, Any]] = None, body: Any = None) -> Any:
    """Call the existing Flask API and decode JSON responses."""
    query_params = {key: value for key, value in (params or {}).items() if value is not None}
    query = parse.urlencode(query_params)
    url = f"{API_BASE_URL}{path}"
    if query:
        url = f"{url}?{query}"

    payload = None
    headers = _headers()
    if body is not None:
        payload = json.dumps(body).encode("utf-8")
        headers["Content-Type"] = "application/json"

    req = request.Request(url, data=payload, headers=headers, method=method.upper())
    try:
        with request.urlopen(req, timeout=60) as response:
            return _decode_response(response.read(), response.headers.get("Content-Type", ""))
    except error.HTTPError as exc:
        payload = _decode_response(exc.read(), exc.headers.get("Content-Type", ""))
        message = payload.get("error") if isinstance(payload, dict) else str(payload)
        raise ApiError(message or f"HTTP {exc.code}", status=exc.code, payload=payload) from exc
    except error.URLError as exc:
        raise ApiError(f"Could not reach Telegram Automate API at {API_BASE_URL}: {exc.reason}") from exc


def _bool_param(value: Optional[bool]) -> Optional[str]:
    if value is None:
        return None
    return "true" if value else "false"


@mcp.tool(annotations={"readOnlyHint": True, "openWorldHint": True})
def get_status() -> Dict[str, Any]:
    """Get system status, queue count, job stats, and Telegram auth state."""
    return api_request("GET", "/api/status")


@mcp.tool(annotations={"readOnlyHint": True, "openWorldHint": True})
def list_jobs(
    page: int = 1,
    page_size: int = 50,
    status: Optional[str] = None,
    relevance: Optional[JobRelevance] = None,
    job_role: Optional[str] = None,
    has_email: Optional[bool] = None,
    include_archived: bool = False,
    sort_by: SortBy = "created_at",
    sort_order: SortOrder = "DESC",
) -> Dict[str, Any]:
    """List dashboard jobs with pagination and filters."""
    return api_request(
        "GET",
        "/api/dashboard/jobs",
        {
            "page": page,
            "page_size": page_size,
            "status": status,
            "relevance": relevance,
            "job_role": job_role,
            "has_email": _bool_param(has_email),
            "include_archived": _bool_param(include_archived),
            "sort_by": sort_by,
            "sort_order": sort_order,
        },
    )


@mcp.tool(annotations={"readOnlyHint": True, "openWorldHint": True})
def get_new_jobs(
    limit: int = 50,
    has_email: Optional[bool] = None,
    status: Optional[str] = None,
    relevance: Optional[JobRelevance] = None,
) -> Dict[str, Any]:
    """Fetch the newest dashboard jobs, sorted by updated_at descending."""
    return api_request(
        "GET",
        "/api/dashboard/jobs",
        {
            "page": 1,
            "page_size": limit,
            "status": status,
            "relevance": relevance,
            "has_email": _bool_param(has_email),
            "sort_by": "updated_at",
            "sort_order": "DESC",
        },
    )


@mcp.tool(annotations={"readOnlyHint": False, "idempotentHint": False, "openWorldHint": True})
def fetch_historical_messages(hours_back: float = 12, enqueue_process: bool = True) -> Dict[str, Any]:
    """Fetch recent Telegram messages through the API, optionally enqueueing processing."""
    return api_request(
        "POST",
        "/api/fetch_historical_messages",
        body={"hours_back": hours_back, "enqueue_process": enqueue_process},
    )


@mcp.tool(annotations={"readOnlyHint": False, "idempotentHint": False, "openWorldHint": True})
def process_queue() -> Dict[str, Any]:
    """Ask the worker to process the raw-message queue."""
    return api_request("POST", "/api/command", body={"command": "/process"})


@mcp.tool(annotations={"readOnlyHint": False, "idempotentHint": False, "openWorldHint": True})
def sync_sheets() -> Dict[str, Any]:
    """Ask the worker to sync jobs to Google Sheets."""
    return api_request("POST", "/api/command", body={"command": "/sync_sheets"})


@mcp.tool(annotations={"readOnlyHint": True, "openWorldHint": True})
def list_queue(limit: int = 50) -> Any:
    """List unprocessed raw Telegram messages."""
    return api_request("GET", "/api/queue", {"limit": limit})


@mcp.tool(annotations={"readOnlyHint": True, "openWorldHint": True})
def list_pending_commands() -> Any:
    """List commands waiting for the worker."""
    return api_request("GET", "/api/pending_commands")


@mcp.tool(annotations={"readOnlyHint": True, "openWorldHint": True})
def get_telegram_status() -> Dict[str, Any]:
    """Get Telegram login/session status."""
    return api_request("GET", "/api/telegram/status")


if __name__ == "__main__":
    mcp.run()
