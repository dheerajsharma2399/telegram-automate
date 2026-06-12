#!/usr/bin/env python3
"""
FastMCP server for the Telegram Automate HTTP API.

The MCP layer intentionally stays thin: every tool calls the existing Flask API
so authorization, validation, and business rules remain centralized there.
"""
import json
import os
from typing import Any, Dict, List, Literal, Optional
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
    headers = {
        "Accept": "application/json",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
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
    source: Optional[str] = None,
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
            "source": source,
        },
    )


@mcp.tool(annotations={"readOnlyHint": True, "openWorldHint": True})
def get_new_jobs(
    limit: int = 50,
    has_email: Optional[bool] = None,
    status: Optional[str] = None,
    relevance: Optional[JobRelevance] = None,
    source: Optional[str] = None,
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
            "source": source,
        },
    )


@mcp.tool(annotations={"readOnlyHint": True, "openWorldHint": True})
def search_leads(
    role: Optional[str] = None,
    role_category: Optional[str] = None,
    source: Optional[str] = None,
    has_email: Optional[bool] = None,
    has_link: Optional[bool] = None,
    location_hint: Optional[str] = None,
    confidence_min: Optional[float] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    keywords: Optional[str] = None,
    limit: int = 50,
    page: int = 1,
) -> Dict[str, Any]:
    """Search parsed leads with filters and full-text search keywords."""
    return api_request(
        "GET",
        "/api/leads/search",
        {
            "keywords": keywords,
            "source": source,
            "role": role,
            "role_category": role_category,
            "has_email": _bool_param(has_email),
            "has_link": _bool_param(has_link),
            "location_hint": location_hint,
            "confidence_min": confidence_min,
            "date_from": date_from,
            "date_to": date_to,
            "page": page,
            "page_size": limit,
        },
    )


@mcp.tool(annotations={"readOnlyHint": True, "openWorldHint": True})
def get_lead(lead_id: str) -> Dict[str, Any]:
    """Get full detail for a single lead."""
    return api_request("GET", f"/api/leads/{lead_id}")


@mcp.tool(annotations={"readOnlyHint": True, "openWorldHint": True})
def get_stats() -> Dict[str, Any]:
    """Leads by source, by role, by date. No user-specific data."""
    return api_request("GET", "/api/leads/stats")


@mcp.tool(annotations={"readOnlyHint": False, "idempotentHint": False, "openWorldHint": True})
def scrape_linkedin(roles: Optional[List[str]] = None) -> Dict[str, Any]:
    """Trigger LinkedIn scraper. Returns enqueued action details."""
    import typing
    return api_request("POST", "/api/scraper/trigger", body={"action": "scrape_linkedin", "roles": roles})


@mcp.tool(annotations={"readOnlyHint": False, "idempotentHint": False, "openWorldHint": True})
def fetch_telegram(hours_back: float = 12) -> Dict[str, Any]:
    """Fetch recent Telegram messages. Returns enqueued action details."""
    return api_request("POST", "/api/scraper/trigger", body={"action": "fetch_telegram", "hours_back": hours_back})


@mcp.tool(annotations={"readOnlyHint": True, "openWorldHint": True})
def get_queue_status() -> Dict[str, Any]:
    """raw_events pending, processing, failed counts."""
    stats = api_request("GET", "/api/leads/stats")
    return stats.get("queue_status", {})


@mcp.tool(annotations={"readOnlyHint": False, "idempotentHint": False, "openWorldHint": True})
def retry_failed(limit: int = 10) -> Dict[str, Any]:
    """Re-queue failed events for retry."""
    return api_request("POST", "/api/queue/retry_failed", body={"limit": limit})


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
    import sys
    transport = os.getenv("MCP_TRANSPORT", "stdio")
    is_sse = "sse" in sys.argv or transport == "sse"
    is_http = "streamable-http" in sys.argv or "http" in sys.argv or transport in ["streamable-http", "http"]
    
    if is_sse or is_http:
        port = int(os.getenv("MCP_PORT", "9502"))
        host = os.getenv("MCP_HOST", "0.0.0.0")
        selected_transport = "sse" if is_sse else "streamable-http"
        print(f"Starting FastMCP server with transport '{selected_transport}' on {host}:{port}", flush=True)
        
        from starlette.middleware import Middleware
        from starlette.requests import Request
        from starlette.responses import Response

        class ApiKeyMiddleware:
            def __init__(self, app):
                self.app = app

            async def __call__(self, scope, receive, send):
                if scope["type"] == "http":
                    request = Request(scope, receive)
                    path = request.url.path
                    
                    if path.startswith("/sse") or path.startswith("/messages") or path.startswith("/mcp"):
                        api_key = request.headers.get("x-api-key") or request.query_params.get("api_key") or request.query_params.get("apiKey")
                        expected_key = os.getenv("API_KEY")
                        
                        if not expected_key:
                            expected_key = "dash1234"
                            
                        if not api_key or api_key != expected_key:
                            response = Response("Unauthorized: Invalid or missing API Key", status_code=401)
                            await response(scope, receive, send)
                            return
                            
                        # Intercept SSE connection response to propagate api_key to client POST uri
                        if path.startswith("/sse") and api_key:
                            async def custom_send(message):
                                if message.get("type") == "http.response.body":
                                    body = message.get("body", b"")
                                    if b"event: endpoint" in body:
                                        text = body.decode("utf-8", errors="replace")
                                        import re
                                        match = re.search(r"data:\s*(\S+)", text)
                                        if match:
                                            original_url = match.group(1)
                                            if "api_key=" not in original_url and "apiKey=" not in original_url:
                                                separator = "&" if "?" in original_url else "?"
                                                new_url = f"{original_url}{separator}api_key={api_key}"
                                                text = text.replace(original_url, new_url)
                                                message["body"] = text.encode("utf-8")
                                await send(message)
                            
                            await self.app(scope, receive, custom_send)
                            return
                            
                await self.app(scope, receive, send)

        middleware = [Middleware(ApiKeyMiddleware)]
        mcp.run(transport=selected_transport, host=host, port=port, middleware=middleware)
    else:
        mcp.run()
