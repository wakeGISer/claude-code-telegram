"""Tests for the shared platform-agnostic message handler."""

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.platforms.message_handler import SharedMessageHandler, _split_message
from src.platforms.types import IncomingMessage


@pytest.fixture
def mock_claude() -> AsyncMock:
    claude = AsyncMock()
    response = MagicMock()
    response.session_id = "sess_123"
    response.content = "Hello from Claude!"
    claude.run_command = AsyncMock(return_value=response)
    return claude


@pytest.fixture
def mock_sender() -> AsyncMock:
    sender = AsyncMock()
    sender.platform_name = "feishu"
    sender.send_text = AsyncMock(return_value="msg_progress_1")
    sender.delete_message = AsyncMock()
    sender.max_message_length = MagicMock(return_value=30000)
    return sender


@pytest.fixture
def handler(mock_claude: AsyncMock, tmp_path: Path) -> SharedMessageHandler:
    return SharedMessageHandler(
        claude_integration=mock_claude,
        approved_directory=tmp_path,
    )


@pytest.fixture
def incoming_msg() -> IncomingMessage:
    return IncomingMessage(
        platform="feishu",
        chat_id="oc_test",
        message_id="om_123",
        user_id="ou_user1",
        display_name="Test User",
        text="write hello world",
    )


class TestSharedMessageHandler:
    async def test_handle_text_success(
        self,
        handler: SharedMessageHandler,
        mock_sender: AsyncMock,
        mock_claude: AsyncMock,
        incoming_msg: IncomingMessage,
    ) -> None:
        await handler.handle_text(incoming_msg, mock_sender)

        # Progress message sent and deleted
        assert mock_sender.send_text.call_count >= 2  # progress + response
        mock_sender.delete_message.assert_called_once()

        # Claude was called
        mock_claude.run_command.assert_called_once()
        call_kwargs = mock_claude.run_command.call_args.kwargs
        assert call_kwargs["prompt"] == "write hello world"

    async def test_handle_text_stores_session(
        self,
        handler: SharedMessageHandler,
        mock_sender: AsyncMock,
        incoming_msg: IncomingMessage,
    ) -> None:
        await handler.handle_text(incoming_msg, mock_sender)
        key = "feishu:ou_user1"
        assert handler._sessions.get(key) == "sess_123"

    async def test_handle_text_error(
        self,
        handler: SharedMessageHandler,
        mock_sender: AsyncMock,
        mock_claude: AsyncMock,
        incoming_msg: IncomingMessage,
    ) -> None:
        mock_claude.run_command.side_effect = RuntimeError("boom")
        await handler.handle_text(incoming_msg, mock_sender)

        # Should still send error response
        calls = mock_sender.send_text.call_args_list
        error_sent = any("Error" in str(c) for c in calls)
        assert error_sent

    async def test_handle_text_empty(
        self,
        handler: SharedMessageHandler,
        mock_sender: AsyncMock,
        mock_claude: AsyncMock,
    ) -> None:
        msg = IncomingMessage(
            platform="feishu",
            chat_id="oc_test",
            message_id="om_1",
            user_id="ou_1",
            display_name="U",
            text="   ",
        )
        await handler.handle_text(msg, mock_sender)
        mock_claude.run_command.assert_not_called()

    async def test_handle_command_new(
        self,
        handler: SharedMessageHandler,
        mock_sender: AsyncMock,
    ) -> None:
        # Set a session first
        handler._sessions["feishu:ou_1"] = "old_session"

        msg = IncomingMessage(
            platform="feishu",
            chat_id="oc_test",
            message_id="om_1",
            user_id="ou_1",
            display_name="U",
            command="new",
        )
        await handler.handle_command(msg, mock_sender)

        assert "feishu:ou_1" not in handler._sessions
        mock_sender.send_text.assert_called_once()

    async def test_handle_command_status(
        self,
        handler: SharedMessageHandler,
        mock_sender: AsyncMock,
    ) -> None:
        msg = IncomingMessage(
            platform="feishu",
            chat_id="oc_test",
            message_id="om_1",
            user_id="ou_1",
            display_name="U",
            command="status",
        )
        await handler.handle_command(msg, mock_sender)
        # Check all positional and keyword args for "Status"
        call_args = mock_sender.send_text.call_args
        all_args_str = str(call_args)
        assert "Status" in all_args_str


class TestSplitMessage:
    def test_short(self) -> None:
        assert _split_message("hi") == ["hi"]

    def test_long(self) -> None:
        text = "A" * 5000
        chunks = _split_message(text, 4096)
        assert len(chunks) == 2
        assert len(chunks[0]) == 4096

    def test_paragraph_boundary(self) -> None:
        text = "A" * 4000 + "\n\n" + "B" * 200
        chunks = _split_message(text, 4096)
        assert len(chunks) == 2
        assert chunks[0].endswith("A")
        assert chunks[1].startswith("B")
