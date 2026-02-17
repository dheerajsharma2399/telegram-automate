import asyncio
import logging
from telethon import TelegramClient
from telethon.sessions import StringSession
from config import TELEGRAM_API_ID, TELEGRAM_API_HASH, DATABASE_URL
from database import Database

# Setup logging
logging.basicConfig(level=logging.INFO)

async def list_dialogs():
    print("--- Connecting to Database ---")
    db = Database(DATABASE_URL)
    session_string = db.auth.get_telegram_session()

    if not session_string:
        print("❌ No session found in database!")
        return

    print("--- Connecting to Telegram ---")
    client = TelegramClient(StringSession(session_string), int(TELEGRAM_API_ID), TELEGRAM_API_HASH)
    await client.connect()

    if not await client.is_user_authorized():
        print("❌ Session invalid/expired!")
        return

    me = await client.get_me()
    print(f"✅ Logged in as: {me.first_name} ({me.id})")

    print("\n--- Fetching Dialogs (Chats) ---")
    dialogs = await client.get_dialogs(limit=None) # Fetch ALL

    print(f"Found {len(dialogs)} dialogs.\n")
    print(f"{'ID':<15} | {'Type':<10} | {'Title'}")
    print("-" * 60)

    for d in dialogs:
        entity = d.entity
        type_str = "User"
        if entity.to_dict().get('_') == 'Channel':
            type_str = "Channel/Group"
        elif entity.to_dict().get('_') == 'Chat':
            type_str = "Group"

        print(f"{entity.id:<15} | {type_str:<10} | {d.title}")
        # Also print with -100 prefix if it's a channel, just in case
        if type_str == "Channel/Group":
             print(f"-100{entity.id:<11} | (Prefix)   | {d.title}")

    print("\n--- End of List ---")
    await client.disconnect()

if __name__ == "__main__":
    asyncio.run(list_dialogs())
