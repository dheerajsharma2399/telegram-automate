# API Documentation - Telegram Automate Dashboard

This document provides a comprehensive specification of all API endpoints available on the Telegram Automate Dashboard. 

**Base URL**: `https://job.mooh.me`

---

## Authentication

Most endpoints require authentication.
- **Header Authentication**: Provide the header `X-API-Key: <YOUR_API_KEY>`
- **Query Parameter Fallback**: Provide `?api_key=<YOUR_API_KEY>` in the request URL.

---

## Table of Contents
1. [Core & System Status](#1-core--system-status)
2. [Bot & Telegram Session Management](#2-bot--telegram-session-management)
3. [Monitored Groups Management](#3-monitored-groups-management)
4. [Command & Processing Queue](#4-command--processing-queue)
5. [Job Repository & Dashboard Operations](#5-job-repository--dashboard-operations)
6. [Email Generation & Application Agent](#6-email-generation--application-agent)
7. [AI Agent Integration (Job Classification API)](#7-ai-agent-integration-job-classification-api)

---

## 1. Core & System Status

### GET /health
Checks basic process health and verifies if the web server is listening.
* **Authentication**: None required.
* **Response (200 OK)**:
  ```json
  {
    "status": "ok",
    "http_port_9501": "listening"
  }
  ```

### GET /api/status
Get current execution status of the system.
* **Authentication**: None required.
* **Response (200 OK)**:
  ```json
  {
    "status": "running"
  }
  ```

---

## 2. Bot & Telegram Session Management

### POST /api/bot/force_restart
Forcefully kills and restarts the bot process.
* **Authentication**: Required (`X-API-Key`).
* **Response (200 OK)**:
  ```json
  {
    "status": "success",
    "message": "Restart signal sent"
  }
  ```

### POST /api/telegram/setup
Initialize the Telegram Client with API details.
* **Authentication**: Required (`X-API-Key`).
* **Request Body**:
  ```json
  {
    "api_id": "12345",
    "api_hash": "abcdef1234567890",
    "phone": "+1234567890"
  }
  ```
* **Response (200 OK)**:
  ```json
  {
    "status": "success",
    "message": "Configuration saved. Please request sign in."
  }
  ```

### POST /api/telegram/signin
Submit credentials or verification code for signing in to Telegram.
* **Authentication**: Required (`X-API-Key`).
* **Request Body**:
  ```json
  {
    "code": "12345",      // Optional: OTP received on Telegram/SMS
    "password": "pass"    // Optional: 2FA password if enabled
  }
  ```
* **Response (200 OK)**:
  * *If OTP code is required*:
    ```json
    {
      "status": "code_required",
      "message": "Verification code required"
    }
    ```
  * *If Password (2FA) is required*:
    ```json
    {
      "status": "password_required",
      "message": "2FA password required"
    }
    ```
  * *If Sign-in succeeded*:
    ```json
    {
      "status": "success",
      "message": "Signed in successfully"
    }
    ```

### POST /api/telegram/clear_session
Clears active Telegram session files and forces sign-out.
* **Authentication**: Required (`X-API-Key`).
* **Response (200 OK)**:
  ```json
  {
    "status": "success",
    "message": "Session cleared"
  }
  ```

### GET /api/telegram/status
Check the connection and authorization status of the Telegram Client.
* **Authentication**: None required.
* **Response (200 OK)**:
  ```json
  {
    "authenticated": true,
    "phone": "+1234567890",
    "connected": true
  }
  ```

### POST /api/fetch_historical_messages
Command the bot worker to scrape historical messages from a channel.
* **Authentication**: Required (`X-API-Key`).
* **Request Body**:
  ```json
  {
    "group_username": "channel_username",
    "hours": 24
  }
  ```
* **Response (200 OK)**:
  ```json
  {
    "status": "success",
    "message": "Historical fetch task queued"
  }
  ```

---

## 3. Monitored Groups Management

### GET /api/monitored_groups
List all Telegram channels/groups currently monitored by the bot.
* **Authentication**: None required.
* **Response (200 OK)**:
  ```json
  [
    {
      "id": 1,
      "group_username": "monitored_channel",
      "display_name": "Tech Jobs Channel",
      "is_active": true
    }
  ]
  ```

### POST /api/monitored_groups
Add a new Telegram channel or group to the monitor list.
* **Authentication**: Required (`X-API-Key`).
* **Request Body**:
  ```json
  {
    "group_username": "new_channel_username"
  }
  ```
* **Response (200 OK)**:
  ```json
  {
    "status": "success",
    "message": "Group added successfully"
  }
  ```

### DELETE /api/monitored_groups
Remove a group from the monitor list.
* **Authentication**: Required (`X-API-Key`).
* **Request Body**:
  ```json
  {
    "group_username": "channel_username"
  }
  ```
* **Response (200 OK)**:
  ```json
  {
    "status": "success",
    "message": "Group removed successfully"
  }
  ```

---

## 4. Command & Processing Queue

### GET /api/pending_commands
Get all pending system background commands (e.g. Scrapers, Sync task runs).
* **Authentication**: None required.
* **Response (200 OK)**:
  ```json
  [
    {
      "id": 1,
      "command": "fetch_historical",
      "payload": "{\"group\":\"chan\",\"hours\":24}",
      "status": "pending",
      "created_at": "2026-05-21T12:00:00Z"
    }
  ]
  ```

### POST /api/command/<int:cmd_id>/cancel
Cancel a pending command.
* **Authentication**: Required (`X-API-Key`).
* **Response (200 OK)**:
  ```json
  {
    "status": "success",
    "message": "Command 1 cancelled"
  }
  ```

### POST /api/command
Queue a new background worker command.
* **Authentication**: Required (`X-API-Key`).
* **Request Body**:
  ```json
  {
    "command": "sync_sheets", // e.g. "sync_sheets", "fetch_historical", etc.
    "payload": {}
  }
  ```
* **Response (200 OK)**:
  ```json
  {
    "status": "success",
    "command_id": 42
  }
  ```

---

## 5. Job Repository & Dashboard Operations

### GET /api/dashboard/jobs
Query jobs with full pagination, search, and relevance filters.
* **Authentication**: None required.
* **Query Parameters**:
  * `page` (default: 1)
  * `page_size` (default: 50)
  * `search` (optional search keyword)
  * `relevance` (optional: `relevant`, `irrelevant`, `unclassified`)
  * `status` (optional: `pending`, `queued`, `applied`, `rejected`, etc.)
  * `has_email` (optional: `true`, `false`)
* **Response (200 OK)**:
  ```json
  {
    "jobs": [
      {
        "id": 12,
        "job_id": "tg_hash_1",
        "company_name": "Acme Inc.",
        "job_role": "Backend dev",
        "email": "hiring@acme.com",
        "salary": "$80k - $100k",
        "location": "Remote",
        "jd_text": "Looking for...",
        "job_relevance": "relevant",
        "status": "pending",
        "is_hidden": false,
        "is_duplicate": false,
        "created_at": "2026-05-21T10:00:00Z"
      }
    ],
    "total_count": 1,
    "page": 1,
    "page_size": 50,
    "total_pages": 1
  }
  ```

### POST /api/dashboard/jobs
Insert a new job opportunity manually.
* **Authentication**: Required (`X-API-Key`).
* **Request Body**:
  ```json
  {
    "job_id": "manual_12345",
    "company_name": "Google",
    "job_role": "SRE",
    "email": "careers@google.com",
    "salary": "$200k",
    "location": "NYC",
    "jd_text": "Detailed description...",
    "recruiter_name": "Jane Doe"
  }
  ```
* **Response (201 Created)**:
  ```json
  {
    "status": "success",
    "job_id": "manual_12345"
  }
  ```

### PATCH /api/dashboard/jobs/<int:job_id>
Update specific properties (like relevance, status, notes) of a job.
* **Authentication**: Required (`X-API-Key`).
* **Request Body**: Any of:
  ```json
  {
    "job_relevance": "relevant",
    "status": "applied",
    "is_hidden": false,
    "is_duplicate": false
  }
  ```
* **Response (200 OK)**:
  ```json
  {
    "status": "success",
    "message": "Job 12 updated"
  }
  ```

### POST /api/dashboard/jobs/bulk_update
Update status or archive/hide state for multiple jobs at once.
* **Authentication**: Required (`X-API-Key`).
* **Request Body**:
  ```json
  {
    "job_ids": [12, 13, 14],
    "status": "rejected", // Optional
    "archive": true       // Optional (marks as hidden)
  }
  ```
* **Response (200 OK)**:
  ```json
  {
    "status": "success",
    "updated_rows": 3
  }
  ```

### POST /api/dashboard/jobs/archive_older_than
Archives (hides) jobs older than a specified number of days.
* **Authentication**: Required (`X-API-Key`).
* **Request Body**:
  ```json
  {
    "days": 30
  }
  ```
* **Response (200 OK)**:
  ```json
  {
    "status": "success",
    "archived_count": 15
  }
  ```

### POST /api/dashboard/import
Manually parse raw job message text using LLM processor and insert into the database.
* **Authentication**: Required (`X-API-Key`).
* **Request Body**:
  ```json
  {
    "message_text": "Hiring remote developers at Stripe! Email us: devs@stripe.com"
  }
  ```
* **Response (200 OK)**:
  ```json
  {
    "status": "success",
    "job": {
      "company_name": "Stripe",
      "job_role": "Developer",
      "email": "devs@stripe.com",
      "relevance": "relevant"
    }
  }
  ```

### GET /api/dashboard/duplicates
Fetch list of potential duplicate job postings.
* **Authentication**: None required.
* **Response (200 OK)**:
  ```json
  [
    {
      "id": 45,
      "company_name": "Acme",
      "job_role": "Backend"
    }
  ]
  ```

### POST /api/dashboard/duplicates/<int:job_id>
Mark a job as duplicate manually.
* **Authentication**: Required (`X-API-Key`).
* **Response (200 OK)**:
  ```json
  {
    "status": "success",
    "message": "Job marked as duplicate"
  }
  ```

### POST /api/dashboard/detect_duplicates
Run automatic duplicate detection logic on database.
* **Authentication**: Required (`X-API-Key`).
* **Response (200 OK)**:
  ```json
  {
    "status": "success",
    "duplicates_found": 3
  }
  ```

### GET /api/dashboard/jobs/export
Retrieve all active jobs.
* **Authentication**: None required.
* **Query Parameters**:
  * `format` (default: `csv`)
* **Response (200 OK)**: JSON array of job objects.

### GET /api/dashboard/stats
Get numerical statistics on relevance and application statuses.
* **Authentication**: None required.
* **Response (200 OK)**:
  ```json
  {
    "total_jobs": 1500,
    "by_status": {
      "pending": 200,
      "applied": 1300
    },
    "by_relevance": {
      "relevant": 400,
      "irrelevant": 1100
    }
  }
  ```

### GET /api/dashboard/jobs/<int:job_id>/message
Get job details alongside raw Telegram message source if available.
* **Authentication**: None required.
* **Response (200 OK)**:
  ```json
  {
    "job": { ... },
    "raw_message": {
      "id": 99,
      "message_text": "...",
      "sent_at": "2026-05-21T09:00:00"
    }
  }
  ```

### POST /api/sheets/advanced_sync
Forces a background sync of database job statuses and new records with configured Google Sheets.
* **Authentication**: Required (`X-API-Key`).
* **Response (200 OK)**:
  ```json
  {
    "status": "success",
    "message": "Advanced Google Sheets synchronization initiated."
  }
  ```

---

## 6. Email Generation & Application Agent

These endpoints are managed by the Apply blueprint and are prefixed with `/apply`.

### GET /apply/api/jobs
Gets the 100 most recent active jobs that have an email and are synced to Google Sheets.
* **Authentication**: Required (`X-API-Key`).
* **Response (200 OK)**:
  ```json
  {
    "jobs": [
      {
        "id": 1,
        "job_id": "job_hash_1",
        "company_name": "ACME Corp",
        "job_role": "Python dev",
        "email": "jobs@acme.com",
        "apply_status": "pending",
        "created_at": "2026-05-21T09:00:00Z"
      }
    ]
  }
  ```

### GET /apply/api/profiles
List available applicant profiles (`.json` format) stored on the server.
* **Authentication**: Required (`X-API-Key`).
* **Response (200 OK)**:
  ```json
  {
    "profiles": [
      {
        "filename": "user_profile.json",
        "label": "user_profile.json (default)"
      }
    ],
    "default": "user_profile.json"
  }
  ```

### POST /apply/api/profiles
Upload a new candidate profile JSON file. Max size 500KB.
* **Authentication**: Required (`X-API-Key`).
* **Form Data**:
  * `file`: File upload (`.json` extension)
* **Response (200 OK)**:
  ```json
  {
    "saved": true,
    "filename": "custom_profile.json"
  }
  ```

### POST /apply/api/generate
Trigger background email draft generation comparing job description with candidate profile.
* **Authentication**: Required (`X-API-Key`).
* **Request Body**:
  ```json
  {
    "job_id": "job_hash_1",
    "profile_filename": "user_profile.json"
  }
  ```
* **Response (200 OK)**:
  ```json
  {
    "run_id": "7f8b9c1d",
    "status": "running"
  }
  ```

### GET /apply/api/runs/<run_id>
Check status and retrieve results of a background generation run.
* **Authentication**: Required (`X-API-Key`).
* **Response (200 OK)**:
  * *If status is Done*:
    ```json
    {
      "run_id": "7f8b9c1d",
      "job_id": "job_hash_1",
      "status": "done",
      "email_subject": "Draft Subject",
      "email_body": "<p>Draft body in HTML format</p>",
      "tokens_used": 1500,
      "model_used": "anthropic/claude-3.5-sonnet",
      "error_message": null,
      "created_at": "2026-05-21T10:05:00Z"
    }
    ```

### POST /apply/api/runs/<run_id>/approve
Approve draft email. Writes the subject and HTML body back to Google Sheets columns L and M, sets column N status to `DRAFTED`, and sets database job `apply_status` to `'queued'`.
* **Authentication**: Required (`X-API-Key`).
* **Request Body**:
  ```json
  {
    "email_subject": "Approved Subject Line",
    "email_body": "<p>Approved Body HTML</p>"
  }
  ```
* **Response (200 OK)**:
  ```json
  {
    "approved": true,
    "job_id": "job_hash_1",
    "sheet_updated": true
  }
  ```

---

## 7. AI Agent Integration (Job Classification API)

### POST /api/ai-agent/export
Pushes batches of pending jobs with email addresses to an external AI Agent (e.g. Hermes) for relevance classification.
* **Authentication**: Required (`X-API-Key`).
* **Request Body**:
  ```json
  {
    "webhook_url": "https://your-vps-ip:port/webhook", // Optional. Defaults to server's AI_AGENT_WEBHOOK_URL env var
    "limit": 20,                                      // Optional. Max jobs to fetch (default: 10)
    "batch_size": 10                                   // Optional. Size of each batch (default: 10)
  }
  ```
* **Response (200 OK)**:
  ```json
  {
    "status": "success",
    "total_processed": 12,
    "batches_sent": 2,
    "details": [
      {
        "identifier": 1,
        "status": "classified",
        "passed_filters": true,
        "relevance": "relevant"
      },
      ...
    ]
  }
  ```
