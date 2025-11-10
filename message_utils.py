#!/usr/bin/env python3
"""
Message Text Extraction Utilities
Shared utilities for extracting text from both direct and forwarded messages
"""

import logging
from typing import Optional

logger = logging.getLogger(__name__)

def extract_message_text(message) -> str:
    """
    Extract text from a Telegram message, handling forwarded messages properly.
    
    This function tries multiple sources to get the message text:
    1. Direct message text (message.text)
    2. Forwarded message text (message.forward.text)
    3. Legacy forwarded text (message.fwd_from.text)
    4. Alternative text fields (message.message)
    5. Media captions (message.caption)
    
    Args:
        message: Telethon message object
        
    Returns:
        str: Extracted text content, or empty string if none found
    """
    try:
        # Try direct text first (most common case)
        if hasattr(message, 'text') and message.text and message.text.strip():
            return message.text.strip()
        
        # Handle forwarded messages (new Telegram structure)
        if hasattr(message, 'forward') and message.forward:
            forward_msg = message.forward
            
            # Try text from forwarded message
            if hasattr(forward_msg, 'text') and forward_msg.text and forward_msg.text.strip():
                return forward_msg.text.strip()
            
            # Try message field from forwarded message
            if hasattr(forward_msg, 'message') and forward_msg.message and forward_msg.message.strip():
                return forward_msg.message.strip()
            
            # Try caption from forwarded media
            if hasattr(forward_msg, 'caption') and forward_msg.caption and forward_msg.caption.strip():
                return forward_msg.caption.strip()
        
        # Handle fwd_from structure (older Telegram versions)
        if hasattr(message, 'fwd_from') and message.fwd_from:
            fwd = message.fwd_from
            if hasattr(fwd, 'text') and fwd.text and fwd.text.strip():
                return fwd.text.strip()
            if hasattr(fwd, 'message') and fwd.message and fwd.message.strip():
                return fwd.message.strip()
            if hasattr(fwd, 'caption') and fwd.caption and fwd.caption.strip():
                return fwd.caption.strip()
        
        # Try message.message as fallback
        if hasattr(message, 'message') and message.message and message.message.strip():
            return message.message.strip()
        
        # Try message.caption for media messages
        if hasattr(message, 'caption') and message.caption and message.caption.strip():
            return message.caption.strip()
        
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
    if message_text:
        if hasattr(message, 'forward') and message.forward:
            msg_type = "forwarded_text"
        elif hasattr(message, 'fwd_from') and message.fwd_from:
            msg_type = "legacy_forwarded_text"
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
        "sender_id": message.sender_id,
        "date": message.date,
        "has_forward": hasattr(message, 'forward') and message.forward,
        "has_fwd_from": hasattr(message, 'fwd_from') and message.fwd_from,
        "has_media": hasattr(message, 'media') and message.media,
        "is_bot_command": is_bot_command(message_text),
        "is_empty": is_empty_message(message_text),
        "should_process": should_process_message(message)
    }

# Export commonly used functions
__all__ = [
    'extract_message_text',
    'is_bot_command', 
    'is_empty_message',
    'should_process_message',
    'get_message_info'
]