#!/usr/bin/env python3
"""
Database Repository Classes for the Telegram Job Scraper
"""
import logging
from contextlib import contextmanager
from typing import List, Dict, Optional
import psycopg2
from psycopg2.extras import RealDictCursor
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
            with conn.cursor() as cursor:
                cursor.execute("""
                UPDATE telegram_auth 
                SET session_string = %s, updated_at = CURRENT_TIMESTAMP 
                WHERE id = 1
                """, (session_string,))
                self.logger.info("Telegram session updated in Supabase")
            conn.commit()

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
            with conn.cursor() as cursor:
                cursor.execute("""
                UPDATE telegram_auth 
                SET login_status = %s, updated_at = CURRENT_TIMESTAMP 
                WHERE id = 1
                """, (status,))
                self.logger.info(f"Telegram login status updated: {status}")
            conn.commit()

class MessageRepository(BaseRepository):
    def add_raw_message(self, message_id: int, message_text: str, 
                       sender_id: int, sent_at, group_id: int) -> Optional[int]:
        """Add a new raw message"""
        with self.get_connection() as conn:
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
            with conn.cursor() as cursor:
                cursor.execute("""
                UPDATE raw_messages 
                SET status = %s, error_message = %s
                WHERE id = %s
                """, (status, error_message, message_id))
            conn.commit()

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

