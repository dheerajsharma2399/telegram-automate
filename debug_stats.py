#!/usr/bin/env python3
"""
Debug script to diagnose stats discrepancies
Run: python3 debug_stats.py
"""
import os
import sys
sys.path.insert(0, '/workspace/telegram-automate')

from database import Database

def debug_stats():
    db = Database(os.getenv('DATABASE_URL', 'postgresql://postgres:postgres@localhost:5432/telegram_bot'))
    
    print("=" * 60)
    print("DASHBOARD STATS DEBUG")
    print("=" * 60)
    
    # 1. Check unprocessed messages
    unprocessed = db.messages.get_unprocessed_count()
    print(f"\n📨 Unprocessed messages: {unprocessed}")
    
    # 2. Get today's stats
    today_stats = db.jobs.get_jobs_today_stats()
    print(f"\n📊 Jobs Today Stats:")
    print(f"   Total: {today_stats['total']}")
    print(f"   From Telegram: {today_stats['telegram']}")
    print(f"   Manual: {today_stats['manual']}")
    print(f"   With Email: {today_stats['with_email']}")
    print(f"   Without Email: {today_stats.get('without_email', 'N/A')}")
    
    # 3. Check for processing/failed messages
    with db.get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT 
                status,
                COUNT(*) as count
            FROM raw_messages
            WHERE created_at::date = CURRENT_DATE
            GROUP BY status
        """)
        results = cursor.fetchall()
        print(f"\n📥 Today's Messages by Status:")
        for row in results:
            print(f"   {row['status']}: {row['count']}")
    
    # 4. Check for duplicates
    with db.get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT 
                COUNT(*) as duplicate_count
            FROM jobs
            WHERE created_at::date = CURRENT_DATE
            AND is_duplicate = TRUE
        """)
        result = cursor.fetchone()
        print(f"\n🔄 Duplicate jobs today: {result['duplicate_count']}")
    
    # 5. Check timezone
    with db.get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SHOW timezone;")
        tz = cursor.fetchone()
        print(f"\n🌍 Database Timezone: {tz['timezone']}")
        
        cursor.execute("SELECT CURRENT_DATE, NOW();")
        dt = cursor.fetchone()
        print(f"   Current Date: {dt['current_date']}")
        print(f"   Current Time: {dt['now']}")
    
    # 6. Calculate expected vs actual
    with db.get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT COUNT(*) as total_messages
            FROM raw_messages
            WHERE created_at::date = CURRENT_DATE
        """)
        total_msgs = cursor.fetchone()['total_messages']
        
        cursor.execute("""
            SELECT COUNT(*) as processed_jobs
            FROM jobs
            WHERE created_at::date = CURRENT_DATE
            AND source = 'telegram'
        """)
        processed_jobs = cursor.fetchone()['processed_jobs']
        
        print(f"\n📈 Analysis:")
        print(f"   Total messages fetched today: {total_msgs}")
        print(f"   Jobs created from messages: {processed_jobs}")
        print(f"   Conversion rate: {(processed_jobs/total_msgs*100) if total_msgs > 0 else 0:.1f}%")
        if total_msgs > processed_jobs:
            print(f"   ⚠️  {total_msgs - processed_jobs} messages didn't create jobs")
            print(f"      Possible reasons: duplicates, failed parsing, or filtered")
    
    print("\n" + "=" * 60)
    print("RECOMMENDATIONS:")
    print("=" * 60)
    print("""
1. If Unprocessed Messages > 0: Worker may not be processing
2. If processed_jobs < total_messages: Check logs for parsing failures
3. If duplicates high: Deduplication is working correctly
4. Check container logs: docker-compose logs worker
    """)

if __name__ == "__main__":
    debug_stats()
