"""Feishu platform adapter.

Wires together:
- FeishuCLIClient (subprocess for sending messages)
- FeishuWSListener (lark-oapi WebSocket for receiving events)
- FeishuSender (PlatformSender implementation)

Incoming messages are converted to IncomingMessage and dispatched
to a callback (typically the shared orchestrator).
"""

import time
from pathlib import Path
from typing import Any, Callable, Coroutine, Dict, Optional

import structlog

from ..types import IncomingMessage
from .cli_client import FeishuCLIClient
from .receiver import parse_feishu_event
from .sender import FeishuSender
from .ws_listener import FeishuWSListener

logger = structlog.get_logger()

# Callback type for dispatching parsed messages
MessageHandler = Callable[[IncomingMessage, FeishuSender], Coroutine[Any, Any, None]]


class FeishuAdapter:
    """Top-level Feishu adapter managing lifecycle of all Feishu components."""

    platform_name = "feishu"

    def __init__(
        self,
        app_id: str,
        app_secret: str,
        on_message: Optional[MessageHandler] = None,
        allowed_users: Optional[list[str]] = None,
        cli_path: Optional[str] = None,
    ) -> None:
        self.app_id = app_id
        self.app_secret = app_secret
        self.on_message = on_message
        self.allowed_users = set(allowed_users) if allowed_users else None

        self._cli_client = FeishuCLIClient(
            cli_path=cli_path,
            app_id=app_id,
            app_secret=app_secret,
        )
        self._sender = FeishuSender(self._cli_client)
        self._ws_listener: Optional[FeishuWSListener] = None

    @property
    def sender(self) -> FeishuSender:
        return self._sender

    async def initialize(self) -> None:
        """Initialize the adapter (validate config, etc.)."""
        logger.info(
            "Feishu adapter initialized",
            app_id=self.app_id[:8] + "...",
        )

    async def start(self) -> None:
        """Start the WebSocket event listener."""
        self._ws_listener = FeishuWSListener(
            app_id=self.app_id,
            app_secret=self.app_secret,
            on_message=self._dispatch_event,
        )
        await self._ws_listener.start()
        logger.info("Feishu adapter started")

    async def stop(self) -> None:
        """Stop the event listener."""
        if self._ws_listener:
            await self._ws_listener.stop()
        logger.info("Feishu adapter stopped")

    async def _dispatch_event(self, event_data: Dict[str, Any]) -> None:
        """Convert raw Feishu event to IncomingMessage and dispatch."""
        msg = parse_feishu_event(event_data)
        if not msg:
            logger.debug("Could not parse Feishu event", event_data=event_data)
            return

        # Auth check: only allow configured users
        if self.allowed_users and msg.user_id not in self.allowed_users:
            logger.warning(
                "Feishu message from unauthorized user",
                user_id=msg.user_id,
            )
            return

        if self.on_message:
            try:
                await self.on_message(msg, self._sender)
            except Exception:
                logger.exception(
                    "Feishu message handler failed",
                    user_id=msg.user_id,
                    message_id=msg.message_id,
                )
