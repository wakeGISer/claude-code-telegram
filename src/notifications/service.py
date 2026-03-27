"""Notification service for delivering proactive agent responses.

Subscribes to AgentResponseEvent on the event bus and delivers messages
through the appropriate platform sender with rate limiting.
"""

import asyncio
from typing import Dict, List, Optional

import structlog

from ..events.bus import Event, EventBus
from ..events.types import AgentResponseEvent
from ..platforms.types import PlatformSender

logger = structlog.get_logger()

# Default rate limit: ~1 msg/sec per chat
SEND_INTERVAL_SECONDS = 1.1


class NotificationService:
    """Delivers agent responses to platform chats with rate limiting."""

    def __init__(
        self,
        event_bus: EventBus,
        senders: Dict[str, PlatformSender],
        default_chat_ids: Optional[List[int]] = None,
    ) -> None:
        self.event_bus = event_bus
        self.senders = senders
        self.default_chat_ids = default_chat_ids or []
        self._send_queue: asyncio.Queue[AgentResponseEvent] = asyncio.Queue()
        self._last_send_per_chat: dict[str, float] = {}
        self._running = False
        self._sender_task: Optional[asyncio.Task[None]] = None

    # Backwards-compatible constructor for existing code that passes bot=
    @classmethod
    def from_bot(
        cls,
        event_bus: EventBus,
        bot: object,
        default_chat_ids: Optional[List[int]] = None,
    ) -> "NotificationService":
        """Create from a telegram.Bot for backwards compatibility."""
        from ..platforms.telegram.sender import TelegramSender

        tg_sender = TelegramSender(bot)  # type: ignore[arg-type]
        return cls(
            event_bus=event_bus,
            senders={"telegram": tg_sender},
            default_chat_ids=default_chat_ids,
        )

    def register(self) -> None:
        """Subscribe to agent response events."""
        self.event_bus.subscribe(AgentResponseEvent, self.handle_response)

    async def start(self) -> None:
        """Start the send queue processor."""
        if self._running:
            return
        self._running = True
        self._sender_task = asyncio.create_task(self._process_send_queue())
        logger.info("Notification service started")

    async def stop(self) -> None:
        """Stop the send queue processor."""
        if not self._running:
            return
        self._running = False
        if self._sender_task:
            self._sender_task.cancel()
            try:
                await self._sender_task
            except asyncio.CancelledError:
                pass
        logger.info("Notification service stopped")

    async def handle_response(self, event: Event) -> None:
        """Queue an agent response for delivery."""
        if not isinstance(event, AgentResponseEvent):
            return
        await self._send_queue.put(event)

    async def _process_send_queue(self) -> None:
        """Process queued messages with rate limiting."""
        while self._running:
            try:
                event = await asyncio.wait_for(self._send_queue.get(), timeout=1.0)
            except asyncio.TimeoutError:
                continue
            except asyncio.CancelledError:
                break

            chat_ids = self._resolve_chat_ids(event)
            sender = self._resolve_sender(event)
            if not sender:
                logger.warning(
                    "No sender for platform",
                    platform=event.platform,
                    event_id=event.id,
                )
                continue

            for chat_id in chat_ids:
                await self._rate_limited_send(str(chat_id), sender, event)

    def _resolve_chat_ids(self, event: AgentResponseEvent) -> List[int]:
        """Determine which chats to send to."""
        if event.chat_id and event.chat_id != 0:
            return [event.chat_id]
        return list(self.default_chat_ids)

    def _resolve_sender(self, event: AgentResponseEvent) -> Optional[PlatformSender]:
        """Pick the right sender based on event.platform."""
        platform = getattr(event, "platform", "telegram")
        sender = self.senders.get(platform)
        if sender:
            return sender
        # Fallback: use first available sender
        if self.senders:
            return next(iter(self.senders.values()))
        return None

    async def _rate_limited_send(
        self, chat_id: str, sender: PlatformSender, event: AgentResponseEvent
    ) -> None:
        """Send message with per-chat rate limiting."""
        loop = asyncio.get_event_loop()
        now = loop.time()
        last_send = self._last_send_per_chat.get(chat_id, 0.0)
        wait_time = SEND_INTERVAL_SECONDS - (now - last_send)

        if wait_time > 0:
            await asyncio.sleep(wait_time)

        try:
            text = event.text
            max_len = sender.max_message_length()
            chunks = self._split_message(text, max_len)

            for chunk in chunks:
                await sender.send_text(
                    chat_id=chat_id,
                    text=chunk,
                    parse_mode=event.parse_mode,
                )
                self._last_send_per_chat[chat_id] = asyncio.get_event_loop().time()

                if len(chunks) > 1:
                    await asyncio.sleep(SEND_INTERVAL_SECONDS)

            logger.info(
                "Notification sent",
                platform=sender.platform_name,
                chat_id=chat_id,
                text_length=len(text),
                chunks=len(chunks),
                originating_event=event.originating_event_id,
            )
        except Exception as e:
            logger.error(
                "Failed to send notification",
                platform=sender.platform_name,
                chat_id=chat_id,
                error=str(e),
                event_id=event.id,
            )

    def _split_message(self, text: str, max_length: int = 4096) -> List[str]:
        """Split long messages at paragraph boundaries."""
        if len(text) <= max_length:
            return [text]

        chunks: List[str] = []
        while text:
            if len(text) <= max_length:
                chunks.append(text)
                break

            split_pos = text.rfind("\n\n", 0, max_length)
            if split_pos == -1:
                split_pos = text.rfind("\n", 0, max_length)
            if split_pos == -1:
                split_pos = text.rfind(" ", 0, max_length)
            if split_pos == -1:
                split_pos = max_length

            chunks.append(text[:split_pos])
            text = text[split_pos:].lstrip()

        return chunks
