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

        # Seed initial configuration from environment
        try:
            from config import TELEGRAM_GROUP_USERNAMES
            from database_repositories import ConfigRepository

            config_repo = ConfigRepository(pool)
            current_groups = config_repo.get_config('monitored_groups')

            if not current_groups and TELEGRAM_GROUP_USERNAMES:
                initial_groups = ",".join(TELEGRAM_GROUP_USERNAMES)
                config_repo.set_config('monitored_groups', initial_groups)
                logger.info(f"Seeded monitored_groups from environment: {initial_groups}")
            elif current_groups:
                logger.info(f"monitored_groups already set in DB: {current_groups}")
            else:
                logger.warning("No TELEGRAM_GROUP_USERNAMES found in environment to seed.")

        except Exception as e:
            logger.error(f"Failed to seed configuration: {e}")

        logger.info("Database initialization completed successfully.")
    except ValueError as e:
        # Config validation failed - this is expected in build environments
        logger.warning(f"Configuration validation failed: {e}")
        logger.warning("Skipping database initialization (likely build environment).")
        sys.exit(0)
    except Exception as e:
        logger.error(f"Database initialization failed: {e}")
        sys.exit(1)
