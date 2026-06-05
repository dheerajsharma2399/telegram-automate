---
name: telegram-automate-mcp
description: >-
  Use when an agent needs to operate the Telegram Automate project through its
  FastMCP server: inspect service/Telegram status, poll or filter dashboard
  jobs, fetch recent Telegram messages, process the raw-message queue, sync
  Google Sheets, or debug MCP/API control paths without bypassing the existing
  Flask API layer.
---

# Telegram Automate MCP

## Purpose

Use `mcp_server.py` as the control plane for Telegram Automate. The MCP layer is intentionally thin: every tool calls the existing Flask API so authorization, validation, and business rules stay centralized in `web_server.py` and the repositories.

## Connection

Run the Flask API first, then run the MCP server with stdio:

```bash
python3 mcp_server.py
```

Alternative FastMCP CLI entrypoint:

```bash
fastmcp run mcp_server.py:mcp
```

Expected environment:

```bash
TELEGRAM_AUTOMATE_API_BASE_URL=http://127.0.0.1:9501
API_KEY=<same key used by the Flask API, when configured>
```

`TELEGRAM_AUTOMATE_API_KEY` is accepted as a fallback if `API_KEY` is not set.

## Tool Reference

Use these MCP tools instead of direct database access:

| Tool | Purpose | Wrapped API route |
|---|---|---|
| `get_status()` | Read monitoring status, queue count, job stats, Telegram auth state | `GET /api/status` |
| `list_jobs(...)` | Query dashboard jobs with pagination and filters | `GET /api/dashboard/jobs` |
| `get_new_jobs(...)` | Poll newest jobs sorted by `updated_at DESC` | `GET /api/dashboard/jobs` |
| `fetch_historical_messages(hours_back=12)` | Fetch recent Telegram messages and process them into jobs | `POST /api/fetch_historical_messages` |
| `process_queue()` | Enqueue `/process` for the worker | `POST /api/command` |
| `sync_sheets()` | Enqueue `/sync_sheets` for the worker | `POST /api/command` |
| `list_queue(limit=50)` | Read unprocessed raw Telegram messages | `GET /api/queue` |
| `list_pending_commands()` | Read worker command queue | `GET /api/pending_commands` |
| `get_telegram_status()` | Read Telegram session/login state | `GET /api/telegram/status` |

`list_jobs` arguments:

```python
page: int = 1
page_size: int = 50
status: str | None = None
relevance: "relevant" | "irrelevant" | "unclassified" | None = None
job_role: str | None = None
has_email: bool | None = None
include_archived: bool = False
sort_by: "created_at" | "updated_at" | "job_role" | "company_name" | "status" | "job_relevance" | "id" = "created_at"
sort_order: "ASC" | "DESC" = "DESC"
```

`get_new_jobs` arguments:

```python
limit: int = 50
has_email: bool | None = None
status: str | None = None
relevance: "relevant" | "irrelevant" | "unclassified" | None = None
```

## Workflows

### Check System Health

1. Call `get_status()`.
2. Call `get_telegram_status()` if Telegram auth/session details are needed.
3. Call `list_pending_commands()` when a control action appears queued but not executed.

### Poll New Jobs

1. Call `get_new_jobs(limit=50)` for the newest jobs.
2. Use `has_email=False` when looking for link-only/non-email jobs.
3. Use `status` and `relevance` filters only when the user asks for a narrower subset.
4. Keep client-side state keyed by `id` or `job_id`; this API has no `updated_since` cursor yet.

### Fetch Fresh Telegram Jobs

1. Call `get_telegram_status()` and confirm there is an active/connected session.
2. Call `fetch_historical_messages(hours_back=<0.1..168>)`.
3. Call `get_status()` and/or `list_queue()` to inspect resulting queue state.
4. Call `get_new_jobs()` to inspect newly created jobs.

### Process Existing Queue

1. Call `list_queue()` to confirm raw messages are waiting.
2. Call `process_queue()`; this enqueues `/process` with the leading slash required by the worker.
3. Call `list_pending_commands()` to confirm the command was queued.
4. Poll `get_status()` and `get_new_jobs()` for results.

### Sync Sheets

1. Call `sync_sheets()` only when the user wants Google Sheets updated.
2. Call `list_pending_commands()` to confirm `/sync_sheets` is queued.
3. Do not assume Sheets is configured; failed API responses should be reported directly.

## Safety Rules

- Do not bypass MCP/API tools to mutate PostgreSQL directly unless the user explicitly asks for database-level repair.
- Treat `fetch_historical_messages`, `process_queue`, and `sync_sheets` as side-effectful actions.
- Preserve API-key behavior: set `API_KEY` or `TELEGRAM_AUTOMATE_API_KEY` for protected routes when the Flask API requires authentication.
- Keep the Flask API running separately; the MCP server does not start `web_server.py`.
- Report wrapped API errors as API errors, not MCP server failures, unless `mcp_server.py` itself fails to load or connect.

## Verification

For local validation after MCP changes:

```bash
python3 -m unittest tests.test_mcp_server
python3 -m py_compile mcp_server.py tests/test_mcp_server.py
```

When FastMCP is installed, use FastMCP client inspection to verify the tool list.
