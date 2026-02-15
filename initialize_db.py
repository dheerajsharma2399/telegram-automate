import logging
import sys
from database import init_connection_pool, init_database

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

if __name__ == "__main__":
    logger.info("Starting database initialization...")
    
    try:
        from config import DATABASE_URL
        
        if not DATABASE_URL:
            logger.warning("DATABASE_URL is not set. Skipping database initialization.")
            sys.exit(0)
            
        pool = init_connection_pool(DATABASE_URL)
        init_database(pool)
        logger.info("Database initialization completed successfully.")
    except ValueError as e:
        # Config validation failed - this is expected in build environments
        logger.warning(f"Configuration validation failed: {e}")
        logger.warning("Skipping database initialization (likely build environment).")
        sys.exit(0)
    except Exception as e:
        logger.error(f"Database initialization failed: {e}")
        sys.exit(1)