class JobRepository(BaseRepository):
    def add_processed_job(self, job_data: Dict) -> Optional[int]:
        """Add a processed job"""
        with self.get_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute("""
                    INSERT INTO processed_jobs (
                        raw_message_id, job_id, first_name, last_name, email,
                        company_name, job_role, location, eligibility, application_link,
                        application_method, jd_text, email_subject, email_body, status, updated_at, is_hidden, sheet_name
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    RETURNING id
                """, (
                    job_data.get('raw_message_id'),
                    job_data.get('job_id'),
                    job_data.get('first_name'),
                    job_data.get('last_name'),
                    job_data.get('email'),
                    job_data.get('company_name'),
                    job_data.get('job_role'),
                    job_data.get('location'),
                    job_data.get('eligibility'),
                    job_data.get('application_link'),
                    job_data.get('application_method'),
                    job_data.get('jd_text'),
                    job_data.get('email_subject'),
                    job_data.get('email_body'),
                    job_data.get('status'),
                    job_data.get('updated_at'),
                    job_data.get('is_hidden', False),
                    job_data.get('sheet_name')
                ))
                result = cursor.fetchone()
            conn.commit()
            return result['id'] if result else None

    def mark_job_synced(self, job_id: str):
        """Mark job as synced to Google Sheets"""
        with self.get_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute("""
                    UPDATE processed_jobs 
                    SET synced_to_sheets = TRUE
                    WHERE job_id = %s
                """, (job_id,))
            conn.commit()

    def get_processed_jobs_by_email_status(self, has_email: bool) -> List[Dict]:
        """Get processed jobs based on whether they have an email."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            if has_email:
                cursor.execute('SELECT * FROM processed_jobs WHERE email IS NOT NULL AND email != "" ORDER BY created_at DESC')
            else:
                cursor.execute('SELECT * FROM processed_jobs WHERE email IS NULL OR email = "" ORDER BY created_at DESC')
            return [dict(row) for row in cursor.fetchall()]

    def get_unsynced_jobs(self) -> List[Dict]:
        """Get all processed jobs that have not been synced to Google Sheets."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM processed_jobs WHERE synced_to_sheets = FALSE ORDER BY created_at ASC')
            return [dict(row) for row in cursor.fetchall()]

    def update_job_email_body(self, job_id: str, email_body: str):
        """Update the email_body for an existing processed job."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE processed_jobs
                SET email_body = %s, updated_at = CURRENT_TIMESTAMP
                WHERE job_id = %s
            """, (email_body, job_id))

    def get_processed_job_by_id(self, job_id: str) -> Optional[Dict]:
        """Get a single processed job by job_id for sheets sync"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM processed_jobs WHERE job_id = %s", (job_id,))
            result = cursor.fetchone()
            return dict(result) if result else None

    def get_email_jobs_needing_generation(self) -> List[Dict]:
        """Get email sheet jobs that need email body generation."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT * FROM processed_jobs
                WHERE email IS NOT NULL AND email != ''
                AND (email_body IS NULL OR TRIM(email_body) = '')
                ORDER BY created_at ASC
            """)
            return [dict(row) for row in cursor.fetchall()]

    def get_all_processed_jobs(self) -> List[Dict]:
        """Get all processed jobs that are not hidden."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM processed_jobs WHERE is_hidden = FALSE ORDER BY created_at DESC')
            return [dict(row) for row in cursor.fetchall()]

    def get_jobs_by_sheet_name(self, sheet_name: str) -> List[Dict]:
        """Get all processed jobs for a given sheet name that are not hidden."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM processed_jobs WHERE sheet_name = %s AND is_hidden = FALSE ORDER BY created_at DESC', (sheet_name,))
            return [dict(row) for row in cursor.fetchall()]

    def hide_jobs(self, job_ids: List[str]) -> int:
        """Mark a list of jobs as hidden."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE processed_jobs
                SET is_hidden = TRUE
                WHERE job_id IN %s
            """, (tuple(job_ids),))
            return cursor.rowcount
            
    def get_jobs_today_stats(self) -> Dict:
        """Get statistics of jobs processed today"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT
                    COUNT(id) as total,
                    SUM(CASE WHEN application_method = 'email' THEN 1 ELSE 0 END) as with_email,
                    SUM(CASE WHEN application_method != 'email' THEN 1 ELSE 0 END) as without_email
                FROM processed_jobs
                WHERE created_at::date = CURRENT_DATE
            """)
            stats = cursor.fetchone()
            return {
                "total": stats["total"] or 0,
                "with_email": stats["with_email"] or 0,
                "without_email": stats["without_email"] or 0,
            }

    def get_stats(self, days: int = 7) -> Dict:
        """Get job statistics for the last N days."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT
                    application_method, 
                    COUNT(id) as count
                FROM processed_jobs
                WHERE created_at >= CURRENT_DATE - INTERVAL '%s days'
                GROUP BY application_method
            """, (days,))
            by_method = {row['application_method']: row['count'] for row in cursor.fetchall()}

            cursor.execute("""
                SELECT
                    company_name,
                    COUNT(id) as count
                FROM processed_jobs
                WHERE created_at >= CURRENT_DATE - INTERVAL '%s days'
                GROUP BY company_name
                ORDER BY count DESC
                LIMIT 5
            """, (days,))
            top_companies = {row['company_name']: row['count'] for row in cursor.fetchall()}

            return {
                "by_method": by_method,
                "top_companies": top_companies,
            }

    def get_relevant_jobs(self, has_email: Optional[bool] = None) -> List[Dict]:
        """Get relevant jobs (fresher-friendly) - NEW METHOD"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            if has_email is None:
                cursor.execute("SELECT * FROM processed_jobs WHERE job_relevance = 'relevant' ORDER BY created_at DESC")
            elif has_email:
                cursor.execute("SELECT * FROM processed_jobs WHERE job_relevance = 'relevant' AND email IS NOT NULL AND email != '' ORDER BY created_at DESC")
            else:
                cursor.execute("SELECT * FROM processed_jobs WHERE job_relevance = 'relevant' AND (email IS NULL OR email = '') ORDER BY created_at DESC")
            return [dict(row) for row in cursor.fetchall()]

    def get_irrelevant_jobs(self, has_email: Optional[bool] = None) -> List[Dict]:
        """Get irrelevant jobs (experienced required) - NEW METHOD"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            if has_email is None:
                cursor.execute("SELECT * FROM processed_jobs WHERE job_relevance = 'irrelevant' ORDER BY created_at DESC")
            elif has_email:
                cursor.execute("SELECT * FROM processed_jobs WHERE job_relevance = 'irrelevant' AND email IS NOT NULL AND email != '' ORDER BY created_at DESC")
            else:
                cursor.execute("SELECT * FROM processed_jobs WHERE job_relevance = 'irrelevant' AND (email IS NULL OR email = '') ORDER BY created_at DESC")
            return [dict(row) for row in cursor.fetchall()]
            
    def get_original_job_data(self, source_job_id: str) -> Optional[Dict]:
        """Get original processed job data by source job ID"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM processed_jobs WHERE job_id = %s", (source_job_id,))
            result = cursor.fetchone()
            return dict(result) if result else None

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

