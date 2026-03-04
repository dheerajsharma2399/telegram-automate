"""
Playwright browser tests for the Telegram Job Scraper Bot Flask web dashboard.

Uses the sync Playwright API and spins up the Flask app on a free port in a
background thread, with the database connection mocked out so no real DB is
needed.

NOTE: config.py raises ValueError at module-level if DATABASE_URL,
TELEGRAM_API_ID/HASH or OPENROUTER_API_KEY are missing, so we inject fake
environment variables before any import of config / web_server happens.
"""

import json
import os
import sys
import socket
import threading
import time
from unittest.mock import MagicMock, patch

import pytest

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

# ---------------------------------------------------------------------------
# Inject required environment variables BEFORE any app import so that
# config.py does not raise ValueError.
# ---------------------------------------------------------------------------
_ENV_DEFAULTS = {
    "DATABASE_URL": "postgresql://fake:fake@localhost:5432/fakedb",
    "TELEGRAM_API_ID": "12345",
    "TELEGRAM_API_HASH": "fakehash",
    "TELEGRAM_PHONE": "+10000000000",
    "OPENROUTER_API_KEY": "fake-openrouter-key",
    "GOOGLE_CREDENTIALS_JSON": "",
    "SPREADSHEET_ID": "",
    "ADMIN_USER_ID": "0",
}

# ---------------------------------------------------------------------------
# Chromium executable
# ---------------------------------------------------------------------------
CHROMIUM_EXECUTABLE = (
    "/root/.cache/ms-playwright/chromium_headless_shell-1208/"
    "chrome-linux/headless_shell"
)


# ---------------------------------------------------------------------------
# Port helper
# ---------------------------------------------------------------------------

