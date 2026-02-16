
import os
import logging
import time
from datetime import datetime, timedelta
import psycopg2
from psycopg2.extras import RealDictCursor
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Need to set Python path to include current directory
import sys
sys.path.append(os.getcwd())

from web_server import get_sheets_sync, db

def backfill_jobs(days=7):
    logger.info(f"Starting backfill for the past {days} days...")
    
    # 1. Initialize Sheets Sync
    sheets_sync = get_sheets_sync()
    if not sheets_sync:
        logger.error("Failed to initialize Google Sheets Sync.")
        return
    logger.info("Google Sheets Sync initialized.")

    # 2. Fetch jobs from DB
    jobs = []
    try:
        with db.get_connection() as conn:
            with conn.cursor() as cursor:
                # Use psycopg2 directly for query
                query = """
                    SELECT * FROM processed_jobs
                    WHERE created_at >= NOW() - INTERVAL '%s days'
                    ORDER BY created_at DESC
                """
                cursor.execute(query, (days,))
                # Convert to dict manually if RealDictCursor isn't default
                columns = [desc[0] for desc in cursor.description]
                jobs = [dict(zip(columns, row)) for row in cursor.fetchall()]
        
        logger.info(f"Found {len(jobs)} jobs in the last {days} days.")
    except Exception as e:
        logger.error(f"Failed to fetch jobs from database: {e}")
        import traceback
        traceback.print_exc()
        return

    if not jobs:
        logger.info("No jobs to sync.")
        return

    # 3. Sync Jobs
    synced_count = 0
    errors = 0
    
    logger.info("Syncing jobs... (This might take a while)")
    
    for i, job in enumerate(jobs):
        job_id = job.get('job_id')
        
        # Determine target sheet name (mimic logic from web_server.py)
        sheet_name = job.get('sheet_name')
        if not sheet_name:
            has_email = bool(job.get('email'))
            sheet_name = 'email' if has_email else 'non-email'
        elif sheet_name in ['email-exp', 'non-email-exp']:
             sheet_name = 'email' if 'email' in sheet_name else 'non-email'
        
        # Ensure job has sheet_name for sync logic
        if not job.get('sheet_name'):
            job['sheet_name'] = sheet_name

        try:
            # sync_job is now idempotent, so we just call it.
            # It returns True if synced/appended, False if failed.
            # Note: Our idempotent modification returns True if "already in sheet" too.
            success = sheets_sync.sync_job(job)
            
            if success:
                synced_count += 1
            else:
                logger.warning(f"Failed to sync job {job_id}")
                errors += 1
            
            # Simple progress
            if (i + 1) % 5 == 0:
                print(f"Processed {i+1}/{len(jobs)}...", end='\r')
                
        except Exception as e:
            logger.error(f"Error processing job {job_id}: {e}")
            errors += 1

    print() # Newline after progress
    logger.info("="*30)
    logger.info(f"Backfill Completed!")
    logger.info(f"Total Jobs Processed: {len(jobs)}")
    logger.info(f"Successfully Synced/Verified: {synced_count}")
    logger.info(f"Errors: {errors}")
    logger.info("="*30)

if __name__ == "__main__":
    backfill_jobs(7)
