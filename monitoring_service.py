#!/usr/bin/env python3
"""
Telegram API Monitoring Service
Runs independently from the bot - handles message monitoring only
Bot handles commands and alerts
"""

import asyncio
import logging
import signal
import sys
from datetime import datetime
from database import Database
from config import DATABASE_URL, TELEGRAM_API_ID, TELEGRAM_API_HASH, TELEGRAM_PHONE
from telegram_api_monitor import TelegramAPIMonitor
import os

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("monitoring_service.log"),
        logging.StreamHandler()
    ]
)

logger = logging.getLogger(__name__)

class MonitoringService:
    def __init__(self):
        self.db = None
        self.monitor = None
        self.is_running = False
        self.monitoring_task = None
        
    async def initialize(self):
        """Initialize the monitoring service"""
        try:
            logger.info("🔧 Initializing Telegram API Monitoring Service...")
            
            # Initialize database
            self.db = Database(DATABASE_URL)
            logger.info("✅ Database initialized")
            
            # Create monitor
            self.monitor = TelegramAPIMonitor(
                TELEGRAM_API_ID,
                TELEGRAM_API_HASH,
                TELEGRAM_PHONE,
                self.db
            )
            logger.info("✅ Telegram API Monitor created")
            
            # Update service status
            self.db.set_config('monitoring_service_status', 'starting')
            logger.info("✅ Service initialized successfully")
            
        except Exception as e:
            logger.error(f"❌ Failed to initialize service: {e}")
            if self.db:
                self.db.set_config('monitoring_service_status', 'failed')
            raise
    
    async def start(self):
        """Start the monitoring service"""
        try:
            logger.info("🚀 Starting Telegram API Monitoring Service...")
            
            if not self.monitor:
                await self.initialize()
            
            self.is_running = True
            self.db.set_config('monitoring_service_status', 'running')
            self.db.set_config('monitoring_service_started', datetime.now().isoformat())
            
            # Start monitoring in background task
            self.monitoring_task = asyncio.create_task(self.monitor.monitor_messages())
            
            logger.info("✅ Monitoring service started successfully")
            logger.info("📡 Telegram API monitoring is now active")
            logger.info("🤖 Bot commands and alerts are handled separately")
            
            # Wait for monitoring to complete
            await self.monitoring_task
            
        except asyncio.CancelledError:
            logger.info("🛑 Monitoring service cancelled")
        except Exception as e:
            logger.error(f"❌ Error in monitoring service: {e}")
            self.db.set_config('monitoring_service_status', 'error')
        finally:
            await self.stop()
    
    async def stop(self):
        """Stop the monitoring service"""
        logger.info("🛑 Stopping Telegram API Monitoring Service...")
        
        self.is_running = False
        
        if self.monitor:
            self.monitor.stop()
        
        if self.monitoring_task and not self.monitoring_task.done():
            self.monitoring_task.cancel()
            try:
                await self.monitoring_task
            except asyncio.CancelledError:
                pass
        
        if self.db:
            self.db.set_config('monitoring_service_status', 'stopped')
        
        logger.info("👋 Monitoring service stopped")

# Service instance
service = MonitoringService()

async def main():
    """Main service entry point"""
    try:
        # Setup signal handlers for graceful shutdown
        def signal_handler(signum, frame):
            logger.info(f"🛑 Received signal {signum}, shutting down gracefully...")
            service.is_running = False
        
        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)
        
        # Start the service
        await service.start()
        
    except KeyboardInterrupt:
        logger.info("🛑 Service interrupted by user")
    except Exception as e:
        logger.error(f"❌ Service error: {e}")
    finally:
        await service.stop()
        logger.info("👋 Service shutdown complete")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("👋 Service stopped by user")
        sys.exit(0)
    except Exception as e:
        print(f"❌ Service failed: {e}")
        sys.exit(1)