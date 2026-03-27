"""Feishu WebSocket event listener using lark-oapi SDK.

Uses Feishu's long-connection (长连接) to receive events without
requiring a public URL. Runs as an asyncio task alongside Telegram
polling and the FastAPI server.
"""

import asyncio
from typing import Any, Callable, Coroutine, Optional

import structlog

logger = structlog.get_logger()

# Type alias for the callback
OnMessageCallback = Callable[[dict], Coroutine[Any, Any, None]]


class FeishuWSListener:
    """WebSocket event listener backed by lark-oapi."""

    def __init__(
        self,
        app_id: str,
        app_secret: str,
        on_message: OnMessageCallback,
    ) -> None:
        self.app_id = app_id
        self.app_secret = app_secret
        self.on_message = on_message
        self._running = False
        self._task: Optional[asyncio.Task[None]] = None
        self._ws_client: Any = None

    async def start(self) -> None:
        """Start the WebSocket listener as a background task."""
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._run_ws())
        logger.info("Feishu WebSocket listener started")

    async def stop(self) -> None:
        """Stop the WebSocket listener."""
        self._running = False
        if self._ws_client:
            try:
                self._ws_client.stop()
            except Exception:
                pass
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("Feishu WebSocket listener stopped")

    async def _run_ws(self) -> None:
        """Main WebSocket loop with auto-reconnect."""
        import lark_oapi as lark
        from lark_oapi.api.im.v1 import P2ImMessageReceiveV1

        while self._running:
            try:
                # Build event handler
                handler = (
                    lark.EventDispatcherHandler.builder("", "")
                    .register_p2_im_message_receive_v1(self._handle_im_message)
                    .build()
                )

                # Build WebSocket client
                self._ws_client = (
                    lark.ws.Client(
                        self.app_id,
                        self.app_secret,
                        event_handler=handler,
                        log_level=lark.LogLevel.INFO,
                    )
                )

                logger.info("Connecting to Feishu WebSocket...")
                # lark-oapi ws.Client.start() is blocking (runs in its own thread)
                # We run it in an executor to avoid blocking asyncio
                loop = asyncio.get_event_loop()
                await loop.run_in_executor(None, self._ws_client.start)

            except asyncio.CancelledError:
                break
            except Exception:
                logger.exception("Feishu WebSocket error, reconnecting in 5s")
                await asyncio.sleep(5)

    def _handle_im_message(self, data: Any) -> None:
        """Sync callback from lark-oapi — bridges to async on_message."""
        try:
            # Extract event data from lark-oapi's typed event
            event_dict = self._event_to_dict(data)
            if event_dict:
                # Schedule the async callback on the event loop
                loop = asyncio.get_event_loop()
                asyncio.run_coroutine_threadsafe(
                    self.on_message(event_dict), loop
                )
        except Exception:
            logger.exception("Failed to handle Feishu IM message")

    @staticmethod
    def _event_to_dict(data: Any) -> Optional[dict]:
        """Convert lark-oapi P2ImMessageReceiveV1 to a plain dict."""
        try:
            # data is P2ImMessageReceiveV1 with .event attribute
            event = data.event
            if not event:
                return None

            message = event.message
            sender = event.sender

            return {
                "message": {
                    "message_id": message.message_id or "",
                    "message_type": message.message_type or "",
                    "content": message.content or "{}",
                    "chat_id": message.chat_id or "",
                    "chat_type": message.chat_type or "",
                    "mentions": [
                        {
                            "key": m.key or "",
                            "id": (m.id_ if hasattr(m, "id_") else m.id) if m else "",
                            "name": m.name or "",
                        }
                        for m in (message.mentions or [])
                    ],
                    "thread_id": getattr(message, "thread_id", None),
                },
                "sender": {
                    "sender_id": {
                        "open_id": (
                            sender.sender_id.open_id
                            if sender and sender.sender_id
                            else ""
                        ),
                        "user_id": (
                            sender.sender_id.user_id
                            if sender and sender.sender_id
                            else ""
                        ),
                    },
                    "sender_type": sender.sender_type if sender else "",
                },
            }
        except Exception:
            logger.exception("Failed to convert Feishu event to dict")
            return None
