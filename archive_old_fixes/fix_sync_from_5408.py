#!/usr/bin/env python3
"""
Fix: Reset sync status for jobs from ID 5408 onwards (Feb 8 onwards)
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from database import Database
from sheets_sync import GoogleSheetsSync
from config import DATABASE_URL, GOOGLE_CREDENTIALS_JSON, SPREADSHEET_ID

def main():
    print("=" * 60)
    print("Google Sheets Sync Fix - From Job ID 5408 (Feb 8 onwards)")
    print("=" * 60)
    
    db = Database(DATABASE_URL)
    
    # 1. Check current status
    print("\n1. Current Status:")
    with db.get_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute("SELECT COUNT(*) as count FROM processed_jobs WHERE id >= 5408")
            total_from_5408 = cursor.fetchone()['count']
            
            cursor.execute("SELECT COUNT(*) as count FROM processed_jobs WHERE id >= 5408 AND synced_to_sheets = TRUE")
            synced = cursor.fetchone()['count']
            
            cursor.execute("SELECT COUNT(*) as count FROM processed_jobs WHERE id >= 5408 AND synced_to_sheets = FALSE")
            unsynced = cursor.fetchone()['count']
            
            cursor.execute("SELECT MIN(created_at) as oldest, MAX(created_at) as newest FROM processed_jobs WHERE id >= 5408")
            dates = cursor.fetchone()
            
            print(f"   Jobs from ID 5408 onwards: {total_from_5408}")
            print(f"   Date range: {dates['oldest']} to {dates['newest']}")
            print(f"   Currently marked as synced: {synced}")
            print(f"   Currently marked as unsynced: {unsynced}")
    
    # 2. Show sample jobs
    print("\n2. Sample Jobs from ID 5408:")
    with db.get_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute("""
                SELECT id, job_id, company_name, job_role, created_at, synced_to_sheets, sheet_name
                FROM processed_jobs 
                WHERE id >= 5408
                ORDER BY id ASC
                LIMIT 5
            """)
            jobs = cursor.fetchall()
            if jobs:
                for job in jobs:
                    sync_status = "✓" if job['synced_to_sheets'] else "✗"
                    print(f"   ID {job['id']} {sync_status} | {job['created_at']} | {job['company_name']} | Sheet: {job.get('sheet_name', 'N/A')}")
            else:
                print("   No jobs found from ID 5408")
                return
    
    # 3. Confirm action
    print(f"\n3. Action:")
    print(f"   This will reset sync status for {total_from_5408} jobs (ID >= 5408)")
    confirm = input("\n   Proceed? (yes/no): ").strip().lower()
    
    if confirm != "yes":
        print("   Cancelled.")
        return
    
    # 4. Reset sync status
    print(f"\n4. Resetting sync status for jobs from ID 5408 onwards...")
    with db.get_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute("""
                UPDATE processed_jobs 
                SET synced_to_sheets = FALSE
                WHERE id >= 5408
            """)
            updated_count = cursor.rowcount
        conn.commit()
    
    print(f"   ✓ Reset {updated_count} jobs to unsynced status")
    
    # 5. Verify
    print("\n5. New Status:")
    with db.get_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute("SELECT COUNT(*) as count FROM processed_jobs WHERE synced_to_sheets = FALSE")
            unsynced_now = cursor.fetchone()['count']
            print(f"   Total jobs ready to sync: {unsynced_now}")
    
    # 6. Test sync
    print("\n6. Testing sync with first job...")
    unsynced_jobs = db.jobs.get_unsynced_jobs()
    if unsynced_jobs:
        test_job = unsynced_jobs[0]
        print(f"   Testing: {test_job.get('company_name')} - {test_job.get('job_role')}")
        print(f"   Sheet: {test_job.get('sheet_name', 'N/A')}")
        
        sync = GoogleSheetsSync(GOOGLE_CREDENTIALS_JSON, SPREADSHEET_ID)
        result = sync.sync_job(test_job)
        
        if result:
            print("   ✓ Test sync successful!")
            db.jobs.mark_job_synced(test_job.get('job_id'))
            print(f"\n   Remaining: {len(unsynced_jobs) - 1} jobs")
        else:
            print("   ✗ Test sync failed")
    
    print("\n" + "=" * 60)
    print("Fix Complete - Jobs will auto-sync every 5 minutes")
    print("=" * 60)

if __name__ == "__main__":
    main()
