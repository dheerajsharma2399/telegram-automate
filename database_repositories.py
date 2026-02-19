#!/usr/bin/env python3
"""
Database Repository Classes for the Telegram Job Scraper
Refactored to use UnifiedJobRepository for the unified 'jobs' table.
"""
import logging
import json
from contextlib import contextmanager
from typing import List, Dict, Optional, Union
import psycopg2
from psycopg2.extras import RealDictCursor, Json
from psycopg2.pool import ThreadedConnectionPool

class BaseRepository:
    def __init__(self, pool):
        self.pool = pool
        self.logger = logging.getLogger(self.__class__.__name__)

    @contextmanager
    def get_connection(self):
        """Get PostgreSQL connection from pool"""
        connection = self.pool.getconn()
        try:
            yield connection
        except Exception:
            connection.rollback()
            raise
        finally:
            self.pool.putconn(connection)

class TelegramAuthRepository(BaseRepository):
    def get_telegram_session(self) -> Optional[str]:
        """Get stored Telegram session string from Supabase"""
        with self.get_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute("SELECT session_string FROM telegram_auth WHERE id = 1")
                result = cursor.fetchone()
            return result['session_string'] if result and result['session_string'] else None

    def set_telegram_session(self, session_string: str):
        """Store Telegram session string in Supabase"""
        with self.get_connection() as conn:
            try:
                with conn.cursor() as cursor:
                    cursor.execute("""
                    UPDATE telegram_auth
                    SET session_string = %s, updated_at = CURRENT_TIMESTAMP
                    WHERE id = 1
                    """, (session_string,))
                    self.logger.info("Telegram session updated in Supabase")
                conn.commit()
            except Exception as e:
                conn.rollback()
                self.logger.error(f"Failed to set telegram session: {e}")
                raise

    def get_telegram_login_status(self) -> str:
        """Get Telegram login status from Supabase"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT login_status FROM telegram_auth WHERE id = 1")
            result = cursor.fetchone()
            return result['login_status'] if result else 'not_authenticated'

    def set_telegram_login_status(self, status: str):
        """Set Telegram login status in Supabase"""
        with self.get_connection() as conn:
            try:
                with conn.cursor() as cursor:
                    cursor.execute("""
                    UPDATE telegram_auth
                    SET login_status = %s, updated_at = CURRENT_TIMESTAMP
                    WHERE id = 1
                    """, (status,))
                    self.logger.info(f"Telegram login status updated: {status}")
                conn.commit()
            except Exception as e:
                conn.rollback()
                self.logger.error(f"Failed to set login status: {e}")
                raise

class MessageRepository(BaseRepository):
    def add_raw_message(self, message_id: int, message_text: str,
                       sender_id: int, sent_at, group_id: int) -> Optional[int]:
        """Add a new raw message"""
        with self.get_connection() as conn:
            try:
                with conn.cursor() as cursor:
                    cursor.execute("""
                        INSERT INTO raw_messages
                        (message_id, message_text, sender_id, sent_at, status, group_id)
                        VALUES (%s, %s, %s, %s, 'unprocessed', %s)
                        ON CONFLICT (group_id, message_id) DO NOTHING
                        RETURNING id
                    """, (message_id, message_text, sender_id, sent_at, group_id))
                    result = cursor.fetchone()
                conn.commit()
                return result['id'] if result else None
            except Exception as e:
                conn.rollback()
                self.logger.error(f"Failed to add raw message: {e}")
                raise

    def get_unprocessed_messages(self, limit: int = 10) -> List[Dict]:
        """Get unprocessed messages"""
        with self.get_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute("""
                    SELECT * FROM raw_messages
                    WHERE status = 'unprocessed'
                    ORDER BY created_at ASC
                    LIMIT %s
                """, (limit,))
                return [dict(row) for row in cursor.fetchall()]

    def update_message_status(self, message_id: int, status: str,
                            error_message: str = None):
        """Update message processing status"""
        with self.get_connection() as conn:
            try:
                with conn.cursor() as cursor:
                    cursor.execute("""
                    UPDATE raw_messages
                    SET status = %s, error_message = %s
                    WHERE id = %s
                    """, (status, error_message, message_id))
                conn.commit()
            except Exception as e:
                conn.rollback()
                self.logger.error(f"Failed to update message status: {e}")
                raise

    def get_unprocessed_count(self) -> int:
        """Get count of unprocessed messages"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM raw_messages WHERE status = 'unprocessed'")
            result = cursor.fetchone()
            return result['count'] if result else 0

    def get_last_message_id_for_group(self, group_id: int) -> Optional[int]:
        """Get the latest message_id for a specific group from the database."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT MAX(message_id) as last_id
                FROM raw_messages
                WHERE group_id = %s
            """, (group_id,))
            result = cursor.fetchone()
            return result['last_id'] if result and result['last_id'] is not None else 0

    def get_raw_message_by_id(self, message_id: int) -> Optional[Dict]:
        """Get raw message by ID"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM raw_messages WHERE id = %s", (message_id,))
            result = cursor.fetchone()
            return dict(result) if result else None

class UnifiedJobRepository(BaseRepository):
    """
    Unified Job Repository that manages the 'jobs' table.
    Replaces both JobRepository and DashboardRepository.
    """
    def add_job(self, job_data: Dict, source: str = 'telegram', cursor=None) -> Optional[int]:
        """
        Add a job to the unified jobs table

        Args:
            job_data: Dictionary containing job information
            source: 'telegram' or 'manual'
            cursor: Optional cursor for transaction handling
        """
        sql = """
            INSERT INTO jobs (
                job_id, source, status, company_name, job_role, location, eligibility, salary,
                jd_text, raw_message_id, email, phone, application_link, notes,
                is_hidden, is_duplicate, duplicate_of_id, job_relevance, metadata, updated_at
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW())
            ON CONFLICT (job_id) DO UPDATE SET
                status = EXCLUDED.status,
                company_name = COALESCE(EXCLUDED.company_name, jobs.company_name),
                job_role = COALESCE(EXCLUDED.job_role, jobs.job_role),
                location = COALESCE(EXCLUDED.location, jobs.location),
                eligibility = COALESCE(EXCLUDED.eligibility, jobs.eligibility),
                salary = COALESCE(EXCLUDED.salary, jobs.salary),
                jd_text = COALESCE(EXCLUDED.jd_text, jobs.jd_text),
                email = COALESCE(EXCLUDED.email, jobs.email),
                phone = COALESCE(EXCLUDED.phone, jobs.phone),
                application_link = COALESCE(EXCLUDED.application_link, jobs.application_link),
                notes = COALESCE(EXCLUDED.notes, jobs.notes),
                job_relevance = COALESCE(EXCLUDED.job_relevance, jobs.job_relevance),
                metadata = jobs.metadata || EXCLUDED.metadata,
                updated_at = NOW()
            RETURNING id
        """

        # Prepare metadata
        metadata = job_data.get('metadata', {})
        if 'sheet_name' in job_data:
            metadata['original_sheet'] = job_data['sheet_name']

        values = (
            job_data.get('job_id'),
            source,
            job_data.get('status', 'not_applied' if source == 'manual' else 'pending'),
            job_data.get('company_name'),
            job_data.get('job_role'),
            job_data.get('location'),
            job_data.get('eligibility'),
            job_data.get('salary'),
            job_data.get('jd_text'),
            job_data.get('raw_message_id'),
            job_data.get('email'),
            job_data.get('phone'),
            job_data.get('application_link'),
            job_data.get('notes'),
            job_data.get('is_hidden', False),
            job_data.get('is_duplicate', False),
            job_data.get('duplicate_of_id'),
            job_data.get('job_relevance', 'relevant'),
            Json(metadata)
        )

        if cursor:
            cursor.execute(sql, values)
            result = cursor.fetchone()
            return result['id'] if result else None
        else:
            with self.get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(sql, values)
                    result = cur.fetchone()
                conn.commit()
                return result['id'] if result else None

    def get_jobs(self, source: Optional[str] = None,
                 status: Optional[str] = None,
                 relevance: Optional[str] = None,
                 job_role: Optional[str] = None,
                 include_hidden: bool = False,
                 has_email: Optional[bool] = None,
                 page: int = 1, page_size: int = 50,
                 sort_by: str = 'created_at', sort_order: str = 'DESC') -> Dict:
        """Unified method to fetch jobs with filtering and pagination"""
        with self.get_connection() as conn:
            with conn.cursor() as cursor:
                base_query = "FROM jobs WHERE 1=1"
                params = []

                if source:
                    base_query += " AND source = %s"
                    params.append(source)

                if status:
                    base_query += " AND status = %s"
                    params.append(status)

                if relevance:
                    base_query += " AND job_relevance = %s"
                    params.append(relevance)

                if job_role:
                    base_query += " AND job_role ILIKE %s"
                    params.append(f"%{job_role}%")

                if not include_hidden:
                    base_query += " AND is_hidden = FALSE"

                if has_email is not None:
                    if has_email:
                        base_query += " AND email IS NOT NULL AND email != ''"
                    else:
                        base_query += " AND (email IS NULL OR email = '')"

                # Get total count
                count_query = f"SELECT COUNT(*) {base_query}"
                cursor.execute(count_query, tuple(params))
                total_count = cursor.fetchone()['count']

                # Sort mapping for safety
                allowed_sort_cols = ['created_at', 'updated_at', 'job_role', 'company_name', 'status', 'job_relevance', 'id']
                if sort_by not in allowed_sort_cols:
                    sort_by = 'created_at'
                if sort_order.upper() not in ['ASC', 'DESC']:
                    sort_order = 'DESC'

                # Get paginated results
                data_query = f"SELECT * {base_query} ORDER BY {sort_by} {sort_order} LIMIT %s OFFSET %s"
                offset = (page - 1) * page_size
                params.extend([page_size, offset])
                cursor.execute(data_query, tuple(params))

                return {
                    "jobs": [dict(row) for row in cursor.fetchall()],
                    "total_count": total_count,
                    "page": page,
                    "page_size": page_size
                }

    def bulk_update_status(self, job_ids: Union[List[int], List[str]], status: str,
                           archive: bool = False, notes: Optional[str] = None) -> int:
        """Update status for multiple jobs at once"""
        with self.get_connection() as conn:
            try:
                with conn.cursor() as cursor:
                    should_hide = archive or (status in ['rejected', 'archived'])

                    sql = """
                        UPDATE jobs
                        SET status = %s,
                            updated_at = NOW(),
                            is_hidden = CASE WHEN %s THEN TRUE ELSE is_hidden END
                    """
                    params = [status, should_hide]

                    if notes:
                        sql += ", notes = %s"
                        params.append(notes)

                    # Handle both integer IDs and string job_ids
                    if all(isinstance(x, int) for x in job_ids):
                        sql += " WHERE id = ANY(%s)"
                    else:
                        sql += " WHERE job_id = ANY(%s)"

                    params.append(list(job_ids))

                    cursor.execute(sql, tuple(params))
                    conn.commit()
                    return cursor.rowcount
            except Exception as e:
                conn.rollback()
                self.logger.error(f"Bulk update failed: {e}")
                raise

    def mark_job_synced(self, job_id: str, sheet_name: Optional[str] = None):
        """Mark job as synced to Google Sheets"""
        with self.get_connection() as conn:
            try:
                with conn.cursor() as cursor:
                    if sheet_name:
                        cursor.execute("""
                            UPDATE jobs
                            SET synced_to_sheets = TRUE,
                                metadata = metadata || jsonb_build_object('last_sheet', %s),
                                updated_at = NOW()
                            WHERE job_id = %s
                        """, (sheet_name, job_id))
                    else:
                        cursor.execute("""
                            UPDATE jobs
                            SET synced_to_sheets = TRUE, updated_at = NOW()
                            WHERE job_id = %s
                        """, (job_id,))
                    conn.commit()
            except Exception as e:
                conn.rollback()
                self.logger.error(f"Failed to mark job as synced: {e}")
                raise

    def get_unsynced_jobs(self, limit: int = 100) -> List[Dict]:
        """Get all jobs that have not been synced to Google Sheets."""
        with self.get_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute("""
                    SELECT * FROM jobs
                    WHERE synced_to_sheets = FALSE AND is_hidden = FALSE
                    ORDER BY created_at ASC
                    LIMIT %s
                """, (limit,))
                return [dict(row) for row in cursor.fetchall()]

    def hide_jobs(self, job_ids: Union[List[int], List[str]]) -> int:
        """Mark a list of jobs as hidden."""
        with self.get_connection() as conn:
            try:
                with conn.cursor() as cursor:
                    if all(isinstance(x, int) for x in job_ids):
                        cursor.execute("UPDATE jobs SET is_hidden = TRUE, updated_at = NOW() WHERE id = ANY(%s)", (list(job_ids),))
                    else:
                        cursor.execute("UPDATE jobs SET is_hidden = TRUE, updated_at = NOW() WHERE job_id = ANY(%s)", (list(job_ids),))
                    conn.commit()
                    return cursor.rowcount
            except Exception as e:
                conn.rollback()
                self.logger.error(f"Hide jobs failed: {e}")
                raise

    def get_jobs_today_stats(self) -> Dict:
        """Get statistics of jobs processed today"""
        with self.get_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute("""
                    SELECT
                        COUNT(id) as total,
                        SUM(CASE WHEN source = 'telegram' THEN 1 ELSE 0 END) as telegram,
                        SUM(CASE WHEN source = 'manual' THEN 1 ELSE 0 END) as manual,
                        SUM(CASE WHEN email IS NOT NULL AND email != '' THEN 1 ELSE 0 END) as with_email
                    FROM jobs
                    WHERE created_at::date = CURRENT_DATE
                """)
                stats = cursor.fetchone()
                return {
                    "total": stats["total"] or 0,
                    "telegram": stats["telegram"] or 0,
                    "manual": stats["manual"] or 0,
                    "with_email": stats["with_email"] or 0,
                }

    def get_stats(self) -> Dict:
        """Get comprehensive job statistics"""
        with self.get_connection() as conn:
            with conn.cursor() as cursor:
                # By status
                cursor.execute("SELECT status, COUNT(*) FROM jobs WHERE is_hidden = FALSE GROUP BY status")
                by_status = {row['status'] or 'Unknown': row['count'] for row in cursor.fetchall()}

                # By relevance
                cursor.execute("SELECT job_relevance, COUNT(*) FROM jobs WHERE is_hidden = FALSE GROUP BY job_relevance")
                by_relevance = {row['job_relevance'] or 'Unknown': row['count'] for row in cursor.fetchall()}

                # Total
                cursor.execute("SELECT COUNT(*) FROM jobs WHERE is_hidden = FALSE")
                total = cursor.fetchone()['count']

                return {
                    "total_jobs": total,
                    "by_status": by_status,
                    "by_relevance": by_relevance
                }

    def find_duplicate_job(self, company_name: str, job_role: str, email: Optional[str]) -> Optional[Dict]:
        """Find duplicate jobs by company/role or email"""
        if not company_name or not job_role:
            if not email: return None

        with self.get_connection() as conn:
            with conn.cursor() as cursor:
                if company_name and job_role:
                    cursor.execute("""
                        SELECT * FROM jobs
                        WHERE lower(company_name) = lower(%s) AND lower(job_role) = lower(%s)
                        ORDER BY created_at DESC LIMIT 1
                    """, (company_name, job_role))
                    dup = cursor.fetchone()
                    if dup: return dict(dup)

                if email:
                    cursor.execute("""
                        SELECT * FROM jobs
                        WHERE lower(email) = lower(%s)
                        ORDER BY created_at DESC LIMIT 1
                    """, (email,))
                    dup = cursor.fetchone()
                    if dup: return dict(dup)
        return None

    def get_job_by_id(self, job_id: Union[int, str]) -> Optional[Dict]:
        """Get job by internal ID or job_id string"""
        with self.get_connection() as conn:
            with conn.cursor() as cursor:
                if isinstance(job_id, int):
                    cursor.execute("SELECT * FROM jobs WHERE id = %s", (job_id,))
                else:
                    cursor.execute("SELECT * FROM jobs WHERE job_id = %s", (job_id,))
                result = cursor.fetchone()
                return dict(result) if result else None

    def archive_jobs_older_than(self, days: int) -> int:
        """Archive old jobs"""
        with self.get_connection() as conn:
            try:
                with conn.cursor() as cursor:
                    cursor.execute("""
                        UPDATE jobs
                        SET is_hidden = TRUE, status = 'archived', updated_at = NOW()
                        WHERE created_at < NOW() - make_interval(days => %s)
                        AND is_hidden = FALSE
                    """, (days,))
                    conn.commit()
                    return cursor.rowcount
            except Exception as e:
                conn.rollback()
                self.logger.error(f"Archive failed: {e}")
                raise

    def get_relevant_jobs(self, has_email: Optional[bool] = None) -> List[Dict]:
        """Get relevant jobs (fresher-friendly) - Compatibility wrapper"""
        result = self.get_jobs(relevance='relevant', has_email=has_email, page_size=1000)
        return result['jobs']

    def get_irrelevant_jobs(self, has_email: Optional[bool] = None) -> List[Dict]:
        """Get irrelevant jobs (experienced required) - Compatibility wrapper"""
        result = self.get_jobs(relevance='irrelevant', has_email=has_email, page_size=1000)
        return result['jobs']

    def get_jobs_by_sheet_name(self, sheet_name: str) -> List[Dict]:
        """Get jobs by original sheet name stored in metadata"""
        with self.get_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute("""
                    SELECT * FROM jobs
                    WHERE metadata->>'original_sheet' = %s AND is_hidden = FALSE
                    ORDER BY created_at DESC
                """, (sheet_name,))
                return [dict(row) for row in cursor.fetchall()]

    def add_processed_job(self, job_data: Dict, cursor=None) -> Optional[int]:
        """Compatibility wrapper for telegram jobs"""
        return self.add_job(job_data, source='telegram', cursor=cursor)

    def add_dashboard_job(self, job_data: Dict, cursor=None) -> Optional[int]:
        """Compatibility wrapper for manual/dashboard jobs"""
        return self.add_job(job_data, source='manual', cursor=cursor)

    def get_dashboard_jobs(self, **kwargs) -> Dict:
        """Compatibility wrapper for dashboard job list"""
        # Map old parameter names if necessary
        status_filter = kwargs.get('status_filter') or kwargs.get('status')
        relevance_filter = kwargs.get('relevance_filter') or kwargs.get('relevance')
        job_role_filter = kwargs.get('job_role_filter') or kwargs.get('job_role')
        include_archived = kwargs.get('include_archived', False)

        return self.get_jobs(
            status=status_filter,
            relevance=relevance_filter,
            job_role=job_role_filter,
            include_hidden=include_archived,
            page=kwargs.get('page', 1),
            page_size=kwargs.get('page_size', 50),
            sort_by=kwargs.get('sort_by', 'created_at'),
            sort_order=kwargs.get('sort_order', 'DESC')
        )

    def add_job_notes(self, job_id: int, notes: str) -> bool:
        """Add or update notes for a job"""
        return self.bulk_update_status([job_id], status=None, notes=notes) > 0

    def import_jobs_from_processed(self, sheet_name: str, max_jobs: int = 100) -> int:
        """
        In the unified model, 'importing' means making sure jobs from a specific
        Telegram 'sheet' are visible (not hidden) in the dashboard.
        """
        with self.get_connection() as conn:
            try:
                with conn.cursor() as cursor:
                    cursor.execute("""
                        UPDATE jobs
                        SET is_hidden = FALSE, updated_at = NOW()
                        WHERE metadata->>'original_sheet' = %s AND source = 'telegram'
                        AND is_hidden = TRUE
                    """, (sheet_name,))
                    conn.commit()
                    return cursor.rowcount
            except Exception as e:
                conn.rollback()
                self.logger.error(f"Import from processed failed: {e}")
                raise

    def find_duplicate_processed_job(self, company_name: str, job_role: str, email: Optional[str]) -> Optional[Dict]:
        """Compatibility wrapper"""
        return self.find_duplicate_job(company_name, job_role, email)

    def get_relevance_stats(self) -> Dict:
        """Get relevance breakdown stats (formerly in web_server.py)"""
        with self.get_connection() as conn:
            with conn.cursor() as cursor:
                query = """
                    SELECT
                        COUNT(*) FILTER (WHERE job_relevance = 'relevant' AND email IS NOT NULL AND email != '') as relevant_with_email,
                        COUNT(*) FILTER (WHERE job_relevance = 'relevant' AND (email IS NULL OR email = '')) as relevant_without_email,
                        COUNT(*) FILTER (WHERE job_relevance = 'irrelevant' AND email IS NOT NULL AND email != '') as irrelevant_with_email,
                        COUNT(*) FILTER (WHERE job_relevance = 'irrelevant' AND (email IS NULL OR email = '')) as irrelevant_without_email
                    FROM jobs
                    WHERE is_hidden = FALSE
                """
                cursor.execute(query)
                stats = cursor.fetchone()

        relevant_total = stats['relevant_with_email'] + stats['relevant_without_email']
        irrelevant_total = stats['irrelevant_with_email'] + stats['irrelevant_without_email']

        return {
            "relevant": {"total": relevant_total, "with_email": stats['relevant_with_email'], "without_email": stats['relevant_without_email']},
            "irrelevant": {"total": irrelevant_total, "with_email": stats['irrelevant_with_email'], "without_email": stats['irrelevant_without_email']},
            "total_jobs": relevant_total + irrelevant_total
        }

    def get_jobs_in_range(self, days: int) -> List[Dict]:
        """Get jobs created in the last N days (for sync)"""
        with self.get_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute("""
                    SELECT * FROM jobs
                    WHERE created_at >= NOW() - make_interval(days => %s)
                    ORDER BY created_at DESC
                """, (days,))
                return [dict(row) for row in cursor.fetchall()]

class ConfigRepository(BaseRepository):
    def get_config(self, key: str) -> Optional[str]:
        """Get config value"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT value FROM bot_config WHERE key = %s", (key,))
            result = cursor.fetchone()
            return result['value'] if result else None

    def set_config(self, key: str, value: str):
        """Set config value"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO bot_config (key, value, updated_at)
                VALUES (%s, %s, CURRENT_TIMESTAMP)
                ON CONFLICT (key) DO UPDATE SET
                value = EXCLUDED.value,
                updated_at = EXCLUDED.updated_at
            """, (key, value))
            conn.commit()

