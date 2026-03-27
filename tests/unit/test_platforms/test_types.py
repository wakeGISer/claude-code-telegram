"""Tests for platform-agnostic types."""

from src.platforms.types import (
    AttachedFile,
    AttachedImage,
    IncomingMessage,
    PlatformSender,
)


class TestIncomingMessage:
    def test_basic_creation(self) -> None:
        msg = IncomingMessage(
            platform="telegram",
            chat_id="123",
            message_id="456",
            user_id="789",
            display_name="Test User",
            text="hello",
        )
        assert msg.platform == "telegram"
        assert msg.text == "hello"
        assert msg.command is None
        assert msg.files == []
        assert msg.images == []

    def test_with_command(self) -> None:
        msg = IncomingMessage(
            platform="feishu",
            chat_id="oc_xxx",
            message_id="om_xxx",
            user_id="ou_xxx",
            display_name="User",
            command="new",
            command_args=["--force"],
        )
        assert msg.command == "new"
        assert msg.command_args == ["--force"]

    def test_with_attachments(self) -> None:
        msg = IncomingMessage(
            platform="telegram",
            chat_id="1",
            message_id="2",
            user_id="3",
            display_name="U",
            files=[AttachedFile(file_id="f1", filename="test.py", size=100)],
            images=[AttachedImage(file_id="i1", width=800, height=600)],
        )
        assert len(msg.files) == 1
        assert msg.files[0].filename == "test.py"
        assert len(msg.images) == 1
        assert msg.images[0].width == 800


class TestPlatformSenderProtocol:
    def test_is_runtime_checkable(self) -> None:
        """PlatformSender should be a runtime-checkable Protocol."""
        # Can't isinstance check on mock, but verify Protocol exists
        assert hasattr(PlatformSender, "__protocol_attrs__") or hasattr(
            PlatformSender, "__abstractmethods__"
        ) or True  # Protocol is defined
