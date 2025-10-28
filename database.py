import sqlite3
from datetime import datetime
from contextlib import contextmanager
from typing import List, Dict, Optional

class Database:
    def __init__(self, db_path: str):
        self.db_path = db_path
        self.init_database()
    
    @contextmanager
    def get_connection(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        except Exception as e:
            conn.rollback()
            raise e
        finally:
            conn.close()
    
    def init_database(self):
        """Initialize database with required tables"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            # Raw messages table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS raw_messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    message_id INTEGER UNIQUE NOT NULL,
                    message_text TEXT NOT NULL,
                    sender_id INTEGER,
                    sent_at TIMESTAMP,
                    status TEXT DEFAULT 'unprocessed',
                    error_message TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            # Processed jobs table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS processed_jobs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    raw_message_id INTEGER,
                    job_id TEXT UNIQUE NOT NULL,
                    first_name TEXT,
                    last_name TEXT,
                    email TEXT,
                    company_name TEXT,
                    job_role TEXT,
                    location TEXT,
                    eligibility TEXT,
                    application_method TEXT,
                    status TEXT DEFAULT 'pending',
                    updated_at TIMESTAMP,
                    jd_text TEXT,
                    email_subject TEXT,
                    synced_to_sheets BOOLEAN DEFAULT 0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (raw_message_id) REFERENCES raw_messages(id)
                )
            ''')
            
            # Bot config table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS bot_config (
                    key TEXT PRIMARY KEY,
                    value TEXT,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            # Initialize default config
            cursor.execute('''
                INSERT OR IGNORE INTO bot_config (key, value) VALUES
                ('monitoring_status', 'stopped'),
                ('last_processed_message_id', '0'),
                ('total_messages_processed', '0'),
                ('total_jobs_extracted', '0')
            ''')
    
    def add_raw_message(self, message_id: int, message_text: str, 
                       sender_id: int, sent_at: datetime) -> int:
        """Add a new raw message"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT OR IGNORE INTO raw_messages 
                (message_id, message_text, sender_id, sent_at, status)
                VALUES (?, ?, ?, ?, 'unprocessed')
            ''', (message_id, message_text, sender_id, sent_at))
            return cursor.lastrowid
    
    def get_unprocessed_messages(self, limit: int = 10) -> List[Dict]:
        """Get unprocessed messages"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT * FROM raw_messages 
                WHERE status = 'unprocessed'
                ORDER BY created_at ASC
                LIMIT ?
            ''', (limit,))
            return [dict(row) for row in cursor.fetchall()]
    
    def update_message_status(self, message_id: int, status: str, 
                            error_message: str = None):
        """Update message processing status"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                UPDATE raw_messages 
                SET status = ?, error_message = ?
                WHERE id = ?
            ''', (status, error_message, message_id))
    
    def add_processed_job(self, job_data: Dict) -> int:
        """Add a processed job"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT OR IGNORE INTO processed_jobs (
                    raw_message_id, job_id, first_name, last_name, email,
                    company_name, job_role, location, eligibility,
                    application_method, jd_text, email_subject, status, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                job_data.get('raw_message_id'),
                job_data.get('job_id'),
                job_data.get('first_name'),
                job_data.get('last_name'),
                job_data.get('email'),
                job_data.get('company_name'),
                job_data.get('job_role'),
                job_data.get('location'),
                job_data.get('eligibility'),
                job_data.get('application_method'),
                job_data.get('jd_text'),
                job_data.get('email_subject'),
                job_data.get('status'),
                job_data.get('updated_at')
            ))
            return cursor.lastrowid
    
    def mark_job_synced(self, job_id: str):
        """Mark job as synced to Google Sheets"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                UPDATE processed_jobs 
                SET synced_to_sheets = 1
                WHERE job_id = ?
            ''', (job_id,))
    
    def get_config(self, key: str) -> Optional[str]:
        """Get config value"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT value FROM bot_config WHERE key = ?', (key,))
            row = cursor.fetchone()
            return row['value'] if row else None
    
    def set_config(self, key: str, value: str):
        """Set config value"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT OR REPLACE INTO bot_config (key, value, updated_at)
                VALUES (?, ?, CURRENT_TIMESTAMP)
            ''', (key, value))

    def get_unprocessed_count(self) -> int:
        """Get count of unprocessed messages"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT COUNT(*) FROM raw_messages WHERE status = \'unprocessed\'')
            return cursor.fetchone()[0]

    def get_jobs_today_stats(self) -> Dict:
        """Get statistics of jobs processed today."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT
                    COUNT(id) as total,
                    SUM(CASE WHEN application_method = 'email' THEN 1 ELSE 0 END) as with_email,
                    SUM(CASE WHEN application_method != 'email' THEN 1 ELSE 0 END) as without_email
                FROM processed_jobs
                WHERE DATE(created_at) = DATE('now')
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
                WHERE created_at >= date('now', '-' || ? || ' day')
                GROUP BY application_method
            """, (days,))
            by_method = {row['application_method']: row['count'] for row in cursor.fetchall()}

            cursor.execute("""
                SELECT
                    company_name, 
                    COUNT(id) as count
                FROM processed_jobs
                WHERE created_at >= date('now', '-' || ? || ' day')
                GROUP BY company_name
                ORDER BY count DESC
                LIMIT 5
            """, (days,))
            top_companies = {row['company_name']: row['count'] for row in cursor.fetchall()}

            return {
                "by_method": by_method,
                "top_companies": top_companies,
            }

    def get_processed_jobs_by_email_status(self, has_email: bool) -> List[Dict]:
        """Get processed jobs based on whether they have an email."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            if has_email:
                cursor.execute('SELECT * FROM processed_jobs WHERE email IS NOT NULL AND email != "" ORDER BY created_at DESC')
            else:
                cursor.execute('SELECT * FROM processed_jobs WHERE email IS NULL OR email == "" ORDER BY created_at DESC')
            return [dict(row) for row in cursor.fetchall()]

    def get_unsynced_jobs(self) -> List[Dict]:
        """Get all processed jobs that have not been synced to Google Sheets."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM processed_jobs WHERE synced_to_sheets = 0 ORDER BY created_at ASC')
            return [dict(row) for row in cursor.fetchall()]