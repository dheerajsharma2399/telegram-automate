#!/usr/bin/env python3
"""
Message Text Extraction Utilities
Shared utilities for extracting text from both direct and forwarded messages
"""

import asyncio
import logging
import os
import tempfile
import functools
import time
from typing import Optional, Any, Callable
import aiohttp
from config import TELEGRAM_BOT_TOKEN, ADMIN_USER_ID

logger = logging.getLogger(__name__)

def log_execution(func: Callable) -> Callable:
    """
    Decorator to log the start, end, and duration of a function execution.
    Also logs any exceptions raised by the function.
    Supports both synchronous and asynchronous functions.
    """
    @functools.wraps(func)
    def sync_wrapper(*args, **kwargs):
        func_name = func.__name__
        logger.info(f"▶️ START: {func_name}")
        start_time = time.time()
        try:
            result = func(*args, **kwargs)
            duration = time.time() - start_time
            logger.info(f"✅ END: {func_name} (took {duration:.2f}s)")
            return result
        except Exception as e:
            duration = time.time() - start_time
            logger.error(f"❌ ERROR: {func_name} failed after {duration:.2f}s: {e}", exc_info=True)
            raise

    @functools.wraps(func)
    async def async_wrapper(*args, **kwargs):
        func_name = func.__name__
        logger.info(f"▶️ START (Async): {func_name}")
        start_time = time.time()
        try:
            result = await func(*args, **kwargs)
            duration = time.time() - start_time
            logger.info(f"✅ END (Async): {func_name} (took {duration:.2f}s)")
            return result
        except Exception as e:
            duration = time.time() - start_time
            logger.error(f"❌ ERROR (Async): {func_name} failed after {duration:.2f}s: {e}", exc_info=True)
            raise

    if asyncio.iscoroutinefunction(func):
        return async_wrapper
    else:
        return sync_wrapper

def extract_message_text(message) -> str:
    """
    Extract text from a Telegram message, handling all message types.
    
    In Telethon:
    - message.message contains the text content (primary field)
    - message.text is a property that formats entities
    - Forwarded messages still have text in message.message
    - Media messages may have captions
    
    Args:
        message: Telethon message object
        
    Returns:
        str: Extracted text content, or empty string if none found
    """
    try:
        # Try message.message first (this is the actual text field in Telethon)
        if hasattr(message, 'message') and message.message:
            text = message.message.strip() if isinstance(message.message, str) else str(message.message).strip()
            if text:
                return text
        
        # Try message.raw_text (often the most reliable for full text)
        if hasattr(message, 'raw_text') and message.raw_text:
            text = message.raw_text.strip()
            if text:
                return text
        
        # Try message.text (formatted with entities)
        if hasattr(message, 'text') and message.text:
            text = message.text.strip() if isinstance(message.text, str) else str(message.text).strip()
            if text:
                return text
        
        # Try caption for media messages (photos, videos, documents, etc.)
        if hasattr(message, 'caption') and message.caption:
            text = message.caption.strip() if isinstance(message.caption, str) else str(message.caption).strip()
            if text:
                return text
        
        # Handle poll messages
        if hasattr(message, 'media') and message.media:
            # Check for poll
            if hasattr(message.media, 'poll') and message.media.poll:
                poll = message.media.poll
                if hasattr(poll, 'question') and poll.question:
                    return f"Poll: {poll.question.strip()}"
            
            # Check for web page preview
            if hasattr(message.media, 'webpage') and message.media.webpage:
                webpage = message.media.webpage
                parts = []
                if hasattr(webpage, 'title') and webpage.title:
                    parts.append(f"Title: {webpage.title}")
                if hasattr(webpage, 'description') and webpage.description:
                    parts.append(webpage.description)
                if parts:
                    return " - ".join(parts).strip()
        
        # Return empty string if no text found
        return ""
        
    except Exception as e:
        logger.warning(f"Error extracting text from message {getattr(message, 'id', 'unknown')}: {e}")
        return ""

def is_bot_command(message_text: str) -> bool:
    """
    Check if the message is a bot command.
    
    Args:
        message_text: The message text to check
        
    Returns:
        bool: True if the message is a bot command (starts with /)
    """
    return message_text.startswith('/')

