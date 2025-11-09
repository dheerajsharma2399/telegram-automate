#!/usr/bin/env python3
"""
Setup webhook environment for Dokploy deployment
Ensures webhook is configured with the correct domain
"""

import os
import asyncio
import aiohttp
from config import TELEGRAM_BOT_TOKEN

def setup_webhook_environment():
    """Set up environment variables for webhook configuration"""
    
    print("🔧 SETTING UP WEBHOOK ENVIRONMENT")
    print("="*50)
    
    # Set environment variables for webhook
    os.environ['WEBHOOK_URL'] = 'https://job.mooh.me/webhook'
    os.environ['CUSTOM_DOMAIN'] = 'https://job.mooh.me/'
    os.environ['BACKUP_WEBHOOK_URL'] = 'https://152.67.7.111:9501/webhook'
    
    print("✅ Environment variables set:")
    print(f"   WEBHOOK_URL: {os.environ['WEBHOOK_URL']}")
    print(f"   CUSTOM_DOMAIN: {os.environ['CUSTOM_DOMAIN']}")
    print(f"   BACKUP_WEBHOOK_URL: {os.environ['BACKUP_WEBHOOK_URL']}")
    
    return True

async def test_webhook_endpoint():
    """Test if webhook endpoint is accessible"""
    
    webhook_url = "https://job.mooh.me/webhook"
    backup_url = "https://152.67.7.111:9501/webhook"
    
    print(f"\n🧪 TESTING WEBHOOK ENDPOINTS")
    print("="*50)
    
    # Test webhook endpoints
    urls_to_test = [webhook_url, backup_url]
    
    for url in urls_to_test:
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as response:
                    if response.status == 405:  # Method Not Allowed (expected for POST endpoint)
                        print(f"✅ {url} - Accessible (POST required)")
                    elif response.status == 404:
                        print(f"❌ {url} - Not found (404)")
                    else:
                        print(f"⚠️  {url} - Status: {response.status}")
                        
        except Exception as e:
            print(f"❌ {url} - Error: {e}")

async def configure_webhook_telegram():
    """Configure webhook with Telegram using current environment"""
    
    if not TELEGRAM_BOT_TOKEN:
        print("❌ TELEGRAM_BOT_TOKEN not configured")
        return False
    
    webhook_url = "https://job.mooh.me/webhook"
    
    print(f"\n🤖 CONFIGURING TELEGRAM WEBHOOK")
    print("="*50)
    print(f"📍 Webhook URL: {webhook_url}")
    
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/setWebhook"
    payload = {
        "url": webhook_url,
        "allowed_updates": ["message", "callback_query", "edited_message"]
    }
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload) as response:
                data = await response.json()
                
                if data.get("ok"):
                    print("✅ Webhook configured successfully!")
                    result = data.get("result", {})
                    print(f"📍 Webhook URL: {result.get('url', 'N/A')}")
                    print(f"🆔 Webhook ID: {result.get('id', 'N/A')}")
                    
                    if result.get('last_error_date'):
                        print(f"⚠️  Last Error: {result.get('last_error_message', 'Unknown error')}")
                    else:
                        print("✅ No recent errors")
                    
                    return True
                else:
                    print(f"❌ Webhook setup failed: {data}")
                    return False
                    
    except Exception as e:
        print(f"❌ Error setting webhook: {e}")
        return False

async def main():
    """Main setup function"""
    
    print("🚀 WEBHOOK SETUP FOR DOKPLOY DEPLOYMENT")
    print("="*60)
    
    # Step 1: Setup environment
    setup_webhook_environment()
    
    # Step 2: Test endpoints
    await test_webhook_endpoint()
    
    # Step 3: Configure Telegram webhook
    success = await configure_webhook_telegram()
    
    if success:
        print("\n🎉 WEBHOOK SETUP COMPLETE!")
        print("\n📋 NEXT STEPS:")
        print("1. Deploy to Dokploy with updated environment")
        print("2. Test webhook by messaging your bot")
        print("3. Check bot logs for any webhook errors")
        print("\n🔗 Your bot should now receive messages at:")
        print("   Primary: https://job.mooh.me/")
        print("   Backup: https://152.67.7.111:9501/")
    else:
        print("\n❌ Webhook setup failed. Please check:")
        print("1. TELEGRAM_BOT_TOKEN is configured")
        print("2. Your domain is accessible")
        print("3. Webhook endpoint is responding")

if __name__ == "__main__":
    asyncio.run(main())