class CommandRepository(BaseRepository):
    def get_pending_commands(self, limit: int = 10) -> List[Dict]:
        """Retrieve pending commands"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT * FROM commands_queue
                WHERE status = 'pending'
                ORDER BY created_at ASC
                LIMIT %s
            """, (limit,))
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
            return result['id'] if result else None

    def mark_command_executed(self, command_id: int):
        """Mark a command as executed."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE commands_queue SET status = 'done', executed_at = CURRENT_TIMESTAMP
                WHERE id = %s
            """, (command_id,))

    def update_command_result(self, command_id: int, status: str, result_text: str = None, executed_by: str = None):
        """Update a command's status, result text and who executed it."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE commands_queue
                SET status = %s, executed_at = CURRENT_TIMESTAMP, result_text = %s, executed_by = %s
                WHERE id = %s
            """, (status, result_text, executed_by, command_id))

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
            return cursor.rowcount > 0

class DashboardRepository(BaseRepository):
    def add_dashboard_job(self, job_data: Dict) -> Optional[int]:
        """Add a job to the dashboard_jobs table"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO dashboard_jobs (
                    source_job_id, original_sheet, company_name, job_role, location,
                    application_link, phone, recruiter_name, job_relevance, original_created_at,
                    application_status, application_date, notes, is_duplicate, duplicate_of_id, conflict_status
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING id
            """, (
                job_data.get('source_job_id'),
                job_data.get('original_sheet'),
                job_data.get('company_name'),
                job_data.get('job_role'),
                job_data.get('location'),
                job_data.get('application_link'),
                job_data.get('phone'),
                job_data.get('recruiter_name'),
                job_data.get('job_relevance'),
                job_data.get('original_created_at'),
                job_data.get('application_status', 'not_applied'),
                job_data.get('application_date'),
                job_data.get('notes'),
                job_data.get('is_duplicate', False),
                job_data.get('duplicate_of_id'),
                job_data.get('conflict_status', 'none')
            ))
            result = cursor.fetchone()
            return result['id'] if result else None

    def get_dashboard_jobs(self, status_filter: Optional[str] = None,
                          relevance_filter: Optional[str] = None,
                          include_archived: bool = False,
                          page: int = 1, page_size: int = 50) -> Dict:
        """Get dashboard jobs with optional filtering"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            base_query = "FROM dashboard_jobs WHERE 1=1"
            params = []
            
            if status_filter:
                base_query += " AND application_status = %s"
                params.append(status_filter)
            
            if relevance_filter:
                base_query += " AND job_relevance = %s"
                params.append(relevance_filter)
            
            if not include_archived:
                base_query += " AND is_hidden = FALSE"
            
            # Get total count for pagination
            count_query = f"SELECT COUNT(*) {base_query}"
            cursor.execute(count_query, tuple(params))
            total_count = cursor.fetchone()['count']
            
            # Get paginated results
            data_query = f"SELECT * {base_query} ORDER BY created_at DESC LIMIT %s OFFSET %s"
            offset = (page - 1) * page_size
            params.extend([page_size, offset])
            cursor.execute(data_query, tuple(params))
            
            return {
                "jobs": [dict(row) for row in cursor.fetchall()],
                "total_count": total_count,
                "page": page,
                "page_size": page_size
            }

    def update_dashboard_job_status(self, job_id: int, status: str,
                                   application_date: Optional[str] = None) -> bool:
        """Update job application status in dashboard"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE dashboard_jobs
                SET application_status = %s, application_date = %s, updated_at = CURRENT_TIMESTAMP
                WHERE id = %s
            """, (status, application_date, job_id))
            return cursor.rowcount > 0

    def add_job_notes(self, job_id: int, notes: str) -> bool:
        """Add or update notes for a job"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE dashboard_jobs
                SET notes = %s, updated_at = CURRENT_TIMESTAMP
                WHERE id = %s
            """, (notes, job_id))
            return cursor.rowcount > 0

    def mark_as_duplicate(self, job_id: int, duplicate_of_id: int, confidence_score: float = 0.8) -> bool:
        """Mark a job as duplicate of another job"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            # Update the job record
            cursor.execute("""
                UPDATE dashboard_jobs
                SET is_duplicate = TRUE, duplicate_of_id = %s, updated_at = CURRENT_TIMESTAMP
                WHERE id = %s
            """, (duplicate_of_id, job_id))
            
            # Add to duplicate groups table (cast array to JSON)
            cursor.execute("""
                INSERT INTO job_duplicate_groups (primary_job_id, duplicate_jobs, confidence_score)
                VALUES (%s, %s::jsonb, %s)
            """, (duplicate_of_id, f'["{job_id}"]', confidence_score))
            
            return cursor.rowcount > 0

    def bulk_update_status(self, job_ids: List[int], status: str,
                          application_date: Optional[str] = None, archive: bool = False) -> int:
        """Update status for multiple jobs at once"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            # If archiving, we set the status to 'archived' regardless of the input status
            final_status = 'archived' if archive else status
            cursor.execute("""
                UPDATE dashboard_jobs
                SET application_status = %s, application_date = %s, updated_at = CURRENT_TIMESTAMP, is_hidden = %s
                WHERE id = ANY(%s)
            """, (final_status, application_date, archive, job_ids))
            return cursor.rowcount

    def import_jobs_from_processed(self, sheet_name: str, max_jobs: int = 100) -> int:
        """Import non-email jobs from processed_jobs to dashboard_jobs"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            # Get processed jobs that are not already in dashboard
            query = """
                SELECT pj.* FROM processed_jobs pj
                LEFT JOIN dashboard_jobs dj ON pj.job_id = dj.source_job_id
                WHERE dj.id IS NULL
                AND pj.sheet_name = %s
                AND pj.is_hidden = FALSE
                ORDER BY pj.created_at DESC
                LIMIT %s
            """
            params = (sheet_name, max_jobs)

            cursor.execute(query, params)
            jobs = [dict(row) for row in cursor.fetchall()]
            
            # Insert into dashboard_jobs
            imported_count = 0
            for job in jobs:
                dashboard_job = {
                    'source_job_id': job['job_id'],
                    'original_sheet': sheet_name,
                    'company_name': job['company_name'],
                    'job_role': job['job_role'],
                    'location': job['location'],
                    'application_link': job['application_link'],
                    'phone': job.get('phone'),
                    'recruiter_name': job.get('recruiter_name'),
                    'job_relevance': job.get('job_relevance', 'relevant'),
                    'original_created_at': job['created_at'],
                    'application_status': 'not_applied'
                }
                
                job_id = self.add_dashboard_job(dashboard_job)
                if job_id:
                    imported_count += 1
            
            return imported_count

    def detect_duplicate_jobs(self) -> int:
        """Detect duplicate jobs in dashboard_jobs table"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            # Find potential duplicates by company name and role
            query = """
                WITH potential_duplicates AS (
                    SELECT
                        id, company_name, job_role,
                        ROW_NUMBER() OVER (
                            PARTITION BY LOWER(TRIM(company_name)), LOWER(TRIM(job_role))
                            ORDER BY created_at
                        ) as rn
                    FROM dashboard_jobs
                    WHERE is_duplicate = FALSE
                )
                SELECT id, company_name, job_role, rn
                FROM potential_duplicates
                WHERE rn > 1
            """
            
            cursor.execute(query)
            duplicates = cursor.fetchall()
            
            detected_count = 0
            for duplicate in duplicates:
                if duplicate['rn'] > 1:
                    try:
                        cursor.execute("""
                            INSERT INTO job_duplicate_groups (primary_job_id, duplicate_jobs, confidence_score)
                            VALUES (%s, %s::jsonb, %s)
                        """, (None, f'["{duplicate["id"]}"]', 0.9))
                        
                        # Update job status
                        cursor.execute("""
                            UPDATE dashboard_jobs
                            SET is_duplicate = TRUE, duplicate_of_id = %s, updated_at = CURRENT_TIMESTAMP
                            WHERE id = %s
                        """, (None, duplicate['id']))
                        
                        detected_count += 1
                    except Exception as e:
                        self.logger.error(f"Error marking duplicate job {duplicate['id']}: {e}")
            
            return detected_count

    def export_dashboard_jobs(self, format_type: str = 'csv') -> Dict:
        """Export dashboard jobs to CSV format"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT
                    company_name, job_role, location, application_link, phone,
                    job_relevance, application_status, application_date, notes, created_at
                FROM dashboard_jobs
                ORDER BY created_at DESC
            """)
            jobs = [dict(row) for row in cursor.fetchall()]
            
            return {
                'format': format_type,
                'count': len(jobs),
                'data': jobs,
                'columns': ['company_name', 'job_role', 'location', 'application_link', 'phone',
                           'job_relevance', 'application_status', 'application_date', 'notes', 'created_at']
            }

    def get_dashboard_job_by_id(self, job_id: int) -> Optional[Dict]:
        """Get a specific dashboard job by ID"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM dashboard_jobs WHERE id = %s", (job_id,))
            result = cursor.fetchone()
            return dict(result) if result else None