def is_empty_message(message_text: str) -> bool:
    """
    Check if the message has meaningful content.
    
    Args:
        message_text: The message text to check
        
    Returns:
        bool: True if the message is empty or just whitespace
    """
    return not message_text or not message_text.strip()

def should_process_message(message) -> bool:
    """
    Determine if a message should be processed for job extraction.
    
    Args:
        message: Telethon message object
        
    Returns:
        bool: True if the message should be processed
    """
    message_text = extract_message_text(message)
    
    # Skip empty messages
    if is_empty_message(message_text):
        return False
    
    # Skip bot commands
    if is_bot_command(message_text):
        return False
    
    # Process all other messages (including forwarded ones)
    return True

def get_message_info(message) -> dict:
    """
    Get comprehensive information about a message.
    
    Args:
        message: Telethon message object
        
    Returns:
        dict: Message information including type, content preview, and metadata
    """
    message_text = extract_message_text(message)
    
    # Determine message type
    msg_type = "unknown"
    is_forwarded = hasattr(message, 'fwd_from') and message.fwd_from is not None
    
    if message_text:
        if is_forwarded:
            msg_type = "forwarded_text"
        elif hasattr(message, 'media') and message.media:
            msg_type = "media_with_caption"
        else:
            msg_type = "direct_text"
    elif hasattr(message, 'media') and message.media:
        msg_type = "media_only"
    else:
        msg_type = "empty"
    
    return {
        "id": message.id,
        "type": msg_type,
        "text": message_text,
        "text_preview": message_text[:100] + "..." if len(message_text) > 100 else message_text,
        "sender_id": getattr(message, 'sender_id', None),
        "date": getattr(message, 'date', None),
        "is_forwarded": is_forwarded,
        "has_media": hasattr(message, 'media') and message.media,
        "media_type": type(message.media).__name__ if hasattr(message, 'media') and message.media else None,
        "is_bot_command": is_bot_command(message_text),
        "is_empty": is_empty_message(message_text),
        "should_process": should_process_message(message),
        "is_service_message": getattr(message, 'service', None) is not None
    }

def debug_message_structure(message) -> dict:
    """
    Debug helper to see all available attributes on a message.
    Useful for troubleshooting when messages are being skipped.
    
    Args:
        message: Telethon message object
        
    Returns:
        dict: All available attributes and their types
    """
    debug_info = {
        "message_id": getattr(message, 'id', None),
        "attributes": {},
        "media_info": None,
        "forward_info": None
    }
    
    # List key attributes
    key_attrs = ['message', 'text', 'caption', 'media', 'fwd_from', 'sender_id', 'date']
    for attr in key_attrs:
        if hasattr(message, attr):
            value = getattr(message, attr)
            debug_info["attributes"][attr] = {
                "type": type(value).__name__,
                "value": str(value)[:100] if value else None,
                "is_none": value is None
            }
    
    # Media details
    if hasattr(message, 'media') and message.media:
        debug_info["media_info"] = {
            "media_type": type(message.media).__name__,
            "has_poll": hasattr(message.media, 'poll'),
            "has_webpage": hasattr(message.media, 'webpage')
        }
        
    # Forward details
    if hasattr(message, 'fwd_from') and message.fwd_from:
        debug_info["forward_info"] = {
            "from_id": getattr(message.fwd_from, 'from_id', None),
            "from_name": getattr(message.fwd_from, 'from_name', None),
            "date": getattr(message.fwd_from, 'date', None)
        }
    
    return debug_info

# --- Centralized Notification Utility ---

def _get_lock_files():
    """Returns the paths for the lock and timestamp files."""
    temp_dir = tempfile.gettempdir()
    return (
        os.path.join(temp_dir, 'notification.lock'),
        os.path.join(temp_dir, 'last_notification_time')
    )

async def send_rate_limited_telegram_notification(message: str):
    """
    Sends a notification to the admin, respecting a process-safe global rate limit.
    """
    # Notifications disabled by user request
    return

# Export commonly used functions
__all__ = [
    'extract_message_text',
    'is_bot_command', 
    'is_empty_message',
    'should_process_message',
    'get_message_info',
    'debug_message_structure',
    'send_rate_limited_telegram_notification',
    'log_execution'
]