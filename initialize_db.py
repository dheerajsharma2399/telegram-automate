import logging
from database import init_connection_pool, init_database
from config import DATABASE_URL

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

if __name__ == "__main__":
    logger.info("Starting database initialization...")
    try:
        pool = init_connection_pool(DATABASE_URL)
        init_database(pool)
        logger.info("Database initialization completed successfully.")
    except Exception as e:
        logger.error(f"Database initialization failed: {e}")
        exit(1)
