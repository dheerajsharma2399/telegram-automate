
import os
import sys

# Add root directory to path FIRST
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database import Database
from config import DATABASE_URL
db = Database(DATABASE_URL)

def reset_todays_messages():
    print("Resetting status of today's messages to 'unprocessed'...")
    with db.get_connection() as conn:
        with conn.cursor() as cursor:
            # Count them first
            cursor.execute("""
                SELECT COUNT(*) as count FROM raw_messages 
                WHERE created_at::date = CURRENT_DATE 
                AND status = 'processed'
            """)
            count = cursor.fetchone()['count']
            print(f"Found {count} processed messages from today.")
            
            if count > 0:
                cursor.execute("""
                    UPDATE raw_messages 
                    SET status = 'unprocessed', error_message = NULL
                    WHERE created_at::date = CURRENT_DATE 
                    AND status = 'processed'
                """)
                conn.commit()
                print(f"✅ Reset {cursor.rowcount} messages to 'unprocessed'.")
                print("The main worker should pick them up in the next cycle.")
            else:
                print("No processed messages found to reset.")

if __name__ == "__main__":
    reset_todays_messages()
