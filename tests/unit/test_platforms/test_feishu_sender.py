"""Tests for Feishu sender."""

import json
from unittest.mock import AsyncMock

import pytest

from src.platforms.feishu.cli_client import FeishuCLIClient
from src.platforms.feishu.sender import FeishuSender


@pytest.fixture
def mock_cli() -> AsyncMock:
    cli = AsyncMock(spec=FeishuCLIClient)
    cli.send_text = AsyncMock(return_value={"message_id": "om_sent_1"})
    cli.reply = AsyncMock(return_value={"message_id": "om_reply_1"})
    cli.delete = AsyncMock(return_value={})
    cli.send_image = AsyncMock(return_value={"message_id": "om_img_1"})
    return cli


@pytest.fixture
def sender(mock_cli: AsyncMock) -> FeishuSender:
    return FeishuSender(mock_cli)


class TestFeishuSender:
    async def test_send_text(self, sender: FeishuSender, mock_cli: AsyncMock) -> None:
        msg_id = await sender.send_text("oc_chat", "hello")
        assert msg_id == "om_sent_1"
        mock_cli.send_text.assert_called_once_with("oc_chat", "hello")

    async def test_send_text_with_reply(
        self, sender: FeishuSender, mock_cli: AsyncMock
    ) -> None:
        msg_id = await sender.send_text("oc_chat", "reply text", reply_to="om_orig")
        assert msg_id == "om_reply_1"
        mock_cli.reply.assert_called_once_with("om_orig", "reply text")

    async def test_delete_message(
        self, sender: FeishuSender, mock_cli: AsyncMock
    ) -> None:
        await sender.delete_message("oc_chat", "om_del")
        mock_cli.delete.assert_called_once_with("om_del")

    async def test_edit_text_is_noop(
        self, sender: FeishuSender, mock_cli: AsyncMock
    ) -> None:
        # edit_text is a no-op because feishu-cli has no update-message
        await sender.edit_text("oc_chat", "om_1", "new text")
        # No CLI calls should have been made
        mock_cli.send_text.assert_not_called()

    async def test_send_typing_is_noop(self, sender: FeishuSender) -> None:
        # Should not raise
        await sender.send_typing("oc_chat")

    def test_max_message_length(self, sender: FeishuSender) -> None:
        assert sender.max_message_length() == 30000

    def test_platform_name(self, sender: FeishuSender) -> None:
        assert sender.platform_name == "feishu"
