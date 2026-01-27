import logging
from database import Database
from config import DATABASE_URL

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def add_salary_columns():
    db = Database(DATABASE_URL)
    with db.get_connection() as conn:
        with conn.cursor() as cursor:
            try:
                # Add salary to processed_jobs
                logger.info("Adding salary column to processed_jobs...")
                cursor.execute("""
                    ALTER TABLE processed_jobs
                    ADD COLUMN IF NOT EXISTS salary TEXT;
                """)
                
                # Add salary to dashboard_jobs
                logger.info("Adding salary column to dashboard_jobs...")
                cursor.execute("""
                    ALTER TABLE dashboard_jobs
                    ADD COLUMN IF NOT EXISTS salary TEXT;
                """)
                
                conn.commit()
                logger.info("Successfully added salary columns.")
            except Exception as e:
                conn.rollback()
                logger.error(f"Failed to add salary columns: {e}")

if __name__ == "__main__":
    add_salary_columns()
