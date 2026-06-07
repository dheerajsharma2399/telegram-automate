#!/usr/bin/env python3
"""Idempotent migration to v2 schema: raw_events, processing_queue, jobs extensions."""
import os, sys, logging
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from database import init_connection_pool, init_database
from config import DATABASE_URL
from dotenv import load_dotenv
load_dotenv()
logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger(__name__)

def verify():
    pool = init_connection_pool(DATABASE_URL)
    conn = pool.getconn()
    try:
        cur = conn.cursor()
        for table in ['raw_events', 'processing_queue', 'jobs']:
            cur.execute("SELECT EXISTS(SELECT 1 FROM information_schema.tables WHERE table_name=%s)", (table,))
            exists = cur.fetchone()['exists']
            logger.info(f"Table {table}: {'✓' if exists else '✗ MISSING'}")
        for col in ['confidence_score', 'job_fingerprint', 'normalized_role', 'search_vector', 'source_event_id']:
            cur.execute("SELECT EXISTS(SELECT 1 FROM information_schema.columns WHERE table_name='jobs' AND column_name=%s)", (col,))
            exists = cur.fetchone()['exists']
            logger.info(f" jobs.{col}: {'✓' if exists else '✗ MISSING'}")
        cur.close()
    finally:
        pool.putconn(conn)

if __name__ == '__main__':
    if not DATABASE_URL:
        logger.error("DATABASE_URL not set. Set in.env or environment.")
        sys.exit(1)
    logger.info("Starting migration to v2 schema.")
    pool = init_connection_pool(DATABASE_URL)
    init_database(pool)
    logger.info("Schema initialization complete")
    verify()
    logger.info("Migration done")
