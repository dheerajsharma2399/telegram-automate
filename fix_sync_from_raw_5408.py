#!/usr/bin/env python3
"""
Fix: Reset sync status for jobs from raw_message_id 5408 onwards
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from database import Database
from sheets_sync import GoogleSheetsSync
from config import DATABASE_URL, GOOGLE_CREDENTIALS_JSON, SPREADSHEET_ID

print("=" * 60)
print("Google Sheets Sync Fix - From Raw Message ID 5408")
print("=" * 60)

db = Database(DATABASE_URL)

# 1. Find jobs from raw_message_id 5408 onwards
print("\n1. Finding jobs from raw_message_id >= 5408:")
with db.get_connection() as conn:
    with conn.cursor() as cursor:
        cursor.execute("""
            SELECT COUNT(*) as count, MIN(id) as min_id, MAX(id) as max_id
            FROM processed_jobs WHERE raw_message_id >= 5408
        """)
        result = cursor.fetchone()
        total = result['count']
        min_id = result['min_id']
        max_id = result['max_id']
        
        print(f"   Total jobs: {total}")
        print(f"   Processed job ID range: {min_id} to {max_id}")
        
        cursor.execute("""
            SELECT COUNT(*) as count FROM processed_jobs 
            WHERE raw_message_id >= 5408 AND synced_to_sheets = FALSE
        """)
        unsynced = cursor.fetchone()['count']
        print(f"   Currently unsynced: {unsynced}")

# 2. Show sample
print("\n2. Sample Jobs:")
with db.get_connection() as conn:
    with conn.cursor() as cursor:
        cursor.execute("""
            SELECT id, raw_message_id, company_name, created_at, synced_to_sheets
            FROM processed_jobs 
            WHERE raw_message_id >= 5408 
            ORDER BY raw_message_id ASC 
            LIMIT 5
        """)
        for job in cursor.fetchall():
            sync = "✓" if job['synced_to_sheets'] else "✗"
            print(f"   Job ID {job['id']} (Raw Msg {job['raw_message_id']}) {sync} | {job['created_at']} | {job['company_name']}")

# 3. Reset sync status
print(f"\n3. Resetting sync status for {total} jobs (raw_message_id >= 5408)...")
with db.get_connection() as conn:
    with conn.cursor() as cursor:
        cursor.execute("""
            UPDATE processed_jobs 
            SET synced_to_sheets = FALSE 
            WHERE raw_message_id >= 5408
        """)
        updated = cursor.rowcount
    conn.commit()
print(f"   ✓ Reset {updated} jobs to unsynced")

# 4. Verify
print("\n4. Verification:")
with db.get_connection() as conn:
    with conn.cursor() as cursor:
        cursor.execute("SELECT COUNT(*) as count FROM processed_jobs WHERE synced_to_sheets = FALSE")
        total_unsynced = cursor.fetchone()['count']
        print(f"   Total unsynced jobs now: {total_unsynced}")

# 5. Test sync
print("\n5. Testing sync with first job...")
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
        print(f"   Remaining: {len(unsynced_jobs) - 1} jobs")
    else:
        print("   ✗ Test sync failed - check error above")

print("\n" + "=" * 60)
print("✅ Fix Complete!")
print("=" * 60)
print(f"\n{updated} jobs from raw_message_id 5408 onwards are now ready to sync.")
print("The bot will automatically sync them every 5 minutes.")
print("\nMonitor Dokploy logs to see sync progress.")
print("Check Google Sheets: https://docs.google.com/spreadsheets/d/1EhaQXeAyYSWU486DerVyiA67QFxMZWg6VynvjvBNi6g")
