
import os
import sys

# Add root directory to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database import Database
from config import DATABASE_URL

db = Database(DATABASE_URL)

def check_raw_messages():
    print("Checking raw_messages table...")
    with db.get_connection() as conn:
        with conn.cursor() as cursor:
            # Check total count
            cursor.execute("SELECT COUNT(*) as count FROM raw_messages")
            total = cursor.fetchone()['count']
            print(f"Total entries: {total}")

            # Check status distribution
            cursor.execute("SELECT status, COUNT(*) as count FROM raw_messages GROUP BY status")
            stats = cursor.fetchall()
            print("\nStatus Distribution:")
            for row in stats:
                print(f" - {row['status']}: {row['count']}")

            # Check last 10 messages with text preview
            print("\nLast 10 Messages (Text Preview):")
            cursor.execute("SELECT id, message_id, left(message_text, 100) as preview, length(message_text) as len FROM raw_messages ORDER BY sent_at DESC LIMIT 10")
            rows = cursor.fetchall()
            for r in rows:
                print(f"ID: {r['id']} | Len: {r['len']} | Text: {r['preview']}")

            # Check Jobs count
            print("\n--- jobs table ---")
            cursor.execute("SELECT COUNT(*) as count FROM jobs")
            total_jobs = cursor.fetchone()['count']
            print(f"Total jobs: {total_jobs}")

            # Check last 5 jobs
            print("\nLast 5 Jobs:")
            cursor.execute("SELECT id, job_id, company_name, created_at FROM jobs ORDER BY created_at DESC LIMIT 5")
            rows = cursor.fetchall()
            for r in rows:
                print(r)

if __name__ == "__main__":
    check_raw_messages()
