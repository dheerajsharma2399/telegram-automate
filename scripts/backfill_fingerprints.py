#!/usr/bin/env python3
"""Backfill Job Fingerprints.

Iterates over all existing jobs, generates their unique fingerprint, 
and sets default values for Phase 4 extension columns if they are empty.
"""

import logging
import os
import sys

# Ensure project root is in path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import DATABASE_URL
from database import Database, init_database
from deduper import make_fingerprint
from normalizer import normalize_role

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

def main():
    if not DATABASE_URL:
        logger.error("DATABASE_URL is not configured")
        sys.exit(1)

    db = Database(DATABASE_URL)
    init_database(db.pool)

    logger.info("Starting backfill for existing jobs...")
    
    with db.get_connection() as conn:
        with conn.cursor() as cursor:
            # Query all jobs to update
            cursor.execute("SELECT id, company_name, job_role, location, job_fingerprint FROM jobs")
            jobs = cursor.fetchall()
            
            total = len(jobs)
            updated = 0
            skipped = 0
            
            logger.info("Found %d jobs in total to process", total)
            
            for job in jobs:
                job_id = job["id"]
                company = job["company_name"]
                role = job["job_role"]
                loc = job["location"]
                existing_fp = job["job_fingerprint"]
                
                # Generate new fingerprint
                fp = make_fingerprint(company, role, loc)
                norm_role = normalize_role(role)
                
                # Update job with the fingerprint and other extension values if null
                cursor.execute("""
                    UPDATE jobs
                    SET job_fingerprint = %s,
                        confidence_score = COALESCE(confidence_score, 1.0),
                        extraction_method = COALESCE(extraction_method, 'existing'),
                        normalized_role = COALESCE(normalized_role, %s),
                        role_category = COALESCE(role_category, %s)
                    WHERE id = %s
                """, (fp, norm_role, norm_role, job_id))
                
                if not existing_fp:
                    updated += 1
                else:
                    skipped += 1
                    
            conn.commit()
            
    logger.info("Backfill complete. Total: %d, Updated: %d, Skipped (already had fingerprint): %d", total, updated, skipped)

if __name__ == "__main__":
    main()