class CommandRepository(BaseRepository):
    def get_pending_commands(self, limit: int = 10) -> List[Dict]:
        """Retrieve pending commands"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            query = """
                SELECT * FROM commands_queue
                WHERE status = 'pending'
                ORDER BY created_at ASC
                LIMIT %s
            """
            cursor.execute(query, (limit,))
            return [dict(row) for row in cursor.fetchall()]

    def list_all_pending_commands(self) -> List[Dict]:
        """Return all pending commands (no limit)."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT * FROM commands_queue
                WHERE status = 'pending'
                ORDER BY created_at ASC
            """)
            return [dict(row) for row in cursor.fetchall()]

    def enqueue_command(self, command: str) -> Optional[int]:
        """Enqueue a command (from web dashboard) to be executed by the bot."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO commands_queue (command, status) VALUES (%s, 'pending')
                RETURNING id
            """, (command,))
            result = cursor.fetchone()
            conn.commit()
            return result['id'] if result else None

    def mark_command_executed(self, command_id: int):
        """Mark a command as executed."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE commands_queue SET status = 'done', executed_at = CURRENT_TIMESTAMP
                WHERE id = %s
            """, (command_id,))
            conn.commit()

    def update_command_result(self, command_id: int, status: str, result_text: str = None, executed_by: str = None):
        """Update a command's status, result text and who executed it."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE commands_queue
                SET status = %s, executed_at = CURRENT_TIMESTAMP, result_text = %s, executed_by = %s
                WHERE id = %s
            """, (status, result_text, executed_by, command_id))
            conn.commit()

    def cancel_command(self, command_id: int) -> bool:
        """Cancel (mark done/cancelled) a pending command by id."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT id FROM commands_queue WHERE id = %s AND status = %s', (command_id, 'pending'))
            if not cursor.fetchone():
                return False
            cursor.execute("""
                UPDATE commands_queue SET status = 'cancelled', executed_at = CURRENT_TIMESTAMP
                WHERE id = %s
            """, (command_id,))
            conn.commit()
            return cursor.rowcount > 0
