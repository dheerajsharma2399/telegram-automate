"""Telegram session helpers extracted from web and worker entrypoints."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import Optional, Tuple

from telethon import TelegramClient
from telethon.sessions import StringSession

logger = logging.getLogger(__name__)


class TelegramSessionService:
    """Create, validate, and clean up Telegram client sessions."""

    def __init__(self, db, api_id, api_hash, phone: Optional[str] = None, group_usernames=None):
        self.db = db
        self.api_id = int(api_id) if api_id is not None else None
        self.api_hash = api_hash
        self.phone = phone
        self.group_usernames = group_usernames or []

    def get_session_string(self) -> str:
        session_string = self.db.auth.get_telegram_session() or ""
        return session_string.strip()

    def has_session(self) -> bool:
        return bool(self.get_session_string())

    def mark_not_authenticated(self, login_status: str = "not_authenticated", clear_session: bool = False) -> None:
        """Persist a stopped unauthenticated state."""
        logger.warning("Marking Telegram unauthenticated; status=%s", login_status)
        self.db.config.set_config("monitoring_status", "stopped")
        self.db.auth.set_telegram_login_status(login_status)
        if clear_session:
            self.db.auth.set_telegram_session("")

    def invalidate_session(self, login_status: str = "not_authenticated") -> None:
        """Persist a cleared session state when auth is invalid."""
        self.mark_not_authenticated(login_status=login_status, clear_session=True)

    async def create_client(self, session_string: Optional[str] = None) -> TelegramClient:
        """Create and connect a Telethon client from a stored session."""
        session_string = (session_string or self.get_session_string()).strip()
        if not session_string:
            self.mark_not_authenticated("not_authenticated", clear_session=False)
            raise ConnectionError("No active Telegram session found. Please authenticate first.")
        if not self.api_id or not self.api_hash:
            raise ValueError("Telegram API credentials not configured")

        client = TelegramClient(StringSession(session_string), self.api_id, self.api_hash)
        await client.connect()
        return client

    async def ensure_authorized_client(self, client: Optional[TelegramClient] = None) -> Tuple[TelegramClient, bool]:
        """Return an authorized client and whether this service created it."""
        if client and client.is_connected():
            try:
                if await client.is_user_authorized():
                    self.db.auth.set_telegram_login_status("connected")
                    return client, False
            except Exception as exc:
                logger.warning("Existing Telegram client failed authorization check: %s", exc)

        new_client = await self.create_client()
        try:
            if not await new_client.is_user_authorized():
                self.invalidate_session("not_authenticated")
                raise ConnectionError("Telegram session is invalid or expired.")
        except Exception:
            await new_client.disconnect()
            raise

        self.db.auth.set_telegram_login_status("connected")
        return new_client, True

    async def get_authorized_client(self) -> Optional[TelegramClient]:
        """Return an authorized client, or None if Telegram is not authenticated."""
        try:
            client, _owns_client = await self.ensure_authorized_client()
            return client
        except ConnectionError as exc:
            logger.warning("Telegram client is not authorized: %s", exc)
            return None

    async def disconnect_client(self, client: Optional[TelegramClient]) -> None:
        if client and client.is_connected():
            await client.disconnect()

    @asynccontextmanager
    async def client_session(self, client: Optional[TelegramClient] = None):
        """Yield an authorized Telegram client and disconnect if created here."""
        resolved_client, owns_client = await self.ensure_authorized_client(client)
        try:
            yield resolved_client
        finally:
            if owns_client:
                await self.disconnect_client(resolved_client)

    async def restore_client(self, client: Optional[TelegramClient] = None) -> TelegramClient:
        """Return a live authorized client without exposing ownership details."""
        resolved_client, _ = await self.ensure_authorized_client(client)
        return resolved_client
