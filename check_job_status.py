#!/usr/bin/env python3
"""
Check database for job sync status and recent activity
"""
import sys
import os
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from database import Database
from config import DATABASE_URL

def main():
    print("=" * 60)
    print("Database Job Sync Status Check")
    print("=" * 60)
    
    db = Database(DATABASE_URL)
    
    # 1. Check total jobs
    print("\n1. Total Jobs in Database:")
    with db.get_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute("SELECT COUNT(*) as count FROM processed_jobs")
            total = cursor.fetchone()['count']
            print(f"   Total processed jobs: {total}")
            
            cursor.execute("SELECT COUNT(*) as count FROM processed_jobs WHERE synced_to_sheets = TRUE")
            synced = cursor.fetchone()['count']
            print(f"   Jobs marked as synced: {synced}")
            
            cursor.execute("SELECT COUNT(*) as count FROM processed_jobs WHERE synced_to_sheets = FALSE")
            unsynced = cursor.fetchone()['count']
            print(f"   Jobs NOT synced: {unsynced}")
    
    # 2. Check recent jobs (last 7 days)
    print("\n2. Recent Jobs (Last 7 Days):")
    with db.get_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute("""
                SELECT COUNT(*) as count FROM processed_jobs 
                WHERE created_at >= NOW() - INTERVAL '7 days'
            """)
            recent = cursor.fetchone()['count']
            print(f"   Jobs created in last 7 days: {recent}")
            
            cursor.execute("""
                SELECT COUNT(*) as count FROM processed_jobs 
                WHERE created_at >= NOW() - INTERVAL '7 days'
                AND synced_to_sheets = FALSE
            """)
            recent_unsynced = cursor.fetchone()['count']
            print(f"   Recent jobs NOT synced: {recent_unsynced}")
    
    # 3. Show sample of recent jobs
    print("\n3. Sample of Recent Jobs:")
    with db.get_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute("""
                SELECT job_id, company_name, job_role, synced_to_sheets, created_at, sheet_name
                FROM processed_jobs 
                ORDER BY created_at DESC 
                LIMIT 10
            """)
            jobs = cursor.fetchall()
            if jobs:
                for job in jobs:
                    sync_status = "✓ SYNCED" if job['synced_to_sheets'] else "✗ NOT SYNCED"
                    print(f"   {sync_status} | {job['created_at']} | {job['company_name']} | {job['job_role']} | Sheet: {job.get('sheet_name', 'N/A')}")
            else:
                print("   No jobs found")
    
    # 4. Check if there are jobs that should be synced but aren't
    print("\n4. Jobs That Should Be Synced:")
    with db.get_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute("""
                SELECT job_id, company_name, job_role, created_at, synced_to_sheets, sheet_name
                FROM processed_jobs 
                WHERE synced_to_sheets = FALSE
                ORDER BY created_at ASC
                LIMIT 5
            """)
            unsynced_jobs = cursor.fetchall()
            if unsynced_jobs:
                print(f"   Found {len(unsynced_jobs)} unsynced jobs:")
                for job in unsynced_jobs:
                    print(f"     - {job['job_id']} | {job['company_name']} | Created: {job['created_at']}")
            else:
                print("   ✓ All jobs are marked as synced")
    
    # 5. Check raw messages
    print("\n5. Message Processing Status:")
    with db.get_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute("SELECT COUNT(*) as count FROM raw_messages")
            total_messages = cursor.fetchone()['count']
            print(f"   Total raw messages: {total_messages}")
            
            cursor.execute("SELECT COUNT(*) as count FROM raw_messages WHERE status = 'unprocessed'")
            unprocessed = cursor.fetchone()['count']
            print(f"   Unprocessed messages: {unprocessed}")
            
            cursor.execute("SELECT COUNT(*) as count FROM raw_messages WHERE status = 'processed'")
            processed = cursor.fetchone()['count']
            print(f"   Processed messages: {processed}")
    
    print("\n" + "=" * 60)
    print("Analysis Complete")
    print("=" * 60)

if __name__ == "__main__":
    main()
