#!/usr/bin/env python3
"""
Webhook Configuration for Telegram Bot
Sets up webhook for the new domain: https://job.mooh.me/
"""

import os
import asyncio
import requests
from config import TELEGRAM_BOT_TOKEN

async def set_webhook_for_domain():
    """Set webhook URL for the new domain"""
    
    if not TELEGRAM_BOT_TOKEN:
        print("❌ TELEGRAM_BOT_TOKEN not configured")
        return False
    
    # Use the new domain
    webhook_url = "https://job.mooh.me/webhook"
    backup_url = "https://152.67.7.111:9501/webhook"
    
    print(f"🔧 CONFIGURING WEBHOOK")
    print(f"📍 Primary URL: {webhook_url}")
    print(f"📍 Backup URL: {backup_url}")
    
    # Try setting webhook
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/setWebhook"
    payload = {
        "url": webhook_url,
        "allowed_updates": ["message", "callback_query", "edited_message"]
    }
    
    try:
        response = requests.post(url, json=payload, timeout=10)
        data = response.json()
        
        if data.get("ok"):
            print("✅ Webhook configured successfully!")
            print(f"📍 Webhook URL: {data.get('result', {}).get('url', 'N/A')}")
            print(f"🆔 Webhook ID: {data.get('result', {}).get('id', 'N/A')}")
            print(f"📊 Last Error Date: {data.get('result', {}).get('last_error_date', 'None')}")
            print(f"⚠️  Last Error Message: {data.get('result', {}).get('last_error_message', 'None')}")
            return True
        else:
            print(f"❌ Webhook setup failed: {data}")
            return False
            
    except Exception as e:
        print(f"❌ Error setting webhook: {e}")
        return False

async def get_current_webhook():
    """Get current webhook info"""
    
    if not TELEGRAM_BOT_TOKEN:
        print("❌ TELEGRAM_BOT_TOKEN not configured")
        return
    
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/getWebhookInfo"
    
    try:
        response = requests.get(url, timeout=10)
        data = response.json()
        
        if data.get("ok"):
            result = data.get("result", {})
            print("\n📊 CURRENT WEBHOOK STATUS:")
            print(f"📍 URL: {result.get('url', 'Not set')}")
            print(f"🆔 ID: {result.get('id', 'N/A')}")
            print(f"📅 Last Sync Date: {result.get('last_synchronization_date', 'N/A')}")
            print(f"📊 Pending Updates: {result.get('pending_update_count', 0)}")
            
            if result.get('last_error_date'):
                print(f"❌ Last Error: {result.get('last_error_date')} - {result.get('last_error_message', 'No message')}")
            else:
                print("✅ No recent errors")
        else:
            print(f"❌ Failed to get webhook info: {data}")
            
    except Exception as e:
        print(f"❌ Error getting webhook info: {e}")

async def remove_webhook():
    """Remove current webhook"""
    
    if not TELEGRAM_BOT_TOKEN:
        print("❌ TELEGRAM_BOT_TOKEN not configured")
        return False
    
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/deleteWebhook"
    
    try:
        response = requests.get(url, timeout=10)
        data = response.json()
        
        if data.get("ok"):
            print("✅ Webhook removed successfully")
            return True
        else:
            print(f"❌ Failed to remove webhook: {data}")
            return False
            
    except Exception as e:
        print(f"❌ Error removing webhook: {e}")
        return False

async def main():
    """Main function"""
    print("🤖 TELEGRAM BOT WEBHOOK CONFIGURATION")
    print("="*50)
    
    # Step 1: Check current webhook
    await get_current_webhook()
    
    # Step 2: Ask user what to do
    print("\nChoose an action:")
    print("1. Set webhook for https://job.mooh.me/")
    print("2. Remove current webhook")
    print("3. Exit")
    
    try:
        choice = input("\nEnter choice (1-3): ").strip()
        
        if choice == "1":
            print("\n🔄 Setting new webhook...")
            success = await set_webhook_for_domain()
            if success:
                print("\n🎉 Webhook configured! Your bot should now receive messages.")
                print("📝 Remember to test by sending a message to your bot.")
            else:
                print("\n❌ Failed to configure webhook")
        
        elif choice == "2":
            print("\n🗑️  Removing webhook...")
            success = await remove_webhook()
            if success:
                print("\n✅ Webhook removed. You can now set a new one.")
        
        elif choice == "3":
            print("\n👋 Exiting...")
        
        else:
            print("\n❌ Invalid choice")
    
    except KeyboardInterrupt:
        print("\n\n⏹️  Operation cancelled by user")
    except Exception as e:
        print(f"\n❌ Unexpected error: {e}")

if __name__ == "__main__":
    asyncio.run(main())