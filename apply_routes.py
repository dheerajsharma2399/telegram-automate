import os
import json
import uuid
import logging
import threading
from flask import Blueprint, render_template, jsonify, request, current_app
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

apply_bp = Blueprint('apply', __name__)

PROFILES_DIR = os.getenv("PROFILES_DIR", "./data/profiles")


def get_db():
    """Get database instance from app config."""
    return current_app.config.get("DB")


def get_sheets_sync():
    """Get sheets sync instance — calls the factory function from web_server."""
    getter = current_app.config.get("GET_SHEETS_SYNC")
    if getter:
        return getter()
    return None


@apply_bp.route("/")
def index():
    return render_template("apply.html")


@apply_bp.route("/api/jobs")
def get_jobs():
    """Get jobs with email addresses that are synced to sheets."""
    db = get_db()
    if not db:
        return jsonify({"error": "Database not configured"}), 500

    conn = db.get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id, job_id, company_name, job_role, email, location,
                   COALESCE(apply_status, 'pending') as apply_status, created_at
            FROM jobs
            WHERE email IS NOT NULL
              AND email != ''
              AND synced_to_sheets = TRUE
              AND is_hidden = FALSE
              AND is_duplicate = FALSE
            ORDER BY created_at DESC
            LIMIT 100
        """)
        jobs = cursor.fetchall()
        return jsonify({"jobs": jobs})
    except Exception as e:
        logger.exception("Failed to fetch apply jobs")
        return jsonify({"error": str(e)}), 500
    finally:
        conn.close()


@apply_bp.route("/api/profiles", methods=["GET"])
def get_profiles():
    """List available profile JSON files."""
    profiles = []
    default_profile = "user_profile.json"

    # Ensure profiles directory exists
    os.makedirs(PROFILES_DIR, exist_ok=True)

    # List files in PROFILES_DIR
    if os.path.isdir(PROFILES_DIR):
        for f in os.listdir(PROFILES_DIR):
            if f.endswith(".json"):
                profiles.append(f)

    # Always include user_profile.json from repo root if it exists
    user_profile_path = os.path.join(os.path.dirname(__file__), "user_profile.json")
    if os.path.exists(user_profile_path):
        if default_profile not in profiles:
            profiles.insert(0, default_profile)

    # Build response with labels
    response_profiles = []
    for p in profiles:
        response_profiles.append({
            "filename": p,
            "label": f"{p} (default)" if p == default_profile else p
        })

    return jsonify({"profiles": response_profiles, "default": default_profile})


@apply_bp.route("/api/profiles", methods=["POST"])
def upload_profile():
    """Upload a new profile JSON file."""
    if 'file' not in request.files:
        return jsonify({"error": "No file provided"}), 400

    file = request.files['file']
    if not file.filename.endswith('.json'):
        return jsonify({"error": "File must be JSON"}), 400

    # Validate file size (500KB max)
    file.seek(0, os.SEEK_END)
    size = file.tell()
    file.seek(0)
    if size > 500 * 1024:
        return jsonify({"error": "File too large (max 500KB)"}), 400

    # Validate JSON parse
    try:
        data = json.load(file)
    except json.JSONDecodeError:
        return jsonify({"error": "Invalid JSON"}), 400

    # Save file
    os.makedirs(PROFILES_DIR, exist_ok=True)
    filename = file.filename
    filepath = os.path.join(PROFILES_DIR, filename)
    with open(filepath, 'w') as f:
        json.dump(data, f, indent=2)

    return jsonify({"saved": True, "filename": filename})


@apply_bp.route("/api/generate", methods=["POST"])
def generate_email():
    """Trigger email generation in background thread."""
    data = request.get_json() or {}
    job_id = data.get("job_id")
    profile_filename = data.get("profile_filename")

    if not job_id or not profile_filename:
        return jsonify({"error": "job_id and profile_filename required"}), 400

    db = get_db()
    if not db:
        return jsonify({"error": "Database not configured"}), 500

    # Fetch job details
    conn = db.get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT job_id, company_name, job_role, email, jd_text
            FROM jobs WHERE job_id = %s
        """, (job_id,))
        row = cursor.fetchone()
        if not row:
            return jsonify({"error": "Job not found"}), 404

        job = dict(row)
        jd_text = job.get("jd_text", "")
        company = job.get("company_name", "")
        role = job.get("job_role", "")
        # Extract recruiter name from email or use empty
        recruiter_name = ""
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        conn.close()

    # Load profile
    profile_path = os.path.join(PROFILES_DIR, profile_filename)
    if not os.path.exists(profile_path):
        # Fallback to user_profile.json in repo root
        profile_path = os.path.join(os.path.dirname(__file__), "user_profile.json")
        if not os.path.exists(profile_path):
            return jsonify({"error": "Profile not found"}), 404

    with open(profile_path) as f:
        profile = json.load(f)

    # Generate run_id
    run_id = uuid.uuid4().hex[:8]

    # Insert apply_runs row
    conn = db.get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO apply_runs (run_id, job_id, profile_used, status, created_at)
            VALUES (%s, %s, %s, 'running', NOW())
            ON CONFLICT DO NOTHING
        """, (run_id, job_id, profile_filename))
        conn.commit()
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        conn.close()

    # Spawn background thread
    def background_generate():
        from apply_agent import generate_email_draft
        try:
            result = generate_email_draft(
                jd_text=jd_text,
                profile=profile,
                company=company,
                role=role,
                recruiter_name=recruiter_name
            )
            # Update with success
            conn = db.get_connection()
            try:
                cursor = conn.cursor()
                cursor.execute("""
                    UPDATE apply_runs
                    SET status = 'done', email_subject = %s, email_body = %s,
                        tokens_used = %s, model_used = %s
                    WHERE run_id = %s
                """, (result["subject"], result["body_html"], result.get("tokens_used", 0),
                      result.get("model_used", ""), run_id))
                conn.commit()
            except Exception as e:
                logger.exception("Failed to update apply_runs on success")
            finally:
                conn.close()
        except Exception as e:
            logger.exception("Email generation failed")
            conn = db.get_connection()
            try:
                cursor = conn.cursor()
                cursor.execute("""
                    UPDATE apply_runs
                    SET status = 'error', error_message = %s
                    WHERE run_id = %s
                """, (str(e), run_id))
                conn.commit()
            except Exception:
                pass
            finally:
                conn.close()

    thread = threading.Thread(target=background_generate)
    thread.start()

    return jsonify({"run_id": run_id, "status": "running"})


@apply_bp.route("/api/runs/<run_id>")
def get_run_status(run_id):
    """Get status of a generation run."""
    db = get_db()
    if not db:
        return jsonify({"error": "Database not configured"}), 500

    conn = db.get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT run_id, job_id, status, email_subject, email_body,
                   tokens_used, model_used, error_message, created_at
            FROM apply_runs WHERE run_id = %s
        """, (run_id,))
        row = cursor.fetchone()
        if not row:
            return jsonify({"error": "Run not found"}), 404
        return jsonify(dict(row))
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        conn.close()


