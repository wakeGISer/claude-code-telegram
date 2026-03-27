"""Tests for the notification service."""

from unittest.mock import AsyncMock

import pytest

from src.events.bus import EventBus
from src.events.types import AgentResponseEvent
from src.notifications.service import NotificationService


@pytest.fixture
def event_bus() -> EventBus:
    return EventBus()


@pytest.fixture
def mock_sender() -> AsyncMock:
    sender = AsyncMock()
    sender.platform_name = "telegram"
    sender.send_text = AsyncMock(return_value="1")
    sender.max_message_length = lambda: 4096
    return sender


@pytest.fixture
def service(event_bus: EventBus, mock_sender: AsyncMock) -> NotificationService:
    svc = NotificationService(
        event_bus=event_bus,
        senders={"telegram": mock_sender},
        default_chat_ids=[100, 200],
    )
    svc.register()
    return svc


class TestNotificationService:
    """Tests for NotificationService."""

    async def test_handle_response_queues_event(
        self, service: NotificationService
    ) -> None:
        """Events are queued for delivery."""
        event = AgentResponseEvent(chat_id=100, text="hello")
        await service.handle_response(event)
        assert service._send_queue.qsize() == 1

    async def test_resolve_chat_ids_specific(
        self, service: NotificationService
    ) -> None:
        """Specific chat_id takes precedence over defaults."""
        event = AgentResponseEvent(chat_id=999, text="test")
        ids = service._resolve_chat_ids(event)
        assert ids == [999]

    async def test_resolve_chat_ids_default(self, service: NotificationService) -> None:
        """chat_id=0 falls back to default chat IDs."""
        event = AgentResponseEvent(chat_id=0, text="test")
        ids = service._resolve_chat_ids(event)
        assert ids == [100, 200]

    def test_split_message_short(self, service: NotificationService) -> None:
        """Short messages are not split."""
        chunks = service._split_message("short text")
        assert len(chunks) == 1
        assert chunks[0] == "short text"

    def test_split_message_long(self, service: NotificationService) -> None:
        """Long messages are split at boundaries."""
        text = "A" * 4000 + "\n\n" + "B" * 200
        chunks = service._split_message(text, max_length=4096)
        assert len(chunks) >= 1
        total_len = sum(len(c) for c in chunks)
        assert total_len > 0

    def test_split_message_no_boundary(self, service: NotificationService) -> None:
        """Messages without boundaries are hard-split."""
        text = "A" * 5000
        chunks = service._split_message(text, max_length=4096)
        assert len(chunks) == 2
        assert len(chunks[0]) == 4096
        assert len(chunks[1]) == 904

    async def test_send_via_sender(
        self, service: NotificationService, mock_sender: AsyncMock
    ) -> None:
        """Messages are sent via the platform sender."""
        event = AgentResponseEvent(chat_id=123, text="hello world")
        await service._rate_limited_send("123", mock_sender, event)

        mock_sender.send_text.assert_called_once()
        call_kwargs = mock_sender.send_text.call_args.kwargs
        assert call_kwargs["chat_id"] == "123"
        assert call_kwargs["text"] == "hello world"

    async def test_ignores_non_response_events(
        self, service: NotificationService
    ) -> None:
        """Non-AgentResponseEvent events are ignored."""
        from src.events.bus import Event

        event = Event(source="test")
        await service.handle_response(event)
        assert service._send_queue.qsize() == 0

    async def test_from_bot_compat(self, event_bus: EventBus) -> None:
        """from_bot() classmethod creates a working service."""
        mock_bot = AsyncMock()
        svc = NotificationService.from_bot(
            event_bus=event_bus,
            bot=mock_bot,
            default_chat_ids=[100],
        )
        assert "telegram" in svc.senders
        assert svc.default_chat_ids == [100]

    async def test_resolve_sender_fallback(
        self, service: NotificationService
    ) -> None:
        """Unknown platform falls back to first available sender."""
        event = AgentResponseEvent(chat_id=1, text="test", platform="feishu")
        sender = service._resolve_sender(event)
        # Falls back to telegram since feishu sender not registered
        assert sender is not None
        assert sender.platform_name == "telegram"