def _free_port() -> int:
    """Return a free TCP port on localhost."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


# ---------------------------------------------------------------------------
# Mock DB factory – returns a MagicMock that satisfies every attribute access
# that web_server.py does at import time and at runtime.
# ---------------------------------------------------------------------------

def _make_mock_db():
    db = MagicMock()
    # config
    db.config.get_config.return_value = "running"
    db.config.set_config.return_value = None
    # messages
    db.messages.get_unprocessed_count.return_value = 0
    db.messages.get_unprocessed_messages.return_value = []
    # jobs
    db.jobs.get_jobs_today_stats.return_value = {"total": 0, "with_email": 0, "without_email": 0}
    db.jobs.get_dashboard_jobs.return_value = {"jobs": [], "total_count": 0}
    db.jobs.get_jobs.return_value = {"jobs": [], "total_count": 0}
    db.jobs.get_stats.return_value = {
        "total_jobs": 0,
        "by_status": {},
        "by_relevance": {"relevant": 0, "irrelevant": 0},
    }
    db.jobs.get_relevance_stats.return_value = {}
    db.jobs.get_relevant_jobs.return_value = []
    db.jobs.get_irrelevant_jobs.return_value = []
    db.jobs.get_jobs_by_sheet_name.return_value = []
    db.jobs.export_jobs.return_value = []
    # auth
    db.auth.get_telegram_login_status.return_value = "not_authenticated"
    db.auth.get_telegram_session.return_value = ""
    # commands
    db.commands.list_all_pending_commands.return_value = []
    db.commands.enqueue_command.return_value = 1
    # monitored groups
    return db


# ---------------------------------------------------------------------------
# Flask app + server fixture
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def flask_base_url():
    """
    Spin up the Flask app on a free port in a background daemon thread.
    Returns the base URL string, e.g. 'http://127.0.0.1:54321'.

    The DB and several heavy dependencies are mocked at the module level so
    the app can start without a real PostgreSQL database.
    """
    port = _free_port()
    mock_db = _make_mock_db()

    # We patch at the web_server module level *before* importing the app so
    # that the Database() call at module scope is intercepted.
    patches = [
        patch("web_server.db", mock_db),
        patch("database.Database", return_value=mock_db),
        # LLMProcessor and sheets are optional
        patch("web_server.llm_processor", MagicMock()),
        patch("web_server.get_sheets_sync", return_value=None),
    ]

    for p in patches:
        p.start()

    # Import (or re-use if already imported) the Flask app *after* patching.
    from web_server import app  # noqa: PLC0415

    app.config["TESTING"] = True
    # Disable the Werkzeug reloader in the background thread
    app.config["DEBUG"] = False

    server_thread = threading.Thread(
        target=lambda: app.run(host="127.0.0.1", port=port, use_reloader=False),
        daemon=True,
    )
    server_thread.start()

    # Wait until the port is accepting connections (up to 10 s)
    deadline = time.time() + 10
    while time.time() < deadline:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.5):
                break
        except OSError:
            time.sleep(0.1)
    else:
        pytest.fail(f"Flask server did not start in time on port {port}")

    yield f"http://127.0.0.1:{port}"

    # Patches are never stopped because the thread is a daemon and pytest will
    # clean up anyway; but we stop them cleanly for correctness.
    for p in patches:
        try:
            p.stop()
        except RuntimeError:
            pass


# ---------------------------------------------------------------------------
# Playwright browser fixture
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def browser_context(flask_base_url):  # noqa: F811
    """Launch a single Chromium headless browser for the entire session."""
    from playwright.sync_api import sync_playwright  # noqa: PLC0415

    with sync_playwright() as pw:
        browser = pw.chromium.launch(
            executable_path=CHROMIUM_EXECUTABLE,
            headless=True,
        )
        context = browser.new_context()
        yield context
        context.close()
        browser.close()


@pytest.fixture()
def page(browser_context):
    """Open a fresh page for each test."""
    p = browser_context.new_page()
    yield p
    p.close()


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def goto(page, base_url: str, path: str = "/"):
    """Navigate and wait for load."""
    page.goto(f"{base_url}{path}", wait_until="domcontentloaded", timeout=15_000)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestDashboardLoads:
    """1. Verify the dashboard page loads and has the expected title / heading."""

    def test_dashboard_loads(self, page, flask_base_url):
        goto(page, flask_base_url, "/")
        # The <title> tag contains "Dashboard"
        assert "Dashboard" in page.title(), (
            f"Page title '{page.title()}' does not contain 'Dashboard'"
        )

    def test_dashboard_has_page_title_element(self, page, flask_base_url):
        goto(page, flask_base_url, "/")
        # The <h1 id="page-title"> element exists and reads "Dashboard"
        heading = page.locator("#page-title")
        assert heading.count() > 0, "Element #page-title not found on page"
        assert "Dashboard" in heading.inner_text()


class TestJobsTableRenders:
    """2. Verify the jobs table element is present in the DOM."""

    def test_jobs_table_exists(self, page, flask_base_url):
        goto(page, flask_base_url, "/")
        # #jobs-table is inside the Jobs view; it is in the DOM even when hidden.
        table = page.locator("#jobs-table")
        assert table.count() > 0, "Element #jobs-table not found in DOM"

    def test_jobs_table_has_thead(self, page, flask_base_url):
        goto(page, flask_base_url, "/")
        thead = page.locator("#jobs-table thead")
        assert thead.count() > 0, "#jobs-table has no <thead>"

    def test_jobs_table_body_exists(self, page, flask_base_url):
        goto(page, flask_base_url, "/")
        tbody = page.locator("#jobs-table-body")
        assert tbody.count() > 0, "#jobs-table-body not found"


class TestHealthEndpoint:
    """3. Verify /health returns the expected JSON payload."""

    def test_health_endpoint_returns_ok(self, page, flask_base_url):
        goto(page, flask_base_url, "/health")
        # The page body is the raw JSON response
        body = page.content()
        assert '"status"' in body, f"'status' key missing from /health response: {body}"
        assert '"ok"' in body, f"'ok' value missing from /health response: {body}"

    def test_health_endpoint_json_valid(self, page, flask_base_url):
        goto(page, flask_base_url, "/health")
        # Grab inner text (the JSON string) and parse it
        raw = page.locator("body").inner_text()
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            pytest.fail(f"/health body is not valid JSON: {raw!r}")
        assert data.get("status") == "ok", f"Expected status=='ok', got: {data}"


class TestNoNotesUI:
    """4. Verify there is NO notes-related UI on the main dashboard page."""

    def test_no_notes_id_element(self, page, flask_base_url):
        goto(page, flask_base_url, "/")
        # No element with id="notes"
        assert page.locator("#notes").count() == 0, (
            "Unexpected element with id='notes' found on the page"
        )

    def test_no_notes_class_element(self, page, flask_base_url):
        goto(page, flask_base_url, "/")
        # No element with class containing "notes"
        assert page.locator(".notes").count() == 0, (
            "Unexpected element with class='notes' found on the page"
        )

    def test_no_data_notes_attribute(self, page, flask_base_url):
        goto(page, flask_base_url, "/")
        assert page.locator("[data-notes]").count() == 0, (
            "Unexpected element with data-notes attribute found on the page"
        )

    def test_no_edit_notes_button(self, page, flask_base_url):
        goto(page, flask_base_url, "/")
        # No button whose visible text is "Edit Notes"
        edit_notes_btns = page.get_by_role("button", name="Edit Notes")
        assert edit_notes_btns.count() == 0, (
            "Unexpected 'Edit Notes' button found on the page"
        )

    def test_no_edit_notes_function_in_source(self, page, flask_base_url):
        goto(page, flask_base_url, "/")
        # The page HTML source must not contain 'editNotes'
        html = page.content()
        assert "editNotes" not in html, (
            "Found 'editNotes' function reference in page source – notes UI should not exist"
        )

    def test_old_page_no_notes_function(self, page, flask_base_url):
        """Verify old.html also has no editNotes function."""
        goto(page, flask_base_url, "/old")
        html = page.content()
        assert "editNotes" not in html, (
            "Found 'editNotes' in /old page source"
        )


class TestNoNotesApiCall:
    """5. Verify POST /api/dashboard/jobs/1/notes returns 404."""

    def test_notes_api_returns_404(self, page, flask_base_url):
        goto(page, flask_base_url, "/")
        # Use page.request to POST to the notes endpoint
        response = page.request.post(
            f"{flask_base_url}/api/dashboard/jobs/1/notes",
            data=json.dumps({"notes": "test"}),
            headers={"Content-Type": "application/json"},
        )
        assert response.status == 404, (
            f"Expected 404 for /api/dashboard/jobs/1/notes, got {response.status}"
        )

    def test_notes_api_via_fetch(self, page, flask_base_url):
        """Double-check via in-page fetch (exercises the actual Playwright API)."""
        goto(page, flask_base_url, "/")
        status = page.evaluate(
            """async (url) => {
                const res = await fetch(url, {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({notes: 'test'})
                });
                return res.status;
            }""",
            f"{flask_base_url}/api/dashboard/jobs/1/notes",
        )
        assert status == 404, (
            f"Expected 404 via fetch for /api/dashboard/jobs/1/notes, got {status}"
        )


class TestBulkUpdateUI:
    """6. Verify the bulk-update UI elements are present (index.html + old.html)."""

    def test_index_has_jobs_view(self, page, flask_base_url):
        goto(page, flask_base_url, "/")
        # The Jobs view container must be in the DOM
        assert page.locator("#view-jobs").count() > 0, (
            "#view-jobs container not found on index page"
        )

    def test_old_page_has_bulk_update_buttons(self, page, flask_base_url):
        goto(page, flask_base_url, "/old")
        # old.html has "Mark Applied & Archive" button
        btns = page.get_by_text("Mark Applied & Archive")
        assert btns.count() > 0, (
            "Bulk update 'Mark Applied & Archive' button not found on /old page"
        )

    def test_old_page_has_bulk_update_rejected_button(self, page, flask_base_url):
        goto(page, flask_base_url, "/old")
        btns = page.get_by_text("Mark Rejected & Archive")
        assert btns.count() > 0, (
            "Bulk update 'Mark Rejected & Archive' button not found on /old page"
        )

    def test_old_page_has_archive_selected_button(self, page, flask_base_url):
        goto(page, flask_base_url, "/old")
        btns = page.get_by_text("Archive Selected")
        assert btns.count() > 0, (
            "'Archive Selected' button not found on /old page"
        )

    def test_index_has_sidebar_nav(self, page, flask_base_url):
        goto(page, flask_base_url, "/")
        # The sidebar navigation with data-view attributes should be present
        nav_items = page.locator(".nav-item[data-view]")
        assert nav_items.count() >= 4, (
            f"Expected at least 4 sidebar nav items, found {nav_items.count()}"
        )
