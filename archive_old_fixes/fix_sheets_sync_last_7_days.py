#!/usr/bin/env python3
"""
Fix: Reset sync status for jobs from last 7 days and trigger re-sync to Google Sheets
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from database import Database
from sheets_sync import GoogleSheetsSync
from config import DATABASE_URL, GOOGLE_CREDENTIALS_JSON, SPREADSHEET_ID

def main():
    print("=" * 60)
    print("Google Sheets Sync Fix - Last 7 Days")
    print("=" * 60)
    
    db = Database(DATABASE_URL)
    
    # 1. Check current status
    print("\n1. Current Status:")
    with db.get_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute("""
                SELECT COUNT(*) as count FROM processed_jobs 
                WHERE created_at >= NOW() - INTERVAL '7 days'
            """)
            total_last_7_days = cursor.fetchone()['count']
            
            cursor.execute("""
                SELECT COUNT(*) as count FROM processed_jobs 
                WHERE created_at >= NOW() - INTERVAL '7 days' 
                AND synced_to_sheets = TRUE
            """)
            synced_last_7_days = cursor.fetchone()['count']
            
            cursor.execute("""
                SELECT COUNT(*) as count FROM processed_jobs 
                WHERE created_at >= NOW() - INTERVAL '7 days' 
                AND synced_to_sheets = FALSE
            """)
            unsynced_last_7_days = cursor.fetchone()['count']
            
            print(f"   Jobs from last 7 days: {total_last_7_days}")
            print(f"   Currently marked as synced: {synced_last_7_days}")
            print(f"   Currently marked as unsynced: {unsynced_last_7_days}")
    
    # 2. Show sample jobs from last 7 days
    print("\n2. Sample Jobs from Last 7 Days:")
    with db.get_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute("""
                SELECT id, job_id, company_name, job_role, created_at, synced_to_sheets 
                FROM processed_jobs 
                WHERE created_at >= NOW() - INTERVAL '7 days'
                ORDER BY created_at DESC
                LIMIT 5
            """)
            jobs = cursor.fetchall()
            if jobs:
                for job in jobs:
                    sync_status = "✓" if job['synced_to_sheets'] else "✗"
                    print(f"   ID {job['id']} {sync_status} | {job['created_at']} | {job['company_name']} - {job['job_role']}")
            else:
                print("   No jobs found in last 7 days")
                return
    
    # 3. Confirm action
    print(f"\n3. Action:")
    print(f"   This will reset sync status for {total_last_7_days} jobs from the last 7 days")
    confirm = input("\n   Proceed? (yes/no): ").strip().lower()
    
    if confirm != "yes":
        print("   Cancelled.")
        return
    
    # 4. Reset sync status for jobs from last 7 days
    print(f"\n4. Resetting sync status for jobs from last 7 days...")
    with db.get_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute("""
                UPDATE processed_jobs 
                SET synced_to_sheets = FALSE
                WHERE created_at >= NOW() - INTERVAL '7 days'
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
            
            cursor.execute("""
                SELECT MIN(created_at) as oldest, MAX(created_at) as newest 
                FROM processed_jobs 
                WHERE synced_to_sheets = FALSE
            """)
            result = cursor.fetchone()
            print(f"   Date range: {result['oldest']} to {result['newest']}")
    
    # 6. Test sync with first unsynced job
    print("\n6. Testing sync with first job...")
    unsynced_jobs = db.jobs.get_unsynced_jobs()
    if unsynced_jobs:
        test_job = unsynced_jobs[0]
        print(f"   Testing with: {test_job.get('company_name')} - {test_job.get('job_role')}")
        print(f"   Sheet destination: {test_job.get('sheet_name', 'N/A')}")
        
        sync = GoogleSheetsSync(GOOGLE_CREDENTIALS_JSON, SPREADSHEET_ID)
        result = sync.sync_job(test_job)
        
        if result:
            print("   ✓ Test sync successful!")
            db.jobs.mark_job_synced(test_job.get('job_id'))
            print("   ✓ Job marked as synced in database")
            print(f"\n   Remaining jobs to sync: {len(unsynced_jobs) - 1}")
        else:
            print("   ✗ Test sync failed - check the error above")
    
    print("\n" + "=" * 60)
    print("Fix Complete")
    print("=" * 60)
    print("\nNext steps:")
    print("1. The bot will automatically sync remaining jobs on next scheduled run (every 5 min)")
    print("2. Or trigger manual sync via Telegram bot: send /process command")
    print("3. Monitor the Dokploy logs to ensure syncing is working")
    print(f"4. Check Google Sheets: https://docs.google.com/spreadsheets/d/1EhaQXeAyYSWU486DerVyiA67QFxMZWg6VynvjvBNi6g")

if __name__ == "__main__":
    main()
