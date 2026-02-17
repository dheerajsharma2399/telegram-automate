import psycopg2
from config import DATABASE_URL, TELEGRAM_GROUP_USERNAMES

def reset_config():
    # Define the IDs explicitly to be safe
    # -1002947896517 (Premium Referrals)
    # -4919334395 (my group for jobs)
    correct_groups = "-1002947896517,-4919334395"

    # Or rely on config if you trust it now
    if TELEGRAM_GROUP_USERNAMES:
        print(f"Using groups from config: {TELEGRAM_GROUP_USERNAMES}")
        # Ensure they are joined as string
        if isinstance(TELEGRAM_GROUP_USERNAMES, list):
            correct_groups = ",".join([str(g) for g in TELEGRAM_GROUP_USERNAMES])
        else:
            correct_groups = str(TELEGRAM_GROUP_USERNAMES)

    print(f"Connecting to DB...")
    conn = psycopg2.connect(DATABASE_URL)
    cursor = conn.cursor()

    print(f"Setting monitored_groups to: {correct_groups}")

    query = """
        INSERT INTO bot_config (key, value, updated_at)
        VALUES ('monitored_groups', %s, CURRENT_TIMESTAMP)
        ON CONFLICT (key) DO UPDATE SET
        value = EXCLUDED.value,
        updated_at = EXCLUDED.updated_at
    """

    cursor.execute(query, (correct_groups,))
    conn.commit()

    print("✅ Configuration updated successfully!")

    # Verify
    cursor.execute("SELECT value FROM bot_config WHERE key = 'monitored_groups'")
    val = cursor.fetchone()[0]
    print(f"Current value in DB: {val}")

    conn.close()

if __name__ == "__main__":
    reset_config()
