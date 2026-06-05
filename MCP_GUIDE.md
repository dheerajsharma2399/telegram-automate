# Telegram Automate MCP Guide

This project exposes a FastMCP server in `mcp_server.py`. The MCP server is a thin control layer over the existing Flask API; it does not access PostgreSQL directly.

## Start the MCP Server

Start the Flask API first:

```bash
python3 web_server.py
```

Then start the MCP server over stdio:

```bash
python3 mcp_server.py
```

FastMCP CLI alternative:

```bash
fastmcp run mcp_server.py:mcp
```

Environment:

```bash
TELEGRAM_AUTOMATE_API_BASE_URL=http://127.0.0.1:9501
API_KEY=your_api_key_if_configured
# fallback: TELEGRAM_AUTOMATE_API_KEY=your_api_key_if_configured
```

## MCP Server Definition

The server object is:

```python
from fastmcp import FastMCP

mcp = FastMCP(name="telegram-automate")
```

The local MCP client config is in `.mcp.json`:

```json
{
  "mcpServers": {
    "telegram-automate": {
      "command": "python3",
      "args": ["mcp_server.py"],
      "env": {
        "TELEGRAM_AUTOMATE_API_BASE_URL": "http://127.0.0.1:9501"
      }
    }
  }
}
```

## Tool Definitions

| Tool | Arguments | Purpose | API route |
|---|---|---|---|
| `get_status` | none | Read monitoring status, queue count, job stats, Telegram auth state | `GET /api/status` |
| `list_jobs` | `page`, `page_size`, `status`, `relevance`, `job_role`, `has_email`, `include_archived`, `sort_by`, `sort_order` | Query dashboard jobs with filters | `GET /api/dashboard/jobs` |
| `get_new_jobs` | `limit`, `has_email`, `status`, `relevance` | Fetch newest jobs sorted by `updated_at DESC` | `GET /api/dashboard/jobs` |
| `fetch_historical_messages` | `hours_back` | Fetch recent Telegram messages and process them into jobs | `POST /api/fetch_historical_messages` |
| `process_queue` | none | Enqueue `/process` for the worker | `POST /api/command` |
| `sync_sheets` | none | Enqueue `/sync_sheets` for the worker | `POST /api/command` |
| `list_queue` | `limit` | Read unprocessed raw Telegram messages | `GET /api/queue` |
| `list_pending_commands` | none | Read worker command queue | `GET /api/pending_commands` |
| `get_telegram_status` | none | Read Telegram login/session state | `GET /api/telegram/status` |

`list_jobs` accepted filter values:

```text
relevance: relevant | irrelevant | unclassified
sort_by: created_at | updated_at | job_role | company_name | status | job_relevance | id
sort_order: ASC | DESC
```

## Common Workflows

### Poll New Jobs

Call:

```json
{
  "name": "get_new_jobs",
  "arguments": {
    "limit": 50,
    "has_email": false
  }
}
```

Keep client-side state keyed by `id` or `job_id`; the API does not yet provide `updated_since` or a cursor.

### Fetch Fresh Telegram Messages

1. Call `get_telegram_status`.
2. If authenticated, call:

```json
{
  "name": "fetch_historical_messages",
  "arguments": {
    "hours_back": 6
  }
}
```

3. Call `get_new_jobs` to inspect the new processed jobs.

### Process Existing Raw Queue

1. Call `list_queue`.
2. Call `process_queue`.
3. Call `list_pending_commands` to confirm `/process` was queued.
4. Poll `get_status` and `get_new_jobs`.

### Sync Sheets

Call `sync_sheets` only when Google Sheets should be updated. This enqueues `/sync_sheets` for the worker; it does not write Sheets directly from MCP.

## Agent Skill

A project-local Codex skill is saved at:

```text
.codex/skills/telegram-automate-mcp/SKILL.md
```

Use that skill when another AI agent needs operational instructions for this MCP layer.

## Safety

- Do not mutate PostgreSQL directly through MCP; use the API-wrapped tools.
- Treat `fetch_historical_messages`, `process_queue`, and `sync_sheets` as side-effectful.
- Preserve API auth by setting `API_KEY` or `TELEGRAM_AUTOMATE_API_KEY` when needed.
- Keep the Flask API running separately; `mcp_server.py` does not start it.

## Verification

```bash
python3 -m unittest tests.test_mcp_server
python3 -m py_compile mcp_server.py tests/test_mcp_server.py
python3 /home/ubuntu/.codex/skills/.system/skill-creator/scripts/quick_validate.py .codex/skills/telegram-automate-mcp
```
