#!/usr/bin/env python3
"""
Find the correct job ID range for Feb 8 onwards
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from database import Database
from config import DATABASE_URL

def main():
    print("=" * 60)
    print("Finding Job ID Range for Feb 8 Onwards")
    print("=" * 60)
    
    db = Database(DATABASE_URL)
    
    with db.get_connection() as conn:
        with conn.cursor() as cursor:
            # Get max job ID
            cursor.execute("SELECT MAX(id) as max_id, MIN(id) as min_id FROM processed_jobs")
            result = cursor.fetchone()
            print(f"\n1. Job ID Range in Database:")
            print(f"   Min ID: {result['min_id']}")
            print(f"   Max ID: {result['max_id']}")
            
            # Get jobs around Feb 8
            cursor.execute("""
                SELECT id, job_id, company_name, created_at, synced_to_sheets
                FROM processed_jobs
                WHERE created_at >= '2026-02-08'::date
                AND created_at < '2026-02-09'::date
                ORDER BY id ASC
                LIMIT 10
            """)
            feb8_jobs = cursor.fetchall()
            
            print(f"\n2. Jobs Created on Feb 8, 2026:")
            if feb8_jobs:
                print(f"   Found {len(feb8_jobs)} jobs (showing first 10):")
                for job in feb8_jobs:
                    sync_status = "✓" if job['synced_to_sheets'] else "✗"
                    print(f"   ID {job['id']} {sync_status} | {job['created_at']} | {job['company_name']}")
                
                first_id = feb8_jobs[0]['id']
                last_id = feb8_jobs[-1]['id']
                print(f"\n   First job on Feb 8: ID {first_id}")
                print(f"   Last job shown: ID {last_id}")
            else:
                print("   No jobs found on Feb 8, 2026")
            
            # Get jobs from Feb 8 onwards
            cursor.execute("""
                SELECT COUNT(*) as count, MIN(id) as min_id, MAX(id) as max_id
                FROM processed_jobs
                WHERE created_at >= '2026-02-08'::date
            """)
            feb8_onwards = cursor.fetchone()
            
            print(f"\n3. Jobs from Feb 8 Onwards:")
            print(f"   Total jobs: {feb8_onwards['count']}")
            print(f"   ID range: {feb8_onwards['min_id']} to {feb8_onwards['max_id']}")
            
            # Check sync status
            cursor.execute("""
                SELECT COUNT(*) as count
                FROM processed_jobs
                WHERE created_at >= '2026-02-08'::date
                AND synced_to_sheets = FALSE
            """)
            unsynced = cursor.fetchone()['count']
            print(f"   Unsynced: {unsynced}")
            
            # Get most recent jobs
            cursor.execute("""
                SELECT id, job_id, company_name, created_at, synced_to_sheets
                FROM processed_jobs
                ORDER BY created_at DESC
                LIMIT 5
            """)
            recent = cursor.fetchall()
            
            print(f"\n4. Most Recent Jobs:")
            for job in recent:
                sync_status = "✓" if job['synced_to_sheets'] else "✗"
                print(f"   ID {job['id']} {sync_status} | {job['created_at']} | {job['company_name']}")
    
    print("\n" + "=" * 60)

if __name__ == "__main__":
    main()