@apply_bp.route("/api/runs/<run_id>/approve", methods=["POST"])
def approve_draft(run_id):
    """Approve draft and write to Google Sheet."""
    data = request.get_json() or {}
    email_subject = data.get("email_subject")
    email_body = data.get("email_body")

    if not email_subject or not email_body:
        return jsonify({"error": "email_subject and email_body required"}), 400

    db = get_db()
    if not db:
        return jsonify({"error": "Database not configured"}), 500

    # Get run details
    conn = db.get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT job_id FROM apply_runs WHERE run_id = %s
        """, (run_id,))
        row = cursor.fetchone()
        if not row:
            return jsonify({"error": "Run not found"}), 404
        job_id = row["job_id"]
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        conn.close()

    # Get job details for logging
    conn = db.get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT company_name, job_role FROM jobs WHERE job_id = %s
        """, (job_id,))
        row = cursor.fetchone()
        company_name = row.get("company_name", "") if row else ""
        job_role = row.get("job_role", "") if row else ""
    except Exception:
        company_name = ""
        job_role = ""
    finally:
        conn.close()

    # Write to Google Sheet
    sheets_sync = get_sheets_sync()
    sheet_updated = False
    if sheets_sync:
        try:
            sheet_updated = _write_draft_to_sheet(sheets_sync, job_id, email_subject, email_body)
        except Exception as e:
            logger.warning(f"Sheet write failed: {e}")

    # Update apply_runs with approved content
    conn = db.get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE apply_runs
            SET status = 'approved', approved_subject = %s, approved_body = %s,
                approved_at = NOW()
            WHERE run_id = %s
        """, (email_subject, email_body, run_id))
        conn.commit()
    except Exception as e:
        logger.exception("Failed to update apply_runs on approve")
    finally:
        conn.close()

    # Update jobs table
    conn = db.get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE jobs SET apply_status = 'queued', apply_run_id = %s
            WHERE job_id = %s
        """, (run_id, job_id))
        conn.commit()
    except Exception as e:
        logger.exception("Failed to update jobs apply_status")
    finally:
        conn.close()

    logger.info(f"Approved draft for {job_id} ({company_name} - {job_role}), sheet_updated={sheet_updated}")

    return jsonify({
        "approved": True,
        "job_id": job_id,
        "sheet_updated": sheet_updated
    })


def _write_draft_to_sheet(sheets_sync, job_id: str, subject: str, body_html: str) -> bool:
    """Write draft to Google Sheet row."""
    # Get the appropriate worksheet
    sheet = None
    if hasattr(sheets_sync, 'sheet_email'):
        sheet = sheets_sync.sheet_email
    elif hasattr(sheets_sync, 'primary_sync') and sheets_sync.primary_sync:
        sheet = sheets_sync.primary_sync.sheet_email

    if not sheet:
        logger.warning("No email sheet found in sheets_sync")
        return False

    try:
        # Find row by job_id in column A
        job_ids = sheet.col_values(1)
        row_index = None
        for idx, jid in enumerate(job_ids):
            if jid == job_id:
                row_index = idx + 1  # 1-indexed
                break

        if row_index is None:
            # Try sheet_email_exp
            if hasattr(sheets_sync, 'sheet_email_exp'):
                sheet = sheets_sync.sheet_email_exp
                job_ids = sheet.col_values(1)
                for idx, jid in enumerate(job_ids):
                    if jid == job_id:
                        row_index = idx + 1
                        break

        if row_index is None:
            logger.warning(f"Job {job_id} not found in any sheet")
            return False

        # Update columns L (12), M (13), N (14)
        sheet.update(f"L{row_index}:N{row_index}", [[subject, body_html, "DRAFTED"]])
        return True
    except Exception as e:
        logger.exception(f"Failed to write draft to sheet: {e}")
        return False