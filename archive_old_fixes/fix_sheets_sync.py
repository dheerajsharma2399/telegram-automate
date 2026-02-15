#!/usr/bin/env python3
"""
Fix: Reset sync status for jobs starting from ID 3900 and trigger re-sync to Google Sheets
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from database import Database
from sheets_sync import GoogleSheetsSync
from config import DATABASE_URL, GOOGLE_CREDENTIALS_JSON, SPREADSHEET_ID

def main():
    print("=" * 60)
    print("Google Sheets Sync Fix - Starting from Job 3900")
    print("=" * 60)
    
    db = Database(DATABASE_URL)
    
    # 1. Check current status
    print("\n1. Current Status:")
    with db.get_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute("SELECT COUNT(*) as count FROM processed_jobs WHERE id >= 3900")
            total_from_3900 = cursor.fetchone()['count']
            
            cursor.execute("SELECT COUNT(*) as count FROM processed_jobs WHERE id >= 3900 AND synced_to_sheets = TRUE")
            synced_from_3900 = cursor.fetchone()['count']
            
            cursor.execute("SELECT COUNT(*) as count FROM processed_jobs WHERE id >= 3900 AND synced_to_sheets = FALSE")
            unsynced_from_3900 = cursor.fetchone()['count']
            
            print(f"   Jobs from ID 3900 onwards: {total_from_3900}")
            print(f"   Currently marked as synced: {synced_from_3900}")
            print(f"   Currently marked as unsynced: {unsynced_from_3900}")
    
    # 2. Show sample jobs from 3900 onwards
    print("\n2. Sample Jobs from ID 3900:")
    with db.get_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute("""
                SELECT id, job_id, company_name, job_role, created_at, synced_to_sheets 
                FROM processed_jobs 
                WHERE id >= 3900
                ORDER BY id ASC
                LIMIT 5
            """)
            jobs = cursor.fetchall()
            for job in jobs:
                sync_status = "✓" if job['synced_to_sheets'] else "✗"
                print(f"   ID {job['id']} {sync_status} | {job['created_at']} | {job['company_name']} - {job['job_role']}")
    
    # 3. Confirm action
    print(f"\n3. Action:")
    print(f"   This will reset sync status for {total_from_3900} jobs (ID >= 3900)")
    confirm = input("\n   Proceed? (yes/no): ").strip().lower()
    
    if confirm != "yes":
        print("   Cancelled.")
        return
    
    # 4. Reset sync status for jobs >= 3900
    print(f"\n4. Resetting sync status for jobs from ID 3900 onwards...")
    with db.get_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute("""
                UPDATE processed_jobs 
                SET synced_to_sheets = FALSE
                WHERE id >= 3900
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
            
            cursor.execute("SELECT MIN(id) as min_id, MAX(id) as max_id FROM processed_jobs WHERE synced_to_sheets = FALSE")
            result = cursor.fetchone()
            print(f"   ID range: {result['min_id']} to {result['max_id']}")
    
    # 6. Test sync with first unsynced job
    print("\n6. Testing sync with first job...")
    unsynced_jobs = db.jobs.get_unsynced_jobs()
    if unsynced_jobs:
        test_job = unsynced_jobs[0]
        print(f"   Testing with: {test_job.get('company_name')} - {test_job.get('job_role')}")
        
        sync = GoogleSheetsSync(GOOGLE_CREDENTIALS_JSON, SPREADSHEET_ID)
        result = sync.sync_job(test_job)
        
        if result:
            print("   ✓ Test sync successful!")
            db.jobs.mark_job_synced(test_job.get('job_id'))
            print("   ✓ Job marked as synced")
            print(f"\n   Remaining jobs to sync: {len(unsynced_jobs) - 1}")
        else:
            print("   ✗ Test sync failed - check the error above")
    
    print("\n" + "=" * 60)
    print("Fix Complete")
    print("=" * 60)
    print("\nNext steps:")
    print("1. The bot will automatically sync remaining jobs on next scheduled run")
    print("2. Or trigger manual sync via web dashboard (/process command)")
    print("3. Monitor the Dokploy logs to ensure syncing is working")
    print(f"4. Check Google Sheets: https://docs.google.com/spreadsheets/d/1EhaQXeAyYSWU486DerVyiA67QFxMZWg6VynvjvBNi6g")

if __name__ == "__main__":
    main()
